# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ui/main_menu.py  —  Main menus
#
#  Rules:
#    • Only InlineKeyboardMarkup / InlineKeyboardButton construction
#    • No business logic, no storage access, no handlers, no Telethon
#    • Every button is built via ui.emojis.create_button() so icons
#      stay centralized in emoji_db.json.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram.types import InlineKeyboardMarkup

from .emojis import create_button, main_menu_button


def kb_main() -> InlineKeyboardMarkup:
    """Main control panel — owner-only bot. Dashboard moved off the menu;
    its data is rendered inline in the menu header text."""
    rows = [
        [main_menu_button("start"),          main_menu_button("stop")],
        [main_menu_button("set_time"),       main_menu_button("choose_groups")],
        [main_menu_button("set_message"),    main_menu_button("account")],
        [main_menu_button("logout")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_time_menu() -> InlineKeyboardMarkup:
    """Submenu for timing controls."""
    rows = [
        [create_button("Set Delay",    "clock",    "m:set_delay",    style="INFO")],
        [create_button("Set Interval", "timer",    "m:set_interval", style="INFO")],
        [create_button("Scheduler",    "calendar", "m:scheduler",    style="PRIMARY")],
        [main_menu_button("back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_groups_menu() -> InlineKeyboardMarkup:
    """Submenu for group selections."""
    rows = [
        [create_button("Select Groups", "pin",  "m:sel_groups",   style="PRIMARY")],
        [create_button("Topic Groups",  "list", "m:topic_groups", style="PRIMARY")],
        [main_menu_button("back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_logout_confirm() -> InlineKeyboardMarkup:
    """Confirmation dialog for logging out active account."""
    rows = [
        [
            main_menu_button("confirm_yes"),
            main_menu_button("confirm_no"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
