# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ui/scheduler.py  —  Scheduler, group selection, log forwarding,
#                       and reset keyboards
#
#  Rules:
#    • Only InlineKeyboardMarkup / InlineKeyboardButton construction
#    • No business logic, no storage access, no handlers, no Telethon
#    • All icons resolved through ui.emojis (emoji_db.json).
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram.types import InlineKeyboardMarkup

from config import DAY_NAMES

from .emojis import create_button


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GROUP SELECTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def kb_groups(groups: list[dict], selected_ids: set[int], page: int = 0) -> InlineKeyboardMarkup:
    """Paginated group-toggle keyboard (50 groups per page)."""
    rows = []
    PER_PAGE    = 50
    total_pages = max(1, (len(groups) + PER_PAGE - 1) // PER_PAGE)
    start       = page * PER_PAGE
    end         = start + PER_PAGE

    for g in groups[start:end]:
        is_selected = g["id"] in selected_ids
        # Premium-only indicator: active rows use the confirm tick icon,
        # inactive rows use the neutral ring — both render as the
        # button's ``icon_custom_emoji_id`` (no plain glyph in text).
        rows.append([create_button(
            label    = g["title"],
            key      = "confirm" if is_selected else "vector_circle",
            callback = f"gtoggle:{g['id']}",
            style    = "SUCCESS" if is_selected else "SECONDARY",
            emoji_on = False,
        )])

    nav_row = []
    if page > 0:
        nav_row.append(create_button("Prev", "back", f"gpage:{page-1}", style="SECONDARY"))
    if page < total_pages - 1:
        nav_row.append(create_button("Next", "next", f"gpage:{page+1}", style="SECONDARY"))
    if nav_row:
        rows.append(nav_row)

    rows.append([
        create_button("All",  "confirm", "gtoggle:all",  style="SUCCESS"),
        create_button("None", "cross",   "gtoggle:none", style="DANGER"),
    ])
    rows.append([
        create_button("Save", "check",   "gsave",  style="SUCCESS"),
        create_button("Back", "back",    "m:main", style="SECONDARY"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_start_choice() -> InlineKeyboardMarkup:
    """Choice of which group source to use when starting the loop."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [create_button("Use Topic Groups",    "list",    "m:start:use_topic",    style="PRIMARY")],
        [create_button("Use Selected Groups", "pin",     "m:start:use_selected", style="PRIMARY")],
        [create_button("Use Both",            "package", "m:start:use_both",     style="PRIMARY")],
        [create_button("Back",                "back",    "m:main",               style="SECONDARY")],
    ])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TOPIC GROUPS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NUM_EMOJI = [f"{i}." for i in range(1, 11)]


def kb_topic_groups(
    forum_groups:    list[dict],
    saved_map:       dict[int, set[int]],
    expanded_groups: set[int],
    page: int = 0,
) -> InlineKeyboardMarkup:
    """Paginated topic-toggle keyboard."""
    PER_PAGE    = 10
    total_pages = max(1, (len(forum_groups) + PER_PAGE - 1) // PER_PAGE)
    start       = page * PER_PAGE
    end         = start + PER_PAGE
    rows        = []

    for grp in forum_groups[start:end]:
        gid    = grp["id"]
        gtitle = grp["title"]
        selected_topics = saved_map.get(gid, set())
        is_expanded     = gid in expanded_groups

        folder = "package" if is_expanded else "list"
        rows.append([create_button(
            label    = f"{gtitle} ({gid})",
            key      = folder,
            callback = f"tgexpand:{gid}",
            style    = "PRIMARY" if is_expanded else "SECONDARY",
        )])

        if is_expanded:
            for t in grp.get("topic_list", []):
                tid    = t["id"]
                ttitle = t["title"]
                is_on  = tid in selected_topics
                rows.append([create_button(
                    label    = f"    {ttitle} ({tid})",
                    key      = "confirm" if is_on else "vector_circle",
                    callback = f"tgtoggle:{gid}:{tid}",
                    style    = "SUCCESS" if is_on else "SECONDARY",
                    emoji_on = False,
                )])

    nav_row = []
    if page > 0:
        nav_row.append(create_button("Prev", "back", f"tgpage:{page-1}", style="SECONDARY"))
    if page < total_pages - 1:
        nav_row.append(create_button("Next", "next", f"tgpage:{page+1}", style="SECONDARY"))
    if nav_row:
        rows.append(nav_row)

    rows.append([
        create_button("Save",   "check",  "tgsave",   style="SUCCESS"),
        create_button("Cancel", "cancel", "tgcancel", style="DANGER"),
        create_button("Back",   "back",   "m:main",   style="SECONDARY"),
    ])
    rows.append([create_button("Refresh", "refresh", "tgrefresh", style="PRIMARY")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SCHEDULER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def kb_scheduler_menu() -> InlineKeyboardMarkup:
    """Scheduler main menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [create_button("Add Schedule",    "add",    "sc:add",    style="SUCCESS")],
        [create_button("View Schedules",  "list",   "sc:view",   style="PRIMARY")],
        [create_button("Delete Schedule", "delete", "sc:delete", style="DANGER")],
        [create_button("Back",            "back",   "m:main",    style="SECONDARY")],
    ])


def kb_sched_type() -> InlineKeyboardMarkup:
    """Schedule type selection."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [create_button("Every X Minutes", "timer",    "sctype:interval", style="PRIMARY")],
        [create_button("Daily at Time",   "calendar", "sctype:daily",    style="PRIMARY")],
        [create_button("Weekly",          "calendar", "sctype:weekly",   style="PRIMARY")],
        [create_button("Cancel",          "cancel",   "m:main",          style="DANGER")],
    ])


def kb_days(selected: set[int]) -> InlineKeyboardMarkup:
    """Day-of-week toggle keyboard for weekly schedules."""
    row = [
        create_button(
            label    = DAY_NAMES[i],
            key      = "confirm" if i in selected else "calendar",
            callback = f"day:{i}",
            style    = "SUCCESS" if i in selected else "SECONDARY",
            emoji_on = False,
        )
        for i in range(7)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        row[:4], row[4:],
        [create_button("Confirm Days", "confirm", "daysok", style="SUCCESS")],
        [create_button("Cancel",       "cancel",  "m:main", style="DANGER")],
    ])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RESET
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def kb_reset_menu() -> InlineKeyboardMarkup:
    """Reset options menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [create_button("Reset Your JSON",        "refresh", "rst:json",    style="PRIMARY")],
        [create_button("Reset Account Sessions", "key",     "rst:session", style="PRIMARY")],
        [create_button("Reset All",              "fire",    "rst:all",     style="DANGER")],
        [create_button("Back",                   "back",    "m:main",      style="SECONDARY")],
    ])


