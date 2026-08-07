# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STANDARD LIBRARY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
import asyncio
import json
import logging
import os
import random
import sys
import time
import uuid

# Force UTF-8 output on Windows so emoji in log messages don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  THIRD-PARTY — aiogram
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    MessageOriginChannel,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  THIRD-PARTY — Telethon (MTProto user accounts)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    ChannelPrivateError,
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    MessageIdInvalidError,
    MessageIdsEmptyError,
    ChannelInvalidError,
)
from telethon.tl.types import Channel, Chat, ChatAdminRights
from telethon.tl.functions.messages import ForwardMessagesRequest
try:
    from telethon.tl.functions.messages import GetForumTopicsRequest
except ImportError:
    from telethon.tl.functions.channels import GetForumTopicsRequest
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    InviteToChannelRequest,
    EditAdminRequest,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONFIG  —  all values live in config.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from config import (
    BOT_TOKEN,
    OWNER_ID,
    OWNER_USERNAME,
    ADMIN_IDS,
    PREMIUM_PLANS,
    FORCE_JOIN_CHANNELS,
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    USER_DATA_DIR,
    LOG_FILE,
    DAY_NAMES,
    HEALTH_CHECK_INTERVAL,
    MAIN_TEXT,
    RESET_EXPLANATIONS,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)

# ── Suppress high-volume INFO spam from framework internals ────────
logging.getLogger("aiogram.event").setLevel(logging.WARNING)
logging.getLogger("aiogram.dispatcher").setLevel(logging.WARNING)
logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)

# ── Suppress Telethon network noise (connection reset, WinError, etc.) ──
logging.getLogger("telethon.network.mtprotosender").setLevel(logging.ERROR)
logging.getLogger("telethon.client.updates").setLevel(logging.ERROR)
logging.getLogger("telethon.extensions.messagepacker").setLevel(logging.ERROR)

