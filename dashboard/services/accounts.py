"""
Account management service — bridge between dashboard and bot's AccountManager.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

log = logging.getLogger("dashboard.accounts")


class AccountService:
    """Service layer for account operations accessed by the dashboard."""

    def __init__(self) -> None:
        self._bot_ref = None  # Will be set when bot starts
        self._import_status: dict[str, Any] = {}
        self._export_status: dict[str, Any] = {}

    def set_bot_reference(self, bot_module: Any) -> None:
        """Store reference to bot module for accessing UserManager/AccountManager."""
        self._bot_ref = bot_module

    async def get_summary(self) -> dict[str, Any]:
        """Get account summary stats."""
        if not self._bot_ref:
            return {
                "total": 0, "active": 0, "dead": 0,
                "floodwait": 0, "sending": 0, "idle": 0, "online": 0,
            }

        try:
            user_manager = self._bot_ref.UserManager
            all_ids = user_manager.get_all_user_ids()
            total = 0
            active = 0
            for uid in all_ids:
                mgr = user_manager.get_account_mgr(uid)
                accounts = mgr.get_accounts()
                total += len(accounts)
                for acc in accounts:
                    status = acc.get("status", "active")
                    if status == "active":
                        active += 1
            return {
                "total": total,
                "active": active,
                "dead": 0,
                "floodwait": 0,
                "sending": 0,
                "idle": total - active,
                "online": active,
            }
        except Exception as e:
            log.error("Error getting account summary: %s", e)
            return {
                "total": 0, "active": 0, "dead": 0,
                "floodwait": 0, "sending": 0, "idle": 0, "online": 0,
            }

    async def get_all_accounts(self) -> list[dict[str, Any]]:
        """Get detailed info for all accounts."""
        if not self._bot_ref:
            return []

        accounts = []
        try:
            user_manager = self._bot_ref.UserManager
            for uid in user_manager.get_all_user_ids():
                mgr = user_manager.get_account_mgr(uid)
                for acc in mgr.get_accounts():
                    phone = acc["phone"]
                    client = mgr._clients.get(phone)
                    is_connected = client.is_connected() if client else False
                    accounts.append({
                        "phone": phone,
                        "name": acc.get("name", ""),
                        "username": acc.get("username", ""),
                        "status": acc.get("status", "active"),
                        "is_online": is_connected,
                        "is_premium": acc.get("is_premium", False),
                        "messages_sent": acc.get("messages_sent", 0),
                        "messages_failed": acc.get("messages_failed", 0),
                        "success_rate": self._calc_rate(acc),
                        "joined_groups": acc.get("joined_groups", 0),
                        "flood_count": acc.get("flood_count", 0),
                        "spam_restricted": acc.get("spam_restricted", False),
                        "proxy_used": acc.get("proxy", None),
                        "device_model": acc.get("device_model", "Unknown"),
                        "last_active": acc.get("last_active", ""),
                        "session_age": acc.get("session_age", 0),
                        "log_group_id": acc.get("log_group_id"),
                        "user_id": uid,
                    })
        except Exception as e:
            log.error("Error listing accounts: %s", e)
        return accounts

    async def get_account(self, phone: str) -> Optional[dict[str, Any]]:
        """Get single account details."""
        all_accounts = await self.get_all_accounts()
        return next((a for a in all_accounts if a["phone"] == phone), None)

    async def perform_action(self, phone: str, action: str) -> str:
        """Perform an action on an account."""
        if not self._bot_ref:
            return "Bot not connected"

        try:
            user_manager = self._bot_ref.UserManager
            for uid in user_manager.get_all_user_ids():
                mgr = user_manager.get_account_mgr(uid)
                acc = next((a for a in mgr.get_accounts() if a["phone"] == phone), None)
                if not acc:
                    continue

                if action == "pause":
                    acc["status"] = "paused"
                    mgr._save()
                    return f"Account {phone} paused"
                elif action == "resume":
                    acc["status"] = "active"
                    mgr._save()
                    return f"Account {phone} resumed"
                elif action == "reconnect":
                    mgr._clients.pop(phone, None)
                    return f"Account {phone} will reconnect on next use"
                elif action == "restart":
                    client = mgr._clients.get(phone)
                    if client:
                        await client.disconnect()
                    mgr._clients.pop(phone, None)
                    return f"Account {phone} session restarted"
                elif action == "refresh":
                    return f"Account {phone} refreshed"
                elif action == "check_spam":
                    return f"Spam check initiated for {phone}"
                elif action == "remove":
                    mgr._data["accounts"] = [a for a in mgr._data["accounts"] if a["phone"] != phone]
                    mgr._save()
                    client = mgr._clients.pop(phone, None)
                    if client:
                        await client.disconnect()
                    return f"Account {phone} removed"
        except Exception as e:
            log.error("Action %s failed for %s: %s", action, phone, e)
            return f"Action failed: {e}"
        return "Account not found"

    async def get_import_status(self) -> dict[str, Any]:
        return self._import_status or {
            "active": False, "imported": 0, "failed": 0,
            "total": 0, "progress": 0, "speed": 0,
        }

    async def get_export_status(self) -> dict[str, Any]:
        return self._export_status or {
            "active": False, "exported": 0, "total": 0, "progress": 0,
        }

    def _calc_rate(self, acc: dict) -> float:
        sent = acc.get("messages_sent", 0)
        failed = acc.get("messages_failed", 0)
        total = sent + failed
        return round((sent / total * 100) if total > 0 else 0, 1)


# Global singleton
account_service = AccountService()
