"""
Standalone dashboard runner.

Usage:
    python run_dashboard.py
    WEB_PORT=8080 python run_dashboard.py        # override port
    WEB_HOST=127.0.0.1 WEB_PORT=8080 python run_dashboard.py

All settings can be overridden via environment variables — see
.env.example for the full list. To deploy on a new VPS/panel you
normally only need to change WEB_PORT.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from dashboard.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "dashboard.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        workers=1,
        ws_max_size=16 * 1024 * 1024,
        forwarded_allow_ips="*",
        proxy_headers=True,
        log_level="info",
    )