log = logging.getLogger("TGBot")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STORAGE  —  async-safe, in-memory-cached JSON persistence
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class Storage:
    """
    Thread-safe JSON storage backed by an in-memory cache.
    Each instance is scoped to a single user via user_id.

    Schema (user_data/{user_id}/settings.json):
      message             str   — broadcast message (HTML)
      interval_seconds    int   — seconds between loop rounds
      delay_between_sends int   — base seconds between group sends
      random_delay        bool  — use randomised delays
      random_delay_min    float — random range lower bound (s)
      random_delay_max    float — random range upper bound (s)
      selected_groups     list  — [{"id": int, "title": str}]
      loop_active         bool  — DERIVED from loop_active_accounts (backward compat only)
      loop_active_accounts dict  — {phone: bool} — SINGLE SOURCE OF TRUTH for loop state
      schedules           list  — persisted APScheduler jobs
    """

    @staticmethod
    def _default() -> dict:
        return {
            "message":               "",
            "interval_seconds":      300,
            "delay_between_sends":   3,
            "random_delay":          True,
            "random_delay_min":      2.0,
            "random_delay_max":      8.0,
            "selected_groups":       [],
            "fetched_groups":        [],
            "loop_active":           False,
            "schedules":             [],
            "log_forwarding_enabled": False,
            "log_group_id":          None,
            "topic_groups":          [],
            "broadcast_mode":        "selected",
            "forward_mode":          False,
            "forward_channel_id":    None,
            "forward_message_id":    None,
            "forward_active":        False,
            "forward_hide_sender":   True,
            "forward_channel_username": None,   # str | None  — set if source channel is public
            "forward_channel_title":    None,   # str | None  — saved title for UX
            "forward_is_public":        None,   # bool | None — derived from username
            "forward_album_ids":        [],     # list[int]   — all msg ids in the source album, in order
            "forward_source_invalid":   False,  # bool        — set when runtime detects source deletion
            "user_mode":             None,
            "fetch_group_account_map": {},
            "loop_active_accounts":    {},
            "immediate_send":          False,
            "media_type":              None,       # "photo" | "video" | "document" | "animation" | None
            "media_file_path":         None,       # local path to saved media file | None
        }

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        self._dir = USER_DATA_DIR / str(user_id)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "settings.json"
        self._lock = asyncio.Lock()
        base = self._default()
        if self._file.exists():
            try:
                saved = json.loads(self._file.read_text(encoding="utf-8"))
                base.update(saved)
            except json.JSONDecodeError:
                log.warning("[User %s] settings.json corrupted — resetting to defaults.", user_id)
        self._data = base
        log.info("[User %s] Storage loaded. loop_active_accounts=%s", user_id, self._data.get("loop_active_accounts", {}))

    def _flush(self) -> None:
        # FIXED — atomic write: temp file + os.replace to prevent corruption
        tmp_path = self._file.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(str(tmp_path), str(self._file))

    async def get(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._data.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            self._data[key] = value
            self._flush()

    async def update(self, partial: dict) -> None:
        async with self._lock:
            self._data.update(partial)
            self._flush()

    async def all(self) -> dict:
        async with self._lock:
            return dict(self._data)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ACCOUNT MANAGER  —  Telethon multi-account management
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class AccountManager:
    """
    Manages multiple Telethon user accounts.
    Each instance is scoped to a single bot user via user_id.

    user_data/{user_id}/accounts.json schema:
    {
      "accounts": [
        {
          "phone":    "+91xxxxxxxxxx",
          "name":     "John Doe",
          "api_id":   12345,
          "api_hash": "abcdef..."
        }
      ],
      "active_phone": "+91xxxxxxxxxx"
    }

    Session files are stored in user_data/{user_id}/sessions/<phone_digits>.session
    """

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        self._dir = USER_DATA_DIR / str(user_id)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._sessions_dir = self._dir / "sessions"
        self._sessions_dir.mkdir(exist_ok=True)
        self._accounts_file = self._dir / "accounts.json"
        self._clients: dict[str, TelegramClient] = {}  # phone → connected client
        self._client_locks: dict[str, asyncio.Lock] = {} # phone -> lock
        self._data = self._load()

    # ── persistence ──────────────────────────────────────────────

    def _load(self) -> dict:
        if self._accounts_file.exists():
            try:
                return json.loads(self._accounts_file.read_text(encoding="utf-8"))
            except Exception:
                log.warning("[User %s] accounts.json corrupted — resetting.", self.user_id)
        return {"accounts": [], "active_phone": None}

    def _save(self) -> None:
        # FIXED — atomic write to prevent corruption on crash
        tmp_path = self._accounts_file.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(str(tmp_path), str(self._accounts_file))

    # ── read helpers ─────────────────────────────────────────────

    def get_accounts(self) -> list[dict]:
        return list(self._data.get("accounts", []))

    def get_active_phone(self) -> str | None:
        return self._data.get("active_phone")

    def get_active_account(self) -> dict | None:
        active = self.get_active_phone()
        if not active:
            return None
        return next((a for a in self._data["accounts"] if a["phone"] == active), None)

    def _session_path(self, phone: str) -> str:
        """Return the Telethon session file path (no extension)."""
        return str(self._sessions_dir / phone.replace("+", "").replace(" ", ""))

    # ── Telethon client management ────────────────────────────────

    async def _get_client(self, acc: dict) -> TelegramClient:
        """Return a connected (but not necessarily authorised) client.
        Auto-reconnects if the cached client is disconnected or stale."""
        phone = acc["phone"]

        if phone not in self._client_locks:
            self._client_locks[phone] = asyncio.Lock()

        async with self._client_locks[phone]:
            if phone in self._clients:
                client = self._clients[phone]
                if not client.is_connected():
                    try:
                        await client.connect()
                    except Exception as e:
                        # FIXED — log reconnection failure instead of silent swallow
                        log.warning("[User %s] Reconnect failed for %s: %s — rebuilding", self.user_id, phone, e)
                        try:
                            await client.disconnect()
                        except Exception:
                            pass
                        del self._clients[phone]
                        # Re-call unlocked logic cautiously
                        # To do this safely inside the lock we should just let it fall through
                        # to recreation instead of recursing immediately to avoid lock contention
                        pass
                    else:
                        # Connected successfully
                        pass

                # Re-check existence in case we deleted it
                if phone in self._clients:
                    # IMPROVED — detect stale/broken connection with throttled health check
                    last_check = _client_health_ts.get(phone, 0)
                    if time.time() - last_check > HEALTH_CHECK_INTERVAL:
                        try:
                            await client.get_me()
                            _client_health_ts[phone] = time.time()
                        except Exception as e:
                            log.warning("[User %s] Stale client for %s (%s) — force rebuild", self.user_id, phone, type(e).__name__)
                            _client_health_ts.pop(phone, None)
                            try:
                                await client.disconnect()
                            except Exception:
                                pass
                            del self._clients[phone]
                        else:
                            return client
                    else:
                        return client

            client = TelegramClient(
                self._session_path(phone),
                int(acc["api_id"]),
                acc["api_hash"],
            )
            await client.connect()

            # Real-time event listener for auto-fetching
            @client.on(events.ChatAction)
            async def on_chat_action(event):
                if getattr(event, 'user_joined', False) or getattr(event, 'user_added', False):
                    log.info("[AutoFetch] Real-time join/add detected for User %s. Resyncing...", self.user_id)
                    store = UserManager.get_store(self.user_id)
                    import asyncio
                    asyncio.create_task(_sync_groups_for_user(self.user_id, self, store))

            self._clients[phone] = client
            return client

    async def get_active_client(self) -> TelegramClient | None:
        """Return the active account's authorised client, or None.
        Retries once on connection errors (network reset, WinError 1236, etc.)."""
        acc = self.get_active_account()
        if not acc:
            return None
        for attempt in range(2):
            try:
                client = await self._get_client(acc)
                if await client.is_user_authorized():
                    return client
                # IMPROVED — log unauthorized state
                log.warning("[User %s] Client for %s not authorized (session expired?)", self.user_id, acc["phone"])
                return None
            except (ConnectionError, OSError) as e:
                if attempt == 0:
                    log.warning("[User %s] Connection lost for %s (%s), reconnecting…", self.user_id, acc["phone"], type(e).__name__)
                    self._clients.pop(acc["phone"], None)
                    await asyncio.sleep(1)
                    continue
                log.error("[User %s] Connection still failing for %s: %s", self.user_id, acc["phone"], e)
            except Exception as e:
                log.error("[User %s] Failed to get active client for %s: %s", self.user_id, acc["phone"], e)
                break
        return None

    # ── account CRUD ─────────────────────────────────────────────

    def add_or_update(self, phone: str, name: str, api_id: int, api_hash: str) -> None:
        # Preserve per-account log_group_id / round_counter across re-adds
        existing = next((a for a in self._data["accounts"] if a["phone"] == phone), None)
        carry_lg = existing.get("log_group_id") if existing else None
        carry_rc = existing.get("round_counter", 0) if existing else 0

        self._data["accounts"] = [a for a in self._data["accounts"] if a["phone"] != phone]
        self._data["accounts"].append({
            "phone":         phone,
            "name":          name,
            "api_id":        api_id,
            "api_hash":      api_hash,
            "log_group_id":  carry_lg,
            "round_counter": carry_rc,
        })
        if not self._data.get("active_phone"):
            self._data["active_phone"] = phone
        self._save()
        log.info("[User %s] Account saved: %s (%s)", self.user_id, name, phone)

    # ── per-account log group + round counter (auto-log system) ──
    #
    # These helpers own the two fields required by the per-account logging
    # system: `log_group_id` (the auto-created "Silent Ads Logs" supergroup)
    # and `round_counter` (persisted across restarts).

    def get_log_group_id(self, phone: str) -> int | None:
        acc = next((a for a in self._data["accounts"] if a["phone"] == phone), None)
        return acc.get("log_group_id") if acc else None

    def set_log_group_id(self, phone: str, gid: int | None) -> None:
        for a in self._data["accounts"]:
            if a["phone"] == phone:
                a["log_group_id"] = gid
                self._save()
                return

    def clear_log_group_id(self, phone: str) -> None:
        self.set_log_group_id(phone, None)

    def get_round_counter(self, phone: str) -> int:
        acc = next((a for a in self._data["accounts"] if a["phone"] == phone), None)
        return int(acc.get("round_counter", 0)) if acc else 0

    def bump_round(self, phone: str) -> int:
        """Increment and persist the round counter for this phone. Returns the new value."""
        for a in self._data["accounts"]:
            if a["phone"] == phone:
                a["round_counter"] = int(a.get("round_counter", 0)) + 1
                self._save()
                return int(a["round_counter"])
        return 0

    def set_active(self, phone: str) -> bool:
        if any(a["phone"] == phone for a in self._data["accounts"]):
            self._data["active_phone"] = phone
            self._save()
            return True
        return False

    async def logout(self, phone: str) -> bool:
        """Disconnect, delete session files, remove from list, clean caches."""
        acc = next((a for a in self._data["accounts"] if a["phone"] == phone), None)
        if not acc:
            return False

        # FIXED — Disconnect BEFORE log_out to prevent auto-reconnection
        client = self._clients.pop(phone, None)
        if client:
            try:
                await client.disconnect()
            except Exception as e:
                log.warning("[User %s] disconnect() failed for %s: %s", self.user_id, phone, e)
            try:
                await client.log_out()
            except Exception as e:
                log.warning("[User %s] log_out() failed for %s: %s", self.user_id, phone, e)
            # STABILITY PATCH — ensure truly disconnected after log_out
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                pass

        # FIXED — Delete BOTH .session AND .session-journal files
        sess_base = self._session_path(phone)
        for suffix in (".session", ".session-journal"):
            p = Path(sess_base + suffix)
            if p.exists():
                try:
                    p.unlink(missing_ok=True)
                    log.info("[User %s] Deleted: %s", self.user_id, p.name)
                except Exception as e:
                    log.error("[User %s] Failed to delete %s: %s", self.user_id, p, e)

        # FIXED — Clear all runtime caches tied to this account
        _cleanup_runtime_caches(self.user_id, phone)

        # Update data
        self._data["accounts"] = [a for a in self._data["accounts"] if a["phone"] != phone]
        if self._data.get("active_phone") == phone:
            remaining = self._data["accounts"]
            self._data["active_phone"] = remaining[0]["phone"] if remaining else None

        self._save()
        log.info("[User %s] Account logged out and fully cleaned: %s", self.user_id, phone)
        return True

    # ── startup reconnect ────────────────────────────────────────

    async def reconnect_all(self) -> None:
        """Re-connect all saved accounts on bot startup."""
        for acc in self._data["accounts"]:
            try:
                client = await self._get_client(acc)
                if await client.is_user_authorized():
                    log.info("[User %s] Account reconnected: %s (%s)", self.user_id, acc["name"], acc["phone"])
                else:
                    log.warning("[User %s] Account NOT authorised (session gone?): %s", self.user_id, acc["phone"])
                    if acc["phone"] in self._clients:
                        del self._clients[acc["phone"]]
            except Exception as e:
                log.error("[User %s] Reconnect failed for %s: %s", self.user_id, acc["phone"], e)

    # ── (fetch_groups and fetch_topics removed in favor of unified background fetch) ──


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  USER MANAGER  —  per-user lazy-init registry
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class UserManager:
    """Lazy-initialising per-user manager registry."""
    _stores: dict[int, Storage] = {}
    _account_mgrs: dict[int, AccountManager] = {}

    @classmethod
    def get_store(cls, user_id: int) -> Storage:
        if user_id not in cls._stores:
            cls._stores[user_id] = Storage(user_id)
        return cls._stores[user_id]

    @classmethod
    def get_account_mgr(cls, user_id: int) -> AccountManager:
        if user_id not in cls._account_mgrs:
            cls._account_mgrs[user_id] = AccountManager(user_id)
        return cls._account_mgrs[user_id]

    @classmethod
    def get_all_user_ids(cls) -> list[int]:
        """Scan user_data/ directory for existing user folders."""
        ids: list[int] = []
        if USER_DATA_DIR.exists():
            for p in USER_DATA_DIR.iterdir():
                if p.is_dir():
                    try:
                        ids.append(int(p.name))
                    except ValueError:
                        pass
        return ids

    @classmethod
    def get_all_account_mgrs(cls) -> dict[int, AccountManager]:
        return dict(cls._account_mgrs)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PREMIUM MANAGER  —  subscription tracking
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class PremiumManager:
    """Global premium subscription tracker.

    Stored in  user_data/premium_users.json:
    {
      "<user_id>": {
        "granted_by": <admin_uid>,
        "granted_at": "ISO timestamp",
        "expires_at": "ISO timestamp",
        "plan":       "7d" | "15d" | "30d" | custom
      }
    }
    """
    _file = USER_DATA_DIR / "premium_users.json"
    _data: dict[str, dict] = {}
    _lock = asyncio.Lock()

    @classmethod
    def _load(cls) -> None:
        cls._file.parent.mkdir(parents=True, exist_ok=True)
        if cls._file.exists():
            try:
                cls._data = json.loads(cls._file.read_text(encoding="utf-8"))
            except Exception:
                log.warning("premium_users.json corrupted — resetting.")
                cls._data = {}
        else:
            cls._data = {}

    @classmethod
    def _save(cls) -> None:
        tmp = cls._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(cls._data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(cls._file))

    @classmethod
    async def grant(cls, user_id: int, duration_seconds: int, plan_label: str, granted_by: int) -> dict:
        async with cls._lock:
            now = datetime.utcnow()
            existing = cls._data.get(str(user_id))
            if existing:
                old_exp = datetime.fromisoformat(existing["expires_at"])
                base = max(now, old_exp)
            else:
                base = now
            expires = base + timedelta(seconds=duration_seconds)
            entry = {
                "granted_by": granted_by,
                "granted_at": now.isoformat(),
                "expires_at": expires.isoformat(),
                "plan": plan_label,
            }
            cls._data[str(user_id)] = entry
            cls._save()
            log.info("[Premium] Granted %s to user %s until %s by admin %s",
                     plan_label, user_id, expires.isoformat(), granted_by)
            return entry

    @classmethod
    async def revoke(cls, user_id: int) -> bool:
        async with cls._lock:
            if str(user_id) in cls._data:
                del cls._data[str(user_id)]
                cls._save()
                log.info("[Premium] Revoked premium for user %s", user_id)
                return True
            return False

    @classmethod
    def is_premium(cls, user_id: int) -> bool:
        entry = cls._data.get(str(user_id))
        if not entry:
            return False
        try:
            expires = datetime.fromisoformat(entry["expires_at"])
            return datetime.utcnow() < expires
        except Exception:
            return False

    @classmethod
    def get_user(cls, user_id: int) -> dict | None:
        entry = cls._data.get(str(user_id))
        if not entry:
            return None
        return {**entry, "user_id": user_id, "active": cls.is_premium(user_id)}

    @classmethod
    def get_all(cls) -> list[dict]:
        result = []
        for uid_str, entry in cls._data.items():
            try:
                uid = int(uid_str)
            except ValueError:
                continue
            result.append({**entry, "user_id": uid, "active": cls.is_premium(uid)})
        return result

    @classmethod
    def get_active_count(cls) -> int:
        return sum(1 for uid_str in cls._data if cls.is_premium(int(uid_str)))

    @classmethod
    def cleanup_expired(cls) -> int:
        now = datetime.utcnow()
        expired = [k for k, v in cls._data.items()
                   if datetime.fromisoformat(v["expires_at"]) < now]
        for k in expired:
            del cls._data[k]
        if expired:
            cls._save()
        return len(expired)


PremiumManager._load()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FORCE JOIN MANAGER  —  channel membership requirement
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class ForceJoinManager:
    """Manage force-join channels.

    Stored in user_data/force_join.json:
    [
      {"channel": "@mychannel" or -1001234, "title": "My Channel", "added_by": admin_uid}
    ]
    """
    _file = USER_DATA_DIR / "force_join.json"
    _data: list[dict] = []
    _lock = asyncio.Lock()

    @classmethod
    def _load(cls) -> None:
        cls._file.parent.mkdir(parents=True, exist_ok=True)
        if cls._file.exists():
            try:
                cls._data = json.loads(cls._file.read_text(encoding="utf-8"))
            except Exception:
                cls._data = []
        else:
            cls._data = []

    @classmethod
    def _save(cls) -> None:
        tmp = cls._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(cls._data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(cls._file))

    @classmethod
    async def add_channel(cls, channel: str | int, title: str, added_by: int) -> bool:
        async with cls._lock:
            ch_str = str(channel)
            if any(str(c["channel"]) == ch_str for c in cls._data):
                return False
            cls._data.append({"channel": channel, "title": title, "added_by": added_by})
            cls._save()
            return True

    @classmethod
    async def remove_channel(cls, channel: str | int) -> bool:
        async with cls._lock:
            ch_str = str(channel)
            before = len(cls._data)
            cls._data = [c for c in cls._data if str(c["channel"]) != ch_str]
            if len(cls._data) < before:
                cls._save()
                return True
            return False

    @classmethod
    def get_channels(cls) -> list[dict]:
        return list(cls._data)

    @classmethod
    async def check_membership(cls, bot: Bot, user_id: int) -> list[dict]:
        """Return list of channels the user has NOT joined."""
        not_joined = []
        all_channels = cls._data + [{"channel": c, "title": str(c)} for c in FORCE_JOIN_CHANNELS
                                     if not any(str(c) == str(x["channel"]) for x in cls._data)]
        for ch in all_channels:
            try:
                member = await bot.get_chat_member(ch["channel"], user_id)
                if member.status in ("left", "kicked"):
                    not_joined.append(ch)
            except Exception:
                pass
        return not_joined


ForceJoinManager._load()


# Temporary storage for in-progress logins.
# TelegramClient can't be stored in aiogram FSM state (not JSON-serialisable),
# so we keep it here keyed by the user_id.
_pending_clients: dict[int, TelegramClient] = {}

# STABILITY PATCH — throttled health check: only call get_me() once per 5 minutes
_client_health_ts: dict[str, float] = {}  # phone -> last_health_check_timestamp
# HEALTH_CHECK_INTERVAL imported from config.py

# Cached Telethon entities for forward-from-channel (keyed by user_id).
# Not JSON-serialisable, so kept in memory and lazily re-resolved.
_forward_entities: dict[int, Any] = {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ACCESS CONTROL  —  owner + admins
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def is_owner(uid: int) -> bool:
    """True only for the configured OWNER_ID."""
    return uid == OWNER_ID


def has_access(uid: int) -> bool:
    """Gate: owner and configured ADMIN_IDS can use the bot."""
    return uid == OWNER_ID or uid in ADMIN_IDS


# Static admin label used in broadcast logs (replaces dynamic plan_badge).
ADMIN_LABEL = "👑 ADMIN"

# ── Owner-as-admin impersonation ─────────────────────────────────
# When the owner uses "Switch to Admin" the target admin's user_id
# is stored here keyed by the owner's uid.  All handler helpers
# (store / account_mgr look-ups) will operate on the *impersonated*
# user when this is set.  The owner still passes ``is_owner()``
# checks normally — only the data scope changes.
_owner_viewing_as: dict[int, int] = {}  # owner_uid → target_admin_uid


def _effective_uid(uid: int) -> int:
    """Return the user_id whose data should be accessed.

    If the caller is the owner and is currently impersonating an admin,
    return the admin's uid.  Otherwise return the caller's own uid.
    """
    if is_owner(uid) and uid in _owner_viewing_as:
        return _owner_viewing_as[uid]
    return uid

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  KEYBOARDS  —  imported from ui/ package
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from ui.main_menu import (
    kb_main,
)
from ui.common import kb_back, kb_cancel
from ui.emojis import create_button, premium_emoji, premium_text


# ─── Premium-emoji auto-rewriter for all HTML outbound messages ─────
#
# Telegram lets bots render custom (premium-animated) emoji in message
# text via ``<tg-emoji emoji-id="…">fallback</tg-emoji>``. To avoid
# touching every ``answer()``/``reply()``/``edit_text()`` call across
# ~5 000 lines of handlers, we monkey-patch the three ``Bot`` methods
# that carry user-visible text. When a caller sets
# ``parse_mode="HTML"`` we run the text through ``premium_text()``,
# which wraps every known emoji in a ``<tg-emoji>`` entity. Existing
# ``<tg-emoji>`` blocks and HTML tag text are left untouched.
#
# Messages sent without HTML parse mode are passed through unchanged —
# the entity syntax only works under HTML parse mode.

def _install_premium_emoji_middleware(bot_cls: type[Bot]) -> None:
    """Patch ``Bot.__call__`` once so every outbound Telegram method
    that carries a user-visible ``text`` / ``caption`` field — regardless
    of which aiogram shortcut produced it (``Message.answer``,
    ``Message.edit_text``, raw ``bot.send_message``…) — has its HTML
    body routed through ``premium_text()`` before hitting the API.

    We hook the single dispatch point ``Bot.__call__(method, …)`` rather
    than the many public shortcuts because every shortcut eventually
    funnels here. The method object is a pydantic model, so fields are
    set via ``object.__setattr__`` to bypass the frozen guard.

    If Telegram rejects the rewritten body with a custom-emoji /
    entity-related error (most commonly ``ENTITY_TEXT_INVALID`` when an
    emoji ID points to a pack the bot cannot use), we transparently
    retry the call with the original text — never silently fail the
    underlying API call (which is what made e.g. the "Set Delay" button
    appear unresponsive: the prompt edit threw and the click was lost).
    """
    if getattr(bot_cls, "_premium_emoji_patched", False):
        return

    from aiogram.exceptions import TelegramBadRequest

    original_call = bot_cls.__call__

    _TEXT_FIELDS = ("text", "caption")
    # Substrings that indicate Telegram rejected a rewritten body because
    # of the premium / custom-emoji entities we added. The error text is
    # uppercased before matching so we don't depend on Telegram's casing.
    _EMOJI_ERR_TOKENS = (
        "ENTITY_TEXT_INVALID",
        "CUSTOM_EMOJI_ENTITY_INVALID",
        "MESSAGE_HAS_NO_CUSTOM_EMOJI",
        "EMOJI_INVALID",
        "EMOJI_NOT_MODIFIED",
    )

    async def _patched_call(self, method, request_timeout=None):
        original_values: dict[str, str] = {}
        try:
            parse_mode = getattr(method, "parse_mode", None)
            # aiogram Default("parse_mode") sentinel — resolve against the
            # bot's configured default. v3 keeps this on ``bot.default``.
            if parse_mode is None or parse_mode.__class__.__name__ == "Default":
                default_props = getattr(self, "default", None)
                parse_mode = getattr(default_props, "parse_mode", None) if default_props else None
            if parse_mode and str(parse_mode).upper() == "HTML":
                # Wrap BOTH text and caption (a single API call can only
                # carry one in practice, but we handle the general case
                # defensively rather than ``break``-ing after the first).
                for field in _TEXT_FIELDS:
                    value = getattr(method, field, None)
                    if isinstance(value, str) and value:
                        rewritten = premium_text(value)
                        if rewritten != value:
                            original_values[field] = value
                            object.__setattr__(method, field, rewritten)
        except Exception as e:     # never block a send because of this
            log.debug("[premium_text] middleware skipped: %s", e)

        try:
            return await original_call(self, method, request_timeout=request_timeout)
        except TelegramBadRequest as e:
            if not original_values:
                raise
            err = str(e).upper()
            if not any(tok in err for tok in _EMOJI_ERR_TOKENS):
                raise
            # Telegram refused the premium-emoji rewrite — restore the
            # caller's original text and retry once. This prevents UI
            # buttons / log edits from silently breaking when an emoji
            # ID in emoji_db.json points to a pack the bot can't use.
            for field, original in original_values.items():
                object.__setattr__(method, field, original)
            log.warning(
                "[premium_text] Telegram rejected rewrite (%s) — retrying with original text.",
                err.split(":", 1)[-1].strip()[:80],
            )
            return await original_call(self, method, request_timeout=request_timeout)

    _patched_call.__wrapped__ = original_call
    bot_cls.__call__ = _patched_call
    bot_cls._premium_emoji_patched = True


_install_premium_emoji_middleware(Bot)
from ui.accounts import (
    kb_accounts_menu,
    kb_accounts_switch,
    kb_accounts_logout,
)
from ui.scheduler import (
    kb_groups,
    kb_start_choice,
    kb_topic_groups,
    kb_scheduler_menu,
    kb_sched_type,
    kb_days,
    kb_reset_menu,
    kb_reset_account_list,
    kb_reset_confirm,
)


def _get_main_kb(user_id: int, user_mode: str | None = None) -> InlineKeyboardMarkup:
    """Main keyboard wrapper. Owner sees an extra Admin Panel button."""
    kb = kb_main()
    if is_owner(user_id) and ADMIN_IDS:
        kb.inline_keyboard.append(
            [create_button("Admin Panel", "profile", "m:admin_panel", style="INFO")]
        )
    # Show impersonation banner button when owner is viewing as another admin
    if is_owner(user_id) and user_id in _owner_viewing_as:
        target = _owner_viewing_as[user_id]
        kb.inline_keyboard.append(
            [create_button(f"Viewing as {target} — Back to Owner", "back", "m:admin_back", style="DANGER")]
        )
    return kb



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FSM STATES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class S(StatesGroup):
    # ── broadcast settings ────────────────────────────────────────
    msg        = State()
    interval   = State()
    delay      = State()
    selecting  = State()

    # ── scheduler ─────────────────────────────────────────────────
    sc_type    = State()
    sc_intv    = State()
    sc_daily   = State()
    sc_wk_days = State()
    sc_wk_time = State()

    # ── account login flow ────────────────────────────────────────
    acc_phone    = State()   # step 1: enter phone number
    acc_code     = State()   # step 2: enter OTP code
    acc_2fa      = State()   # step 3 (optional): enter 2FA password

    # ── log forwarding ────────────────────────────────────────────
    log_group_id = State()   # enter log group ID

    # ── topic groups (new forum-topic selector) ───────────────────
    topic_selecting    = State()   # interactive topic toggle mode

    # ── forward from channel ──────────────────────────────────────
    forward_msg        = State()   # waiting for user to forward a channel post

    # ── fetch group ───────────────────────────────────────────────
    fetch_group_set    = State()   # enter fetch group ID for current account

    # ── premium grant ─────────────────────────────────────────────
    premium_grant_uid  = State()   # step 1: enter user ID
    premium_grant_dur  = State()   # step 2: enter duration (e.g. 7d, 3h)

    # ── force join ────────────────────────────────────────────────
    fj_add_channel     = State()   # enter channel username or ID

    # ── broadcast (admin panel quick-send) ────────────────────────
    broadcast_msg      = State()   # enter broadcast message text
    broadcast_confirm  = State()   # confirm broadcast



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SCHEDULER WRAPPER  —  APScheduler singleton
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class Sched:
    _instance: AsyncIOScheduler | None = None

    @classmethod
    def get(cls) -> AsyncIOScheduler:
        if cls._instance is None:
            cls._instance = AsyncIOScheduler(timezone="UTC")
        return cls._instance

    @classmethod
    def start(cls) -> None:
        s = cls.get()
        if not s.running:
            s.start()

    @classmethod
    def shutdown(cls) -> None:
        s = cls.get()
        if s.running:
            s.shutdown(wait=False)

    @classmethod
    def is_loop_running(cls, user_id: int, phone: str | None = None) -> bool:
        if phone:
            return cls.get().get_job(f"broadcast_loop_{user_id}_{phone}") is not None
        # Check if ANY loop is running for this user
        scheduler = cls.get()
        return any(
            j.id.startswith(f"broadcast_loop_{user_id}_")
            for j in scheduler.get_jobs()
        )

    @classmethod
    async def add_loop(cls, bot: Bot, user_id: int, interval_seconds: int, phone: str) -> None:
        job_id = f"broadcast_loop_{user_id}_{phone}"
        # STABILITY PATCH — always remove existing job before adding to prevent ghosts
        existing = cls.get().get_job(job_id)
        if existing:
            existing.remove()
            log.info("[User %s] Removed existing loop job for %s before re-add.", user_id, phone)
        cls.get().add_job(
            broadcast_once,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            args=[bot, user_id, phone],
            replace_existing=True,
            misfire_grace_time=30,
        )
        log.info("[User %s] Loop job registered for %s (every %ds).", user_id, phone, interval_seconds)

    @classmethod
    async def remove_loop(cls, user_id: int, phone: str) -> None:
        job_id = f"broadcast_loop_{user_id}_{phone}"
        job = cls.get().get_job(job_id)
        if job:
            job.remove()
            log.info("[User %s] Loop job removed for %s.", user_id, phone)

    @classmethod
    async def remove_all_loops(cls, user_id: int) -> None:
        """Remove all broadcast loop jobs for a user (all accounts)."""
        scheduler = cls.get()
        for job in scheduler.get_jobs():
            if job.id.startswith(f"broadcast_loop_{user_id}_"):
                job.remove()
        log.info("[User %s] All loop jobs removed.", user_id)

    @classmethod
    async def add_schedule(cls, bot: Bot, user_id: int, sched: dict) -> None:
        job_id = f"sc_{user_id}_{sched['id']}"
        stype  = sched["type"]
        if stype == "interval":
            trigger = IntervalTrigger(minutes=sched["interval_minutes"])
        elif stype == "daily":
            h, m = sched["time"].split(":")
            trigger = CronTrigger(hour=int(h), minute=int(m))
        elif stype == "weekly":
            days_str = ",".join(str(d) for d in sched.get("days", []))
            h, m     = sched["time"].split(":")
            trigger  = CronTrigger(day_of_week=days_str, hour=int(h), minute=int(m))
        else:
            log.warning("Unknown schedule type '%s' — skipped.", stype)
            return
        cls.get().add_job(
            broadcast_once,
            trigger=trigger,
            id=job_id,
            args=[bot, user_id],
            replace_existing=True,
            misfire_grace_time=60,
        )
        # ── Human-readable schedule log ──
        if stype == "interval":
            log.info(
                "[SCHEDULE ADDED] Type: Interval | Every: %d minutes | Account: User %s",
                sched["interval_minutes"], user_id,
            )
        elif stype == "daily":
            log.info(
                "[SCHEDULE ADDED] Type: Daily | Time: %s | Account: User %s",
                sched["time"], user_id,
            )
        elif stype == "weekly":
            day_labels = ", ".join(DAY_NAMES[d] for d in sched.get("days", []))
            log.info(
                "[SCHEDULE ADDED] Type: Weekly | Days: %s | Time: %s | Account: User %s",
                day_labels, sched["time"], user_id,
            )

    @classmethod
    async def remove_schedule(cls, user_id: int, sched_id: str) -> None:
        job = cls.get().get_job(f"sc_{user_id}_{sched_id}")
        if job:
            job.remove()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BROADCAST ENGINE  —  helpers + core
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Per-(user, phone) live process message ID in the fetch group
_process_msg_ids: dict[tuple[int, str], int] = {}

# Round counter per (user_id, phone)
_round_counter: dict[tuple[int, str], int] = {}
_last_round_stats: dict[tuple[int, str], tuple[int, int]] = {}

# ── Live round-log state ───────────────────────────────────────────
# One log message per (user, phone, round) edited in place from 0%
# through 100%. ``_round_log_msg_ids`` holds the message ID of the
# current round's status card in that account's log group;
# ``_round_log_last_text`` caches the last text we edited it to so we
# can skip a wasted API round-trip when nothing actually changed
# (Telegram rejects no-op edits with "message is not modified");
# ``_round_log_last_edit_ts`` throttles edits to once every ~1.2s per
# round to stay comfortably under the per-chat edit rate limit.
_round_log_msg_ids: dict[tuple[int, str], int] = {}
_round_log_last_text: dict[tuple[int, str], str] = {}
_round_log_last_edit_ts: dict[tuple[int, str], float] = {}


# FIXED — Centralized runtime cache cleanup to prevent memory leaks
def _cleanup_runtime_caches(user_id: int, phone: str | None = None) -> None:
    """Clean up all runtime caches for a user/phone.
    Called on logout, reset, and user removal."""
    _pending_clients.pop(user_id, None)
    _forward_entities.pop(user_id, None)
    if phone:
        key = (user_id, phone)
        _process_msg_ids.pop(key, None)
        _round_counter.pop(key, None)
        _last_round_stats.pop(key, None)
        _client_health_ts.pop(phone, None)  # STABILITY PATCH — clean health check cache
    else:
        for k in list(_process_msg_ids.keys()):
            if k[0] == user_id:
                del _process_msg_ids[k]
        for k in list(_round_counter.keys()):
            if k[0] == user_id:
                del _round_counter[k]
        for k in list(_last_round_stats.keys()):
            if k[0] == user_id:
                del _last_round_stats[k]
        # Clean ALL health check entries for this user's phones
        acct_mgr = UserManager.get_account_mgr(user_id) if user_id in UserManager._account_mgrs else None
        if acct_mgr:
            for acc in acct_mgr.get_accounts():
                _client_health_ts.pop(acc["phone"], None)
    _log_lines_sent.pop(user_id, None)
    log.info("[User %s] Runtime caches cleaned (phone=%s).", user_id, phone or "all")


def _progress_bar(current: int, total: int) -> tuple[str, int]:
    """Return (bar_string, percentage)."""
    pct = int((current / total) * 100) if total else 0
    filled = pct // 10
    return "█" * filled + "░" * (10 - filled), pct


_TERMINAL_STATUSES = {
    "COMPLETED", "INTERRUPTED", "SOURCE GONE", "NO CLIENT", "ERROR",
}


def _fmt_interval(secs: int) -> str:
    """Human-readable interval, e.g. 300 -> '5m 0s', 90 -> '1m 30s', 45 -> '45s'."""
    secs = max(0, int(secs))
    if secs < 60:
        return f"{secs}s"
    m, s = divmod(secs, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"


def _build_process_msg(
    phone: str, plan: str, round_num: int, threads: int,
    total: int, current: int, sent: int, failed: int, status: str,
    *,
    interval_seconds: int | None = None,
    failures: list[tuple[str, str]] | None = None,
) -> str:
    """Build the round status card. ``interval_seconds`` and ``failures``
    are appended only when the round reaches a terminal status, so the
    same message ID can be edited from RUNNING (0%) all the way through
    to COMPLETED with the next-round countdown and a numbered failure
    breakdown — one card per round."""
    bar, pct = _progress_bar(current, total)
    lines = [
        "=============================",
        f"👤 ACCOUNT: {phone}",
        f"⚙️ PLAN: {plan}",
        f"🔁 ROUND: #{round_num}",
        f"⚡ THREADS: {threads}",
        f"📦 GROUPS: {total}",
        "=============================",
        f"📊 PROGRESS: [{bar}] {pct}%",
        f"↗️ TOTAL SENT: {sent}",
        f"❌ FAILED: {failed}",
        f"⏳ STATUS: {status}",
        "=============================",
    ]

    is_terminal = status.upper() in _TERMINAL_STATUSES
    if is_terminal and interval_seconds is not None and status.upper() == "COMPLETED":
        lines.append(f"⏰ NEXT ROUND IN: {_fmt_interval(interval_seconds)}")
        lines.append("=============================")

    if is_terminal and failures:
        lines.append("❌ FAILED GROUPS:")
        # Cap at 20 entries to stay safely under Telegram's 4096-char
        # message limit even on rounds with many failures. The rest are
        # summarised on the next line — full detail still lives in logs.
        for i, (title, reason) in enumerate(failures[:20], 1):
            safe_title  = _html_escape(str(title))
            safe_reason = _html_escape(str(reason))
            lines.append(f"  {i}. {safe_title} → {safe_reason}")
        if len(failures) > 20:
            lines.append(f"  …and {len(failures) - 20} more")
        lines.append("=============================")

    return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PER-ACCOUNT AUTO LOG GROUP
#
#  Each Telegram account gets a dedicated, bot-accessible supergroup
#  titled "Silent Ads Logs". The Telethon user creates it on first login
#  and invites the aiogram bot as admin so the bot can post structured
#  round logs. On creation, a welcome message is posted and pinned by
#  the bot. The chat_id is persisted on the account record
#  (AccountManager.get_log_group_id / set_log_group_id) and reused on
#  every subsequent run; if the group was deleted or the bot was kicked
#  the next send recreates it transparently.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Concurrency guard: don't race two creations for the same (user, phone).
_log_group_create_locks: dict[tuple[int, str], asyncio.Lock] = {}


def _log_group_lock(user_id: int, phone: str) -> asyncio.Lock:
    key = (user_id, phone)
    lock = _log_group_create_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _log_group_create_locks[key] = lock
    return lock


async def _create_log_group_via_telethon(
    bot: Bot, client: TelegramClient, phone: str,
) -> int | None:
    """Create a private megagroup "Silent Ads Logs", invite the aiogram bot
    and promote it to admin, then post and pin a branded welcome message.
    Returns the aiogram-style chat_id (-100…) or None on failure."""
    try:
        title = "Silent Ads Logs"
        about = "Automated broadcast logs. Managed by the bot — do not delete."
        res   = await client(CreateChannelRequest(
            title=title, about=about, megagroup=True,
        ))
        # CreateChannelRequest returns `Updates`; the new channel is in .chats.
        channel = None
        for c in getattr(res, "chats", []) or []:
            if isinstance(c, Channel):
                channel = c
                break
        if channel is None:
            log.error("[LogGroup] Create returned no channel for %s", phone)
            return None

        chat_id = int(f"-100{channel.id}")

        # Invite and promote the aiogram bot so it can post.
        try:
            me         = await bot.get_me()
            bot_entity = await client.get_input_entity(me.username)
            channel_in = await client.get_input_entity(channel)

            await client(InviteToChannelRequest(channel_in, [bot_entity]))
            try:
                await client(EditAdminRequest(
                    channel_in,
                    bot_entity,
                    ChatAdminRights(
                        change_info=True,
                        post_messages=True,
                        edit_messages=True,
                        delete_messages=True,
                        invite_users=True,
                        pin_messages=True,
                        manage_topics=True,
                    ),
                    "bot",
                ))
            except Exception as e:
                log.warning("[LogGroup] EditAdmin failed for %s: %s", phone, e)
        except Exception as e:
            log.warning("[LogGroup] Invite/promote bot failed for %s: %s", phone, e)

        # Post + pin the branded welcome message via the aiogram bot.
        # Best-effort: never let a failure here abort group creation.
        try:
            welcome_text = (
                "📢 <b>Silent Ads Log System Activated</b>\n\n"
                "This group will store all your automation logs.\n\n"
                "You will see:\n"
                "• Live progress updates\n"
                "• Sent / Failed messages\n"
                "• Round status\n"
                "• Next round timing\n\n"
                "⚠️ Do not delete this group or logs may stop working."
            )
            # Give Telegram a moment to propagate the bot's admin rights.
            await asyncio.sleep(1.5)
            sent = None
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    sent = await bot.send_message(
                        chat_id=chat_id, text=welcome_text, parse_mode="HTML",
                    )
                    break
                except TelegramRetryAfter as e:
                    last_exc = e
                    await asyncio.sleep(min(int(e.retry_after) + 1, 30))
                except (TelegramForbiddenError, TelegramBadRequest) as e:
                    last_exc = e
                    await asyncio.sleep(1.0 + attempt)
            if sent is None:
                log.warning("[LogGroup] Welcome send failed for %s: %s", phone, last_exc)
            else:
                try:
                    await bot.pin_chat_message(
                        chat_id=chat_id,
                        message_id=sent.message_id,
                        disable_notification=True,
                    )
                except Exception as e:
                    log.warning("[LogGroup] Pin welcome failed for %s: %s", phone, e)
        except Exception as e:
            log.warning("[LogGroup] Welcome message flow failed for %s: %s", phone, e)

        log.info("[LogGroup] Created '%s' → %s", title, chat_id)
        return chat_id
    except Exception as e:
        log.error("[LogGroup] Create failed for %s: %s", phone, e)
        return None


async def _is_log_group_reachable(bot: Bot, gid: int) -> bool:
    """Return True if the bot can still see and address the chat."""
    try:
        await bot.get_chat(gid)
        return True
    except (TelegramForbiddenError, TelegramBadRequest):
        return False
    except Exception as e:
        # Network errors — don't treat as deleted; assume reachable.
        log.debug("[LogGroup] get_chat(%s) soft error: %s", gid, e)
        return True


async def ensure_log_group(
    bot: Bot, user_id: int, phone: str, *, force_recreate: bool = False,
) -> int | None:
    """Return the persisted per-account log group id, creating it if
    missing / invalid. Safe to call multiple times; concurrent callers
    for the same (user, phone) serialise on an asyncio.Lock."""
    account_mgr = UserManager.get_account_mgr(user_id)
    acc = next((a for a in account_mgr.get_accounts() if a["phone"] == phone), None)
    if not acc:
        return None

    async with _log_group_lock(user_id, phone):
        if not force_recreate:
            gid = account_mgr.get_log_group_id(phone)
            if gid and await _is_log_group_reachable(bot, gid):
                return gid
            if gid:
                log.warning(
                    "[LogGroup][User %s][%s] Stored group %s unreachable — recreating.",
                    user_id, phone, gid,
                )

        # (Re-)create: need an authorised Telethon client.
        try:
            client = await account_mgr._get_client(acc)
            if not await client.is_user_authorized():
                log.warning(
                    "[LogGroup][User %s][%s] Session not authorised — cannot create log group.",
                    user_id, phone,
                )
                return None
        except Exception as e:
            log.error(
                "[LogGroup][User %s][%s] No Telethon client available: %s",
                user_id, phone, e,
            )
            return None

        gid = await _create_log_group_via_telethon(bot, client, phone)
        if gid:
            account_mgr.set_log_group_id(phone, gid)
        else:
            account_mgr.clear_log_group_id(phone)
        return gid


async def _safe_send_log(
    bot: Bot, user_id: int, phone: str, text: str,
    *, max_retries: int = 3,
) -> bool:
    """Send a structured log message to this account's log group, with
    retries, flood-wait handling and transparent recreation if the group
    was deleted or the bot was kicked."""
    account_mgr = UserManager.get_account_mgr(user_id)
    gid = account_mgr.get_log_group_id(phone)
    if not gid:
        gid = await ensure_log_group(bot, user_id, phone)
        if not gid:
            return False

    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            await bot.send_message(chat_id=gid, text=text, parse_mode="HTML")
            return True
        except TelegramRetryAfter as e:
            wait = min(int(e.retry_after) + 1, 120)
            log.warning(
                "[LogGroup][User %s][%s] FloodWait %ds (attempt %d/%d)",
                user_id, phone, wait, attempt, max_retries,
            )
            await asyncio.sleep(wait)
        except TelegramForbiddenError:
            log.warning(
                "[LogGroup][User %s][%s] Bot kicked from log group %s — recreating.",
                user_id, phone, gid,
            )
            account_mgr.clear_log_group_id(phone)
            new_gid = await ensure_log_group(bot, user_id, phone, force_recreate=True)
            if not new_gid or new_gid == gid:
                return False
            gid = new_gid
        except TelegramBadRequest as e:
            msg = str(e).lower()
            if "chat not found" in msg or "chat_id is empty" in msg or "peer_id_invalid" in msg:
                log.warning(
                    "[LogGroup][User %s][%s] Log group %s not found — recreating.",
                    user_id, phone, gid,
                )
                account_mgr.clear_log_group_id(phone)
                new_gid = await ensure_log_group(bot, user_id, phone, force_recreate=True)
                if not new_gid:
                    return False
                gid = new_gid
            else:
                log.error(
                    "[LogGroup][User %s][%s] BadRequest (gid=%s): %s",
                    user_id, phone, gid, e,
                )
                return False
        except Exception as e:
            log.warning(
                "[LogGroup][User %s][%s] send error (attempt %d/%d): %s",
                user_id, phone, attempt, max_retries, e,
            )
            await asyncio.sleep(0.5 + random.random())
    return False


async def _send_round_log_message(
    bot: Bot, user_id: int, phone: str, text: str,
    *, max_retries: int = 3,
) -> int | None:
    """Send a NEW round-status card to the account's log group and
    return its message_id, so callers can edit the same card later.
    Returns None on persistent failure. Mirrors ``_safe_send_log``'s
    flood-wait / kicked / group-deleted handling."""
    account_mgr = UserManager.get_account_mgr(user_id)
    gid = account_mgr.get_log_group_id(phone)
    if not gid:
        gid = await ensure_log_group(bot, user_id, phone)
        if not gid:
            return None

    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            sent = await bot.send_message(chat_id=gid, text=text, parse_mode="HTML")
            return sent.message_id
        except TelegramRetryAfter as e:
            wait = min(int(e.retry_after) + 1, 120)
            log.warning(
                "[LogGroup][User %s][%s] (init) FloodWait %ds (attempt %d/%d)",
                user_id, phone, wait, attempt, max_retries,
            )
            await asyncio.sleep(wait)
        except TelegramForbiddenError:
            log.warning(
                "[LogGroup][User %s][%s] (init) Bot kicked from %s — recreating.",
                user_id, phone, gid,
            )
            account_mgr.clear_log_group_id(phone)
            new_gid = await ensure_log_group(bot, user_id, phone, force_recreate=True)
            if not new_gid or new_gid == gid:
                return None
            gid = new_gid
        except TelegramBadRequest as e:
            msg = str(e).lower()
            if "chat not found" in msg or "chat_id is empty" in msg or "peer_id_invalid" in msg:
                account_mgr.clear_log_group_id(phone)
                new_gid = await ensure_log_group(bot, user_id, phone, force_recreate=True)
                if not new_gid:
                    return None
                gid = new_gid
            else:
                log.error(
                    "[LogGroup][User %s][%s] (init) BadRequest: %s",
                    user_id, phone, e,
                )
                return None
        except Exception as e:
            log.warning(
                "[LogGroup][User %s][%s] (init) error (attempt %d/%d): %s",
                user_id, phone, attempt, max_retries, e,
            )
            await asyncio.sleep(0.5 + random.random())
    return None


async def begin_round_log(
    bot: Bot, user_id: int, phone: str, plan: str,
    round_num: int, total_groups: int, threads: int = 1,
) -> None:
    """Start a new round's live status card (RUNNING, 0%). Stores the
    message ID so subsequent progress / final updates edit the same
    message instead of spamming a new card per round phase."""
    key = (user_id, phone)
    text = _build_process_msg(
        phone=phone, plan=plan, round_num=round_num, threads=threads,
        total=total_groups, current=0, sent=0, failed=0, status="RUNNING",
    )
    msg_id = await _send_round_log_message(bot, user_id, phone, text)
    if msg_id is not None:
        _round_log_msg_ids[key] = msg_id
        _round_log_last_text[key] = text
        _round_log_last_edit_ts[key] = time.monotonic()


async def update_round_log(
    bot: Bot, user_id: int, phone: str, plan: str,
    round_num: int, total_groups: int, current: int,
    sent: int, failed: int, threads: int = 1,
    *, force: bool = False,
) -> None:
    """Edit the round's status card with live progress. Throttled to
    one edit every ~1.2s per (user, phone) and skipped when the
    rendered text would be identical to the last successful edit, so a
    100-group round produces ~10 visible updates (one per 10% bucket)
    rather than hammering Telegram. ``force=True`` overrides the
    throttle — used by the terminal edit so the final stats always
    land even if the previous edit was very recent."""
    key = (user_id, phone)
    msg_id = _round_log_msg_ids.get(key)
    if msg_id is None:
        # Initial send failed (e.g. log group unreachable) — nothing to
        # edit. Stay silent; the broadcast itself continues unaffected.
        return

    now = time.monotonic()
    if not force:
        last_ts = _round_log_last_edit_ts.get(key, 0.0)
        if now - last_ts < 1.2:
            return

    text = _build_process_msg(
        phone=phone, plan=plan, round_num=round_num, threads=threads,
        total=total_groups, current=current,
        sent=sent, failed=failed, status="RUNNING",
    )
    if not force and text == _round_log_last_text.get(key):
        return

    account_mgr = UserManager.get_account_mgr(user_id)
    gid = account_mgr.get_log_group_id(phone)
    if not gid:
        return

    try:
        await bot.edit_message_text(
            chat_id=gid, message_id=msg_id, text=text, parse_mode="HTML",
        )
        _round_log_last_text[key] = text
        _round_log_last_edit_ts[key] = now
    except TelegramRetryAfter as e:
        # Just back off — the next progress update will re-attempt.
        log.debug(
            "[LogGroup][User %s][%s] live-edit flood-wait %ds — deferring.",
            user_id, phone, int(e.retry_after),
        )
        _round_log_last_edit_ts[key] = now + float(e.retry_after)
    except TelegramBadRequest as e:
        emsg = str(e).lower()
        if "message is not modified" in emsg:
            # Nothing changed in this update — harmless.
            _round_log_last_edit_ts[key] = now
            return
        if (
            "message to edit not found" in emsg
            or "message can't be edited" in emsg
            or "message_id_invalid" in emsg
        ):
            # The status card was deleted in the log group. Post a new
            # one so the user keeps seeing live progress.
            new_id = await _send_round_log_message(bot, user_id, phone, text)
            if new_id is not None:
                _round_log_msg_ids[key] = new_id
                _round_log_last_text[key] = text
                _round_log_last_edit_ts[key] = now
            return
        log.debug(
            "[LogGroup][User %s][%s] live-edit BadRequest: %s",
            user_id, phone, e,
        )
    except Exception as e:
        log.debug(
            "[LogGroup][User %s][%s] live-edit error: %s",
            user_id, phone, e,
        )


async def finalize_round_log(
    bot: Bot, user_id: int, phone: str, plan: str,
    round_num: int, total_groups: int, sent: int, failed: int,
    status: str, threads: int = 1,
    *, interval_seconds: int | None = None,
    failures: list[tuple[str, str]] | None = None,
) -> None:
    """Edit the round's status card to its terminal state (COMPLETED /
    INTERRUPTED / etc.) with sent + failed totals, the failure
    breakdown, and the next-round countdown — all in the same message
    that was first posted by ``begin_round_log``. Falls back to a new
    message if the original was deleted. Always clears the per-round
    cache so the next round starts fresh."""
    key = (user_id, phone)
    text = _build_process_msg(
        phone=phone, plan=plan, round_num=round_num, threads=threads,
        total=total_groups, current=sent + failed,
        sent=sent, failed=failed, status=status,
        interval_seconds=interval_seconds,
        failures=failures,
    )

    msg_id = _round_log_msg_ids.get(key)
    account_mgr = UserManager.get_account_mgr(user_id)
    gid = account_mgr.get_log_group_id(phone)

    edited = False
    if msg_id is not None and gid:
        try:
            await bot.edit_message_text(
                chat_id=gid, message_id=msg_id, text=text, parse_mode="HTML",
            )
            edited = True
        except TelegramBadRequest as e:
            emsg = str(e).lower()
            if "message is not modified" in emsg:
                edited = True
            elif (
                "message to edit not found" in emsg
                or "message can't be edited" in emsg
                or "message_id_invalid" in emsg
            ):
                edited = False
            else:
                log.warning(
                    "[LogGroup][User %s][%s] finalize edit BadRequest: %s",
                    user_id, phone, e,
                )
                edited = False
        except TelegramRetryAfter as e:
            wait = min(int(e.retry_after) + 1, 120)
            log.warning(
                "[LogGroup][User %s][%s] finalize FloodWait %ds — waiting and retrying once.",
                user_id, phone, wait,
            )
            await asyncio.sleep(wait)
            try:
                await bot.edit_message_text(
                    chat_id=gid, message_id=msg_id, text=text, parse_mode="HTML",
                )
                edited = True
            except Exception as e2:
                log.warning(
                    "[LogGroup][User %s][%s] finalize edit retry failed: %s",
                    user_id, phone, e2,
                )
                edited = False
        except Exception as e:
            log.warning(
                "[LogGroup][User %s][%s] finalize edit error: %s",
                user_id, phone, e,
            )
            edited = False

    if not edited:
        # Original status card was lost (deleted, kicked, missing): post
        # a fresh terminal card so the user still sees the final stats.
        await _safe_send_log(bot, user_id, phone, text)

    _round_log_msg_ids.pop(key, None)
    _round_log_last_text.pop(key, None)
    _round_log_last_edit_ts.pop(key, None)


# ── Legacy shims kept for any external callers / tests. ───────────
# These wrap the new live-edit flow so older code paths keep working
# even though the in-bot broadcast loop now uses the new helpers
# directly.
async def send_round_start_log(
    bot: Bot, user_id: int, phone: str, plan: str,
    round_num: int, total_groups: int, threads: int = 1,
) -> None:
    await begin_round_log(
        bot, user_id, phone, plan,
        round_num=round_num, total_groups=total_groups, threads=threads,
    )


async def send_round_end_log(
    bot: Bot, user_id: int, phone: str, plan: str,
    round_num: int, total_groups: int, sent: int, failed: int,
    status: str, threads: int = 1,
    *, interval_seconds: int | None = None,
    failures: list[tuple[str, str]] | None = None,
) -> None:
    await finalize_round_log(
        bot, user_id, phone, plan,
        round_num=round_num, total_groups=total_groups,
        sent=sent, failed=failed, status=status, threads=threads,
        interval_seconds=interval_seconds, failures=failures,
    )


async def send_failure_report(
    bot: Bot, user_id: int, phone: str, round_num: int,
    failures: list[tuple[str, str]],
) -> None:
    """Send a summary report of failed groups for a round to the account's log group."""
    if not failures:
        return
    lines = [
        "❌ <b>FAILED GROUPS REPORT</b>",
        f"Round #{round_num} — Account: <code>{phone}</code>",
        "",
    ]
    for idx, (grp, reason) in enumerate(failures, 1):
        lines.append(f"{idx}. {grp} → {reason}")
    text = "\n".join(lines)
    await _send_round_log_message(bot, user_id, phone, text)


# ── legacy compatibility shim ────────────────────────────────────
# Old code paths still call `_send_to_fetch_group(...)` for one-off
# warnings. Route those through the new auto-log group so the UX stays
# consistent even if a user previously set a manual fetch group.

async def _send_to_fetch_group(bot: Bot, user_id: int, phone: str, text: str) -> None:
    """Send an error/warning message to the account's log group.
    Retained for backward compatibility with existing call sites."""
    # If the user has explicitly configured a manual fetch group, honour it
    # (backward compat). Otherwise route to the auto-created log group.
    store = UserManager.get_store(user_id)
    fmap = await store.get("fetch_group_account_map", {})
    gid  = fmap.get(phone)
    if gid:
        try:
            await bot.send_message(chat_id=gid, text=text, parse_mode="HTML")
            return
        except Exception as e:
            log.warning("[User %s] manual fetch-group send failed (gid=%s): %s", user_id, gid, e)
    await _safe_send_log(bot, user_id, phone, text)


async def _update_process_msg(
    bot: Bot, user_id: int, phone: str, text: str,
) -> None:
    """Send or edit the live process message in the fetch group."""
    store = UserManager.get_store(user_id)
    fmap = await store.get("fetch_group_account_map", {})
    gid = fmap.get(phone)
    if not gid:
        return
    key = (user_id, phone)
    msg_id = _process_msg_ids.get(key)
    if msg_id:
        try:
            await bot.edit_message_text(chat_id=gid, message_id=msg_id, text=text)
            return
        except Exception as e:
            # FIXED — log edit failure
            log.debug("[User %s] Process msg edit failed, sending new: %s", user_id, e)
    try:
        sent_msg = await bot.send_message(chat_id=gid, text=text)
        _process_msg_ids[key] = sent_msg.message_id
    except Exception as e:
        # FIXED — log send failure
        log.warning("[User %s] Process msg send failed (gid=%s): %s", user_id, gid, e)


async def _check_loop_active(store: "Storage", phone: str) -> bool:
    """Check if the loop for a specific phone is still active."""
    active_map = await store.get("loop_active_accounts", {})
    return active_map.get(phone, False)


# ── Dashboard metrics hook (safe — no-op if dashboard not available) ──
async def _dashboard_record_send(success: bool, phone: str = "", group: str = "", error: str = "") -> None:
    """Record a send event for dashboard metrics. Non-blocking, never raises."""
    try:
        from dashboard.core.metrics import metrics
        from dashboard.services.stats import stats_service
        from dashboard.core.events import Event, EventType, event_bus
        await metrics.record_send(success)
        await stats_service.record_message(success)
        event_type = EventType.MESSAGE_SENT if success else EventType.MESSAGE_FAILED
        await event_bus.publish(Event(
            type=event_type,
            data={"phone": phone, "group": group, "error": error},
        ))
    except Exception:
        pass


async def broadcast_once(bot: Bot, user_id: int, phone: str | None = None) -> None:
    """
    Full broadcast round to all selected groups for a specific user+account.
    phone: the Telethon account phone to use. If None, uses the active account.
    Called by APScheduler — never sends replies to the user.
    """
    store = UserManager.get_store(user_id)
    account_mgr = UserManager.get_account_mgr(user_id)

    # Resolve phone
    if not phone:
        phone = account_mgr.get_active_phone()
    if not phone:
        log.warning("[User %s] Broadcast skipped — no active phone.", user_id)
        return

    # Abort immediately if this account's loop was stopped
    if not await _check_loop_active(store, phone):
        log.info("[User %s][%s] Broadcast skipped — loop not active.", user_id, phone)
        return

    # ── Cache ALL settings once at start ──
    settings = await store.all()
    message  = settings.get("message", "").strip()
    forward_active = settings.get("forward_active", False)
    immediate_send = settings.get("immediate_send", False)

    bmode = settings.get("broadcast_mode", "selected")
    if bmode == "topic":
        raw_tg  = settings.get("topic_groups", [])
        groups  = []
        for tg in raw_tg:
            gid   = tg["id"]
            gtitle = tg.get("title", str(gid))
            for tid in tg.get("topics", []):
                groups.append({"id": gid, "title": gtitle, "topic_id": tid})
    elif bmode == "both":
        unique: dict[int, dict] = {}
        for g in settings.get("topic_groups", []):
            gid = g["id"]
            gtitle = g.get("title", str(gid))
            for tid in g.get("topics", []):
                unique[f"{gid}_{tid}"] = {"id": gid, "title": gtitle, "topic_id": tid}
        for g in settings.get("selected_groups", []):
            gid = g["id"]
            if f"{gid}_None" not in unique:
                unique[f"{gid}_None"] = {"id": gid, "title": g.get("title", str(gid)), "topic_id": None}
        groups = list(unique.values())
    else:
        groups = list(settings.get("selected_groups", []))

    if not groups:
        log.warning("[User %s][%s] Broadcast skipped — no groups.", user_id, phone)
        return
    has_media = bool(settings.get("media_type") and settings.get("media_file_path"))
    if not forward_active and not message and not has_media:
        log.warning("[User %s][%s] Broadcast skipped — no message/forward/media.", user_id, phone)
        return

    use_random = settings.get("random_delay", True)
    d_base     = float(settings.get("delay_between_sends", 3))
    d_min      = float(settings.get("random_delay_min", 2.0))
    d_max      = float(settings.get("random_delay_max", 8.0))

    # Get the correct Telethon client for this phone
    acc = next((a for a in account_mgr.get_accounts() if a["phone"] == phone), None)
    tl_client = None
    if acc:
        try:
            tl_client = await account_mgr._get_client(acc)
            if not await tl_client.is_user_authorized():
                # FAIL-SAFE — log unauthorized as critical
                log.critical("[User %s][%s] Client NOT authorized — session expired or revoked.", user_id, phone)
                tl_client = None
        except Exception as e:
            # FIXED — log instead of silent swallow
            log.error("[User %s][%s] Failed to get Telethon client: %s", user_id, phone, e)
            tl_client = None
    else:
        log.critical("[User %s][%s] Account not found in accounts list.", user_id, phone)

    # ── Round tracking ──
    # Persisted across restarts on the account record.
    key = (user_id, phone)
    round_num = account_mgr.bump_round(phone)
    _round_counter[key] = round_num   # back-compat for any lingering readers

    # ── Ensure the per-account log group exists (auto-create / reuse) ──
    # Safe to call every round; it's a cheap get_chat() when the group
    # already exists, and recreates transparently if deleted.
    await ensure_log_group(bot, user_id, phone)

    # Static admin label used in broadcast logs.
    plan_label = ADMIN_LABEL

    total = len(groups)
    sent_count = 0
    fail_count = 0
    failures: list[tuple[str, str]] = []  # (group_title, failure_reason)

    # Interval between rounds — surfaced in the final status card so the
    # user can see exactly when the next round will fire.
    interval_seconds = int(settings.get("interval_seconds", 300))

    # ── Round-start: ONE message per round, edited in place ──────
    # ``begin_round_log`` sends a RUNNING/0% status card and caches the
    # message id. Every progress milestone and the final terminal state
    # edit that same card via ``update_round_log`` /
    # ``finalize_round_log`` — no more two-card "start + end" pairs.
    await begin_round_log(
        bot, user_id, phone, plan_label,
        round_num=round_num, total_groups=total, threads=1,
    )

    # ── Forward mode branch ──────────────────────────────────────
    if forward_active:
        if not tl_client:
            log.warning("[User %s][%s] Forward mode but no Telethon client.", user_id, phone)
            await finalize_round_log(
                bot, user_id, phone, plan_label, round_num,
                total_groups=total, sent=0, failed=0, status="NO CLIENT",
                interval_seconds=interval_seconds, failures=failures,
            )
            return

        fwd_channel_id = settings.get("forward_channel_id")
        fwd_message_id = settings.get("forward_message_id")
        if not fwd_channel_id or not fwd_message_id:
            log.warning("[User %s][%s] Forward mode missing channel/message data.", user_id, phone)
            await finalize_round_log(
                bot, user_id, phone, plan_label, round_num,
                total_groups=total, sent=0, failed=0, status="ERROR",
                interval_seconds=interval_seconds, failures=failures,
            )
            return

        # Album = all message IDs belonging to the source media group (1+).
        # Falls back to a single-ID list for non-album posts and for legacy
        # settings files that pre-date the album-detection feature.
        album_ids: list[int] = list(settings.get("forward_album_ids") or [fwd_message_id])
        if not album_ids:
            album_ids = [fwd_message_id]

        from_peer = _forward_entities.get(user_id)
        if from_peer is None:
            try:
                from_peer = await tl_client.get_entity(fwd_channel_id)
                _forward_entities[user_id] = from_peer
            except Exception as e:
                log.error("[User %s][%s] Cannot resolve forward channel: %s", user_id, phone, e)
                await finalize_round_log(
                    bot, user_id, phone, plan_label, round_num,
                    total_groups=total, sent=0, failed=0, status="ERROR",
                    interval_seconds=interval_seconds, failures=failures,
                )
                return

        hide_sender = settings.get("forward_hide_sender", True)
        mode_labels = {"selected": "Selected", "topic": "Topic", "both": "Both"}
        log.info(
            "[User %s][%s] Forward broadcast round #%d started [%s] (%d groups, %d msg(s)/post).",
            user_id, phone, round_num, mode_labels.get(bmode, bmode), total, len(album_ids),
        )

        source_gone = False
        for idx, group in enumerate(groups):
            if not await _check_loop_active(store, phone):
                log.info("[User %s][%s] ⏹ Forward broadcast interrupted at %d/%d.", user_id, phone, idx + 1, total)
                await finalize_round_log(
                    bot, user_id, phone, plan_label, round_num,
                    total_groups=total, sent=sent_count, failed=fail_count,
                    status="INTERRUPTED",
                    interval_seconds=interval_seconds, failures=failures,
                )
                _last_round_stats[key] = (sent_count, fail_count)
                return

            gid      = group["id"]
            title    = group.get("title", str(gid))
            topic_id = group.get("topic_id")

            ok, reason = await _forward_safe_telethon(
                bot, user_id, phone, tl_client, gid, title,
                album_ids, from_peer, topic_id=topic_id,
                drop_author=hide_sender,
            )
            if ok:
                sent_count += 1
                asyncio.create_task(_dashboard_record_send(True, phone=phone, group=title))
            else:
                fail_count += 1
                failures.append((title, reason or "forward failed"))
                asyncio.create_task(_dashboard_record_send(False, phone=phone, group=title, error=reason or ""))
                # Hard-stop: if the source post is gone we'd just keep
                # failing on every destination this round and every future
                # round — stop the loop and notify the owner once.
                if reason in (FWD_REASON_SOURCE_MISSING, FWD_REASON_NO_ACCESS):
                    source_gone = True
                    break

            # Live progress: throttled edit of the status card so the user
            # sees 10% → 20% → 30% → … land on the same message rather
            # than a fresh card per group.
            await update_round_log(
                bot, user_id, phone, plan_label, round_num,
                total_groups=total, current=idx + 1,
                sent=sent_count, failed=fail_count,
            )

            if not immediate_send and idx < total - 1:
                delay = random.uniform(d_min, d_max) if use_random else d_base
                await asyncio.sleep(delay)

        if source_gone:
            await store.update({
                "forward_source_invalid": True,
                "forward_active":         False,
            })
            # Halt this account's loop so we don't spam failures next tick.
            active_map = await store.get("loop_active_accounts", {})
            if phone in active_map:
                active_map[phone] = False
                await store.set("loop_active_accounts", active_map)
            try:
                await Sched.remove_loop(user_id, phone)
            except Exception as _sched_exc:
                log.warning("[User %s][%s] remove_loop after source-missing failed: %s", user_id, phone, _sched_exc)
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        "🚨 <b>Forward source is gone.</b>\n\n"
                        "The saved channel post was deleted or your account can no longer "
                        "access it. I've stopped this account's broadcast loop to avoid "
                        "spamming groups with failures.\n\n"
                        "Use <b>✏️ Set Message → 📢 Forward From Channel</b> to save a new post."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            log.error("[User %s][%s] Forward source missing/unreachable — loop halted.", user_id, phone)
            await finalize_round_log(
                bot, user_id, phone, plan_label, round_num,
                total_groups=total, sent=sent_count, failed=fail_count,
                status="SOURCE GONE",
                interval_seconds=None, failures=failures,
            )
            _last_round_stats[key] = (sent_count, fail_count)
            return

        await finalize_round_log(
            bot, user_id, phone, plan_label, round_num,
            total_groups=total, sent=sent_count, failed=fail_count,
            status="COMPLETED",
            interval_seconds=interval_seconds, failures=failures,
        )
        _last_round_stats[key] = (sent_count, fail_count)
        log.info("[User %s][%s] ✅ Forward broadcast round #%d done. Sent=%d Failed=%d", user_id, phone, round_num, sent_count, fail_count)
        return

    # ── Normal text / media message branch ────────────────────────
    media_type  = settings.get("media_type")        # "photo" | "video" | … | None
    media_fpath = settings.get("media_file_path")   # local path | None

    if not tl_client:
        log.critical("[User %s][%s] No Telethon client — broadcast ABORTED. Check session.", user_id, phone)
        await finalize_round_log(
            bot, user_id, phone, plan_label, round_num,
            total_groups=total, sent=0, failed=0, status="NO CLIENT",
            interval_seconds=interval_seconds, failures=failures,
        )
        return

    mode_labels2 = {"selected": "Selected", "topic": "Topic", "both": "Both"}
    kind = media_type or "text"
    log.info(
        "[User %s][%s] %s broadcast round #%d started [Telethon][%s] (%d groups).",
        user_id, phone, kind.capitalize(), round_num, mode_labels2.get(bmode, bmode), total,
    )

    for idx, group in enumerate(groups):
        if not await _check_loop_active(store, phone):
            log.info("[User %s][%s] ⏹ Broadcast interrupted at %d/%d.", user_id, phone, idx + 1, total)
            await finalize_round_log(
                bot, user_id, phone, plan_label, round_num,
                total_groups=total, sent=sent_count, failed=fail_count,
                status="INTERRUPTED",
                interval_seconds=interval_seconds, failures=failures,
            )
            _last_round_stats[key] = (sent_count, fail_count)
            return

        gid      = group["id"]
        title    = group.get("title", str(gid))
        topic_id = group.get("topic_id")

        if not isinstance(gid, int) or gid == 0:
            log.warning("[User %s][%s] Skipping invalid group ID: %s", user_id, phone, gid)
            fail_count += 1
            failures.append((str(title), "invalid group ID"))
            await update_round_log(
                bot, user_id, phone, plan_label, round_num,
                total_groups=total, current=idx + 1,
                sent=sent_count, failed=fail_count,
            )
            continue

        ok, reason = await _send_safe_telethon(
            bot, user_id, phone, tl_client, gid, title, message,
            topic_id=topic_id,
            media_type=media_type,
            media_file_path=media_fpath,
        )
        if ok:
            sent_count += 1
            asyncio.create_task(_dashboard_record_send(True, phone=phone, group=title))
        else:
            fail_count += 1
            failures.append((title, reason or "send failed"))
            asyncio.create_task(_dashboard_record_send(False, phone=phone, group=title, error=reason or ""))

        # Live progress update on the same status card.
        await update_round_log(
            bot, user_id, phone, plan_label, round_num,
            total_groups=total, current=idx + 1,
            sent=sent_count, failed=fail_count,
        )

        if not immediate_send and idx < total - 1:
            delay = random.uniform(d_min, d_max) if use_random else d_base
            await asyncio.sleep(delay)

    await finalize_round_log(
        bot, user_id, phone, plan_label, round_num,
        total_groups=total, sent=sent_count, failed=fail_count,
        status="COMPLETED",
        interval_seconds=interval_seconds, failures=failures,
    )
    _last_round_stats[key] = (sent_count, fail_count)
    log.info("[User %s][%s] ✅ Broadcast round #%d done [Telethon]. Sent=%d Failed=%d", user_id, phone, round_num, sent_count, fail_count)


# ----------------------------------------------------------------
# Source resolution + native forwarding for the "Forward From Channel" flow.
#
# Native MTProto `ForwardMessagesRequest` is the gold standard — it
# preserves every entity, premium/custom emoji, caption, media item,
# album grouping, and reply target without any client-side text
# reconstruction. We use it for both single posts and full albums.
# ----------------------------------------------------------------

# Reasons returned by the forwarding stack. "source missing" is the
# sentinel the broadcast loop watches for to stop and notify the owner.
FWD_REASON_SOURCE_MISSING = "source missing"
FWD_REASON_NO_ACCESS      = "source not accessible"
FWD_REASON_TOPIC_MISSING  = "topic missing"


async def _resolve_forward_source(
    tl_client: TelegramClient, channel_id: int, message_id: int,
) -> tuple[Any, list[int] | None, str]:
    """Resolve a forwarded source to ``(entity, album_ids, status)``.

    - ``entity``     : Telethon entity for the source channel, or ``None``
                       if the account can't access it.
    - ``album_ids``  : Ordered list of message IDs to forward together.
                       Single-message posts return ``[message_id]``; albums
                       return all sibling IDs in the same media group.
                       ``None`` when the resolution itself failed.
    - ``status``     : ``"ok"`` / ``"no_access"`` / ``"message_missing"``
                       / ``"error:<ExceptionName>"``.
    """
    # 1. Resolve the channel entity.
    try:
        entity = await tl_client.get_entity(channel_id)
    except (ChannelPrivateError, ChannelInvalidError, ValueError):
        return None, None, "no_access"
    except FloodWaitError as e:
        await asyncio.sleep(min(e.seconds + 2, 60))
        try:
            entity = await tl_client.get_entity(channel_id)
        except Exception:
            return None, None, "no_access"
    except Exception as e:
        return None, None, f"error:{type(e).__name__}"

    # 2. Verify the message exists and detect album/grouped_id.
    try:
        msg = await tl_client.get_messages(entity, ids=message_id)
    except (MessageIdInvalidError, MessageIdsEmptyError):
        return entity, None, "message_missing"
    except Exception as e:
        return entity, None, f"error:{type(e).__name__}"
    if not msg:
        return entity, None, "message_missing"

    grouped_id = getattr(msg, "grouped_id", None)
    if not grouped_id:
        return entity, [message_id], "ok"

    # 3. Pull ±9 IDs around the target and collect the full album.
    # Telegram albums are at most 10 items, contiguous in message-id space.
    nearby_ids = list(range(max(1, message_id - 9), message_id + 10))
    try:
        nearby = await tl_client.get_messages(entity, ids=nearby_ids)
    except Exception:
        return entity, [message_id], "ok"
    album_ids = sorted(
        m.id for m in nearby
        if m is not None and getattr(m, "grouped_id", None) == grouped_id
    )
    return entity, album_ids or [message_id], "ok"


async def _forward_safe_telethon(
    bot: Bot, user_id: int, phone: str,
    client: TelegramClient, chat_id: int, title: str,
    message_ids: int | list[int], from_peer: Any, topic_id: int | None = None,
    drop_author: bool = True,
) -> tuple[bool, str | None]:
    """Forward a channel post (or full album) via Telethon with topic support.

    ``message_ids`` may be a single ID or a list of IDs in the same media
    group; Telegram groups them on the destination automatically.

    Returns ``(True, None)`` on success or ``(False, reason)`` on failure.
    No intra-loop log-group chatter — failures are aggregated and posted
    by the caller as a single failure report at round end.
    """
    ids = [message_ids] if isinstance(message_ids, int) else list(message_ids)
    if not ids:
        return False, FWD_REASON_SOURCE_MISSING

    to_peer    = await client.get_input_entity(chat_id)
    from_input = await client.get_input_entity(from_peer)

    async def _do_forward():
        return await client(ForwardMessagesRequest(
            from_peer=from_input,
            id=ids,
            to_peer=to_peer,
            top_msg_id=topic_id,
            drop_author=drop_author,
            random_id=[random.randint(0, 2 ** 63) for _ in ids],
        ))

    try:
        await _do_forward()
        log.info(
            "  → [FWD] Forwarded %d msg(s) to '%s' (%s) topic=%s",
            len(ids), title, chat_id, topic_id,
        )
        return True, None

    except FloodWaitError as e:
        wait = min(e.seconds + 2, 120)
        log.warning("  ⏳ [FWD] FloodWait for '%s' — sleeping %ds (raw=%ds)", title, wait, e.seconds)
        await asyncio.sleep(wait)
        try:
            await _do_forward()
            return True, None
        except Exception as retry_err:
            log.error("  ❌ [FWD] Retry failed for '%s': %s", title, retry_err)
            return False, f"flood wait {e.seconds}s, retry failed"

    except (MessageIdInvalidError, MessageIdsEmptyError):
        log.error("  ❌ [FWD] Source message(s) gone for '%s'.", title)
        return False, FWD_REASON_SOURCE_MISSING
    except ChannelPrivateError:
        # Could be either source or destination; the broadcast loop is
        # iterating per-destination, so treat as destination by default.
        log.error("  ❌ [FWD] '%s' is private or user was removed.", title)
        return False, "private group"
    except ChannelInvalidError:
        log.error("  ❌ [FWD] Source channel invalid/inaccessible for '%s'.", title)
        return False, FWD_REASON_NO_ACCESS
    except ChatWriteForbiddenError:
        log.error("  ❌ [FWD] No write permission for '%s'.", title)
        return False, "messaging off"
    except UserBannedInChannelError:
        log.error("  ❌ [FWD] User banned in '%s'.", title)
        return False, "user banned"

    except (ConnectionError, OSError) as e:
        log.warning("  ⚠️ [FWD] Connection lost during forward to '%s': %s — attempting reconnect", title, type(e).__name__)
        try:
            if not client.is_connected():
                await client.connect()
            await _do_forward()
            log.info("  → [FWD] Reconnect+retry succeeded for '%s'", title)
            return True, None
        except Exception as re_err:
            log.error("  ❌ [FWD] Reconnect+retry failed for '%s': %s", title, re_err)
            return False, f"connection error ({type(e).__name__})"

    except Exception as e:
        err_str = str(e).lower()
        if any(s in err_str for s in (
            "message_id_invalid", "message id is invalid",
            "message_ids_empty", "messageidsempty",
        )):
            return False, FWD_REASON_SOURCE_MISSING
        if "topic" in err_str and any(s in err_str for s in (
            "not found", "invalid", "closed", "deleted",
        )):
            return False, FWD_REASON_TOPIC_MISSING
        log.error("  ❌ [FWD] Error for '%s' (%s): %s", title, chat_id, e)
        return False, f"{type(e).__name__}: {str(e)[:80]}"


async def _send_safe_telethon(
    bot: Bot, user_id: int, phone: str,
    client: TelegramClient, chat_id: int, title: str, text: str,
    topic_id: int | None = None,
    media_type: str | None = None,
    media_file_path: str | None = None,
) -> tuple[bool, str | None]:
    """Send via Telethon user account. Returns ``(True, None)`` on success
    or ``(False, reason)`` on failure. No intra-loop log-group chatter —
    failures are aggregated and posted by the caller as a single failure
    report at round end.

    When *media_type* and *media_file_path* are provided the function
    sends a file (photo / video / animation / document) with *text* as
    the caption instead of a plain text message.
    """
    # Strip <tg-emoji> tags — Telethon's HTML parser doesn't support them.
    clean_text = _strip_tg_emoji_for_telethon(text) if text else text

    kwargs: dict = {"parse_mode": "html"}
    if topic_id:
        kwargs["reply_to"] = topic_id

    async def _do_send():
        if media_type and media_file_path:
            import os
            if not os.path.isfile(media_file_path):
                raise FileNotFoundError(f"Media file missing: {media_file_path}")
            force_doc = media_type == "document"
            await client.send_file(
                chat_id, media_file_path,
                caption=clean_text or None,
                force_document=force_doc,
                **kwargs,
            )
        else:
            await client.send_message(chat_id, clean_text, **kwargs)

    try:
        await _do_send()
        log.info("  → [TL] Sent %s to '%s' (%s) topic=%s",
                 media_type or "text", title, chat_id, topic_id)
        return True, None

    except FloodWaitError as e:
        wait = min(e.seconds + 2, 120)
        log.warning("  ⏳ [TL] FloodWait for '%s' — sleeping %ds (raw=%ds)", title, wait, e.seconds)
        await asyncio.sleep(wait)
        try:
            await _do_send()
            return True, None
        except Exception as retry_err:
            log.error("  ❌ [TL] Retry failed for '%s': %s", title, retry_err)
            return False, f"flood wait {e.seconds}s, retry failed"

    except ChatWriteForbiddenError:
        log.error("  ❌ [TL] No write permission for '%s'.", title)
        return False, "messaging off"
    except UserBannedInChannelError:
        log.error("  ❌ [TL] User banned in '%s'.", title)
        return False, "user banned"
    except ChannelPrivateError:
        log.error("  ❌ [TL] '%s' is private or user was removed.", title)
        return False, "private group"

    except (ConnectionError, OSError) as e:
        log.warning("  ⚠️ [TL] Connection lost during send to '%s': %s — attempting reconnect", title, type(e).__name__)
        try:
            if not client.is_connected():
                await client.connect()
            await _do_send()
            log.info("  → [TL] Reconnect+retry succeeded for '%s'", title)
            return True, None
        except Exception as re_err:
            log.error("  ❌ [TL] Reconnect+retry failed for '%s': %s", title, re_err)
            return False, f"connection error ({type(e).__name__})"

    except Exception as e:
        log.error("  ❌ [TL] Error for '%s' (%s): %s", title, chat_id, e)
        return False, f"{type(e).__name__}: {str(e)[:80]}"


# DEPRECATED — Bot API sending removed from broadcast engine (Fix #2: Dual Transport)
# Function kept for backward compatibility but no longer called by broadcast_once()
async def _send_safe_bot(
    bot_obj: Bot, user_id: int, phone: str,
    chat_id: int, title: str, text: str,
    topic_id: int | None = None,
) -> bool:
    """Send via bot token with auto-retry on FloodWait. Returns True on success."""
    kwargs: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if topic_id:
        kwargs["message_thread_id"] = topic_id
    try:
        await bot_obj.send_message(**kwargs)
        log.info("  → [Bot] Sent to '%s' (%s) topic=%s", title, chat_id, topic_id)
        return True
    except TelegramRetryAfter as e:
        wait = e.retry_after + 1
        await _send_to_fetch_group(bot_obj, user_id, phone, f"⏳ FloodWait {wait}s for '<b>{title}</b>'")
        log.warning("  ⏳ [Bot] FloodWait for '%s' — sleeping %ds", title, wait)
        await asyncio.sleep(wait)
        try:
            await bot_obj.send_message(**kwargs)
            return True
        except Exception as retry_err:
            await _send_to_fetch_group(bot_obj, user_id, phone, f"❌ Retry failed for '<b>{title}</b>': {retry_err}")
            log.error("  ❌ [Bot] Retry failed for '%s': %s", title, retry_err)
            return False
    except TelegramForbiddenError:
        await _send_to_fetch_group(bot_obj, user_id, phone, f"🚫 Bot removed from '<b>{title}</b>'")
        log.error("  ❌ [Bot] Removed from '%s' (%s).", title, chat_id)
        return False
    except TelegramBadRequest as e:
        if topic_id:
            await _send_to_fetch_group(bot_obj, user_id, phone, f"⚠️ Topic fail for '<b>{title}</b>' (topic={topic_id}): {e}")
            log.warning("  ⚠️ [Bot] Topic send failed for '%s', retrying without: %s", title, e)
            try:
                await bot_obj.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
                return True
            except Exception as fb_err:
                await _send_to_fetch_group(bot_obj, user_id, phone, f"❌ Fallback failed for '<b>{title}</b>': {fb_err}")
                log.error("  ❌ [Bot] Fallback also failed for '%s': %s", title, fb_err)
                return False
        else:
            await _send_to_fetch_group(bot_obj, user_id, phone, f"❌ BadRequest for '<b>{title}</b>': {e}")
            log.error("  ❌ [Bot] BadRequest for '%s': %s", title, e)
            return False
    except Exception as e:
        await _send_to_fetch_group(bot_obj, user_id, phone, f"❌ Error for '<b>{title}</b>': {e}")
        log.error("  ❌ [Bot] Error for '%s' (%s): %s", title, chat_id, e)
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STARTUP RECOVERY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def recover(bot: Bot) -> None:
    """Reconnect saved Telethon accounts and resume schedules for ALL users.
    Broadcast loops are NOT auto-resumed — user must manually press Start Loop."""
    for uid in UserManager.get_all_user_ids():
        account_mgr = UserManager.get_account_mgr(uid)
        store = UserManager.get_store(uid)
        await account_mgr.reconnect_all()

        # Force all broadcast loops to remain stopped after restart
        await store.set("loop_active", False)
        # FIXED — also reset per-account loop state map
        await store.set("loop_active_accounts", {})
        await store.set("forward_active", False)
        log.info("[User %s] Recovery: loop states reset (manual restart required).", uid)

        settings = await store.all()
        for sched in settings.get("schedules", []):
            if sched.get("enabled", True):
                await Sched.add_schedule(bot, uid, sched)

        # Pre-cache forward channel entity if forward_mode is active
        if settings.get("forward_mode") and settings.get("forward_channel_id"):
            tl_client = await account_mgr.get_active_client()
            if tl_client:
                try:
                    entity = await tl_client.get_entity(settings["forward_channel_id"])
                    _forward_entities[uid] = entity
                    log.info("[User %s] Recovery: forward entity cached for channel %s.", uid, settings["forward_channel_id"])
                except Exception as e:
                    log.warning("[User %s] Recovery: could not cache forward entity: %s", uid, e)

    log.info("Recovery done. Active jobs: %s", [j.id for j in Sched.get().get_jobs()])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _normalize_chat_id(raw: str) -> int | None:
    """Normalize a chat ID to Bot API format (-100...).
    Accepts '-100123456789' (returned as-is) or '123456789' (prepends -100).
    Returns int or None on failure."""
    raw = raw.strip()
    try:
        val = int(raw)
    except ValueError:
        return None
    s = str(val)
    if s.startswith("-100"):
        return val
    # Positive raw ID → prepend -100
    if val > 0:
        return int(f"-100{val}")
    # Negative but not -100... (e.g. old-style -12345) → prepend -100 to abs
    return int(f"-100{abs(val)}")


async def _deny(target: Message | CallbackQuery, user_id: int) -> None:
    """Reject anyone who isn't the configured owner."""
    text = "❌ <b>You are not authorized to use this bot.</b>\nContact the owner."
    if isinstance(target, CallbackQuery):
        plain = text.replace("<b>", "").replace("</b>", "")
        await target.answer(plain, show_alert=True)
    else:
        await target.answer(text, parse_mode="HTML")


async def _fetch_all_groups_unified(client: TelegramClient) -> list[dict]:
    """
    Fetch ALL groups and their topics into a unified structure:
    {"id": int, "title": str, "topic_id": int | None, "is_forum": bool}

    ``Chat`` / ``Channel`` / ``GetForumTopicsRequest`` are imported at
    the top of the module; don't re-import them here.
    """
    unified: list[dict] = []

    try:
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if isinstance(entity, Chat):
                # Normal group
                bot_api_id = -int(entity.id)
                unified.append({
                    "id": bot_api_id,
                    "title": dialog.name,
                    "topic_id": None,
                    "topic_title": None,
                    "is_forum": False
                })
            elif isinstance(entity, Channel):
                if getattr(entity, "broadcast", False):
                    continue  # skip channels
                if getattr(entity, "megagroup", False):
                    bot_api_id = int(f"-100{entity.id}")
                    is_forum = getattr(entity, "forum", False)

                    if is_forum:
                        try:
                            # Fetch topics for forum
                            topics_req = await client(GetForumTopicsRequest(
                                channel=entity,
                                offset_date=None,
                                offset_id=0,
                                offset_topic=0,
                                limit=100,
                            ))
                            for topic in topics_req.topics:
                                # Create entry for each topic
                                unified.append({
                                    "id": bot_api_id,
                                    "title": dialog.name,
                                    "topic_id": topic.id,
                                    "topic_title": getattr(topic, "title", str(topic.id)),
                                    "is_forum": True
                                })
                        except Exception as e:
                            log.warning("[UnifiedFetch] Failed to fetch topics for %s: %s", bot_api_id, e)
                            # Fallback as normal group if topic fetch fails
                            unified.append({
                                "id": bot_api_id,
                                "title": dialog.name,
                                "topic_id": None,
                                "topic_title": None,
                                "is_forum": True
                            })
                    else:
                        # Normal supergroup
                        unified.append({
                            "id": bot_api_id,
                            "title": dialog.name,
                            "topic_id": None,
                            "topic_title": None,
                            "is_forum": False
                        })
    except Exception as e:
        log.error("[UnifiedFetch] Error: %s", e)

    return unified


async def _sync_groups_for_user(
    user_id: int,
    account_mgr: "AccountManager",
    store: "Storage",
) -> int:
    """Refresh ``auto_groups`` in the user's store from the active account.

    Called on login success, on 2FA success, and from the real-time
    ``ChatAction`` listener whenever the user joins or is added to a
    group. Returns the number of unified entries stored (0 on failure).
    Never raises — broadcast loops must not crash if a resync fails.
    """
    try:
        client = await account_mgr.get_active_client()
        if client is None:
            log.debug("[SyncGroups][User %s] No active client; skipped.", user_id)
            return 0
        unified = await _fetch_all_groups_unified(client)
        await store.set("auto_groups", unified)
        log.info(
            "[SyncGroups][User %s] auto_groups refreshed: %d entries",
            user_id, len(unified),
        )
        return len(unified)
    except Exception as exc:
        log.warning("[SyncGroups][User %s] resync failed: %s", user_id, exc)
        return 0


def kb_log_forwarding_menu() -> InlineKeyboardMarkup:
    """Inline keyboard for the Log Forwarding control panel.

    Surfaces the four lf:* callbacks (set group, start, stop, status)
    plus a back button. All icons come from the centralized emoji DB.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [create_button("Set Log Group",       "mail",    "lf:set_group", style="PRIMARY")],
        [
            create_button("Start",  "rocket", "lf:start",  style="SUCCESS"),
            create_button("Stop",   "cross",  "lf:stop",   style="DANGER"),
        ],
        [create_button("Status",              "info",    "lf:status",    style="INFO")],
        [create_button("Back",                "back",    "m:main",       style="SECONDARY")],
    ])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MEDIA / CAPTION / PREMIUM-EMOJI HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import re as _re_main

_TG_EMOJI_RE = _re_main.compile(r'<tg-emoji[^>]*>([^<]*)</tg-emoji>', _re_main.IGNORECASE)


def _caption_to_html(message: Message) -> str:
    """Reconstruct an HTML caption from a Message that carries media.

    aiogram's ``message.html_text`` only covers ``.text`` — for captions
    we must build the HTML ourselves from ``.caption`` + ``.caption_entities``.
    The result is safe for ``parse_mode='HTML'`` and preserves bold, italic,
    links, and ``<tg-emoji>`` (premium/custom emoji) entities.
    """
    caption = message.caption
    if not caption:
        return ""
    entities = message.caption_entities
    if not entities:
        from html import escape
        return escape(caption)
    # Use aiogram's built-in HTML unparser
    try:
        from aiogram.utils.text_decorations import html_decoration
        return html_decoration.unparse(caption, entities)
    except Exception:
        from html import escape
        return escape(caption)


def _strip_tg_emoji_for_telethon(html_text: str) -> str:
    """Strip ``<tg-emoji>`` tags, keeping their fallback character.

    Telethon's HTML parser does not recognise ``<tg-emoji>`` — sending
    the tag verbatim causes a parse error or silent entity corruption.
    Stripping to the fallback char guarantees a clean send while the
    emoji remains human-readable.
    """
    if not html_text:
        return html_text
    return _TG_EMOJI_RE.sub(r'\1', html_text)


def _valid_time(t: str) -> bool:
    try:
        h, m = t.split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
    except Exception:
        return False


def _uid() -> str:
    return str(uuid.uuid4())[:8]


async def _edit_or_send(cb: CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    """Edit callback message, falling back to a new message on error."""
    if cb.message is None:
        # Message was deleted; send a fresh one to the chat
        await cb.bot.send_message(cb.from_user.id, text, parse_mode="HTML", reply_markup=kb)
        return
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)


async def get_dashboard_text(user_id: int) -> str:
    """Generate the dynamic dashboard text."""
    store = UserManager.get_store(user_id)
    account_mgr = UserManager.get_account_mgr(user_id)

    accounts = account_mgr.get_accounts()
    total_accounts = len(accounts)

    active_account = account_mgr.get_active_account()
    active_phone = active_account["phone"] if active_account else "None"

    settings = await store.all()
    selected_groups = settings.get("selected_groups", [])
    topic_groups = settings.get("topic_groups", [])

    total_groups = len(selected_groups) + len(topic_groups)
    total_topics = sum(len(g.get("topics", [])) for g in topic_groups)

    is_running = await _check_loop_active(store, active_phone) if active_phone != "None" else False
    loop_status = "🟢 Running" if is_running else "🔴 Stopped"

    if active_phone != "None":
        key = (user_id, active_phone)
        last_stats = _last_round_stats.get(key)
        if last_stats:
            sent, failed = last_stats
            stats_text = f"{sent} sent / {failed} failed"
        else:
            stats_text = "N/A (Not run yet)"
    else:
        stats_text = "N/A"

    # Premium custom-emoji rendering on message headers. Shows animated
    # icons to Telegram-Premium users; non-premium users see the plain
    # fallback character automatically.
    return (
        f"{premium_emoji('chart')} <b>CONTROL DASHBOARD</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji('profile')} <b>Active Account:</b> {active_phone}\n"
        f"{premium_emoji('phone')} <b>Total Accounts:</b> {total_accounts}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji('package')} <b>Selected Groups:</b> {total_groups}\n"
        f"{premium_emoji('pin')} <b>Selected Topics:</b> {total_topics}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji('refresh')} <b>Loop Status:</b> {loop_status}\n"
        f"{premium_emoji('stats')} <b>Last Round:</b> {stats_text}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Select an option below to manage your bot:</i>"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ROUTER  +  ALL HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
router = Router()

# ── /start & main menu ────────────────────────────────────────────
@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    uid = message.from_user.id
    if not has_access(uid):
        await _deny(message, uid)
        return
    eff = _effective_uid(uid)
    text = await get_dashboard_text(eff)
    await message.answer(text, reply_markup=_get_main_kb(uid))


# ── /help ─────────────────────────────────────────────────────────
@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    uid = message.from_user.id
    if not has_access(uid):
        await _deny(message, uid); return
    await message.answer(
        "📋 <b>Bot User Guidance</b>\n\n"
        "Click the button below to read all features and functions of this bot.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [create_button("Read Full Guide", "receipt", url="https://telegra.ph/Ads-bot-guidance-02-25", style="PRIMARY")],
        ]),
    )


# ── /admins  (owner-only) ─────────────────────────────────────────
@router.message(Command("admins"))
async def cmd_admins(message: Message) -> None:
    uid = message.from_user.id
    if not is_owner(uid):
        await _deny(message, uid); return
    text, kb = _build_admin_panel()
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


def _build_admin_panel() -> tuple[str, InlineKeyboardMarkup]:
    """Build the Admin Panel text + keyboard listing all admins."""
    lines = ["👥 <b>Admin Panel</b>\n", "━━━━━━━━━━━━━━━━━━━━\n"]
    if not ADMIN_IDS:
        lines.append("<i>No admins configured.</i>\n")
        lines.append("Add admin IDs to <code>ADMIN_IDS</code> in config.py.\n")
    else:
        for i, aid in enumerate(ADMIN_IDS, 1):
            has_data = (USER_DATA_DIR / str(aid)).exists()
            status = "🟢 Active" if has_data else "⚪ No data yet"
            lines.append(f"{i}. <code>{aid}</code> — {status}\n")
    lines.append(f"\n👑 <b>Owner:</b> <code>{OWNER_ID}</code>")
    if OWNER_ID in _owner_viewing_as:
        lines.append(f"\n🔄 <b>Viewing as:</b> <code>{_owner_viewing_as[OWNER_ID]}</code>")
    prem_count = PremiumManager.get_active_count()
    fj_count = len(ForceJoinManager.get_channels()) + len(FORCE_JOIN_CHANNELS)
    lines.append(f"\n\n⭐ <b>Premium Users:</b> {prem_count} active")
    lines.append(f"\n🔗 <b>Force Join Channels:</b> {fj_count}")

    buttons: list[list[InlineKeyboardButton]] = []
    for aid in ADMIN_IDS:
        buttons.append([
            create_button(f"View {aid}", "chart", f"adm:view:{aid}", style="INFO"),
            create_button(f"Switch to {aid}", "refresh", f"adm:switch:{aid}", style="PRIMARY"),
        ])
    buttons.append([
        create_button("Premium", "star", "adm:premium", style="SUCCESS"),
        create_button("Force Join", "link", "adm:forcejoin", style="INFO"),
    ])
    buttons.append([
        create_button("Broadcast", "rocket", "adm:broadcast", style="PRIMARY"),
    ])
    if OWNER_ID in _owner_viewing_as:
        buttons.append([create_button("Back to Owner Data", "back", "m:admin_back", style="DANGER")])
    buttons.append([create_button("Back to Menu", "back", "m:main", style="SECONDARY")])
    return "".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "m:admin_panel")
async def cb_admin_panel(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    text, kb = _build_admin_panel()
    await _edit_or_send(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:view:"))
async def cb_admin_view(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    target_uid = int(cb.data.split(":")[2])
    if target_uid not in ADMIN_IDS:
        await cb.answer("❌ Not a valid admin.", show_alert=True); return
    text = await get_dashboard_text(target_uid)
    text = f"👤 <b>Admin {target_uid} Dashboard</b>\n━━━━━━━━━━━━━━━━━━━━\n\n" + text
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [create_button(f"Switch to {target_uid}", "refresh", f"adm:switch:{target_uid}", style="PRIMARY")],
        [create_button("Back to Admin Panel", "back", "m:admin_panel", style="SECONDARY")],
    ])
    await _edit_or_send(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:switch:"))
async def cb_admin_switch(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    target_uid = int(cb.data.split(":")[2])
    if target_uid not in ADMIN_IDS:
        await cb.answer("❌ Not a valid admin.", show_alert=True); return
    _owner_viewing_as[uid] = target_uid
    log.info("[Owner %s] Now viewing as admin %s", uid, target_uid)
    text = await get_dashboard_text(target_uid)
    text = f"🔄 <b>Now managing Admin {target_uid}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n" + text
    await _edit_or_send(cb, text, _get_main_kb(uid))
    await cb.answer(f"Switched to admin {target_uid}")


@router.callback_query(F.data == "m:admin_back")
async def cb_admin_back(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    _owner_viewing_as.pop(uid, None)
    log.info("[Owner %s] Returned to own data", uid)
    text = await get_dashboard_text(uid)
    await _edit_or_send(cb, text, _get_main_kb(uid))
    await cb.answer("Back to owner data")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PREMIUM MANAGEMENT  (admin panel inline buttons)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_duration(text: str) -> tuple[int, str] | None:
    """Parse duration string like '7d', '3h', '1d12h' etc.
    Returns (total_seconds, human_label) or None."""
    import re
    text = text.strip().lower()
    pattern = re.findall(r'(\d+)\s*([dhm])', text)
    if not pattern:
        try:
            days = int(text)
            return days * 86400, f"{days}d"
        except ValueError:
            return None
    total = 0
    label_parts = []
    for val, unit in pattern:
        v = int(val)
        if unit == 'd':
            total += v * 86400
            label_parts.append(f"{v}d")
        elif unit == 'h':
            total += v * 3600
            label_parts.append(f"{v}h")
        elif unit == 'm':
            total += v * 60
            label_parts.append(f"{v}m")
    if total <= 0:
        return None
    return total, "".join(label_parts)


def _build_premium_panel() -> tuple[str, InlineKeyboardMarkup]:
    users = PremiumManager.get_all()
    active = [u for u in users if u["active"]]
    expired = [u for u in users if not u["active"]]
    lines = ["⭐ <b>Premium Management</b>\n", "━━━━━━━━━━━━━━━━━━━━\n"]
    lines.append(f"Active: <b>{len(active)}</b> | Expired: <b>{len(expired)}</b>\n\n")
    if active:
        lines.append("<b>Active Users:</b>\n")
        for u in active[:20]:
            exp = datetime.fromisoformat(u["expires_at"])
            remaining = exp - datetime.utcnow()
            days = remaining.days
            hours = remaining.seconds // 3600
            lines.append(f"  <code>{u['user_id']}</code> — {days}d {hours}h left ({u.get('plan', '?')})\n")
        if len(active) > 20:
            lines.append(f"  <i>... and {len(active) - 20} more</i>\n")
    else:
        lines.append("<i>No active premium users.</i>\n")
    lines.append(f"\n<b>Plans:</b>\n")
    for p in PREMIUM_PLANS:
        lines.append(f"  {p['label']} — ${p['price']}\n")
    buttons = [
        [create_button("Grant Premium", "star", "prem:grant", style="SUCCESS"),
         create_button("Revoke Premium", "cross", "prem:revoke_menu", style="DANGER")],
        [create_button("List All Users", "list", "prem:list", style="INFO")],
        [create_button("Quick Grant Plans", "rocket", "prem:plans", style="PRIMARY")],
        [create_button("Back to Admin Panel", "back", "m:admin_panel", style="SECONDARY")],
    ]
    return "".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "adm:premium")
async def cb_premium_panel(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    text, kb = _build_premium_panel()
    await _edit_or_send(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data == "prem:grant")
async def cb_premium_grant_start(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    await state.set_state(S.premium_grant_uid)
    text = ("📝 <b>Grant Premium</b>\n\n"
            "Send the <b>user ID</b> you want to grant premium to.\n\n"
            "Example: <code>123456789</code>")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [create_button("Cancel", "back", "adm:premium", style="SECONDARY")],
    ])
    await _edit_or_send(cb, text, kb)
    await cb.answer()


@router.message(S.premium_grant_uid)
async def on_premium_grant_uid(msg: Message, state: FSMContext) -> None:
    uid = msg.from_user.id
    if not is_owner(uid):
        return
    text = msg.text.strip() if msg.text else ""
    try:
        target_uid = int(text)
    except ValueError:
        await msg.reply("❌ Invalid user ID. Send a numeric user ID.")
        return
    await state.update_data(premium_target_uid=target_uid)
    await state.set_state(S.premium_grant_dur)
    await msg.reply(
        f"✅ User: <code>{target_uid}</code>\n\n"
        "Now send the <b>duration</b>:\n"
        "  <code>7d</code> = 7 days\n"
        "  <code>3h</code> = 3 hours\n"
        "  <code>1d12h</code> = 1 day 12 hours\n"
        "  <code>30</code> = 30 days\n\n"
        "Or tap a quick plan below:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [create_button(f"{p['label']} (${p['price']})", "star",
                           f"prem:quick:{p['id']}", style="SUCCESS") for p in PREMIUM_PLANS],
            [create_button("Cancel", "back", "adm:premium", style="SECONDARY")],
        ]),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("prem:quick:"))
async def cb_premium_quick_plan(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    plan_id = cb.data.split(":")[2]
    plan = next((p for p in PREMIUM_PLANS if p["id"] == plan_id), None)
    if not plan:
        await cb.answer("❌ Unknown plan.", show_alert=True); return
    data = await state.get_data()
    target_uid = data.get("premium_target_uid")
    if not target_uid:
        await cb.answer("❌ No user selected. Start over.", show_alert=True); return
    duration_secs = plan["days"] * 86400
    entry = await PremiumManager.grant(target_uid, duration_secs, plan["label"], uid)
    await state.clear()
    text = (f"✅ <b>Premium Granted!</b>\n\n"
            f"User: <code>{target_uid}</code>\n"
            f"Plan: {plan['label']} (${plan['price']})\n"
            f"Expires: {entry['expires_at'][:19]}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [create_button("Back to Premium", "back", "adm:premium", style="SECONDARY")],
    ])
    await _edit_or_send(cb, text, kb)
    await cb.answer("Premium granted!")


@router.message(S.premium_grant_dur)
async def on_premium_grant_dur(msg: Message, state: FSMContext) -> None:
    uid = msg.from_user.id
    if not is_owner(uid):
        return
    text = msg.text.strip() if msg.text else ""
    parsed = _parse_duration(text)
    if not parsed:
        await msg.reply("❌ Invalid duration. Use: <code>7d</code>, <code>3h</code>, <code>1d12h</code>",
                        parse_mode="HTML")
        return
    duration_secs, label = parsed
    data = await state.get_data()
    target_uid = data.get("premium_target_uid")
    if not target_uid:
        await msg.reply("❌ No user selected. Start over with /premium.")
        await state.clear()
        return
    entry = await PremiumManager.grant(target_uid, duration_secs, label, uid)
    await state.clear()
    await msg.reply(
        f"✅ <b>Premium Granted!</b>\n\n"
        f"User: <code>{target_uid}</code>\n"
        f"Duration: {label}\n"
        f"Expires: {entry['expires_at'][:19]}",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "prem:plans")
async def cb_premium_plans(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    await state.set_state(S.premium_grant_uid)
    text = ("📋 <b>Quick Grant — Select Plan</b>\n\n"
            "First, send the <b>user ID</b> to grant premium to:")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [create_button("Cancel", "back", "adm:premium", style="SECONDARY")],
    ])
    await _edit_or_send(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data == "prem:revoke_menu")
async def cb_premium_revoke_menu(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    active = [u for u in PremiumManager.get_all() if u["active"]]
    if not active:
        await cb.answer("No active premium users.", show_alert=True); return
    buttons = []
    for u in active[:30]:
        buttons.append([create_button(
            f"Revoke {u['user_id']}", "cross",
            f"prem:revoke:{u['user_id']}", style="DANGER"
        )])
    buttons.append([create_button("Back to Premium", "back", "adm:premium", style="SECONDARY")])
    text = "🗑 <b>Revoke Premium</b>\n\nSelect a user to revoke:"
    await _edit_or_send(cb, text, InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()


@router.callback_query(F.data.startswith("prem:revoke:"))
async def cb_premium_revoke(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    target_uid = int(cb.data.split(":")[2])
    await PremiumManager.revoke(target_uid)
    text, kb = _build_premium_panel()
    text = f"✅ Premium revoked for <code>{target_uid}</code>.\n\n" + text
    await _edit_or_send(cb, text, kb)
    await cb.answer("Premium revoked!")


@router.callback_query(F.data == "prem:list")
async def cb_premium_list(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    users = PremiumManager.get_all()
    if not users:
        await cb.answer("No premium users.", show_alert=True); return
    lines = ["📋 <b>All Premium Users</b>\n", "━━━━━━━━━━━━━━━━━━━━\n\n"]
    for u in users:
        status = "🟢" if u["active"] else "🔴"
        exp = u.get("expires_at", "?")[:19]
        lines.append(f"{status} <code>{u['user_id']}</code> — {u.get('plan', '?')} — expires {exp}\n")
    buttons = [[create_button("Back to Premium", "back", "adm:premium", style="SECONDARY")]]
    await _edit_or_send(cb, "".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FORCE JOIN MANAGEMENT  (admin panel inline buttons)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_forcejoin_panel() -> tuple[str, InlineKeyboardMarkup]:
    channels = ForceJoinManager.get_channels()
    config_channels = [{"channel": c, "title": str(c), "added_by": 0} for c in FORCE_JOIN_CHANNELS
                       if not any(str(c) == str(x["channel"]) for x in channels)]
    all_ch = channels + config_channels
    lines = ["🔗 <b>Force Join Management</b>\n", "━━━━━━━━━━━━━━━━━━━━\n\n"]
    if all_ch:
        for i, ch in enumerate(all_ch, 1):
            source = "config" if ch.get("added_by", 0) == 0 else "dynamic"
            lines.append(f"{i}. <code>{ch['channel']}</code> — {ch.get('title', '?')} ({source})\n")
    else:
        lines.append("<i>No force join channels configured.</i>\n")
    lines.append("\nUsers must join all listed channels before using the bot.\n")
    buttons = [
        [create_button("Add Channel", "link", "fj:add", style="SUCCESS"),
         create_button("Remove Channel", "cross", "fj:remove_menu", style="DANGER")],
        [create_button("Back to Admin Panel", "back", "m:admin_panel", style="SECONDARY")],
    ]
    return "".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "adm:forcejoin")
async def cb_forcejoin_panel(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    text, kb = _build_forcejoin_panel()
    await _edit_or_send(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data == "fj:add")
async def cb_forcejoin_add(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    await state.set_state(S.fj_add_channel)
    text = ("📝 <b>Add Force Join Channel</b>\n\n"
            "Send the channel <b>username</b> (with @) or <b>channel ID</b>.\n\n"
            "Examples:\n"
            "  <code>@mychannel</code>\n"
            "  <code>-1001234567890</code>\n\n"
            "Make sure the bot is an admin of the channel.")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [create_button("Cancel", "back", "adm:forcejoin", style="SECONDARY")],
    ])
    await _edit_or_send(cb, text, kb)
    await cb.answer()


@router.message(S.fj_add_channel)
async def on_fj_add_channel(msg: Message, state: FSMContext) -> None:
    uid = msg.from_user.id
    if not is_owner(uid):
        return
    text = msg.text.strip() if msg.text else ""
    if not text:
        await msg.reply("❌ Empty input. Send channel username or ID.")
        return
    channel: str | int = text
    title = text
    if text.lstrip("-").isdigit():
        channel = int(text)
        title = f"Channel {text}"
    try:
        chat = await msg.bot.get_chat(channel)
        title = chat.title or title
    except Exception:
        pass
    added = await ForceJoinManager.add_channel(channel, title, uid)
    await state.clear()
    if added:
        await msg.reply(f"✅ Added force join channel: <b>{title}</b> (<code>{channel}</code>)",
                        parse_mode="HTML")
    else:
        await msg.reply(f"⚠️ Channel <code>{channel}</code> already in the list.", parse_mode="HTML")


@router.callback_query(F.data == "fj:remove_menu")
async def cb_forcejoin_remove_menu(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    channels = ForceJoinManager.get_channels()
    if not channels:
        await cb.answer("No dynamic channels to remove.", show_alert=True); return
    buttons = []
    for ch in channels:
        buttons.append([create_button(
            f"Remove {ch.get('title', ch['channel'])}", "cross",
            f"fj:rm:{ch['channel']}", style="DANGER"
        )])
    buttons.append([create_button("Back", "back", "adm:forcejoin", style="SECONDARY")])
    await _edit_or_send(cb, "🗑 <b>Remove Channel</b>\n\nSelect:", InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()


@router.callback_query(F.data.startswith("fj:rm:"))
async def cb_forcejoin_remove(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not is_owner(uid):
        await _deny(cb, uid); return
    channel = cb.data.split(":", 2)[2]
    if channel.lstrip("-").isdigit():
        channel = int(channel)
    await ForceJoinManager.remove_channel(channel)
    text, kb = _build_forcejoin_panel()
    text = f"✅ Channel removed.\n\n" + text
    await _edit_or_send(cb, text, kb)
    await cb.answer("Channel removed!")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BROADCAST MANAGEMENT  (admin panel inline buttons)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_broadcast_panel(uid: int) -> tuple[str, InlineKeyboardMarkup]:
    eff = _effective_uid(uid)
    store = UserManager.get_store(eff)
    s = store.all()
    lines = ["📢 <b>Broadcast Management</b>\n", "━━━━━━━━━━━━━━━━━━━━\n\n"]
    msg_text = s.get("broadcast_text", "") or s.get("message", "") or "<i>Not set</i>"
    if len(msg_text) > 100:
        msg_text = msg_text[:100] + "..."
    media_type = s.get("media_type", "")
    interval = s.get("interval", 0) or 0
    delay = s.get("delay_between", 0) or 0
    loop_running = Sched.is_loop_running(eff)
    lines.append(f"📝 <b>Message:</b> {msg_text}\n")
    if media_type:
        lines.append(f"📎 <b>Media:</b> {media_type}\n")
    lines.append(f"⏱ <b>Interval:</b> {_fmt_interval(interval) if interval else 'Not set'}\n")
    lines.append(f"⏳ <b>Delay:</b> {delay}s\n")
    lines.append(f"🔄 <b>Loop:</b> {'🟢 Running' if loop_running else '🔴 Stopped'}\n")
    buttons = [
        [create_button("Set Message", "edit", "m:msg", style="PRIMARY"),
         create_button("Set Interval", "clock", "m:time_menu", style="INFO")],
        [create_button("Set Delay", "clock", "m:delay", style="INFO")],
    ]
    if loop_running:
        buttons.append([create_button("Stop Loop", "stop", "m:loop_stop", style="DANGER")])
    else:
        buttons.append([create_button("Start Loop", "play", "m:loop_start", style="SUCCESS")])
    buttons.append([create_button("Send Once", "rocket", "m:once", style="PRIMARY")])
    buttons.append([create_button("Back to Admin Panel", "back", "m:admin_panel", style="SECONDARY")])
    return "".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "adm:broadcast")
async def cb_broadcast_panel(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await _deny(cb, uid); return
    text, kb = _build_broadcast_panel(uid)
    await _edit_or_send(cb, text, kb)
    await cb.answer()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FORCE JOIN ENFORCEMENT on /start
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _check_force_join(msg_or_cb, bot) -> bool:
    """Check if user must join channels. Returns True if user passed (or no channels configured)."""
    user_id = msg_or_cb.from_user.id
    if has_access(user_id):
        return True
    not_joined = await ForceJoinManager.check_membership(bot, user_id)
    if not not_joined:
        return True
    buttons = []
    for ch in not_joined:
        ch_val = ch["channel"]
        if isinstance(ch_val, str) and ch_val.startswith("@"):
            url = f"https://t.me/{ch_val[1:]}"
        elif isinstance(ch_val, str):
            url = f"https://t.me/{ch_val}"
        else:
            url = f"https://t.me/c/{str(ch_val).replace('-100', '')}"
        buttons.append([InlineKeyboardButton(
            text=f"Join {ch.get('title', ch_val)}",
            url=url
        )])
    buttons.append([InlineKeyboardButton(text="✅ I've Joined", callback_data="fj:check")])
    text = ("🔒 <b>You must join the following channels to use this bot:</b>\n\n"
            "Click the buttons below to join, then tap '✅ I've Joined'.")
    if isinstance(msg_or_cb, Message):
        await msg_or_cb.reply(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                              parse_mode="HTML")
    else:
        await _edit_or_send(msg_or_cb, text, InlineKeyboardMarkup(inline_keyboard=buttons))
    return False


@router.callback_query(F.data == "fj:check")
async def cb_forcejoin_check(cb: CallbackQuery) -> None:
    user_id = cb.from_user.id
    not_joined = await ForceJoinManager.check_membership(cb.bot, user_id)
    if not_joined:
        names = ", ".join(str(c.get("title", c["channel"])) for c in not_joined)
        await cb.answer(f"❌ You still need to join: {names}", show_alert=True)
    else:
        await cb.answer("✅ Verified! You can now use the bot.")
        eff = _effective_uid(user_id) if has_access(user_id) else user_id
        text = await get_dashboard_text(eff) if has_access(user_id) else "Welcome! Bot is ready."
        kb = _get_main_kb(user_id) if has_access(user_id) else None
        await _edit_or_send(cb, text, kb)


@router.callback_query(F.data == "m:main")
async def cb_main(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await _deny(cb, uid); return
    await state.clear()
    _pending_clients.pop(uid, None)
    eff = _effective_uid(uid)
    text = await get_dashboard_text(eff)
    await _edit_or_send(cb, text, _get_main_kb(uid))
    await cb.answer()


@router.callback_query(F.data == "m:dashboard")
async def cb_dashboard(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await _deny(cb, uid); return
    await state.clear()
    text = await get_dashboard_text(uid)
    await _edit_or_send(cb, text, _get_main_kb(uid))
    await cb.answer()


@router.callback_query(F.data == "m:time_menu")
async def cb_time_menu(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await _deny(cb, uid); return
    from ui.main_menu import kb_time_menu
    await _edit_or_send(cb, "⏱ <b>Time Settings</b>\n\nChoose an option below:", kb_time_menu())
    await cb.answer()


@router.callback_query(F.data == "m:groups_menu")
async def cb_groups_menu(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await _deny(cb, uid); return
    from ui.main_menu import kb_groups_menu
    await _edit_or_send(cb, "📌 <b>Group Management</b>\n\nChoose an option below:", kb_groups_menu())
    await cb.answer()


@router.callback_query(F.data == "m:logout_active")
async def cb_logout_active(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await _deny(cb, uid); return
    account_mgr = UserManager.get_account_mgr(uid)
    active = account_mgr.get_active_account()
    if not active:
        await cb.answer("❌ No active account.", show_alert=True)
        return
    from ui.main_menu import kb_logout_confirm
    text = f"⚠️ Are you sure you want to log out of <b>{active['phone']}</b>?"
    await _edit_or_send(cb, text, kb_logout_confirm())
    await cb.answer()


@router.callback_query(F.data == "m:logout_yes")
async def cb_logout_yes(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await _deny(cb, uid); return
    account_mgr = UserManager.get_account_mgr(uid)
    active = account_mgr.get_active_phone()
    if not active:
        await cb.answer("❌ No active account.", show_alert=True)
        return

    # Actually perform the logout
    await cb.answer("🚪 Logging out... Please wait.", show_alert=False)
    await account_mgr.logout(active)

    # Return to dashboard
    text = await get_dashboard_text(uid)
    await _edit_or_send(cb, text, _get_main_kb(uid))
# ── Mode toggle stubs (legacy deep-link compat — redirect to main) ─
@router.callback_query(F.data == "mode:normal")
async def cb_mode_normal(cb: CallbackQuery) -> None:
    """Legacy callback — mode switching removed. Redirect to main menu."""
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    await _edit_or_send(cb, MAIN_TEXT, _get_main_kb(uid))


@router.callback_query(F.data == "mode:advanced")
async def cb_mode_advanced(cb: CallbackQuery) -> None:
    """Legacy callback — mode switching removed. Redirect to main menu."""
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    await _edit_or_send(cb, MAIN_TEXT, _get_main_kb(uid))


# ── /addgroup (legacy manual add) ─────────────────────────────────
@router.message(Command("addgroup"))
async def cmd_addgroup(message: Message) -> None:
    uid = message.from_user.id
    if not has_access(uid):
        await _deny(message, uid); return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Usage: <code>/addgroup -1001234567890</code>", parse_mode="HTML"); return
    try:
        chat_id = int(args[1].strip())
    except ValueError:
        await message.reply("⚠️ Invalid chat ID."); return
    try:
        chat   = await message.bot.get_chat(chat_id)
        title  = chat.title or str(chat_id)
        store = UserManager.get_store(uid)
        groups = await store.get("selected_groups", [])
        if any(g["id"] == chat_id for g in groups):
            await message.reply(f"ℹ️ <b>{title}</b> already in list.", parse_mode="HTML"); return
        groups.append({"id": chat_id, "title": title})
        await store.set("selected_groups", groups)
        await message.reply(f"✅ Added: <b>{title}</b>\n<code>{chat_id}</code>", parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Failed: <code>{e}</code>", parse_mode="HTML")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ACCOUNT MANAGEMENT HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(F.data == "m:accounts")
async def cb_accounts_menu(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    account_mgr = UserManager.get_account_mgr(uid)
    active   = account_mgr.get_active_phone()
    acc_list = account_mgr.get_accounts()
    count    = f"<b>{len(acc_list)}</b> account(s) saved."
    act_line = f"\n🟢 Active: <code>{active}</code>" if active else "\n⚠️ No active account."
    await _edit_or_send(cb, f"👤 <b>Accounts</b>\n\n{count}{act_line}", kb_accounts_menu(can_add=True))
    await cb.answer()


# ── ADD ACCOUNT: step 1 — ask phone number ───────────────────────
@router.callback_query(F.data == "acc:add")
async def cb_acc_add(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return

    # Validate global API credentials before proceeding
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH or len(TELEGRAM_API_HASH) < 10:
        log.error("TELEGRAM_API_ID or TELEGRAM_API_HASH is missing/invalid in config.")
        await cb.answer(
            "⚠️ API credentials not configured. Check TELEGRAM_API_ID / TELEGRAM_API_HASH in the script.",
            show_alert=True,
        )
        return

    await state.set_state(S.acc_phone)
    await _edit_or_send(
        cb,
        "📱 <b>Login Telegram Account — Step 1/3</b>\n\n"
        "Send your <b>phone number</b>\n"
        "Include country code: <code>+91XXXXXXXXXX</code>",
        kb_cancel(),
    )
    await cb.answer()


# ── ADD ACCOUNT: step 2 — phone → send OTP ───────────────────────
@router.message(S.acc_phone)
async def handle_acc_phone(message: Message, state: FSMContext) -> None:
    if not has_access(message.from_user.id):
        return
    phone = message.text.strip()
    if not phone.startswith("+"):
        await message.reply(
            "⚠️ Phone must start with country code, e.g. <code>+91XXXXXXXXXX</code>.",
            parse_mode="HTML",
        ); return

    # Use global API credentials — never ask the user for them
    api_id   = TELEGRAM_API_ID
    api_hash = TELEGRAM_API_HASH

    wait_msg = await message.answer("⏳ Connecting to Telegram and sending OTP …")

    account_mgr = UserManager.get_account_mgr(message.from_user.id)
    sess_path = account_mgr._session_path(phone)
    client    = TelegramClient(sess_path, int(api_id), api_hash)

    try:
        await client.connect()
        sent = await client.send_code_request(phone)
        _pending_clients[message.from_user.id] = client
        await state.update_data(phone=phone, phone_code_hash=sent.phone_code_hash)
        await state.set_state(S.acc_code)
        await wait_msg.delete()
        await message.answer(
            "📲 <b>OTP sent!</b>\n\n"
            "<b>Step 2/3</b> — Send the <b>verification code</b> you received.\n"
            "Just the digits, e.g. <code>12345</code>",
            parse_mode="HTML", reply_markup=kb_cancel(),
        )
    except Exception as e:
        await client.disconnect()
        _pending_clients.pop(message.from_user.id, None)
        await state.clear()
        await wait_msg.delete()
        await message.answer(
            f"❌ Failed to send OTP: <code>{e}</code>",
            parse_mode="HTML", reply_markup=kb_back(),
        )


# ── ADD ACCOUNT: step 2 — OTP code ───────────────────────────────
@router.message(S.acc_code)
async def handle_acc_code(message: Message, state: FSMContext) -> None:
    if not has_access(message.from_user.id):
        return
    code   = message.text.strip()
    data   = await state.get_data()
    phone  = data["phone"]
    client = _pending_clients.get(message.from_user.id)

    if not client:
        await message.answer("❌ Session expired. Please start over.", reply_markup=kb_back())
        await state.clear(); return

    try:
        user = await client.sign_in(phone=phone, code=code, phone_code_hash=data["phone_code_hash"])
        name = getattr(user, "first_name", "") or phone
        account_mgr = UserManager.get_account_mgr(message.from_user.id)
        account_mgr.add_or_update(phone, name, TELEGRAM_API_ID, TELEGRAM_API_HASH)
        account_mgr._clients[phone] = client      # cache the authorised client
        _pending_clients.pop(message.from_user.id, None)
        await state.clear()
        store = UserManager.get_store(message.from_user.id)
        # Auto-create the per-account log group (silent; never blocks login).
        try:
            await ensure_log_group(message.bot, message.from_user.id, phone)
        except Exception as _lg_exc:
            log.warning("[User %s][%s] ensure_log_group at login failed: %s", message.from_user.id, phone, _lg_exc)
        # ── Start Real-time Auto-fetch listener on the new client ──
        @client.on(events.ChatAction)
        async def on_chat_action(event):
            if getattr(event, 'user_joined', False) or getattr(event, 'user_added', False):
                log.info("[AutoFetch] Real-time join/add detected for User %s. Resyncing...", message.from_user.id)
                import asyncio
                asyncio.create_task(_sync_groups_for_user(message.from_user.id, account_mgr, store))

        user_mode = await store.get("user_mode", "advanced")
        status_msg = await message.answer(
            f"✅ <b>Account added successfully!</b>\n\n"
            f"👤 Name: <b>{name}</b>\n"
            f"📱 Phone: <code>{phone}</code>\n\n"
            "This is now the active account for broadcasting.\n"
            "🔄 <b>Scanning your groups and topics...</b>",
            parse_mode="HTML"
        )

        await _sync_groups_for_user(message.from_user.id, account_mgr, store)

        auto_groups = await store.get("auto_groups", [])
        total = len({g["id"] for g in auto_groups})
        forum_count = len({g["id"] for g in auto_groups if g.get("is_forum")})
        normal_count = total - forum_count
        topic_count = sum(1 for g in auto_groups if g.get("topic_id") is not None)

        await status_msg.edit_text(
            f"✅ <b>Account added successfully!</b>\n\n"
            f"👤 Name: <b>{name}</b>\n"
            f"📱 Phone: <code>{phone}</code>\n\n"
            "This is now the active account for broadcasting.\n"
            f"✅ <b>Scan Complete:</b>\n"
            f"📦 Total Groups: <b>{total}</b>\n"
            f"💬 Standard Groups: <b>{normal_count}</b>\n"
            f"📌 Forum Groups: <b>{forum_count}</b> ({topic_count} topics)",
            parse_mode="HTML", reply_markup=_get_main_kb(message.from_user.id, user_mode)
        )

    except SessionPasswordNeededError:
        await state.set_state(S.acc_2fa)
        await message.answer(
            "🔒 <b>Two-Factor Authentication required.</b>\n\n"
            "<b>Step 3/3</b> — Send your <b>2FA / cloud password</b>:",
            parse_mode="HTML", reply_markup=kb_cancel(),
        )

    except PhoneCodeInvalidError:
        await message.reply("⚠️ Wrong code. Please send the correct OTP:")

    except PhoneCodeExpiredError:
        # Code expired — client must request a fresh OTP; clear state entirely
        await client.disconnect()
        _pending_clients.pop(message.from_user.id, None)
        await state.clear()
        await message.answer(
            "⚠️ <b>OTP expired.</b>\n\nPlease start the login again and request a new code.",
            parse_mode="HTML", reply_markup=kb_back(),
        )

    except Exception as e:
        await client.disconnect()
        _pending_clients.pop(message.from_user.id, None)
        await state.clear()
        await message.answer(
            f"❌ Sign-in failed: <code>{e}</code>",
            parse_mode="HTML", reply_markup=kb_back(),
        )


# ── ADD ACCOUNT: step 3 (optional) — 2FA password ────────────────
@router.message(S.acc_2fa)
async def handle_acc_2fa(message: Message, state: FSMContext) -> None:
    if not has_access(message.from_user.id):
        return
    password = message.text.strip()
    data     = await state.get_data()
    phone    = data["phone"]
    client   = _pending_clients.get(message.from_user.id)

    if not client:
        await message.answer("❌ Session expired. Please start over.", reply_markup=kb_back())
        await state.clear(); return

    try:
        user = await client.sign_in(password=password)
        name = getattr(user, "first_name", "") or phone
        account_mgr = UserManager.get_account_mgr(message.from_user.id)
        account_mgr.add_or_update(phone, name, TELEGRAM_API_ID, TELEGRAM_API_HASH)
        account_mgr._clients[phone] = client
        _pending_clients.pop(message.from_user.id, None)
        await state.clear()
        store_2fa = UserManager.get_store(message.from_user.id)
        # Auto-create the per-account log group (silent; never blocks login).
        try:
            await ensure_log_group(message.bot, message.from_user.id, phone)
        except Exception as _lg_exc:
            log.warning("[User %s][%s] ensure_log_group at login failed: %s", message.from_user.id, phone, _lg_exc)
        user_mode_2fa = await store_2fa.get("user_mode", "advanced")

        # Start Real-time Auto-fetch listener on the new client for 2FA as well
        @client.on(events.ChatAction)
        async def on_chat_action_2fa(event):
            if getattr(event, 'user_joined', False) or getattr(event, 'user_added', False):
                log.info("[AutoFetch] Real-time join/add detected for User %s. Resyncing...", message.from_user.id)
                import asyncio
                asyncio.create_task(_sync_groups_for_user(message.from_user.id, account_mgr, store_2fa))

        status_msg = await message.answer(
            f"✅ <b>Account added (2FA)!</b>\n\n"
            f"👤 Name: <b>{name}</b>\n"
            f"📱 Phone: <code>{phone}</code>\n\n"
            "This is now the active account for broadcasting.\n"
            "🔄 <b>Scanning your groups and topics...</b>",
            parse_mode="HTML"
        )

        await _sync_groups_for_user(message.from_user.id, account_mgr, store_2fa)

        auto_groups = await store_2fa.get("auto_groups", [])
        total = len({g["id"] for g in auto_groups})
        forum_count = len({g["id"] for g in auto_groups if g.get("is_forum")})
        normal_count = total - forum_count
        topic_count = sum(1 for g in auto_groups if g.get("topic_id") is not None)

        await status_msg.edit_text(
            f"✅ <b>Account added (2FA)!</b>\n\n"
            f"👤 Name: <b>{name}</b>\n"
            f"📱 Phone: <code>{phone}</code>\n\n"
            "This is now the active account for broadcasting.\n"
            f"✅ <b>Scan Complete:</b>\n"
            f"📦 Total Groups: <b>{total}</b>\n"
            f"💬 Standard Groups: <b>{normal_count}</b>\n"
            f"📌 Forum Groups: <b>{forum_count}</b> ({topic_count} topics)",
            parse_mode="HTML", reply_markup=_get_main_kb(message.from_user.id, user_mode_2fa)
        )
    except Exception as e:
        await client.disconnect()
        _pending_clients.pop(message.from_user.id, None)
        await state.clear()
        await message.answer(
            f"❌ 2FA failed: <code>{e}</code>",
            parse_mode="HTML", reply_markup=kb_back(),
        )


# ── VIEW ALL ACCOUNTS ─────────────────────────────────────────────
@router.callback_query(F.data == "acc:view")
async def cb_acc_view(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    account_mgr = UserManager.get_account_mgr(uid)
    accounts = account_mgr.get_accounts()
    active   = account_mgr.get_active_phone()
    if not accounts:
        await _edit_or_send(
            cb, "📋 No accounts saved yet.\n\nUse ➕ Add Account to login.", kb_accounts_menu()
        )
        return
    lines = ["📋 <b>Saved Accounts</b>\n"]
    for acc in accounts:
        star = "🟢 " if acc["phone"] == active else "⚪ "
        lines.append(f"{star}<b>{acc['name']}</b>  <code>{acc['phone']}</code>")
    lines.append("\n🟢 = active  ⚪ = inactive")
    await _edit_or_send(cb, "\n".join(lines), kb_accounts_menu())


# ── SWITCH ACTIVE ACCOUNT ─────────────────────────────────────────
@router.callback_query(F.data == "acc:switch")
async def cb_acc_switch_menu(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    account_mgr = UserManager.get_account_mgr(uid)
    accounts = account_mgr.get_accounts()
    if not accounts:
        await cb.answer("No accounts saved.", show_alert=True); return
    active = account_mgr.get_active_phone()
    await _edit_or_send(
        cb,
        "🔁 <b>Switch Active Account</b>\n\nTap an account to activate it:",
        kb_accounts_switch(accounts, active),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("accswitch:"))
async def cb_accswitch(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    account_mgr = UserManager.get_account_mgr(uid)
    phone = cb.data.split(":", 1)[1]
    ok    = account_mgr.set_active(phone)
    if ok:
        acc  = account_mgr.get_active_account()
        name = acc["name"] if acc else phone
        await cb.answer(f"✅ Switched to {name}", show_alert=True)
    else:
        await cb.answer("⚠️ Account not found.", show_alert=True)
    # Refresh the keyboard
    accounts = account_mgr.get_accounts()
    await cb.message.edit_reply_markup(
        reply_markup=kb_accounts_switch(accounts, account_mgr.get_active_phone())
    )


# ── LOGOUT ACCOUNT ────────────────────────────────────────────────
@router.callback_query(F.data == "acc:logout")
async def cb_acc_logout_menu(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    account_mgr = UserManager.get_account_mgr(uid)
    accounts = account_mgr.get_accounts()
    if not accounts:
        await cb.answer("No accounts to logout.", show_alert=True); return
    await _edit_or_send(
        cb,
        "🚪 <b>Logout Account</b>\n\nSelect which account to logout:",
        kb_accounts_logout(accounts),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("acclogout:"))
async def cb_acclogout(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    account_mgr = UserManager.get_account_mgr(uid)
    phone = cb.data.split(":", 1)[1]
    ok    = await account_mgr.logout(phone)
    if ok:
        await cb.answer(f"✅ Logged out: {phone}", show_alert=True)
    else:
        await cb.answer("⚠️ Not found.", show_alert=True); return
    # Refresh or go back if no more accounts
    accounts = account_mgr.get_accounts()
    if accounts:
        await cb.message.edit_reply_markup(reply_markup=kb_accounts_logout(accounts))
    else:
        await _edit_or_send(cb, "✅ All accounts logged out.", kb_accounts_menu())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  (fetch_groups removed in favor of auto-sync)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOOP CONTROL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == "m:start")
async def cb_start_loop(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return

    account_mgr = UserManager.get_account_mgr(uid)
    phone = account_mgr.get_active_phone()
    if not phone:
        await cb.answer("⚠️ No active account. Add one first.", show_alert=True); return

    if Sched.is_loop_running(uid, phone):
        await cb.answer(f"Loop already running for {phone}.", show_alert=True); return

    store = UserManager.get_store(uid)
    settings = await store.all()
    has_text = bool(settings.get("message", "").strip())
    has_fwd  = settings.get("forward_mode", False)
    if not has_text and not has_fwd:
        await cb.answer("⚠️ No message or forward post set. Use ✏️ Set Message first.", show_alert=True); return

    await _edit_or_send(
        cb,
        "▶️ <b>Start Loop</b>\n\nChoose which groups to broadcast to:",
        kb_start_choice(),
    )
    await cb.answer()


async def _do_start_loop(cb: CallbackQuery, uid: int, bmode: str) -> None:
    """Shared logic for starting the broadcast loop after user chooses group source.
    bmode: 'selected' | 'topic' | 'both'
    """
    store = UserManager.get_store(uid)
    settings = await store.all()

    topic_groups = settings.get("topic_groups", [])
    sel_groups   = settings.get("selected_groups", [])

    if bmode == "topic":
        if not topic_groups:
            await _edit_or_send(
                cb,
                "⚠️ <b>No Topic Groups saved.</b>\n\n"
                "Open the 📌 Topic Groups menu to add them.",
                kb_topic_groups([], {}, 0),
            )
            await cb.answer(); return
        total = sum(len(g.get("topics", [])) or 1 for g in topic_groups)
    elif bmode == "both":
        if not topic_groups and not sel_groups:
            await cb.answer("⚠️ No groups at all. Add Topic or Select Groups first.", show_alert=True); return
        unique_ids = (
            {f"{g['id']}_{t}" for g in topic_groups for t in (g.get("topics", []) or [None])}
            | {f"{g['id']}_None" for g in sel_groups}
        )
        total = len(unique_ids)
    else:
        if not sel_groups:
            await cb.answer("⚠️ No groups selected. Use 📌 Select Groups first.", show_alert=True); return
        total = len(sel_groups)

    await store.set("broadcast_mode", bmode)

    # Check if user has both text and forward options
    has_text = bool(settings.get("message", "").strip())
    has_fwd  = settings.get("forward_mode", False)

    if has_text and has_fwd:
        # Ask user which message type to use
        kb_msg_type = InlineKeyboardMarkup(inline_keyboard=[
            [create_button("Use Saved Text Message",      "edit",      "m:start:use_text",    style="PRIMARY")],
            [create_button("Forward Saved Channel Post", "broadcast", "m:start:use_forward", style="PRIMARY")],
            [create_button("Back",                       "back",      "m:start",             style="SECONDARY")],
        ])
        await _edit_or_send(
            cb,
            f"✉️ <b>Choose Message Type</b>\n\n"
            f"Groups: <b>{total}</b> ({bmode})\n\n"
            "Which content should be broadcast?",
            kb_msg_type,
        )
        await cb.answer()
        return
    elif has_fwd:
        await _finalize_start_loop(cb, uid, bmode, total, use_forward=True)
    else:
        await _finalize_start_loop(cb, uid, bmode, total, use_forward=False)


async def _finalize_start_loop(
    cb: CallbackQuery, uid: int, bmode: str, total: int, *, use_forward: bool
) -> None:
    """Actually start the broadcast loop after all choices are made."""
    store = UserManager.get_store(uid)
    settings = await store.all()

    await store.set("forward_active", use_forward)

    # Validate forward requirements
    if use_forward:
        account_mgr = UserManager.get_account_mgr(uid)
        tl_client = await account_mgr.get_active_client()
        if not tl_client:
            await _edit_or_send(
                cb,
                "⚠️ <b>Telethon account required for forwarding.</b>\n\n"
                "Add one via 👤 Accounts first.",
                kb_back(),
            )
            await cb.answer(); return
        fwd_channel = settings.get("forward_channel_id")
        if not fwd_channel:
            await _edit_or_send(
                cb,
                "⚠️ <b>No saved channel post found.</b>\n\n"
                "Use ✏️ Set Message → 📢 Forward From Channel first.",
                kb_back(),
            )
            await cb.answer(); return

    account_mgr = UserManager.get_account_mgr(uid)
    active_client = await account_mgr.get_active_client()
    acc           = account_mgr.get_active_account()
    mode_note = (
        f"\n\n👤 Sending as: <b>{acc['name']}</b> <code>{acc['phone']}</code>"
        if active_client and acc
        else "\n\n⚠️ No active user account — using bot token (limited groups)."
    )
    source_labels = {"topic": "📌 Topic Groups", "selected": "📋 Selected Groups", "both": "📦 Both"}
    source_note = source_labels.get(bmode, bmode)
    msg_type = "📢 Channel Forward" if use_forward else "✉️ Text Message"
    if use_forward:
        hide = settings.get("forward_hide_sender", True)
        msg_type += " (🔒 Hidden)" if hide else " (👁 Original)"

    account_mgr = UserManager.get_account_mgr(uid)
    phone = account_mgr.get_active_phone()
    if not phone:
        await cb.answer("⚠️ No active account.", show_alert=True); return

    interval = settings.get("interval_seconds", 300)
    await Sched.add_loop(cb.bot, uid, interval, phone)
    # FIXED — loop_active_accounts is the SINGLE SOURCE OF TRUTH
    active_map = await store.get("loop_active_accounts", {})
    active_map[phone] = True
    await store.set("loop_active_accounts", active_map)
    await store.set("loop_active", True)  # backward compat — derived from above
    # Fire first broadcast immediately (non-blocking)
    _task = asyncio.create_task(broadcast_once(cb.bot, uid, phone=phone))
    _task.add_done_callback(
        lambda t: log.error("[User %s] broadcast_once task raised: %s", uid, t.exception())
        if not t.cancelled() and t.exception() else None
    )
    await _edit_or_send(
        cb,
        f"✅ <b>Auto sending started.</b>\n\nUsing: <b>{source_note}</b> ({total} groups)"
        f"\nMode: <b>{msg_type}</b>"
        + mode_note +
        "\n\nPress ⏹ Stop Loop to halt.",
        kb_back(),
    )
    await cb.answer()


@router.callback_query(F.data == "m:start:use_topic")
async def cb_start_use_topic(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    if Sched.is_loop_running(uid):
        await cb.answer("Loop is already running.", show_alert=True); return
    await _do_start_loop(cb, uid, bmode="topic")


@router.callback_query(F.data == "m:start:use_selected")
async def cb_start_use_selected(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    if Sched.is_loop_running(uid):
        await cb.answer("Loop is already running.", show_alert=True); return
    await _do_start_loop(cb, uid, bmode="selected")


@router.callback_query(F.data == "m:start:use_both")
async def cb_start_use_both(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    if Sched.is_loop_running(uid):
        await cb.answer("Loop is already running.", show_alert=True); return
    await _do_start_loop(cb, uid, bmode="both")


# ── MESSAGE TYPE CHOICE (text vs forward) after group source chosen ──

@router.callback_query(F.data == "m:start:use_text")
async def cb_start_use_text(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    if Sched.is_loop_running(uid):
        await cb.answer("Loop is already running.", show_alert=True); return
    store = UserManager.get_store(uid)
    settings = await store.all()
    bmode = settings.get("broadcast_mode", "selected")
    topic_groups = settings.get("topic_groups", [])
    sel_groups   = settings.get("selected_groups", [])
    if bmode == "topic":
        total = sum(len(g.get("topics", [])) or 1 for g in topic_groups)
    elif bmode == "both":
        total = len({f"{g['id']}_{t}" for g in topic_groups for t in (g.get("topics", []) or [None])} | {f"{g['id']}_None" for g in sel_groups})
    else:
        total = len(sel_groups)
    await _finalize_start_loop(cb, uid, bmode, total, use_forward=False)


@router.callback_query(F.data == "m:start:use_forward")
async def cb_start_use_forward(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    if Sched.is_loop_running(uid):
        await cb.answer("Loop is already running.", show_alert=True); return
    store = UserManager.get_store(uid)
    settings = await store.all()
    if not settings.get("forward_mode", False):
        await cb.answer("⚠️ No saved channel post found.", show_alert=True); return
    # Show hide/show sender choice
    kb_sender = InlineKeyboardMarkup(inline_keyboard=[
        [create_button("Hide Sender",            "lock",    "m:forward:hide", style="PRIMARY")],
        [create_button("Show Original Sender",   "globe",   "m:forward:show", style="SECONDARY")],
        [create_button("Back",                   "back",    "m:main",         style="SECONDARY")],
    ])
    await _edit_or_send(
        cb,
        "📢 <b>Forward Sender Option</b>\n\n"
        "🔒 <b>Hide Sender</b> — post appears as your own\n"
        "👁 <b>Show Original Sender</b> — shows \"Forwarded from…\"\n\n"
        "Choose how to forward:",
        kb_sender,
    )
    await cb.answer()


async def _start_forward_with_sender(cb: CallbackQuery, hide_sender: bool) -> None:
    """Shared logic: set forward_hide_sender and start the loop."""
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    account_mgr_fwd = UserManager.get_account_mgr(uid)
    phone_fwd = account_mgr_fwd.get_active_phone()
    if phone_fwd and Sched.is_loop_running(uid, phone_fwd):
        await cb.answer(f"Loop already running for {phone_fwd}.", show_alert=True); return
    store = UserManager.get_store(uid)
    await store.set("forward_hide_sender", hide_sender)
    settings = await store.all()
    bmode = settings.get("broadcast_mode", "selected")
    topic_groups = settings.get("topic_groups", [])
    sel_groups   = settings.get("selected_groups", [])
    if bmode == "topic":
        total = sum(len(g.get("topics", [])) or 1 for g in topic_groups)
    elif bmode == "both":
        total = len({f"{g['id']}_{t}" for g in topic_groups for t in (g.get("topics", []) or [None])} | {f"{g['id']}_None" for g in sel_groups})
    else:
        total = len(sel_groups)
    await _finalize_start_loop(cb, uid, bmode, total, use_forward=True)


@router.callback_query(F.data == "m:forward:hide")
async def cb_forward_hide(cb: CallbackQuery) -> None:
    await _start_forward_with_sender(cb, hide_sender=True)


@router.callback_query(F.data == "m:forward:show")
async def cb_forward_show(cb: CallbackQuery) -> None:
    await _start_forward_with_sender(cb, hide_sender=False)


@router.callback_query(F.data == "m:stop")
async def cb_stop_loop(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return

    account_mgr = UserManager.get_account_mgr(uid)
    phone = account_mgr.get_active_phone()
    if not phone:
        await cb.answer("⚠️ No active account.", show_alert=True); return

    if not Sched.is_loop_running(uid, phone):
        await cb.answer(f"No active loop for {phone}.", show_alert=True); return

    store = UserManager.get_store(uid)
    # Set per-account flag FIRST so in-flight rounds exit immediately
    active_map = await store.get("loop_active_accounts", {})
    active_map[phone] = False
    await store.set("loop_active_accounts", active_map)
    await Sched.remove_loop(uid, phone)

    # Post a standalone STOPPED log message (no edit — full history preserved).
    plan_lbl  = ADMIN_LABEL
    round_num = account_mgr.get_round_counter(phone)
    stopped_text = _build_process_msg(phone, plan_lbl, round_num, 1, 0, 0, 0, 0, "STOPPED")
    await _safe_send_log(cb.bot, uid, phone, stopped_text)

    # FIXED — derive loop_active from loop_active_accounts (single source of truth)
    any_active = any(v for v in active_map.values())
    await store.set("loop_active", any_active)

    await _edit_or_send(cb, f"⏹ <b>Loop stopped for {phone}.</b>", kb_back())
    await cb.answer()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STATUS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == "m:status")
async def cb_status(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    store = UserManager.get_store(uid)
    account_mgr = UserManager.get_account_mgr(uid)
    s       = await store.all()
    groups  = s.get("selected_groups", [])
    running = Sched.is_loop_running(uid)
    active  = account_mgr.get_active_account()
    acc_line = (
        f"👤 Account: <b>{active['name']}</b> <code>{active['phone']}</code>"
        if active else "👤 Account: <b>⚠️ None (bot fallback)</b>"
    )
    lines = [
        "📊 <b>Status</b>\n",
        f"🔄 Loop: {'<b>Running ✅</b>' if running else '<b>Stopped ⏹</b>'}",
        acc_line,
        f"⏱ Interval: <code>{s.get('interval_seconds', 300)}s</code>",
        f"⏳ Delay: <code>{s.get('delay_between_sends', 3)}s</code>  "
        f"(random: {s.get('random_delay', True)}  "
        f"{s.get('random_delay_min', 2.0)}–{s.get('random_delay_max', 8.0)}s)",
        f"📌 Groups: <code>{len(groups)}</code>",
        f"📅 Schedules: <code>{len(s.get('schedules', []))}</code>",
        f"✉️ Message: {'✅ Set' if s.get('message', '').strip() else '<b>⚠️ Not set</b>'}",
    ]
    if groups:
        lines.append("\n<b>Groups:</b>")
        for g in groups[:10]:
            lines.append(f"  • {g['title']}  <code>{g['id']}</code>")
        if len(groups) > 10:
            lines.append(f"  … and {len(groups) - 10} more")
    await _edit_or_send(cb, "\n".join(lines), kb_back())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GROUPS VIEW
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == "m:groups")
async def cb_groups_view(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    store = UserManager.get_store(uid)
    groups = await store.get("selected_groups", [])
    if not groups:
        await _edit_or_send(
            cb,
            "📦 <b>No groups selected yet.</b>\n\n"
            "1️⃣ Add a Telethon account (👤 Accounts → ➕ Add)\n"
            "2️⃣ Tap <b>📌 Choose Groups</b> to select which ones to send to.\n"
            "(Your groups are automatically synchronized in the background.)",
            kb_back(),
        )
    else:
        lines = [f"📦 <b>Selected Groups</b>  ({len(groups)} total)\n"]
        for g in groups[:30]:
            lines.append(f"• {g['title']}\n  <code>{g['id']}</code>")
        if len(groups) > 30:
            lines.append(f"\n… and {len(groups) - 30} more.")
        await _edit_or_send(cb, "\n".join(lines), kb_back())
    await cb.answer()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GROUP SELECTION  (inline toggle)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == "m:sel_groups")
async def cb_sel_groups(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return

    await cb.answer()
    await _edit_or_send(
        cb,
        "⏳ <b>Fetching groups...</b>\n<i>Please wait, this may take a few moments.</i>",
        InlineKeyboardMarkup(inline_keyboard=[])
    )

    account_mgr = UserManager.get_account_mgr(uid)
    client = await account_mgr.get_active_client()
    if not client or not await client.is_user_authorized():
        await _edit_or_send(cb, "⚠️ <b>No active Telethon account.</b>\nPlease add or login to an account first.", kb_back())
        return

    # Fetch dynamically on demand
    all_groups = await _fetch_all_groups_unified(client)

    store = UserManager.get_store(uid)
    await store.set("auto_groups", all_groups)  # Save for other references if needed

    # Filter out topics since this is the normal group select
    auto_groups = [g for g in all_groups if g.get("topic_id") is None]
    selected = await store.get("selected_groups", [])

    if not auto_groups and not selected:
        await _edit_or_send(cb, "❌ <b>No groups found.</b>\nEnsure your account has joined some groups.", kb_back())
        return

    # Combine fetched and selected to ensure we don't lose manually added ones
    candidates_dict = {g["id"]: {"id": g["id"], "title": g["title"]} for g in auto_groups + selected}
    candidates = list(candidates_dict.values())

    selected_ids = {g["id"] for g in selected}

    await state.set_state(S.selecting)
    await state.update_data(candidates=candidates, selected_ids=list(selected_ids), page=0)

    await _edit_or_send(
        cb,
        f"📌 <b>Select Groups</b>\n\n✅ <b>Found {len(candidates)} groups.</b>\nTap to toggle, or <b>send a list of Group IDs</b> (comma or space separated) to select them manually:",
        kb_groups(candidates, selected_ids, 0)
    )


@router.callback_query(F.data.startswith("gpage:"), S.selecting)
async def cb_gpage(cb: CallbackQuery, state: FSMContext) -> None:
    if not has_access(cb.from_user.id):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    try:
        page = int(cb.data.split(":")[1])
    except (IndexError, ValueError):
        await cb.answer("⚠️ Invalid page.", show_alert=True); return
    await state.update_data(page=page)

    data = await state.get_data()
    candidates = data.get("candidates", [])
    selected_ids = set(data.get("selected_ids", []))

    await cb.message.edit_reply_markup(reply_markup=kb_groups(candidates, selected_ids, page))
    await cb.answer()


@router.callback_query(F.data.startswith("gtoggle:"), S.selecting)
async def cb_gtoggle(cb: CallbackQuery, state: FSMContext) -> None:
    if not has_access(cb.from_user.id):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    data         = await state.get_data()
    candidates   = data.get("candidates", [])
    selected_ids = set(data.get("selected_ids", []))
    page         = data.get("page", 0)
    action = cb.data.split(":", 1)[1]
    uid    = cb.from_user.id

    if action == "all":
        selected_ids = {g["id"] for g in candidates}
    elif action == "none":
        selected_ids = set()
    else:
        gid = int(action)
        selected_ids.symmetric_difference_update({gid})
    await state.update_data(selected_ids=list(selected_ids))
    await cb.message.edit_reply_markup(reply_markup=kb_groups(candidates, selected_ids, page))
    await cb.answer()


@router.message(S.selecting)
async def handle_manual_group_selection(message: Message, state: FSMContext) -> None:
    if not has_access(message.from_user.id):
        return

    text = message.text.replace(",", " ").split()
    new_ids = set()
    for word in text:
        try:
            new_ids.add(int(word.strip()))
        except ValueError:
            pass

    if not new_ids:
        await message.reply("⚠️ No valid IDs found. Please send numeric Group IDs.")
        return

    data = await state.get_data()
    candidates = data.get("candidates", [])
    selected_ids = set(data.get("selected_ids", []))
    page = data.get("page", 0)

    added = 0
    for gid in new_ids:
        if not any(c["id"] == gid for c in candidates):
            candidates.append({"id": gid, "title": str(gid)})
        selected_ids.add(gid)
        added += 1

    await state.update_data(candidates=candidates, selected_ids=list(selected_ids))

    await message.answer(
        f"✅ Added {added} valid group(s) from your input.\n"
        "You can continue selecting or press <b>💾 Save</b>.",
        reply_markup=kb_groups(candidates, selected_ids, page),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "gsave", S.selecting)
async def cb_gsave(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    data         = await state.get_data()
    candidates   = data.get("candidates", [])
    selected_ids = set(data.get("selected_ids", []))
    saved        = [g for g in candidates if g["id"] in selected_ids]
    store = UserManager.get_store(uid)

    # De-duplicate: remove any IDs that already exist in topic_groups
    spec_ids = {g["id"] for g in await store.get("topic_groups", [])}
    saved = [g for g in saved if g["id"] not in spec_ids]

    await store.set("selected_groups", saved)
    await state.clear()
    await _edit_or_send(cb, f"✅ Saved <b>{len(saved)}</b> group(s).", kb_back())
    await cb.answer()



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TOPIC GROUPS  (📌 Forum supergroup + per-topic selection)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_saved_map(topic_groups: list[dict]) -> dict[int, set[int]]:
    """Convert stored topic_groups list → {group_id: {topic_id, ...}} for the keyboard."""
    return {tg["id"]: set(tg.get("topics", [])) for tg in topic_groups}


@router.callback_query(F.data == "m:topic_groups")
async def cb_topic_groups(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return

    await state.clear()
    await cb.answer()
    await _edit_or_send(
        cb,
        "⏳ <b>Fetching topic groups...</b>\n<i>Please wait, this may take a few moments.</i>",
        InlineKeyboardMarkup(inline_keyboard=[])
    )

    account_mgr = UserManager.get_account_mgr(uid)
    client = await account_mgr.get_active_client()
    if not client or not await client.is_user_authorized():
        await _edit_or_send(cb, "⚠️ <b>No active Telethon account.</b>\nPlease add or login to an account first.", kb_back())
        return

    # Fetch dynamically on demand
    all_groups = await _fetch_all_groups_unified(client)

    store = UserManager.get_store(uid)
    await store.set("auto_groups", all_groups)  # Save for other references if needed

    # Group topics into expected forum_groups structure for the UI
    fg_map = {}
    for g in all_groups:
        if g.get("is_forum", False):
            gid = g["id"]
            if gid not in fg_map:
                fg_map[gid] = {"id": gid, "title": g["title"], "topic_list": []}
            if g.get("topic_id") is not None:
                fg_map[gid]["topic_list"].append({
                    "id": g["topic_id"],
                    "title": g.get("topic_title") or str(g["topic_id"])
                })

    # Filter out groups that have 0 topics
    forum_groups = [grp for grp in fg_map.values() if grp["topic_list"]]

    if not forum_groups:
        await _edit_or_send(
            cb,
            "❌ <b>No topic-enabled groups found.</b>\n\n"
            "Make sure your active account is a member of at least one forum supergroup.",
            kb_back(),
        )
        return

    saved_tg  = await store.get("topic_groups", [])
    saved_map = _build_saved_map(saved_tg)

    await state.set_state(S.topic_selecting)
    await state.update_data(forum_groups=forum_groups, saved_map={k: list(v) for k, v in saved_map.items()}, expanded_groups=[], page=0)

    total_topics = sum(len(grp["topic_list"]) for grp in forum_groups)

    text = (
        f"📌 <b>Topic Groups Selection</b>\n\n"
        f"✅ <b>Found {len(forum_groups)} groups and {total_topics} topics.</b>\n"
        "📦 Tap a group to expand and view its topics.\n"
        "✅ Tap a topic to toggle selection.\n\n"
        "<i>Counted per topic, not per group.</i>"
    )

    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb_topic_groups(forum_groups, saved_map, set(), 0))
    except Exception:
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb_topic_groups(forum_groups, saved_map, set(), 0))


@router.callback_query(F.data == "tgnoop")
async def cb_tgnoop(cb: CallbackQuery) -> None:
    """No-op for group header buttons."""
    await cb.answer()


@router.callback_query(F.data.startswith("tgexpand:"), S.topic_selecting)
async def cb_tgexpand(cb: CallbackQuery, state: FSMContext) -> None:
    if not has_access(cb.from_user.id):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    try:
        gid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer("⚠️ Invalid group.", show_alert=True); return

    data = await state.get_data()
    forum_groups = data.get("forum_groups", [])
    raw_map      = data.get("saved_map", {})
    saved_map    = {int(k): set(v) for k, v in raw_map.items()}
    page         = data.get("page", 0)

    expanded_groups = set(data.get("expanded_groups", []))
    if gid in expanded_groups:
        expanded_groups.discard(gid)
    else:
        expanded_groups.add(gid)

    await state.update_data(expanded_groups=list(expanded_groups))
    try:
        await cb.message.edit_reply_markup(
            reply_markup=kb_topic_groups(forum_groups, saved_map, expanded_groups, page)
        )
    except Exception:
        pass
    await cb.answer()


@router.callback_query(F.data.startswith("tgtoggle:"), S.topic_selecting)
async def cb_tgtoggle(cb: CallbackQuery, state: FSMContext) -> None:
    if not has_access(cb.from_user.id):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    try:
        _, gid_s, tid_s = cb.data.split(":")
        gid = int(gid_s); tid = int(tid_s)
    except (ValueError, TypeError):
        await cb.answer("⚠️ Invalid toggle.", show_alert=True); return

    data         = await state.get_data()
    forum_groups = data.get("forum_groups", [])
    raw_map      = data.get("saved_map", {})
    expanded     = set(data.get("expanded_groups", []))
    page         = data.get("page", 0)
    saved_map: dict[int, set[int]] = {int(k): set(v) for k, v in raw_map.items()}
    bucket = saved_map.setdefault(gid, set())
    if tid in bucket:
        bucket.discard(tid)
    else:
        bucket.add(tid)
    await state.update_data(saved_map={k: list(v) for k, v in saved_map.items()})
    try:
        await cb.message.edit_reply_markup(reply_markup=kb_topic_groups(forum_groups, saved_map, expanded, page))
    except Exception:
        pass
    await cb.answer()


@router.callback_query(F.data.startswith("tgpage:"), S.topic_selecting)
async def cb_tgpage(cb: CallbackQuery, state: FSMContext) -> None:
    if not has_access(cb.from_user.id):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    try:
        page = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer(); return
    data         = await state.get_data()
    forum_groups = data.get("forum_groups", [])
    raw_map      = data.get("saved_map", {})
    saved_map    = {int(k): set(v) for k, v in raw_map.items()}
    expanded     = set(data.get("expanded_groups", []))
    await state.update_data(page=page)
    try:
        await cb.message.edit_reply_markup(reply_markup=kb_topic_groups(forum_groups, saved_map, expanded, page))
    except Exception:
        pass
    await cb.answer()


@router.callback_query(F.data == "tgrefresh", S.topic_selecting)
async def cb_tgrefresh(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer("🔄 Refreshing topics from Telegram…")

    account_mgr  = UserManager.get_account_mgr(uid)
    tl_client    = await account_mgr.get_active_client()
    if not tl_client:
        await cb.answer("⚠️ No active Telethon account.", show_alert=True); return

    # Fetch all groups again
    all_groups = await _fetch_all_groups_unified(tl_client)
    store = UserManager.get_store(uid)
    await store.set("auto_groups", all_groups)

    # Rebuild forum_groups map
    fg_map = {}
    for g in all_groups:
        if g.get("is_forum", False):
            gid = g["id"]
            if gid not in fg_map:
                fg_map[gid] = {"id": gid, "title": g["title"], "topic_list": []}
            if g.get("topic_id") is not None:
                fg_map[gid]["topic_list"].append({
                    "id": g["topic_id"],
                    "title": g.get("topic_title") or str(g["topic_id"])
                })

    # Filter out empty ones
    forum_groups = [grp for grp in fg_map.values() if grp["topic_list"]]

    if not forum_groups:
        await _edit_or_send(cb, "❌ <b>No topic-enabled groups found after refresh.</b>", kb_back())
        await state.clear(); return

    data      = await state.get_data()
    raw_map   = data.get("saved_map", {})
    saved_map = {int(k): set(v) for k, v in raw_map.items()}
    expanded  = set(data.get("expanded_groups", []))

    await state.update_data(forum_groups=forum_groups, page=0)

    total_topics = sum(len(grp["topic_list"]) for grp in forum_groups)
    text = (
        f"📌 <b>Topic Groups Selection</b>\n\n"
        f"✅ <b>Found {len(forum_groups)} groups and {total_topics} topics.</b>\n"
        "📦 Tap a group to expand and view its topics.\n"
        "✅ Tap a topic to toggle selection.\n\n"
        "<i>Counted per topic, not per group.</i>"
    )

    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb_topic_groups(forum_groups, saved_map, expanded, 0))
    except Exception:
        pass


@router.callback_query(F.data == "tgall", S.topic_selecting)
async def cb_tgall(cb: CallbackQuery, state: FSMContext) -> None:
    if not has_access(cb.from_user.id):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    data = await state.get_data()
    forum_groups = data.get("forum_groups", [])
    expanded = set(data.get("expanded_groups", []))
    page = data.get("page", 0)

    saved_map = {}
    for grp in forum_groups:
        gid = grp["id"]
        topics = grp.get("topic_list", [])
        saved_map[gid] = {t["id"] for t in topics}

    await state.update_data(saved_map={k: list(v) for k, v in saved_map.items()})
    try:
        await cb.message.edit_reply_markup(reply_markup=kb_topic_groups(forum_groups, saved_map, expanded, page))
    except Exception:
        pass
    await cb.answer("✅ Selected all topics.")


@router.callback_query(F.data == "tgnone", S.topic_selecting)
async def cb_tgnone(cb: CallbackQuery, state: FSMContext) -> None:
    if not has_access(cb.from_user.id):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    data = await state.get_data()
    forum_groups = data.get("forum_groups", [])
    expanded = set(data.get("expanded_groups", []))
    page = data.get("page", 0)

    saved_map = {}
    await state.update_data(saved_map={})
    try:
        await cb.message.edit_reply_markup(reply_markup=kb_topic_groups(forum_groups, saved_map, expanded, page))
    except Exception:
        pass
    await cb.answer("❌ Deselected all topics.")
@router.callback_query(F.data == "tgsave", S.topic_selecting)
async def cb_tgsave(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    data         = await state.get_data()
    forum_groups = data.get("forum_groups", [])
    raw_map      = data.get("saved_map", {})
    saved_map    = {int(k): set(v) for k, v in raw_map.items()}

    # Calculate total topics selected (each topic = 1 count)
    total_selected = sum(len(tids) for tids in saved_map.values())

    title_map    = {grp["id"]: grp["title"] for grp in forum_groups}
    topic_groups = [
        {"id": gid, "title": title_map.get(gid, str(gid)), "topics": sorted(tids)}
        for gid, tids in saved_map.items() if tids
    ]
    store = UserManager.get_store(uid)
    await store.set("topic_groups", topic_groups)
    await store.set("broadcast_mode", "topic")
    await state.clear()
    await _edit_or_send(
        cb,
        f"✅ <b>Topic groups saved!</b>\n\n"
        f"<b>{len(topic_groups)}</b> group(s), <b>{total_selected}</b> topic(s) selected.\n"
        "Broadcast mode set to <b>Topic Groups</b>.",
        kb_back(),
    )
    await cb.answer()


@router.callback_query(F.data == "tgcancel", S.topic_selecting)
async def cb_tgcancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit_or_send(cb, "❌ Topic selection cancelled.", kb_back())
    await cb.answer()

# _fetch_forum_groups removed in favor of _fetch_all_groups_unified

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MESSAGE SETTING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == "m:set_msg")
async def cb_set_msg_prompt(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    store = UserManager.get_store(uid)
    current = await store.get("message", "")
    preview = f"\n\n<b>Current:</b>\n<code>{current[:200]}</code>" if current else ""
    fwd_status = ""
    if await store.get("forward_mode", False):
        fwd_ch = await store.get("forward_channel_id")
        fwd_msg = await store.get("forward_message_id")
        fwd_status = f"\n\n📢 <b>Saved Channel Post:</b> channel <code>{fwd_ch}</code> msg <code>{fwd_msg}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [create_button("Forward From Channel", "broadcast", "m:forward_channel", style="PRIMARY")],
        [create_button("Cancel",               "cancel",    "m:main",            style="DANGER")],
    ])
    await _edit_or_send(
        cb,
        f"✏️ <b>Set Message</b>{preview}{fwd_status}\n\n"
        "Send your new <b>text message</b> (HTML supported),\n"
        "or tap 📢 to save a <b>channel post</b> for forwarding.",
        kb,
    )
    await state.set_state(S.msg)
    await cb.answer()


@router.message(S.msg)
async def handle_msg(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    if not has_access(uid):
        return
    store = UserManager.get_store(uid)

    # ── Detect media (photo, video, document, animation) ──────────
    media_type: str | None = None
    media_obj = None
    if message.photo:
        media_type = "photo"
        media_obj = message.photo[-1]   # largest resolution
    elif message.video:
        media_type = "video"
        media_obj = message.video
    elif message.animation:
        media_type = "animation"
        media_obj = message.animation
    elif message.document:
        media_type = "document"
        media_obj = message.document

    # ── Extract text with full HTML entity preservation ───────────
    # html_text / caption reconstruction preserves bold, italic,
    # links, custom/premium emojis (<tg-emoji>), etc.
    if media_type:
        text = _caption_to_html(message) or ""
    else:
        text = message.html_text or ""
    text = text.strip()

    # Reject only if BOTH text and media are absent
    if not text and not media_type:
        await message.reply("⚠️ Empty message not allowed.")
        return

    # ── Save media file locally ───────────────────────────────────
    media_file_path: str | None = None
    if media_type and media_obj:
        media_dir = USER_DATA_DIR / str(uid) / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        ext = {"photo": ".jpg", "video": ".mp4", "animation": ".mp4", "document": ".bin"}.get(media_type, ".bin")
        dest = media_dir / f"broadcast_media{ext}"
        await message.bot.download(media_obj, destination=dest)
        media_file_path = str(dest)
        log.info("[User %s] Saved %s to %s", uid, media_type, dest)

    await store.update({
        "message":         text,
        "media_type":      media_type,
        "media_file_path": media_file_path,
    })
    await state.clear()
    label = media_type.capitalize() if media_type else "Message"
    caption_note = " with caption" if media_type and text else ""
    await message.answer(
        f"✅ <b>{label}{caption_note} saved.</b>",
        parse_mode="HTML", reply_markup=kb_back(),
    )


# ── FORWARD FROM CHANNEL ─────────────────────────────────────────

@router.callback_query(F.data == "m:forward_channel")
async def cb_forward_from_channel(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await state.set_state(S.forward_msg)
    await _edit_or_send(
        cb,
        "📢 <b>Forward From Channel</b>\n\n"
        "Forward a message from a channel where the bot/account is admin.\n\n"
        "The post will be saved and broadcast exactly as the original "
        "(premium emojis, media, formatting preserved).",
        kb_cancel(),
    )
    await cb.answer()


@router.message(S.forward_msg)
async def handle_forward_msg(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    if not has_access(uid):
        return

    # 1. Auto-detect source channel + message + public/private from aiogram
    #    forward metadata. aiogram v3 uses MessageOriginChannel; older Bot
    #    API clients populate forward_from_chat — support both.
    channel_id: int | None = None
    message_id: int | None = None
    channel_username: str | None = None
    chat_title: str | None = None

    origin = message.forward_origin
    if isinstance(origin, MessageOriginChannel):
        channel_id       = origin.chat.id
        message_id       = origin.message_id
        channel_username = origin.chat.username
        chat_title       = getattr(origin.chat, "title", None)
    elif message.forward_from_chat and message.forward_from_message_id:
        channel_id       = message.forward_from_chat.id
        message_id       = message.forward_from_message_id
        channel_username = message.forward_from_chat.username
        chat_title       = getattr(message.forward_from_chat, "title", None)

    is_public = bool(channel_username)

    if not channel_id or not message_id:
        await message.reply(
            "⚠️ <b>That isn't a forwarded channel post.</b>\n\n"
            "Use Telegram's <b>Forward</b> action on a post from the channel "
            "you want to broadcast. Don't paste a link, copy the text, or send a screenshot.",
            parse_mode="HTML",
        )
        return

    # 2. Verify a Telethon account is available — we need it to validate the
    #    source and to native-forward in the broadcast loop.
    account_mgr = UserManager.get_account_mgr(uid)
    tl_client = await account_mgr.get_active_client()
    if not tl_client:
        await message.reply(
            "⚠️ <b>No active Telethon account.</b>\n\n"
            "Add one via 👤 Accounts first — forwarding requires a user session.",
            parse_mode="HTML", reply_markup=kb_back(),
        )
        await state.clear()
        return

    # 3. Resolve the source: entity + access + album detection in one pass.
    entity, album_ids, status = await _resolve_forward_source(
        tl_client, channel_id, message_id,
    )

    if status == "no_access":
        active_phone = account_mgr.get_active_phone() or "—"
        privacy_note = "private" if not is_public else "restricted"
        await message.reply(
            f"⚠️ <b>Can't access that channel.</b>\n\n"
            f"It looks <b>{privacy_note}</b>, and your active Telethon account "
            f"(<code>{active_phone}</code>) isn't a member, so it can't read the "
            f"original post.\n\n<b>Two ways to fix this:</b>\n"
            f"1️⃣ Add that account into the channel/group, then forward the post again.\n"
            f"2️⃣ Forward the post here once more — native forwarding will still work "
            f"as long as the channel doesn't have <i>Restrict saving content</i> enabled.\n\n"
            f"<i>Tip: channels with \"Restrict saving content\" only let members "
            f"rebroadcast. Joining as the account above is the safest path.</i>",
            parse_mode="HTML", reply_markup=kb_back(),
        )
        await state.clear()
        return

    if status == "message_missing":
        await message.reply(
            "⚠️ <b>That post no longer exists.</b>\n\n"
            "The original message was deleted or is hidden from your account. "
            "Forward a different post.",
            parse_mode="HTML", reply_markup=kb_back(),
        )
        await state.clear()
        return

    if status.startswith("error:") or entity is None or not album_ids:
        detail = status[6:] if status.startswith("error:") else "unknown"
        await message.reply(
            f"⚠️ <b>Couldn't validate the source post.</b>\n\n"
            f"<code>{detail}</code>\n\nTry again in a moment.",
            parse_mode="HTML", reply_markup=kb_back(),
        )
        await state.clear()
        return

    # 4. Save forward data + clear any stale 'invalid' flag.
    ch_title = chat_title or getattr(entity, "title", str(channel_id))
    store = UserManager.get_store(uid)
    await store.update({
        "forward_mode":             True,
        "forward_channel_id":       channel_id,
        "forward_message_id":       message_id,
        "forward_channel_username": channel_username,
        "forward_channel_title":    ch_title,
        "forward_is_public":        is_public,
        "forward_album_ids":        album_ids,
        "forward_source_invalid":   False,
    })
    _forward_entities[uid] = entity

    await state.clear()
    album_note = (
        f"\n🖼 <b>Album:</b> {len(album_ids)} items (forwarded as one media group)"
        if len(album_ids) > 1 else ""
    )
    visibility = "🌐 Public" if is_public else "🔒 Private"
    username_line = (
        f"\n🔗 <code>@{channel_username}</code>" if channel_username else ""
    )
    await message.answer(
        f"✅ <b>Channel post saved successfully.</b>\n\n"
        f"📢 <b>{ch_title}</b> ({visibility})\n"
        f"🆔 Channel: <code>{channel_id}</code>"
        f"{username_line}\n"
        f"📨 Message ID: <code>{message_id}</code>"
        f"{album_note}\n\n"
        f"It will be rebroadcast natively — every entity, premium emoji, "
        f"caption, and media item is preserved exactly.",
        parse_mode="HTML", reply_markup=kb_back(),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  INTERVAL SETTING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == "m:set_interval")
async def cb_set_interval_prompt(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    store = UserManager.get_store(uid)
    current = await store.get("interval_seconds", 300)
    await _edit_or_send(
        cb,
        f"⏱ <b>Set Interval</b>\n\nCurrent: <code>{current}s</code> ({current // 60}m {current % 60}s)\n\n"
        "Send new interval in <b>seconds</b> (min: 10).\nExample: <code>300</code> = 5 minutes.",
        kb_cancel(),
    )
    await state.set_state(S.interval)
    await cb.answer()


@router.message(S.interval)
async def handle_interval(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    if not has_access(uid):
        return
    try:
        secs = int(message.text.strip())
        if secs < 10:
            await message.reply("⚠️ Minimum 10 seconds."); return
    except ValueError:
        await message.reply("⚠️ Send a number (seconds). E.g. <code>300</code>", parse_mode="HTML"); return
    store = UserManager.get_store(uid)
    await store.set("interval_seconds", secs)
    await state.clear()
    note = ""
    if Sched.is_loop_running(uid):
        # FIXED — pass phone to add_loop (was missing, would cause TypeError)
        account_mgr = UserManager.get_account_mgr(uid)
        phone = account_mgr.get_active_phone()
        if phone:
            await Sched.add_loop(message.bot, uid, secs, phone)
            note = "\n🔄 Running loop updated with new interval."
    await message.answer(
        f"✅ Interval set to <code>{secs}s</code>.{note}",
        parse_mode="HTML", reply_markup=kb_back(),
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DELAY SETTING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == "m:set_delay")
async def cb_set_delay_prompt(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    store = UserManager.get_store(uid)
    s = await store.all()
    imm = s.get("immediate_send", False)
    imm_label = f"Immediate Send: {'ON' if imm else 'OFF'}"
    imm_cb = "delay:imm_off" if imm else "delay:imm_on"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [create_button(imm_label, "bolt" if imm else "timer", imm_cb, style="SUCCESS" if imm else "SECONDARY")],
        [create_button("Cancel", "cancel", "m:main", style="DANGER")],
    ])
    await _edit_or_send(
        cb,
        f"⏳ <b>Set Delay</b>\n\n"
        f"Base: <code>{s.get('delay_between_sends', 3)}s</code>  "
        f"Random: <code>{'ON' if s.get('random_delay') else 'OFF'}</code>  "
        f"({s.get('random_delay_min', 2.0)}–{s.get('random_delay_max', 8.0)}s)\n"
        f"Immediate: <code>{'ON' if imm else 'OFF'}</code>\n\n"
        "Commands:\n"
        "• <code>5</code>          → base delay = 5s\n"
        "• <code>random on</code>  → enable random delay\n"
        "• <code>random off</code> → disable random delay\n"
        "• <code>range 2 8</code>  → random range 2–8s",
        kb,
    )
    await state.set_state(S.delay)
    await cb.answer()


@router.message(S.delay)
async def handle_delay(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    if not has_access(uid):
        return
    text   = message.text.strip().lower()
    update: dict = {}
    if text == "random on":
        update["random_delay"] = True
        reply = "✅ Random delay <b>enabled</b>."
    elif text == "random off":
        update["random_delay"] = False
        reply = "✅ Random delay <b>disabled</b>."
    elif text.startswith("range "):
        parts = text.split()
        if len(parts) == 3:
            try:
                lo, hi = float(parts[1]), float(parts[2])
                if lo >= hi:
                    await message.reply("⚠️ Min must be less than max."); return
                update.update({"random_delay_min": lo, "random_delay_max": hi})
                reply = f"✅ Random range: <code>{lo}–{hi}s</code>."
            except ValueError:
                await message.reply("⚠️ Format: <code>range 2 8</code>", parse_mode="HTML"); return
        else:
            await message.reply("⚠️ Format: <code>range 2 8</code>", parse_mode="HTML"); return
    else:
        try:
            delay = int(text)
            if delay < 0:
                await message.reply("⚠️ Delay must be ≥ 0."); return
            update["delay_between_sends"] = delay
            reply = f"✅ Base delay set to <code>{delay}s</code>."
        except ValueError:
            await message.reply(
                "⚠️ Unrecognised. Send a number, <code>random on/off</code>, or <code>range 2 8</code>.",
                parse_mode="HTML"
            ); return
    store = UserManager.get_store(uid)
    await store.update(update)
    await state.clear()
    await message.answer(reply, parse_mode="HTML", reply_markup=kb_back())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  IMMEDIATE SEND TOGGLE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(F.data == "delay:imm_on")
async def cb_imm_on(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    await state.clear()

    # Check group count for 100+ warning
    store = UserManager.get_store(uid)
    settings = await store.all()
    bmode = settings.get("broadcast_mode", "selected")
    if bmode == "topic":
        count = sum(len(g.get("topics", [])) or 1 for g in settings.get("topic_groups", []))
    elif bmode == "both":
        ids = {f"{g['id']}_{t}" for g in settings.get("topic_groups", []) for t in (g.get("topics", []) or [None])} | {f"{g['id']}_None" for g in settings.get("selected_groups", [])}
        count = len(ids)
    else:
        count = len(settings.get("selected_groups", []))

    if count >= 100:
        kb_warn = InlineKeyboardMarkup(inline_keyboard=[
            [create_button("Yes, Continue", "confirm", "delay:imm_confirm", style="SUCCESS")],
            [create_button("Cancel",        "cancel",  "m:main",             style="DANGER")],
        ])
        await _edit_or_send(
            cb,
            f"⚠️ <b>Warning!</b>\n\n"
            f"You are about to send to <b>{count}</b> groups instantly.\n"
            "This may cause flood or account ban.\n\n"
            "Are you sure?",
            kb_warn,
        )
        return

    await store.set("immediate_send", True)
    await _edit_or_send(
        cb,
        "⚡ Immediate Send <b>ENABLED</b>.\n\n"
        "All delays between groups will be skipped.\n"
        "After finishing a round → wait for interval → next round.",
        kb_back(),
    )


@router.callback_query(F.data == "delay:imm_confirm")
async def cb_imm_confirm(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    store = UserManager.get_store(uid)
    await store.set("immediate_send", True)
    await _edit_or_send(
        cb,
        "⚡ Immediate Send <b>ENABLED</b> (100+ confirmed).\n\n"
        "All delays between groups will be skipped.",
        kb_back(),
    )


@router.callback_query(F.data == "delay:imm_off")
async def cb_imm_off(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    await state.clear()
    store = UserManager.get_store(uid)
    await store.set("immediate_send", False)
    await _edit_or_send(
        cb,
        "⚡ Immediate Send <b>DISABLED</b>.\n\n"
        "Normal delay between groups will be used.",
        kb_back(),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FETCH GROUP SETTING  (per-account)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(F.data == "m:set_fetch_group")
async def cb_set_fetch_group(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()

    account_mgr = UserManager.get_account_mgr(uid)
    phone = account_mgr.get_active_phone()
    if not phone:
        await _edit_or_send(
            cb,
            "⚠️ <b>No active account.</b>\n\nAdd an account via 👤 Accounts first.",
            kb_back(),
        )
        return

    store = UserManager.get_store(uid)
    fmap = await store.get("fetch_group_account_map", {})
    existing = fmap.get(phone)

    if existing:
        kb_fg = InlineKeyboardMarkup(inline_keyboard=[
            [create_button("Use Existing", "confirm", "fg:use_existing", style="SUCCESS")],
            [create_button("Set New",      "edit",    "fg:set_new",      style="PRIMARY")],
            [create_button("Back",         "back",    "m:main",          style="SECONDARY")],
        ])
        await _edit_or_send(
            cb,
            f"📡 <b>Fetch Group for {phone}</b>\n\n"
            f"Already set: <code>{existing}</code>\n\n"
            "Use existing or set new?",
            kb_fg,
        )
    else:
        await _edit_or_send(
            cb,
            f"📡 <b>Set Fetch Group for {phone}</b>\n\n"
            "Send the group ID where process updates and errors will be sent.\n"
            "Example: <code>-1001234567890</code>\n\n"
            "⚠️ Make sure the bot is an <b>admin</b> in that group.",
            kb_cancel(),
        )
        await state.set_state(S.fetch_group_set)


@router.callback_query(F.data == "fg:use_existing")
async def cb_fg_use_existing(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer("✅ Using existing fetch group.")
    await _edit_or_send(
        cb,
        "✅ <b>Fetch Group kept.</b>\n\nNo changes made.",
        kb_back(),
    )


@router.callback_query(F.data == "fg:set_new")
async def cb_fg_set_new(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()

    account_mgr = UserManager.get_account_mgr(uid)
    phone = account_mgr.get_active_phone()
    await _edit_or_send(
        cb,
        f"📡 <b>Set New Fetch Group for {phone}</b>\n\n"
        "Send the group ID:\n"
        "Example: <code>-1001234567890</code>",
        kb_cancel(),
    )
    await state.set_state(S.fetch_group_set)


@router.message(S.fetch_group_set)
async def handle_fetch_group_id(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    if not has_access(uid):
        return
    raw = message.text.strip()
    try:
        gid = int(raw)
    except ValueError:
        await message.reply("⚠️ Invalid ID. Must be an integer like <code>-1001234567890</code>.", parse_mode="HTML")
        return

    account_mgr = UserManager.get_account_mgr(uid)
    phone = account_mgr.get_active_phone()
    if not phone:
        await message.reply("⚠️ No active account.", parse_mode="HTML")
        await state.clear()
        return

    store = UserManager.get_store(uid)
    fmap = await store.get("fetch_group_account_map", {})
    fmap[phone] = gid
    await store.set("fetch_group_account_map", fmap)
    await state.clear()
    await message.answer(
        f"✅ Fetch Group for <code>{phone}</code> saved: <code>{gid}</code>\n\n"
        "Process updates and errors will be sent to this group.",
        parse_mode="HTML",
        reply_markup=kb_back(),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SCHEDULER MENU
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data == "m:scheduler")
async def cb_scheduler(cb: CallbackQuery) -> None:
    if not has_access(cb.from_user.id):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await _edit_or_send(cb, "📅 <b>Scheduler</b>", kb_scheduler_menu())
    await cb.answer()


@router.callback_query(F.data == "sc:add")
async def cb_sc_add(cb: CallbackQuery, state: FSMContext) -> None:
    if not has_access(cb.from_user.id):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await state.set_state(S.sc_type)
    await _edit_or_send(cb, "➕ <b>Add Schedule</b>\n\nSelect type:", kb_sched_type())
    await cb.answer()


# Interval schedule
@router.callback_query(F.data == "sctype:interval", S.sc_type)
async def cb_sc_interval_type(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(stype="interval")
    await state.set_state(S.sc_intv)
    await _edit_or_send(cb, "🔁 Send interval in <b>minutes</b>. E.g. <code>30</code>", kb_cancel())
    await cb.answer()


@router.message(S.sc_intv)
async def handle_sc_intv(message: Message, state: FSMContext) -> None:
    if not has_access(message.from_user.id):
        return
    try:
        mins = int(message.text.strip())
        if mins < 1:
            await message.reply("⚠️ Minimum 1 minute."); return
    except ValueError:
        await message.reply("⚠️ Send a number."); return
    sched = {"id": _uid(), "type": "interval", "interval_minutes": mins, "enabled": True}
    await _save_sched(message, state, sched)


# Daily schedule
@router.callback_query(F.data == "sctype:daily", S.sc_type)
async def cb_sc_daily_type(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(stype="daily")
    await state.set_state(S.sc_daily)
    await _edit_or_send(cb, "📅 Send time as <code>HH:MM</code>. E.g. <code>09:30</code>", kb_cancel())
    await cb.answer()


@router.message(S.sc_daily)
async def handle_sc_daily(message: Message, state: FSMContext) -> None:
    if not has_access(message.from_user.id):
        return
    t = message.text.strip()
    if not _valid_time(t):
        await message.reply("⚠️ Invalid time. Use <code>HH:MM</code>.", parse_mode="HTML"); return
    sched = {"id": _uid(), "type": "daily", "time": t, "enabled": True}
    await _save_sched(message, state, sched)


# Weekly schedule
@router.callback_query(F.data == "sctype:weekly", S.sc_type)
async def cb_sc_weekly_type(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(stype="weekly", sel_days=[])
    await state.set_state(S.sc_wk_days)
    await _edit_or_send(cb, "📅 <b>Weekly Schedule</b>\n\nSelect days:", kb_days(set()))
    await cb.answer()


@router.callback_query(F.data.startswith("day:"), S.sc_wk_days)
async def cb_day_toggle(cb: CallbackQuery, state: FSMContext) -> None:
    try:
        day = int(cb.data.split(":")[1])
        if not (0 <= day <= 6):
            raise ValueError
    except (IndexError, ValueError):
        await cb.answer("⚠️ Invalid day.", show_alert=True); return
    data = await state.get_data()
    days = set(data.get("sel_days", []))
    days.symmetric_difference_update({day})
    await state.update_data(sel_days=list(days))
    await cb.message.edit_reply_markup(reply_markup=kb_days(days))
    await cb.answer()


@router.callback_query(F.data == "daysok", S.sc_wk_days)
async def cb_days_ok(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    days = data.get("sel_days", [])
    if not days:
        await cb.answer("Select at least one day.", show_alert=True); return
    await state.update_data(sel_days=days)
    await state.set_state(S.sc_wk_time)
    await _edit_or_send(cb, "📅 Send time as <code>HH:MM</code>. E.g. <code>08:00</code>", kb_cancel())
    await cb.answer()


@router.message(S.sc_wk_time)
async def handle_sc_wk_time(message: Message, state: FSMContext) -> None:
    if not has_access(message.from_user.id):
        return
    t = message.text.strip()
    if not _valid_time(t):
        await message.reply("⚠️ Invalid time. Use <code>HH:MM</code>.", parse_mode="HTML"); return
    data  = await state.get_data()
    sched = {"id": _uid(), "type": "weekly", "time": t, "days": data.get("sel_days", []), "enabled": True}
    await _save_sched(message, state, sched)


async def _save_sched(message: Message, state: FSMContext, sched: dict) -> None:
    uid = message.from_user.id
    store = UserManager.get_store(uid)
    schedules = await store.get("schedules", [])
    schedules.append(sched)
    await store.set("schedules", schedules)
    await Sched.add_schedule(message.bot, uid, sched)
    await state.clear()
    await message.answer(
        f"✅ Schedule <code>[{sched['id']}]</code> created.",
        parse_mode="HTML", reply_markup=kb_back(),
    )


# View schedules
@router.callback_query(F.data == "sc:view")
async def cb_sc_view(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    store = UserManager.get_store(uid)
    scheds = await store.get("schedules", [])
    if not scheds:
        await _edit_or_send(cb, "📋 No schedules configured.", kb_scheduler_menu())
        return
    lines = ["📋 <b>Active Schedules</b>\n"]
    for s in scheds:
        t = s["type"]
        if t == "interval":
            desc = f"Every {s.get('interval_minutes')}m"
        elif t == "daily":
            desc = f"Daily at {s.get('time')}"
        else:
            day_str = ", ".join(DAY_NAMES[d] for d in s.get("days", []))
            desc    = f"Weekly [{day_str}] at {s.get('time')}"
        icon = "✅" if s.get("enabled") else "⏸"
        lines.append(f"{icon} <code>[{s['id']}]</code> {desc}")
    await _edit_or_send(cb, "\n".join(lines), kb_scheduler_menu())


# Delete schedules
@router.callback_query(F.data == "sc:delete")
async def cb_sc_delete_list(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    store = UserManager.get_store(uid)
    scheds = await store.get("schedules", [])
    if not scheds:
        await cb.answer("No schedules to delete.", show_alert=True)
        return
    await cb.answer()
    await _show_sched_delete_list(cb, scheds)


async def _show_sched_delete_list(cb: CallbackQuery, scheds: list) -> None:
    """Render the schedule-delete list without calling cb.answer() (already answered)."""
    rows = []
    for s in scheds:
        t = s["type"]
        if t == "interval":
            label = f"🗑 [{s['id']}] Every {s.get('interval_minutes')}m"
        elif t == "daily":
            label = f"🗑 [{s['id']}] Daily {s.get('time')}"
        else:
            day_str = ",".join(DAY_NAMES[d] for d in s.get("days", []))
            label   = f"🗑 [{s['id']}] {day_str} {s.get('time')}"
        rows.append([create_button(label, "delete", f"scdel:{s['id']}", style="DANGER", emoji_on=False)])
    rows.append([create_button("Back", "back", "m:scheduler", style="SECONDARY")])
    await _edit_or_send(
        cb, "🗑 <b>Delete Schedule</b>\n\nTap to remove:",
        InlineKeyboardMarkup(inline_keyboard=rows)
    )


@router.callback_query(F.data.startswith("scdel:"))
async def cb_scdel(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    sid    = cb.data.split(":", 1)[1]
    store = UserManager.get_store(uid)
    scheds = await store.get("schedules", [])
    await store.set("schedules", [s for s in scheds if s["id"] != sid])
    await Sched.remove_schedule(uid, sid)
    await cb.answer(f"Deleted [{sid}].", show_alert=True)
    # Refresh the delete list directly (cb already answered — don't re-call the handler)
    remaining = [s for s in scheds if s["id"] != sid]
    if not remaining:
        await _edit_or_send(cb, "📋 No schedules left.", kb_scheduler_menu())
    else:
        await _show_sched_delete_list(cb, remaining)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOG FORWARDING ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Per-user task references for log forwarder
_log_tasks: dict[int, asyncio.Task] = {}
_log_lines_sent: dict[int, int] = {}


def _html_escape(text: str) -> str:
    """Safely escape text for Telegram HTML."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


async def log_forwarder(bot: Bot, user_id: int) -> None:
    """
    Background async task that tails bot.log and forwards new lines
    to the configured Telegram log group for a specific user.
    Only forwards lines tagged with [User <user_id>] — prevents
    cross-user log leakage.
    """
    _log_lines_sent[user_id] = 0

    store = UserManager.get_store(user_id)
    log_group_id: int | None = await store.get("log_group_id", None)
    if not log_group_id:
        log.warning("[LogFwd][User %s] No log_group_id set — forwarder exiting.", user_id)
        return

    log_path = Path(LOG_FILE)

    # Tag used to filter log lines belonging to THIS user only
    user_tag = f"[User {user_id}]"

    # Seek to current end of file so we only send NEW lines
    try:
        offset = log_path.stat().st_size if log_path.exists() else 0
    except Exception:
        offset = 0

    log.info("[LogFwd][User %s] Started. Tailing '%s' from offset %d → group %s", user_id, LOG_FILE, offset, log_group_id)

    try:
        while True:
            await asyncio.sleep(0.5)

            if not log_path.exists():
                continue

            try:
                current_size = log_path.stat().st_size
            except Exception:
                continue

            if current_size <= offset:
                # File may have been rotated/truncated
                if current_size < offset:
                    offset = 0
                continue

            try:
                with log_path.open("r", encoding="utf-8", errors="replace") as f:
                    f.seek(offset)
                    new_data = f.read()
                    offset = f.tell()
            except Exception as read_err:
                log.error("[LogFwd][User %s] Read error: %s", user_id, read_err)
                continue

            if not new_data:
                continue

            lines = new_data.splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # ── Per-user isolation: only forward lines for THIS user ──
                if user_tag not in line:
                    continue

                # Split long lines into ≤ 4000-char chunks (leaving room for <code> tags)
                chunks = [line[i:i + 4000] for i in range(0, len(line), 4000)]
                for chunk in chunks:
                    safe = _html_escape(chunk)
                    text = f"<code>{safe}</code>"
                    sent_ok = False
                    for attempt in range(3):
                        try:
                            await bot.send_message(
                                chat_id=log_group_id,
                                text=text,
                                parse_mode="HTML",
                            )
                            _log_lines_sent[user_id] = _log_lines_sent.get(user_id, 0) + 1
                            sent_ok = True
                            break
                        except TelegramRetryAfter as e:
                            wait_secs = e.retry_after + 1
                            log.warning("[LogFwd][User %s] FloodWait %ds — sleeping.", user_id, wait_secs)
                            await asyncio.sleep(wait_secs)
                        except TelegramForbiddenError:
                            log.error("[LogFwd][User %s] Bot removed from log group — stopping forwarder.", user_id)
                            await store.set("log_forwarding_enabled", False)
                            return
                        except TelegramBadRequest as e:
                            log.error("[LogFwd][User %s] BadRequest: %s", user_id, e)
                            break
                        except Exception as e:
                            log.error("[LogFwd][User %s] Send error (attempt %d): %s", user_id, attempt + 1, e)
                            await asyncio.sleep(1)

                    if not sent_ok:
                        log.error("[LogFwd][User %s] Failed to send line after retries — skipping.", user_id)

                    # Small delay between messages to avoid flood
                    await asyncio.sleep(random.uniform(0.3, 0.5))

    except asyncio.CancelledError:
        log.info("[LogFwd][User %s] Task cancelled — forwarder stopped.", user_id)
        raise


def _is_log_forwarding_active(user_id: int) -> bool:
    """Return True if the log_task for this user is running."""
    task = _log_tasks.get(user_id)
    return task is not None and not task.done()


async def _start_log_forwarder(bot: Bot, user_id: int) -> bool:
    """Start log forwarder for a user if not already running. Returns True on success."""
    if _is_log_forwarding_active(user_id):
        return False  # already running

    store = UserManager.get_store(user_id)
    log_group_id = await store.get("log_group_id", None)
    if not log_group_id:
        return False

    _task = asyncio.create_task(log_forwarder(bot, user_id), name=f"log_forwarder_{user_id}")
    _task.add_done_callback(
        lambda t: log.error("[LogFwd][User %s] task raised: %s", user_id, t.exception())
        if not t.cancelled() and t.exception() else None
    )
    _log_tasks[user_id] = _task
    await store.set("log_forwarding_enabled", True)
    log.info("[LogFwd][User %s] Task created.", user_id)
    return True


async def _stop_log_forwarder(user_id: int) -> bool:
    """Cancel log forwarder task for a user safely. Returns True if it was running."""
    if not _is_log_forwarding_active(user_id):
        return False
    task = _log_tasks[user_id]
    task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    _log_tasks.pop(user_id, None)
    store = UserManager.get_store(user_id)
    await store.set("log_forwarding_enabled", False)
    log.info("[LogFwd][User %s] Task stopped.", user_id)
    return True



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  (removed) Permission / plan / my_plan handlers — owner-only bot now.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.callback_query(F.data == "m:log_forwarding")
async def cb_log_forwarding_menu(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    store = UserManager.get_store(uid)
    group_id = await store.get("log_group_id", None)
    state_str = "🟢 Running" if _is_log_forwarding_active(uid) else "🔴 Stopped"
    group_str = f"<code>{group_id}</code>" if group_id else "⚠️ Not set"
    await _edit_or_send(
        cb,
        f"📡 <b>Log Forwarding</b>\n\n"
        f"Group: {group_str}\n"
        f"State: {state_str}",
        kb_log_forwarding_menu(),
    )


@router.callback_query(F.data == "lf:set_group")
async def cb_lf_set_group(cb: CallbackQuery, state: FSMContext) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    store = UserManager.get_store(uid)
    current = await store.get("log_group_id", None)
    current_str = f"\n\nCurrent: <code>{current}</code>" if current else ""
    await _edit_or_send(
        cb,
        f"🔧 <b>Set Log Group ID</b>{current_str}\n\n"
        "Send the Telegram group ID where logs should be forwarded.\n"
        "Example: <code>-1001234567890</code>\n\n"
        "⚠️ Make sure the bot is an <b>admin</b> in that group.",
        kb_cancel(),
    )
    await state.set_state(S.log_group_id)
    await cb.answer()


@router.message(S.log_group_id)
async def handle_lf_group_id(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    if not has_access(uid):
        return
    raw = message.text.strip()
    try:
        gid = int(raw)
    except ValueError:
        await message.reply("⚠️ Invalid ID. Must be an integer like <code>-1001234567890</code>.", parse_mode="HTML")
        return
    store = UserManager.get_store(uid)
    await store.set("log_group_id", gid)
    await state.clear()
    await message.answer(
        f"✅ Log Group ID saved: <code>{gid}</code>\n\n"
        "Now use <b>▶️ Start Log Forwarding</b> to begin.",
        parse_mode="HTML",
        reply_markup=kb_log_forwarding_menu(),
    )


@router.callback_query(F.data == "lf:start")
async def cb_lf_start(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return

    if _is_log_forwarding_active(uid):
        await cb.answer("Log forwarding is already running.", show_alert=True); return

    store = UserManager.get_store(uid)
    group_id = await store.get("log_group_id", None)
    if not group_id:
        await cb.answer("⚠️ Set a Log Group ID first.", show_alert=True); return

    ok = await _start_log_forwarder(cb.bot, uid)
    if ok:
        await _edit_or_send(
            cb,
            f"✅ <b>Log Forwarding started.</b>\n\n"
            f"Group: <code>{group_id}</code>\n"
            "New log lines will be sent in real-time.",
            kb_log_forwarding_menu(),
        )
        await cb.answer()
    else:
        await cb.answer("⚠️ Could not start forwarder. Check group ID.", show_alert=True)


@router.callback_query(F.data == "lf:stop")
async def cb_lf_stop(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return

    if not _is_log_forwarding_active(uid):
        await cb.answer("Log forwarding is not running.", show_alert=True); return

    await _stop_log_forwarder(uid)
    await _edit_or_send(cb, "⏹ <b>Log Forwarding stopped.</b>", kb_log_forwarding_menu())
    await cb.answer()


@router.callback_query(F.data == "lf:status")
async def cb_lf_status(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return

    store = UserManager.get_store(uid)
    group_id = await store.get("log_group_id", None)
    group_str = f"<code>{group_id}</code>" if group_id else "⚠️ Not set"
    state_str = "🟢 Running" if _is_log_forwarding_active(uid) else "🔴 Stopped"

    await _edit_or_send(
        cb,
        f"📡 <b>Log Forwarding Status</b>\n\n"
        f"Group: {group_str}\n"
        f"State: {state_str}\n"
        f"Lines Sent: <code>{_log_lines_sent.get(uid, 0)}</code>",
        kb_log_forwarding_menu(),
    )
    await cb.answer()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RESET HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _reset_json_for_user(user_id: int, phone: str | None = None) -> None:
    """
    Reset all JSON settings for a user to defaults.
    Does NOT touch accounts.json or session files.
    If phone is None, resets for all accounts.
    """
    store = UserManager.get_store(user_id)

    # Stop running loop
    # FIXED — use remove_all_loops instead of single-phone remove (was missing phone arg)
    await Sched.remove_all_loops(user_id)
    await store.set("loop_active", False)
    await store.set("loop_active_accounts", {})

    # Remove all scheduler jobs for this user
    schedules = await store.get("schedules", [])
    for s in schedules:
        await Sched.remove_schedule(user_id, s["id"])

    # Clear forward entity cache
    _forward_entities.pop(user_id, None)

    # Reset storage to defaults (preserves the Storage object reference)
    defaults = Storage._default()
    async with store._lock:
        store._data = defaults
        store._flush()

    log.info("[User %s] JSON reset completed (phone=%s).", user_id, phone or "all")


async def _reset_session_for_user(user_id: int, phone: str) -> None:
    """
    Remove a single Telegram session file and disconnect the client.
    Does NOT delete the account entry from accounts.json.
    Does NOT touch JSON settings.
    """
    account_mgr = UserManager.get_account_mgr(user_id)

    # Disconnect client if cached
    if phone in account_mgr._clients:
        try:
            await account_mgr._clients[phone].disconnect()
        except Exception as e:
            # FIXED — log instead of silent swallow
            log.warning("[User %s] disconnect() failed for %s during reset: %s", user_id, phone, e)
        del account_mgr._clients[phone]

    # FIXED — Delete BOTH .session AND .session-journal files
    sess_base = account_mgr._session_path(phone)
    for suffix in (".session", ".session-journal"):
        p = Path(sess_base + suffix)
        if p.exists():
            try:
                p.unlink(missing_ok=True)
            except Exception as e:
                log.error("[User %s] Failed to delete %s: %s", user_id, p, e)

    log.info("[User %s] Session reset for %s.", user_id, phone)


async def _reset_all_sessions_for_user(user_id: int) -> None:
    """Reset sessions for ALL accounts of a user."""
    account_mgr = UserManager.get_account_mgr(user_id)
    for acc in account_mgr.get_accounts():
        await _reset_session_for_user(user_id, acc["phone"])


async def _reset_all_for_user(user_id: int, phone: str | None = None) -> None:
    """
    Full reset: sessions + JSON + accounts.json entry.
    If phone is None, resets everything for all accounts.
    """
    account_mgr = UserManager.get_account_mgr(user_id)

    # Stop loop immediately
    store = UserManager.get_store(user_id)
    # FIXED — use remove_all_loops (was missing phone arg)
    await Sched.remove_all_loops(user_id)
    await store.set("loop_active", False)
    await store.set("loop_active_accounts", {})

    # Remove all scheduler jobs
    schedules = await store.get("schedules", [])
    for s in schedules:
        await Sched.remove_schedule(user_id, s["id"])

    # Stop log forwarder if running
    await _stop_log_forwarder(user_id)

    # Clear forward entity cache
    _forward_entities.pop(user_id, None)

    # FIXED — Clean all runtime caches
    _cleanup_runtime_caches(user_id)

    if phone:
        # Reset single account session
        await _reset_session_for_user(user_id, phone)
        # Remove from accounts.json
        account_mgr._data["accounts"] = [
            a for a in account_mgr._data["accounts"] if a["phone"] != phone
        ]
        if account_mgr._data.get("active_phone") == phone:
            remaining = account_mgr._data["accounts"]
            account_mgr._data["active_phone"] = remaining[0]["phone"] if remaining else None
        account_mgr._save()
    else:
        # Reset ALL sessions
        await _reset_all_sessions_for_user(user_id)
        # Clear accounts.json
        account_mgr._data = {"accounts": [], "active_phone": None}
        account_mgr._save()

    # Reset storage to defaults
    defaults = Storage._default()
    async with store._lock:
        store._data = defaults
        store._flush()

    log.info("[User %s] FULL reset completed (phone=%s).", user_id, phone or "all")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RESET MENU HANDLERS

@router.callback_query(F.data == "m:reset")
async def cb_reset_menu(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    await _edit_or_send(
        cb,
        "🗑 <b>Reset Menu</b>\n\n"
        "Choose what you want to reset.\n"
        "All destructive actions will ask for confirmation first.",
        kb_reset_menu(),
    )


@router.callback_query(F.data == "rst:json")
async def cb_reset_json(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    account_mgr = UserManager.get_account_mgr(uid)
    accounts = account_mgr.get_accounts()
    explanation = RESET_EXPLANATIONS["json"]
    if len(accounts) <= 1:
        # Single account or no accounts → direct confirmation
        phone = accounts[0]["phone"] if accounts else "__none__"
        label = f"{accounts[0]['name']}  ({accounts[0]['phone']})" if accounts else "(no accounts)"
        await _edit_or_send(
            cb,
            f"{explanation}\n\n⚠️ Are you sure you want to reset JSON for:\n<b>{label}</b> ?",
            kb_reset_confirm("json", phone),
        )
    else:
        await _edit_or_send(
            cb,
            f"{explanation}\n\nWhich account do you want to apply this reset to?",
            kb_reset_account_list(accounts, "json"),
        )


@router.callback_query(F.data == "rst:session")
async def cb_reset_session(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    account_mgr = UserManager.get_account_mgr(uid)
    accounts = account_mgr.get_accounts()
    explanation = RESET_EXPLANATIONS["session"]
    if not accounts:
        await _edit_or_send(cb, "⚠️ No accounts found.", kb_reset_menu())
        return
    if len(accounts) == 1:
        phone = accounts[0]["phone"]
        label = f"{accounts[0]['name']}  ({phone})"
        await _edit_or_send(
            cb,
            f"{explanation}\n\n⚠️ Are you sure you want to reset session for:\n<b>{label}</b> ?",
            kb_reset_confirm("session", phone),
        )
    else:
        await _edit_or_send(
            cb,
            f"{explanation}\n\nWhich account session do you want to reset?",
            kb_reset_account_list(accounts, "session"),
        )


@router.callback_query(F.data == "rst:all")
async def cb_reset_all(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    account_mgr = UserManager.get_account_mgr(uid)
    accounts = account_mgr.get_accounts()
    explanation = RESET_EXPLANATIONS["all"]
    if len(accounts) <= 1:
        phone = accounts[0]["phone"] if accounts else "__none__"
        label = f"{accounts[0]['name']}  ({accounts[0]['phone']})" if accounts else "(all data)"
        await _edit_or_send(
            cb,
            f"{explanation}\n\n⚠️ FINAL CONFIRMATION:\n"
            f"Are you absolutely sure you want to RESET EVERYTHING for:\n<b>{label}</b> ?",
            kb_reset_confirm("all", phone),
        )
    else:
        await _edit_or_send(
            cb,
            f"{explanation}\n\nApply reset to which account?",
            kb_reset_account_list(accounts, "all"),
        )


# ── Account picker → ask confirmation ─────────────────────────────
@router.callback_query(F.data.startswith("rstpick:"))
async def cb_reset_pick_account(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    _, action, phone = cb.data.split(":", 2)
    account_mgr = UserManager.get_account_mgr(uid)
    acc = next((a for a in account_mgr.get_accounts() if a["phone"] == phone), None)
    if not acc:
        await _edit_or_send(cb, "⚠️ Account not found.", kb_reset_menu())
        return
    label = f"{acc['name']}  ({acc['phone']})"
    if action == "all":
        await _edit_or_send(
            cb,
            f"⚠️ FINAL CONFIRMATION:\nAre you absolutely sure you want to "
            f"RESET EVERYTHING for:\n<b>{label}</b> ?",
            kb_reset_confirm(action, phone),
        )
    else:
        await _edit_or_send(
            cb,
            f"⚠️ Are you sure you want to reset {action} for:\n<b>{label}</b> ?",
            kb_reset_confirm(action, phone),
        )


# ── "Reset All Accounts" picker ───────────────────────────────────
@router.callback_query(F.data.startswith("rstpickall:"))
async def cb_reset_pick_all(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    action = cb.data.split(":", 1)[1]
    if action == "all":
        await _edit_or_send(
            cb,
            "⚠️ FINAL CONFIRMATION:\nAre you absolutely sure you want to "
            "RESET EVERYTHING for <b>ALL accounts</b> ?",
            kb_reset_confirm(action, "__all__"),
        )
    else:
        await _edit_or_send(
            cb,
            f"⚠️ Are you sure you want to reset {action} for <b>ALL accounts</b> ?",
            kb_reset_confirm(action, "__all__"),
        )


# ── Confirmation: YES ─────────────────────────────────────────────
@router.callback_query(F.data.startswith("rstyes:"))
async def cb_reset_confirm_yes(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    if not has_access(uid):
        await cb.answer("❌ Unauthorized.", show_alert=True); return
    await cb.answer()
    _, action, target = cb.data.split(":", 2)

    if action == "json":
        if target == "__all__" or target == "__none__":
            await _reset_json_for_user(uid)
        else:
            await _reset_json_for_user(uid, target)
        await _edit_or_send(
            cb,
            "✅ <b>JSON data has been reset.</b>\n\n"
            "All settings restored to defaults.\n"
            "Account sessions remain intact.",
            kb_reset_menu(),
        )

    elif action == "session":
        if target == "__all__":
            await _reset_all_sessions_for_user(uid)
        else:
            await _reset_session_for_user(uid, target)
        await _edit_or_send(
            cb,
            "✅ <b>Session(s) have been reset.</b>\n\n"
            "Session files removed. You will need to re-login.\n"
            "JSON settings remain intact.",
            kb_reset_menu(),
        )

    elif action == "all":
        if target == "__all__" or target == "__none__":
            await _reset_all_for_user(uid)
        else:
            await _reset_all_for_user(uid, target)
        await _edit_or_send(
            cb,
            "✅ <b>Full reset completed.</b>\n\n"
            "All data has been cleared.\n"
            "Sessions removed, settings restored to defaults.",
            kb_reset_menu(),
        )


# ── Confirmation: NO → back to Reset Menu ─────────────────────────
@router.callback_query(F.data == "rstno")
async def cb_reset_confirm_no(cb: CallbackQuery) -> None:
    await cb.answer()
    await _edit_or_send(
        cb,
        "🗑 <b>Reset Menu</b>\n\n"
        "Choose what you want to reset.\n"
        "All destructive actions will ask for confirmation first.",
        kb_reset_menu(),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DASHBOARD INTEGRATION  —  non-blocking FastAPI server
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

async def _start_dashboard() -> None:
    """Start dashboard server as non-blocking background task."""
    try:
        from dashboard.runner import dashboard_server
        from dashboard.services.accounts import account_service
        import sys as _s
        # Pass reference to this module so dashboard can access UserManager etc.
        _this_module = _s.modules[__name__]
        account_service.set_bot_reference(_this_module)
        await dashboard_server.start()
    except Exception as e:
        log.warning("Dashboard failed to start (non-critical): %s", e)


async def _stop_dashboard() -> None:
    """Stop dashboard server gracefully."""
    try:
        from dashboard.runner import dashboard_server
        await dashboard_server.stop()
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def main() -> None:
    errors = []
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        errors.append("BOT_TOKEN is not set.")
    if errors:
        for e in errors:
            log.critical("❌  %s", e)
        sys.exit(1)

    # Ensure user_data dir exists
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ── Start Dashboard (non-blocking) ──
    await _start_dashboard()

    # Build bot + dispatcher
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Start APScheduler, reconnect Telethon accounts, resume loop/schedules
    Sched.start()
    await recover(bot)

    # Resume log forwarders for users that had it enabled
    for uid in UserManager.get_all_user_ids():
        store = UserManager.get_store(uid)
        if await store.get("log_forwarding_enabled", False):
            await _start_log_forwarder(bot, uid)

    log.info("[BOT] Online. OWNER_ID=%s", OWNER_ID)
    if ADMIN_IDS:
        log.info("[BOT] Admins: %s", ADMIN_IDS)
    else:
        log.info("[BOT] No admins configured (owner-only mode).")
    try:
        from dashboard.config import settings as _web
        _disp = "localhost" if _web.host in ("0.0.0.0", "::") else _web.host
        log.info("[BOT] Dashboard: http://%s:%s", _disp, _web.port)
    except Exception:
        pass
    user_ids = UserManager.get_all_user_ids()
    log.info("[BOT] Loaded %d user(s): %s", len(user_ids), user_ids)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        # Stop dashboard
        await _stop_dashboard()
        # Stop all log forwarder tasks
        for uid, task in list(_log_tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
        # Cleanly disconnect all Telethon sessions for all users
        for uid, mgr in UserManager.get_all_account_mgrs().items():
            for phone, client in list(mgr._clients.items()):
                try:
                    await client.disconnect()
                    log.info("[User %s] Disconnected Telethon account: %s", uid, phone)
                except Exception:
                    pass
        Sched.shutdown()
        await bot.session.close()
        log.info("✨  Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
