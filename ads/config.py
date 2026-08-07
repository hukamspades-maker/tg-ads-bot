# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  config.py  —  Centralised configuration for TG Auto-Sender Bot
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import os
from pathlib import Path


# ── Bot API credentials ───────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "8182671400:AAEGXPOP53KN3MK8rn--jIuoe388MYyga_U")

# ── Owner ─────────────────────────────────────────────────────────
OWNER_ID: int       = 8603872187   # permanent owner — can grant/revoke permissions
OWNER_USERNAME: str = "@oldsit"    # your Telegram username (with @)

# ── Admins ────────────────────────────────────────────────────────
# Add Telegram user IDs of admins here.  Each admin gets their own
# isolated sessions, settings, and broadcast data.  The owner can
# view/manage any admin's data and has exclusive dashboard access.
ADMIN_IDS: list[int] = [
    # 989009,
    # 998977,
]

# ── Premium Plans ──────────────────────────────────────────────────
# Each plan: label, duration in days, price in USD.
PREMIUM_PLANS: list[dict] = [
    {"id": "7d",  "label": "7 Days",  "days": 7,  "price": 2},
    {"id": "15d", "label": "15 Days", "days": 15, "price": 5},
    {"id": "30d", "label": "30 Days", "days": 30, "price": 8},
]

# ── Force Join ─────────────────────────────────────────────────────
# Channels / groups users must join before using the bot.
# Format: list of channel usernames (without @) or channel IDs.
FORCE_JOIN_CHANNELS: list[str | int] = [
    # "my_channel",
    # -1001234567890,
]

# ── Telethon / MTProto API credentials (shared for ALL accounts) ──
# Get yours from https://my.telegram.org/apps
TELEGRAM_API_ID:   int = 28822372
TELEGRAM_API_HASH: str = "99978f7cdf7bed10f7f35b1a15d85908"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FILE PATHS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USER_DATA_DIR:    Path = Path("user_data")
LOG_FILE:         str  = "bot.log"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GENERAL DEFAULTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DAY_NAMES: list[str] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Seconds between Telethon client health-checks (get_me throttle)
HEALTH_CHECK_INTERVAL: int = 300


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  UI / MESSAGE STRINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODE_TEXT: str = "👋 <b>Welcome to Telegram Auto-Sender Bot</b>\n\nChoose your mode:"

MAIN_TEXT: str = (
    "🚀 <b>Silent Sender Control Center</b>\n\n"
    "Welcome to your centralized automation panel for advanced Telegram broadcasting.\n"
    "Manage multiple accounts, configure smart delays, control group targeting, "
    "enable scheduling systems, and operate high-performance broadcast loops with precision.\n\n"
    "Select an operation below to continue.\n\n"
    '📘 <i>For a complete feature breakdown and detailed usage instructions, use the /help command.</i>'
)

# ADV_DENY and PLANS_TEXT removed — now handled by plans.py (build_plans_text)
# and inline plan-check messages in handlers.

RESET_EXPLANATIONS: dict[str, str] = {
    "json": (
        "🗂 <b>Reset Your JSON</b>\n\n"
        "This will reset all saved JSON data:\n"
        "• Saved message\n"
        "• Forwarded channel data\n"
        "• Scheduler jobs\n"
        "• Selected groups\n"
        "• Specific groups\n"
        "• Broadcast settings\n"
        "• Log forwarding settings\n\n"
        "Your account sessions will <b>NOT</b> be removed."
    ),
    "session": (
        "👤 <b>Reset Account Sessions</b>\n\n"
        "This will remove only Telegram account session files.\n"
        "Messages, schedules, and JSON settings will remain untouched."
    ),
    "all": (
        "🔥 <b>Reset All</b>\n\n"
        "This will completely reset:\n"
        "• All account sessions\n"
        "• All JSON settings\n"
        "• Saved message\n"
        "• Forwarded channel\n"
        "• Schedules\n"
        "• Selected groups\n"
        "• Specific groups\n"
        "• Loop state\n"
        "• Broadcast settings\n"
        "• Log forwarding\n"
        "• Statistics\n\n"
        "<b>This action cannot be undone.</b>"
    ),
}
