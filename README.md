# MVG Monitor

Live departures from Garching-Forschungszentrum (U6) and active MVG service notices, displayed on a lightweight Flask dashboard.

The dashboard reads the current MVG JSON endpoints:

- `https://www.mvg.de/api/bgw-pt/v3/departures`
- `https://www.mvg.de/api/bgw-pt/v3/messages`

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`. The app refreshes every minute during the day and every ten minutes from 22:00 to 07:00 (Berlin time).

## Proxy configuration

Set `MVG_PROXY_URL` in the hosting environment to route MVG requests through an HTTP proxy, for example:

```text
MVG_PROXY_URL=http://username:password@proxy-host:port
```

Do not commit real proxy credentials. If credentials contain URL-reserved characters, percent-encode them. Standard `HTTP_PROXY` and `HTTPS_PROXY` environment variables are also supported by Requests.

Optional settings are `MVG_STATION_ID`, `MVG_STATION_NAME`, `HOST` and `PORT`. A sample is in `.env.example`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Run behind a production WSGI server or reverse proxy when exposing the dashboard publicly; the built-in Flask server is intended for local use.