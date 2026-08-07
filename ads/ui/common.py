# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ui/common.py  —  Reusable navigation buttons (back, cancel)
#
#  Every button goes through ui.emojis.create_button() so icons stay
#  centralized in emoji_db.json.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram.types import InlineKeyboardMarkup

from .emojis import main_menu_button


def kb_back() -> InlineKeyboardMarkup:
    """Generic 'Back to Menu' button."""
    return InlineKeyboardMarkup(inline_keyboard=[[main_menu_button("back")]])


def kb_cancel() -> InlineKeyboardMarkup:
    """Generic 'Cancel' button — returns user to main menu."""
    return InlineKeyboardMarkup(inline_keyboard=[[main_menu_button("cancel")]])
