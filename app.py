import logging
import os
from datetime import datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import requests
from flask import Flask, render_template


app = Flask(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

STATION_ID = os.getenv("MVG_STATION_ID", "de:09184:490")
STATION_NAME = os.getenv("MVG_STATION_NAME", "Garching-Forschungszentrum")
API_BASE_URL = "https://www.mvg.de/api/bgw-pt/v3"
DEPARTURES_URL = f"{API_BASE_URL}/departures"
MESSAGES_URL = f"{API_BASE_URL}/messages"
LOCAL_TIMEZONE = ZoneInfo("Europe/Berlin")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(markup):
    parser = _TextExtractor()
    parser.feed(markup or "")
    text = " ".join(parser.parts).replace("< >", "<>")
    return " ".join(text.split())


def _request_json(url, params=None):
    options = {"params": params, "timeout": 10}
    proxy_url = os.getenv("MVG_PROXY_URL")
    if proxy_url:
        options["proxies"] = {"http": proxy_url, "https": proxy_url}

    response = requests.get(url, **options)
    response.raise_for_status()
    return response.json()


def _timestamp(value):
    if value is None:
        return None
    return datetime.fromtimestamp(int(value) / 1000, LOCAL_TIMEZONE)


def fetch_departures(now=None):
    now = now or datetime.now(LOCAL_TIMEZONE)
    payload = _request_json(
        DEPARTURES_URL,
        {"globalId": STATION_ID, "limit": 10, "transportTypes": "UBAHN"},
    )
    if not isinstance(payload, list):
        raise ValueError("Unexpected departures response")

    departures = []
    for item in payload:
        departure_time = _timestamp(
            item.get("realtimeDepartureTime") or item.get("plannedDepartureTime")
        )
        if departure_time is None:
            continue

        raw_messages = item.get("messages") or []
        if isinstance(raw_messages, str):
            raw_messages = [raw_messages]
        departures.append(
            {
                "line": item.get("label") or "U6",
                "destination": item.get("destination") or "Unbekannt",
                "time": departure_time.strftime("%H:%M"),
                "minutes": max(0, int((departure_time - now).total_seconds() / 60)),
                "platform": item.get("platform"),
                "cancelled": bool(item.get("cancelled")),
                "message": plain_text(" ".join(str(message) for message in raw_messages)),
            }
        )
    return departures


def fetch_network_alerts(now=None):
    now = now or datetime.now(LOCAL_TIMEZONE)
    now_ms = int(now.timestamp() * 1000)
    payload = _request_json(MESSAGES_URL)
    if not isinstance(payload, list):
        raise ValueError("Unexpected messages response")

    alerts = []
    for item in payload:
        valid_from = item.get("validFrom")
        valid_to = item.get("validTo")
        if valid_from is not None and int(valid_from) > now_ms:
            continue
        if valid_to is not None and int(valid_to) < now_ms:
            continue

        lines = list(
            dict.fromkeys(
                line.get("label", "")
                for line in item.get("lines", [])
                if line.get("label")
            )
        )
        station_ids = item.get("stationGlobalIds") or []
        if lines and "U6" not in lines and STATION_ID not in station_ids:
            continue

        alerts.append(
            {
                "title": plain_text(item.get("title")) or "Netzmeldung",
                "description": plain_text(item.get("description")),
                "lines": lines,
                "type": item.get("type", "INFORMATION"),
                "valid_to": _timestamp(valid_to).strftime("%d.%m.%Y") if valid_to else None,
            }
        )
    return alerts


def get_refresh_interval(now):
    if now.hour >= 22 or now.hour < 7:
        return 600
    return 60


@app.route("/")
def index():
    now = datetime.now(LOCAL_TIMEZONE)
    departures = []
    alerts = []
    errors = []

    try:
        departures = fetch_departures(now)
    except (requests.RequestException, ValueError, TypeError) as error:
        logger.warning("MVG departures unavailable (%s)", type(error).__name__)
        errors.append("Abfahrten sind momentan nicht erreichbar.")

    try:
        alerts = fetch_network_alerts(now)
    except (requests.RequestException, ValueError, TypeError) as error:
        logger.warning("MVG network alerts unavailable (%s)", type(error).__name__)
        errors.append("Netzmeldungen sind momentan nicht erreichbar.")

    return render_template(
        "index.html",
        station_name=STATION_NAME,
        departures=departures,
        alerts=alerts,
        errors=errors,
        current_time=now.strftime("%H:%M:%S"),
        refresh_interval=get_refresh_interval(now),
    )


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000")),
        debug=False,
    )
