# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ui/emojis.py  —  Centralized premium emoji system.
#
#  One source of truth for every icon used across the bot UI.
#  Edit ads/emoji_db.json to change icons everywhere — no code
#  changes needed.
#
#  Scope of what this module DOES:
#    • Loads emoji_db.json (JSON of { key: [fallback_char, custom_emoji_id] }).
#    • get_emoji(key) → (fallback_char, custom_emoji_id | None)
#    • create_button(label, key, callback, style=...) → aiogram
#      InlineKeyboardButton with:
#         - text:                  "{fallback} {label}" (or just label if
#                                  emoji_on=False)
#         - icon_custom_emoji_id:  set from emoji_db.json (premium-only
#                                  rendering on the client side; fallback
#                                  char in text handles non-premium).
#         - style:                 lowercase Bot API value ("primary",
#                                  "success", "danger"). Our semantic
#                                  tags PRIMARY / SUCCESS / DANGER /
#                                  SECONDARY / INFO are mapped to this
#                                  value below.
#    • premium_emoji(key) → HTML snippet suitable for message text,
#      using <tg-emoji emoji-id="…">{fallback}</tg-emoji>. Premium
#      Telegram users see the animated custom emoji; everyone else
#      sees the fallback character — automatic graceful degradation.
#
#  Telegram Bot API constraints (verified against aiogram 3.27.0):
#    • `style` must be one of "danger" | "success" | "primary" or None.
#      Our SECONDARY and INFO tags map to None and "primary" respectively.
#    • `icon_custom_emoji_id` is only rendered when the bot has a
#      Fragment-purchased username OR the owner of the bot has
#      Telegram Premium. If the client can't show the custom emoji,
#      the fallback character in `text` ensures the button still works.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from __future__ import annotations

import json
import logging
import os
from html import escape as _html_escape
from pathlib import Path
from typing import Literal

from aiogram.types import InlineKeyboardButton

log = logging.getLogger(__name__)

# Style taxonomy (semantic). Mapped to the Bot API's `style` field.
# Bot API only supports three literal colors: primary (blue), success
# (green), danger (red). SECONDARY and INFO are project-level niceties
# that fall back to the app default / blue respectively.
Style = Literal["PRIMARY", "SUCCESS", "DANGER", "SECONDARY", "INFO"]

_STYLE_API: dict[Style, str | None] = {
    "PRIMARY":   "primary",
    "SUCCESS":   "success",
    "DANGER":    "danger",
    "SECONDARY": None,        # Telegram renders an app-specific neutral style.
    "INFO":      "primary",   # No distinct "info" color in Bot API → blue.
}

# Fallback when a key is missing from emoji_db.json.
_MISSING = ("•", None)

# Warn-once memoisation so a missing key doesn't spam the logs.
_warned_missing: set[str] = set()


# ───────── DB loader ─────────────────────────────────────────────

def _resolve_db_path() -> Path:
    """Look for emoji_db.json next to ads/main.py by default, or the
    path pointed to by $EMOJI_DB_PATH if set."""
    override = os.environ.get("EMOJI_DB_PATH")
    if override:
        return Path(override)
    here = Path(__file__).resolve().parent.parent   # ads/
    return here / "emoji_db.json"


def _load_db() -> dict[str, tuple[str, str | None]]:
    path = _resolve_db_path()
    if not path.exists():
        log.warning("[emojis] emoji_db.json not found at %s — using fallback-only mode.", path)
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("[emojis] Failed to parse %s: %s — using fallback-only mode.", path, e)
        return {}

    # Support either {key: [fallback, id]} at top level or {"emojis": {...}}.
    container = raw.get("emojis") if isinstance(raw, dict) and "emojis" in raw else raw
    if not isinstance(container, dict):
        log.error("[emojis] Unexpected emoji_db.json shape: %s", type(container).__name__)
        return {}

    out: dict[str, tuple[str, str | None]] = {}
    for key, value in container.items():
        if key.startswith("_"):
            continue
        if isinstance(value, (list, tuple)) and len(value) >= 1:
            fallback = str(value[0]).strip() or "•"
            emoji_id = str(value[1]).strip() if len(value) >= 2 and value[1] else None
            out[key] = (fallback, emoji_id)
        elif isinstance(value, str):
            out[key] = (value, None)
    return out


_DB: dict[str, tuple[str, str | None]] = _load_db()

# Reverse index: fallback character -> custom_emoji_id. Built from _DB so
# premium_text() can scan arbitrary strings and wrap every emoji it finds.
# Longest fallback first so multi-codepoint emoji (e.g. flags, ZWJ
# sequences) are matched before their single-codepoint prefixes.
_FALLBACK_TO_ID: dict[str, str] = {}
_SORTED_FALLBACKS: list[str] = []


_VS16 = "\uFE0F"  # emoji presentation selector — optional on most glyphs.


