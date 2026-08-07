# Hosting the Dashboard

The dashboard is **host/IP agnostic** — to move it to a new VPS or panel, you only need to change the port.

## Quick start

```bash
pip install -r requirements.txt
WEB_PORT=30036 python run_dashboard.py
```

That's it — open `http://<your-server-ip>:30036/` in a browser.

## Deploying to a new server

You only need to change the port (everything else is auto-detected from the browser's URL):

```bash
WEB_PORT=8080 python run_dashboard.py     # listen on :8080
```

The web UI builds its own API and WebSocket URLs from `window.location`, so there is **no IP/host hardcoded anywhere** in source.

## All environment variables

See `.env.example` for the complete list. Most common:

| Variable          | Default     | Notes                              |
|-------------------|-------------|------------------------------------|
| `WEB_HOST`        | `0.0.0.0`   | Bind address (use `0.0.0.0` for VPS) |
| `WEB_PORT`        | `30036`     | The only thing you usually need to change |
| `WEB_USERNAME`    | `admin`     |                                    |
| `WEB_PASSWORD`    | `admin`     | **CHANGE THIS** in production       |
| `WEB_SECRET_KEY`  | random      | Set a long static string in production |

## Behind a reverse proxy (HTTPS)

If you serve via nginx/Caddy with HTTPS, set:

```bash
WEB_HOST=127.0.0.1      # only listen on loopback
WEB_PORT=30036
WEB_COOKIE_SECURE=1     # require HTTPS cookies
```

The dashboard already trusts `X-Forwarded-*` headers (uvicorn is started with `proxy_headers=True` and `forwarded_allow_ips="*"`).

## What I fixed in this drop

Previous build had three blockers that prevented it from running anywhere except the original VPS:

1. **`dashboard/app.py`** — CORS list was hardcoded to `http://92.118.206.132:30036`. Removed; CORS is now off by default (same-origin) and only enabled if you set `WEB_CORS_ORIGINS`.
2. **`dashboard/config.py`** — every setting was hardcoded in Python. Now every value reads from an env var (`WEB_HOST`, `WEB_PORT`, `WEB_PASSWORD`, `WEB_SECRET_KEY`, `WEB_DATABASE_URL`, …) with sensible defaults.
3. **Settings page** — used to display host/port (and the values were hardcoded `0.0.0.0` / `8000`). Removed entirely: host/port are operator concerns, not something the browser should ever care about. The Settings nav entry is gone.

Bonus: `ads/main.py` startup log used to print `http://0.0.0.0:8000` which is neither clickable nor the right port. Now prints the real port and substitutes `localhost` when bound to `0.0.0.0`.