def kb_reset_account_list(accounts: list[dict], action: str) -> InlineKeyboardMarkup:
    """Build account picker for reset actions. action: 'json' | 'session' | 'all'"""
    rows = []
    for i, acc in enumerate(accounts):
        num = NUM_EMOJI[i] if i < len(NUM_EMOJI) else f"{i+1}."
        rows.append([create_button(
            label    = f"{num} {acc['name']}  ({acc['phone']})",
            key      = "profile",
            callback = f"rstpick:{action}:{acc['phone']}",
            style    = "SECONDARY",
            emoji_on = False,
        )])
    if action == "json":
        rows.append([create_button("Reset All Accounts JSON", "refresh", f"rstpickall:{action}", style="DANGER")])
    elif action == "session":
        rows.append([create_button("Reset All Sessions",      "refresh", f"rstpickall:{action}", style="DANGER")])
    elif action == "all":
        rows.append([create_button("Reset Everything For All Accounts", "fire", f"rstpickall:{action}", style="DANGER")])
    rows.append([create_button("Back", "back", "m:reset", style="SECONDARY")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_reset_confirm(action: str, target: str) -> InlineKeyboardMarkup:
    """Confirmation keyboard. target is a phone number or '__all__'."""
    yes_text = "Yes, Reset All" if action == "all" else "Yes, Reset"
    return InlineKeyboardMarkup(inline_keyboard=[
        [create_button(yes_text, "confirm", f"rstyes:{action}:{target}", style="DANGER")],
        [create_button("No",     "cross",   "rstno",                     style="SECONDARY")],
    ])