def _rebuild_reverse_index() -> None:
    global _FALLBACK_TO_ID, _SORTED_FALLBACKS
    rev: dict[str, str] = {}
    for _key, (fallback, emoji_id) in _DB.items():
        if not emoji_id or not fallback:
            continue
        # First registration wins — the DB may have multiple keys pointing
        # to the same fallback character (e.g. two synonyms for 📊).
        rev.setdefault(fallback, emoji_id)
        # Also register VS16-stripped and VS16-suffixed variants so that
        # source text which omits (or adds) the emoji-presentation
        # selector still matches. Telegram displays either form with the
        # same animated glyph — the reverse index just needs to see them
        # as interchangeable.
        if _VS16 in fallback:
            stripped = fallback.replace(_VS16, "")
            if stripped:
                rev.setdefault(stripped, emoji_id)
        else:
            rev.setdefault(fallback + _VS16, emoji_id)
    _FALLBACK_TO_ID = rev
    _SORTED_FALLBACKS = sorted(rev.keys(), key=len, reverse=True)


_rebuild_reverse_index()


def reload_db() -> int:
    """Reload emoji_db.json from disk. Useful for hot-swapping icons
    without restarting the bot. Returns the number of entries loaded."""
    global _DB, _warned_missing
    _DB = _load_db()
    _warned_missing.clear()
    _rebuild_reverse_index()
    log.info("[emojis] Reloaded — %d entries.", len(_DB))
    return len(_DB)


# ───────── public API ────────────────────────────────────────────

def get_emoji(key: str) -> tuple[str, str | None]:
    """Return ``(fallback_char, custom_emoji_id or None)`` for the given
    semantic key. Missing keys degrade gracefully and log once."""
    hit = _DB.get(key)
    if hit is not None:
        return hit
    if key not in _warned_missing:
        _warned_missing.add(key)
        log.warning("[emojis] Missing key: %r — using fallback '•'.", key)
    return _MISSING


def premium_emoji(key: str) -> str:
    """Render an HTML snippet that shows the custom emoji on premium
    clients and the fallback character everywhere else.

    Safe to inline anywhere we send with ``parse_mode='HTML'``.
    """
    fallback, emoji_id = get_emoji(key)
    if not emoji_id:
        return _html_escape(fallback)
    return f'<tg-emoji emoji-id="{emoji_id}">{_html_escape(fallback)}</tg-emoji>'


# ───────── full-message premium-emoji rewriter ───────────────────
#
# ``premium_text(s)`` scans an HTML message body and wraps every plain
# emoji character found in the reverse index with a matching
# ``<tg-emoji emoji-id="…">char</tg-emoji>`` entity. Premium Telegram
# users see animated custom emojis for every icon in the message;
# non-premium users see the plain fallback character — identical to
# the original string. Safe for parse_mode="HTML" only.
#
# Two guards keep the rewriter correct:
#   1. Anything already inside an existing ``<tg-emoji …>…</tg-emoji>``
#      block is left untouched (no double-wrapping).
#   2. HTML tag boundaries (``<b>``, ``<code>``, etc.) are never
#      rewritten — we only scan the plain-text segments between tags.
#
# Characters not present in ``_FALLBACK_TO_ID`` are left as-is.

import re as _re

_HTML_TAG_RE = _re.compile(r"<[^>]+>")


def _wrap_segment(seg: str) -> str:
    if not seg or not _SORTED_FALLBACKS:
        return seg
    out: list[str] = []
    i, n = 0, len(seg)
    while i < n:
        matched = False
        for fb in _SORTED_FALLBACKS:
            if fb and seg.startswith(fb, i):
                emoji_id = _FALLBACK_TO_ID[fb]
                out.append(
                    f'<tg-emoji emoji-id="{emoji_id}">{_html_escape(fb)}</tg-emoji>'
                )
                i += len(fb)
                matched = True
                break
        if not matched:
            out.append(seg[i])
            i += 1
    return "".join(out)


def premium_text(s: str | None) -> str | None:
    """Wrap every known emoji in ``s`` with a ``<tg-emoji>`` entity.

    The input must be an HTML string (parse_mode="HTML"). Returns the
    rewritten string, or the original when no emoji matched. Existing
    ``<tg-emoji>`` blocks are preserved verbatim.
    """
    if not s:
        return s
    # Split on HTML tags and on existing <tg-emoji>...</tg-emoji> blocks so
    # we never rewrite text inside them. ``re.split`` with a capturing
    # group returns the delimiters alongside the chunks.
    pieces = _re.split(
        r"(<tg-emoji[^>]*>.*?</tg-emoji>|<[^>]+>)",
        s,
        flags=_re.IGNORECASE | _re.DOTALL,
    )
    for i, part in enumerate(pieces):
        if i % 2 == 0:
            # Plain text chunk — scan and wrap emojis.
            pieces[i] = _wrap_segment(part)
        # odd indices are tag / tg-emoji blocks — leave untouched.
    return "".join(pieces)


