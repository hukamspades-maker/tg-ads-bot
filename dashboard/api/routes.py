"""
Main API routes for the dashboard.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from dashboard.api.auth import get_current_user
from dashboard.core.events import EventType, event_bus
from dashboard.core.logger import log_buffer
from dashboard.core.metrics import metrics
from dashboard.core.websocket import ws_manager
from dashboard.services.accounts import account_service
from dashboard.services.stats import stats_service

log = logging.getLogger("dashboard.api")
router = APIRouter(prefix="/api")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  OVERVIEW & METRICS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/overview")
async def get_overview(user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Global overview stats."""
    overview = await metrics.get_all()
    accounts = await account_service.get_summary()
    return {**overview, "accounts": accounts}


@router.get("/stats/time/{period}")
async def get_time_stats(
    period: str,
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Time-based analytics: today, yesterday, weekly, monthly, lifetime."""
    if period not in ("today", "yesterday", "weekly", "monthly", "lifetime"):
        raise HTTPException(400, "Invalid period")
    return await stats_service.get_period_stats(period)


@router.get("/stats/charts")
async def get_chart_data(user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Chart data for live graphs."""
    return await stats_service.get_chart_data()


@router.get("/system")
async def get_system_metrics(user: str = Depends(get_current_user)) -> dict[str, Any]:
    """System monitor data."""
    return await metrics.get_system_metrics()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ACCOUNTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/accounts")
async def get_accounts(user: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    """List all accounts with full details."""
    return await account_service.get_all_accounts()


@router.get("/accounts/{phone}")
async def get_account(phone: str, user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Get single account details."""
    acc = await account_service.get_account(phone)
    if not acc:
        raise HTTPException(404, "Account not found")
    return acc


@router.post("/accounts/{phone}/action/{action}")
async def account_action(
    phone: str,
    action: str,
    user: str = Depends(get_current_user),
) -> dict[str, str]:
    """Perform action on account: pause, resume, remove, restart, reconnect."""
    valid_actions = {"pause", "resume", "remove", "restart", "reconnect", "check_spam", "refresh"}
    if action not in valid_actions:
        raise HTTPException(400, f"Invalid action. Valid: {valid_actions}")
    result = await account_service.perform_action(phone, action)
    return {"status": "ok", "message": result}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/logs")
async def get_logs(
    limit: int = 100,
    category: str | None = None,
    level: str | None = None,
    user: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Get recent log entries with optional filtering."""
    return log_buffer.get_recent(limit=limit, category=category, level=level)


@router.delete("/logs")
async def clear_logs(user: str = Depends(get_current_user)) -> dict[str, str]:
    """Clear all logs."""
    log_buffer.clear()
    return {"status": "ok", "message": "Logs cleared"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SCHEDULER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/scheduler")
async def get_scheduler_tasks(user: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    """List all scheduler tasks."""
    return await stats_service.get_scheduler_info()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  IMPORT / EXPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/import/status")
async def get_import_status(user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Get current import progress."""
    return await account_service.get_import_status()


@router.get("/export/status")
async def get_export_status(user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Get current export progress."""
    return await account_service.get_export_status()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PREMIUM MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_premium_manager():
    """Lazy import to avoid circular deps."""
    import sys
    main_mod = sys.modules.get("ads.main")
    if main_mod and hasattr(main_mod, "PremiumManager"):
        return main_mod.PremiumManager
    return None

def _get_forcejoin_manager():
    import sys
    main_mod = sys.modules.get("ads.main")
    if main_mod and hasattr(main_mod, "ForceJoinManager"):
        return main_mod.ForceJoinManager
    return None

def _get_premium_plans():
    try:
        from ads.config import PREMIUM_PLANS
        return PREMIUM_PLANS
    except Exception:
        return [
            {"id": "7d", "label": "7 Days", "days": 7, "price": 2},
            {"id": "15d", "label": "15 Days", "days": 15, "price": 5},
            {"id": "30d", "label": "30 Days", "days": 30, "price": 8},
        ]


@router.get("/premium/users")
async def get_premium_users(user: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    pm = _get_premium_manager()
    if not pm:
        return []
    return pm.get_all()


@router.get("/premium/plans")
async def get_premium_plans(user: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    return _get_premium_plans()


@router.post("/premium/grant")
async def grant_premium(
    request: dict[str, Any],
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    pm = _get_premium_manager()
    if not pm:
        raise HTTPException(500, "PremiumManager not available")
    user_id = int(request.get("user_id", 0))
    duration = request.get("duration", "")
    if not user_id:
        raise HTTPException(400, "user_id required")
    import re
    text = str(duration).strip().lower()
    pattern = re.findall(r'(\d+)\s*([dhm])', text)
    total_secs = 0
    label_parts = []
    if not pattern:
        try:
            days = int(text)
            total_secs = days * 86400
            label_parts.append(f"{days}d")
        except ValueError:
            raise HTTPException(400, "Invalid duration format")
    else:
        for val, unit in pattern:
            v = int(val)
            if unit == 'd':
                total_secs += v * 86400; label_parts.append(f"{v}d")
            elif unit == 'h':
                total_secs += v * 3600; label_parts.append(f"{v}h")
            elif unit == 'm':
                total_secs += v * 60; label_parts.append(f"{v}m")
    if total_secs <= 0:
        raise HTTPException(400, "Duration must be > 0")
    label = "".join(label_parts)
    entry = await pm.grant(user_id, total_secs, label, 0)
    return {"status": "ok", "entry": entry}


@router.post("/premium/revoke")
async def revoke_premium(
    request: dict[str, Any],
    user: str = Depends(get_current_user),
) -> dict[str, str]:
    pm = _get_premium_manager()
    if not pm:
        raise HTTPException(500, "PremiumManager not available")
    user_id = int(request.get("user_id", 0))
    if not user_id:
        raise HTTPException(400, "user_id required")
    await pm.revoke(user_id)
    return {"status": "ok", "message": f"Premium revoked for {user_id}"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FORCE JOIN MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/forcejoin/channels")
async def get_forcejoin_channels(user: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    fm = _get_forcejoin_manager()
    if not fm:
        return []
    return fm.get_channels()


@router.post("/forcejoin/add")
async def add_forcejoin_channel(
    request: dict[str, Any],
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    fm = _get_forcejoin_manager()
    if not fm:
        raise HTTPException(500, "ForceJoinManager not available")
    channel = request.get("channel", "")
    title = request.get("title", str(channel))
    if not channel:
        raise HTTPException(400, "channel required")
    if str(channel).lstrip("-").isdigit():
        channel = int(channel)
    added = await fm.add_channel(channel, title, 0)
    if not added:
        return {"status": "exists", "message": "Channel already in list"}
    return {"status": "ok", "message": f"Added {channel}"}


@router.post("/forcejoin/remove")
async def remove_forcejoin_channel(
    request: dict[str, Any],
    user: str = Depends(get_current_user),
) -> dict[str, str]:
    fm = _get_forcejoin_manager()
    if not fm:
        raise HTTPException(500, "ForceJoinManager not available")
    channel = request.get("channel", "")
    if not channel:
        raise HTTPException(400, "channel required")
    if str(channel).lstrip("-").isdigit():
        channel = int(channel)
    await fm.remove_channel(channel)
    return {"status": "ok", "message": f"Removed {channel}"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BROADCAST MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/broadcast/status")
async def get_broadcast_status(user: str = Depends(get_current_user)) -> dict[str, Any]:
    import sys
    main_mod = sys.modules.get("ads.main")
    if not main_mod:
        return {"message": "", "interval": 0, "delay": 0, "loop_running": False}
    owner_id = getattr(main_mod, "OWNER_ID", 0)
    UserManager = getattr(main_mod, "UserManager", None)
    Sched = getattr(main_mod, "Sched", None)
    if not UserManager or not Sched:
        return {"message": "", "interval": 0, "delay": 0, "loop_running": False}
    store = UserManager.get_store(owner_id)
    s = store.all()
    return {
        "message": s.get("broadcast_text", "") or s.get("message", ""),
        "media_type": s.get("media_type", ""),
        "interval": s.get("interval", 0) or 0,
        "delay": s.get("delay_between", 0) or 0,
        "loop_running": Sched.is_loop_running(owner_id),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  WEBSOCKET
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Real-time WebSocket endpoint for live updates."""
    # Accept connection (auth checked via query param or cookie)
    token = websocket.query_params.get("token")
    if not token:
        token = websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    from dashboard.api.auth import decode_token
    user_data = decode_token(token)
    if not user_data:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await ws_manager.connect(websocket)

    # Subscribe to log stream
    log_queue = log_buffer.subscribe()

    try:
        # Send initial state
        overview = await metrics.get_all()
        await ws_manager.send_to(websocket, {"type": "init", "data": overview})

        # Dual task: receive pings + forward logs
        async def forward_logs():
            while True:
                try:
                    entry = await asyncio.wait_for(log_queue.get(), timeout=1.0)
                    await ws_manager.send_to(websocket, {
                        "type": "log",
                        "data": entry.to_dict(),
                    })
                except asyncio.TimeoutError:
                    pass
                except Exception:
                    break

        log_task = asyncio.create_task(forward_logs())

        while True:
            try:
                data = await websocket.receive_text()
                # Handle ping/pong for keepalive
                if data == "ping":
                    await ws_manager.send_to(websocket, {"type": "pong"})
            except WebSocketDisconnect:
                break
            except Exception:
                break
    finally:
        log_task.cancel()
        log_buffer.unsubscribe(log_queue)
        await ws_manager.disconnect(websocket)
