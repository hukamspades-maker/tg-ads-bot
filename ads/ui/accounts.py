# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ui/accounts.py  —  Account-related keyboards
#
#  Rules:
#    • Only InlineKeyboardMarkup / InlineKeyboardButton construction
#    • No business logic, no storage access, no handlers, no Telethon
#    • Icons come from ui.emojis (emoji_db.json).
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram.types import InlineKeyboardMarkup

from .emojis import create_button


def kb_accounts_menu(can_add: bool = True) -> InlineKeyboardMarkup:
    """Main accounts management menu.

    can_add: when False the Add button is hidden (reserved for future use).
    """
    rows = []
    if can_add:
        rows.append([create_button("Add / Login Account", "add",     "acc:add",    style="SUCCESS")])
    rows += [
        [create_button("Switch Active Account", "next",    "acc:switch", style="PRIMARY")],
        [create_button("Logout Account",        "lock",    "acc:logout", style="DANGER")],
        [create_button("View Accounts",         "list",    "acc:view",   style="SECONDARY")],
        [create_button("Back",                  "back",    "m:main",     style="SECONDARY")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_accounts_switch(accounts: list[dict], active_phone: str | None) -> InlineKeyboardMarkup:
    """List of accounts for switching the active one.
    The currently active account uses the ``confirm`` icon; inactive
    rows use the ``profile`` icon. No plain glyphs in button text.
    """
    rows = []
    for acc in accounts:
        is_active = acc["phone"] == active_phone
        rows.append([create_button(
            label    = f"{acc['name']}  ({acc['phone']})",
            key      = "confirm" if is_active else "profile",
            callback = f"accswitch:{acc['phone']}",
            style    = "SUCCESS" if is_active else "SECONDARY",
            emoji_on = False,
        )])
    rows.append([create_button("Back", "back", "m:accounts", style="SECONDARY")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_accounts_logout(accounts: list[dict]) -> InlineKeyboardMarkup:
    """List of accounts for logout selection."""
    rows = []
    for acc in accounts:
        rows.append([create_button(
            label    = f"{acc['name']}  ({acc['phone']})",
            key      = "lock",
            callback = f"acclogout:{acc['phone']}",
            style    = "DANGER",
        )])
    rows.append([create_button("Back", "back", "m:accounts", style="SECONDARY")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