def create_button(
    label:    str,
    key:      str,
    callback: str | None = None,
    *,
    style:    Style = "PRIMARY",
    url:      str | None = None,
    emoji_on: bool | None = None,
) -> InlineKeyboardButton:
    """Build an aiogram ``InlineKeyboardButton`` with a consistent
    emoji prefix taken from ``emoji_db.json``.

    Parameters
    ----------
    label:
        The visible text (sans emoji).
    key:
        A semantic key that resolves in ``emoji_db.json``. Missing keys
        degrade to a bullet, not a crash.
    callback:
        The ``callback_data`` value. Mutually exclusive with ``url``.
    style:
        One of ``PRIMARY | SUCCESS | DANGER | SECONDARY | INFO``. Used
        as a semantic tag — it does NOT colour the button (not supported
        by the Telegram Bot API). Kept here so call-sites document intent
        and so future formatting passes can act on it.
    url:
        If provided, builds a URL button instead of a callback button.
    emoji_on:
        Set False to suppress the emoji prefix (useful when a parent
        container already carries the icon).
    """
    if bool(callback) == bool(url):
        raise ValueError("create_button needs exactly one of `callback` or `url`")

    fallback, emoji_id = get_emoji(key)
    # emoji_on=None (default) → show the fallback char in text only when
    # there is no ``icon_custom_emoji_id`` to render the premium version.
    # This keeps clean single-icon buttons on premium-aware clients while
    # guaranteeing a visible glyph for everyone else. Explicit True / False
    # still works for callers that want the old behaviour.
    if emoji_on is True or (emoji_on is None and not emoji_id):
        text = f"{fallback} {label}".strip()
    else:
        text = label

    api_style = _STYLE_API.get(style)

    kwargs: dict[str, object] = {"text": text}
    if api_style is not None:
        kwargs["style"] = api_style
    if emoji_id:
        # Rendered as a colored icon before the label on clients that
        # support it (Fragment-purchased bot usernames or Premium-owner
        # bots). Everyone else gets the plain fallback char in `text`.
        kwargs["icon_custom_emoji_id"] = emoji_id
    if callback is not None:
        kwargs["callback_data"] = callback
    else:
        kwargs["url"] = url

    btn = InlineKeyboardButton(**kwargs)
    # Preserve the original semantic tag and key for introspection / tests.
    object.__setattr__(btn, "_ui_style", style)
    object.__setattr__(btn, "_ui_key",   key)
    return btn


# ───────── stable taxonomy for the main menu ─────────────────────
#
# One place that maps every primary action to its emoji key + style.
# Change the emoji for "Start Ads" everywhere by editing the key below.

MAIN_MENU_BUTTONS = {
    "dashboard":    {"label": "Dashboard",      "key": "chart",    "style": "PRIMARY",   "cb": "m:dashboard"},
    "account":      {"label": "Account",        "key": "profile",  "style": "SECONDARY", "cb": "m:accounts"},
    "start":        {"label": "Start Ads",      "key": "rocket",   "style": "SUCCESS",   "cb": "m:start"},
    "stop":         {"label": "Stop Ads",       "key": "cross",    "style": "DANGER",    "cb": "m:stop"},
    "set_time":     {"label": "Set Time",       "key": "timer",    "style": "INFO",      "cb": "m:time_menu"},
    "choose_groups":{"label": "Choose Groups",  "key": "pin",      "style": "PRIMARY",   "cb": "m:groups_menu"},
    "set_message":  {"label": "Set Message",    "key": "edit",     "style": "SECONDARY", "cb": "m:set_msg"},
    "logout":       {"label": "Logout Account", "key": "lock",     "style": "DANGER",    "cb": "m:logout_active"},
    # Nav:
    "back":         {"label": "Back to Menu",   "key": "back",     "style": "SECONDARY", "cb": "m:main"},
    "cancel":       {"label": "Cancel",         "key": "cancel",   "style": "DANGER",    "cb": "m:main"},
    "confirm_yes":  {"label": "Yes, Logout",    "key": "confirm",  "style": "SUCCESS",   "cb": "m:logout_yes"},
    "confirm_no":   {"label": "No, Cancel",     "key": "cross",    "style": "SECONDARY", "cb": "m:main"},
}


def main_menu_button(action_id: str) -> InlineKeyboardButton:
    """Factory helper — build a main-menu button from the taxonomy above."""
    spec = MAIN_MENU_BUTTONS[action_id]
    return create_button(
        label    = spec["label"],
        key      = spec["key"],
        callback = spec["cb"],
        style    = spec["style"],
    )


__all__ = [
    "Style",
    "get_emoji",
    "premium_emoji",
    "create_button",
    "main_menu_button",
    "reload_db",
    "MAIN_MENU_BUTTONS",
]
