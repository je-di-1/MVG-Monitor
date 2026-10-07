from datetime import datetime

import pytest
import requests

import app as monitor


@pytest.fixture
def berlin_now():
    return datetime(2026, 10, 7, 16, 0, tzinfo=monitor.LOCAL_TIMEZONE)


def test_departures_use_live_time_and_include_platform(monkeypatch, berlin_now):
    monkeypatch.setattr(
        monitor,
        "_request_json",
        lambda url, params=None: [
            {
                "label": "U6",
                "destination": "Garching-Forschungszentrum",
                "plannedDepartureTime": int(berlin_now.timestamp() * 1000),
                "realtimeDepartureTime": int(berlin_now.timestamp() * 1000) + 300_000,
                "platform": 1,
                "messages": ["Gleiswechsel"],
            }
        ],
    )

    departures = monitor.fetch_departures(berlin_now)

    assert departures == [
        {
            "line": "U6",
            "destination": "Garching-Forschungszentrum",
            "time": "16:05",
            "minutes": 5,
            "platform": 1,
            "cancelled": False,
            "message": "Gleiswechsel",
        }
    ]


def test_alerts_are_filtered_to_active_u6_and_html_is_removed(monkeypatch, berlin_now):
    now_ms = int(berlin_now.timestamp() * 1000)
    monkeypatch.setattr(
        monitor,
        "_request_json",
        lambda url, params=None: [
            {
                "title": "U6 <b>Hinweis</b>",
                "description": "<div>Fahrt &amp; Umstieg</div>",
                "validFrom": now_ms - 1000,
                "validTo": now_ms + 86_400_000,
                "type": "INCIDENT",
                "lines": [{"label": "U6"}],
            },
            {
                "title": "U5 Meldung",
                "validFrom": now_ms - 1000,
                "validTo": now_ms + 86_400_000,
                "lines": [{"label": "U5"}],
            },
        ],
    )

    alerts = monitor.fetch_network_alerts(berlin_now)

    assert len(alerts) == 1
    assert alerts[0]["title"] == "U6 Hinweis"
    assert alerts[0]["description"] == "Fahrt & Umstieg"
    assert alerts[0]["lines"] == ["U6"]


def test_refresh_interval_changes_at_night(berlin_now):
    assert monitor.get_refresh_interval(berlin_now.replace(hour=6)) == 600
    assert monitor.get_refresh_interval(berlin_now.replace(hour=7)) == 60
    assert monitor.get_refresh_interval(berlin_now.replace(hour=22)) == 600


def test_homepage_surfaces_upstream_errors(monkeypatch):
    def fail(_now=None):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(monitor, "fetch_departures", fail)
    monkeypatch.setattr(monitor, "fetch_network_alerts", fail)

    response = monitor.app.test_client().get("/")

    assert response.status_code == 200
    assert b"Verbindungsproblem" in response.data
    assert b"Abfahrten sind momentan nicht erreichbar." in response.data
    assert b"Netzmeldungen sind momentan nicht erreichbar." in response.data


def test_proxy_url_is_used_when_configured(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return []

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setenv("MVG_PROXY_URL", "http://proxy.example:8080")
    monkeypatch.setattr(monitor.requests, "get", fake_get)

    assert monitor._request_json(monitor.DEPARTURES_URL) == []
    assert captured["proxies"] == {
        "http": "http://proxy.example:8080",
        "https": "http://proxy.example:8080",
    }
    assert captured["timeout"] == 10
