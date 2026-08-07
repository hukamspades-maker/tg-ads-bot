"""Smoke test for the per-account logging system.

Runs entirely offline — no real Telegram connection required.
Verifies the new helpers produce the exact spec format.
"""
import asyncio
import os
import sys

# Minimal env for main.py config.py — we just need the module to import.
os.environ.setdefault("BOT_TOKEN", "fake")
os.environ.setdefault("OWNER_ID", "1")
os.environ.setdefault("OWNER_USERNAME", "x")
os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "x")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main  # noqa: E402


class FakeBot:
    """Records every send_message call."""
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text, parse_mode=None):
        msg_obj = type("Message", (), {"message_id": 100 + len(self.messages)})()
        self.messages.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
        return msg_obj

    async def edit_message_text(self, chat_id, message_id, text, parse_mode=None):
        self.messages.append({"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode})
        return True

    async def get_me(self):
        class Me:
            username = "fake_bot"
        return Me()

    async def get_chat(self, chat_id):
        return {"id": chat_id}


async def run_tests() -> int:
    failures = 0

    # Install a fake account record directly on the AccountManager.
    uid = 999999
    phone = "+919732399359"
    mgr = main.UserManager.get_account_mgr(uid)
    mgr._data = {
        "accounts": [{
            "phone": phone, "name": "T", "api_id": 1, "api_hash": "x",
            "log_group_id": -100123456789,   # pretend log group already exists
            "round_counter": 0,
        }],
        "active_phone": phone,
    }
    # Skip save for the test
    mgr._save = lambda: None

    bot = FakeBot()

    # ── 1. Round counter persistence ─────────────────────────────
    assert mgr.get_round_counter(phone) == 0
    r1 = mgr.bump_round(phone)
    r2 = mgr.bump_round(phone)
    if (r1, r2) != (1, 2):
        print(f"FAIL: bump_round returned ({r1}, {r2}), expected (1, 2)")
        failures += 1
    else:
        print("PASS: bump_round increments correctly (1 → 2)")

    # ── 2. Round-start message format ────────────────────────────
    await main.send_round_start_log(
        bot, uid, phone, plan="ADVANCED",
        round_num=1, total_groups=3, threads=1,
    )
    assert len(bot.messages) == 1
    start_text = bot.messages[0]["text"]
    expected_start_lines = [
        "👤 ACCOUNT: +919732399359",
        "⚙️ PLAN: ADVANCED",
        "🔁 ROUND: #1",
        "⚡ THREADS: 1",
        "📦 GROUPS: 3",
        "↗️ TOTAL SENT: 0",
        "❌ FAILED: 0",
        "⏳ STATUS: RUNNING",
    ]
    missing = [ln for ln in expected_start_lines if ln not in start_text]
    if missing:
        print(f"FAIL: round-start missing lines: {missing}")
        print("--- full message ---"); print(start_text)
        failures += 1
    else:
        print("PASS: round-start message matches spec format")

    # ── 3. Round-end message (NEW message, not edit) ─────────────
    await main.send_round_end_log(
        bot, uid, phone, plan="ADVANCED",
        round_num=1, total_groups=3, sent=2, failed=1,
        status="COMPLETED",
    )
    assert len(bot.messages) == 2
    end_text = bot.messages[1]["text"]
    if "STATUS: COMPLETED" not in end_text or "TOTAL SENT: 2" not in end_text:
        print("FAIL: round-end missing COMPLETED / sent=2")
        print(end_text); failures += 1
    else:
        print("PASS: round-end message produces fresh message with final stats")

    # ── 4. Failure report format ─────────────────────────────────
    failures_list = [
        ("Group A", "messaging off"),
        ("Group B", "user banned"),
        ("Group C", "flood wait 30s"),
        ("Group D", "private group"),
    ]
    await main.send_failure_report(bot, uid, phone, round_num=1, failures=failures_list)
    assert len(bot.messages) == 3
    rep = bot.messages[2]["text"]
    required = [
        "❌ <b>FAILED GROUPS REPORT</b>",
        f"Round #1 — Account: <code>{phone}</code>",
        "1. Group A → messaging off",
        "2. Group B → user banned",
        "3. Group C → flood wait 30s",
        "4. Group D → private group",
    ]
    missing = [ln for ln in required if ln not in rep]
    if missing:
        print(f"FAIL: failure report missing lines: {missing}")
        print("--- full message ---"); print(rep)
        failures += 1
    else:
        print("PASS: failure report has numbered list with reasons")

    # ── 5. Empty failure list → no message sent ──────────────────
    before = len(bot.messages)
    await main.send_failure_report(bot, uid, phone, round_num=2, failures=[])
    if len(bot.messages) != before:
        print("FAIL: empty failure list should not send a message")
        failures += 1
    else:
        print("PASS: empty failure list sends nothing")

    # ── 6. Round 2 → NEW message (no edit of round 1) ────────────
    await main.send_round_start_log(
        bot, uid, phone, plan="ADVANCED",
        round_num=2, total_groups=5, threads=1,
    )
    if "ROUND: #2" not in bot.messages[-1]["text"]:
        print("FAIL: round 2 didn't produce a new message")
        failures += 1
    else:
        print("PASS: round 2 produced a NEW message (history preserved)")

    # ── 7. All log messages go to the per-account log group id ───
    gids = {m["chat_id"] for m in bot.messages}
    if gids != {-100123456789}:
        print(f"FAIL: messages fanned to unexpected chat ids: {gids}")
        failures += 1
    else:
        print("PASS: all log messages delivered to per-account log group")

    # ── 8. Strict format — divider & emoji header present ────────
    if not end_text.startswith("=") or "PROGRESS: [" not in end_text:
        print("FAIL: divider / progress bar missing in final round message")
        failures += 1
    else:
        print("PASS: divider & progress bar present")

    # ── UI premium-emoji system ───────────────────────────────────
    from ui.emojis import (
        get_emoji, create_button, premium_emoji, reload_db, MAIN_MENU_BUTTONS,
    )
    from ui.main_menu import kb_main, kb_time_menu, kb_groups_menu, kb_logout_confirm
    from ui.common    import kb_back, kb_cancel
    from ui.accounts  import kb_accounts_menu
    from ui.scheduler import kb_scheduler_menu

    # 9. emoji_db.json loads and has known keys
    if reload_db() < 100 or get_emoji("rocket")[1] is None:
        print("FAIL: emoji_db.json not loaded / rocket id missing")
        failures += 1
    else:
        print("PASS: emoji_db.json loaded with rocket custom_emoji_id")

    # 10. Missing key degrades to bullet, no crash
    fb, eid = get_emoji("__definitely_missing_key__")
    if fb != "•" or eid is not None:
        print(f"FAIL: missing-key fallback wrong: {fb!r}, {eid!r}")
        failures += 1
    else:
        print("PASS: missing key degrades to '•' with no crash")

    # 11. create_button forwards style + icon_custom_emoji_id to the Bot API
    btn = create_button("Start Ads", "rocket", "m:start", style="SUCCESS")
    if "Start Ads" not in btn.text or btn.callback_data != "m:start":
        print(f"FAIL: create_button text/cb wrong: {btn}")
        failures += 1
    elif getattr(btn, "_ui_style", None) != "SUCCESS":
        print("FAIL: semantic style tag not attached to button")
        failures += 1
    elif btn.style != "success":
        print(f"FAIL: Bot-API style not forwarded: {btn.style!r}")
        failures += 1
    elif not btn.icon_custom_emoji_id:
        print("FAIL: icon_custom_emoji_id not forwarded from emoji_db.json")
        failures += 1
    else:
        print("PASS: create_button forwards style + icon_custom_emoji_id to Bot API")

    # 11b. SECONDARY style omits the Bot API style (neutral default)
    btn_sec = create_button("Back", "back", "m:main", style="SECONDARY")
    if btn_sec.style is not None:
        print(f"FAIL: SECONDARY should map to None, got {btn_sec.style!r}")
        failures += 1
    else:
        print("PASS: SECONDARY style maps to Bot API None (neutral)")

    # 12. premium_emoji produces <tg-emoji> HTML for premium users
    snippet = premium_emoji("rocket")
    if "<tg-emoji emoji-id=" not in snippet or "</tg-emoji>" not in snippet:
        print(f"FAIL: premium_emoji HTML malformed: {snippet!r}")
        failures += 1
    else:
        print("PASS: premium_emoji renders <tg-emoji> with fallback")

    # 13. Main menu is a 2x3 grid + 1 full-width logout button
    kb = kb_main()
    rows = kb.inline_keyboard
    grid_rows = rows[:3]   # first 3 rows are 2-button pairs
    labels = [[b.text for b in r] for r in rows]
    if len(rows) != 4 or any(len(r) != 2 for r in grid_rows) or len(rows[3]) != 1:
        print(f"FAIL: main menu not a 2x3+1 grid: {labels}")
        failures += 1
    else:
        print("PASS: main menu is a structured 2x3 + 1 dashboard grid")

    # 14. Every main-menu button has a semantic style tag attached
    tagged = all(getattr(b, "_ui_style", None) in
                 {"PRIMARY", "SUCCESS", "DANGER", "SECONDARY", "INFO"}
                 for row in rows for b in row)
    if not tagged:
        print("FAIL: some buttons missing semantic style tag")
        failures += 1
    else:
        print("PASS: every main-menu button carries a semantic style tag")

    # 15. No keyboard builder crashes when constructed
    try:
        for kb_build in (
            lambda: kb_time_menu(),
            lambda: kb_groups_menu(),
            lambda: kb_logout_confirm(),
            lambda: kb_back(),
            lambda: kb_cancel(),
            lambda: kb_accounts_menu(can_add=True),
            lambda: kb_accounts_menu(can_add=False),
            lambda: kb_scheduler_menu(),
        ):
            kb_build()
        print("PASS: all migrated keyboards build without error")
    except Exception as e:
        print(f"FAIL: keyboard build raised: {e}")
        failures += 1

    # 16. Taxonomy covers every spec item
    required_actions = {
        "dashboard", "account", "start", "stop",
        "set_time", "choose_groups", "set_message", "logout",
    }
    if not required_actions.issubset(MAIN_MENU_BUTTONS):
        missing = required_actions - MAIN_MENU_BUTTONS.keys()
        print(f"FAIL: taxonomy missing spec actions: {missing}")
        failures += 1
    else:
        print("PASS: taxonomy covers all 8 spec actions")

    # ── premium_text() auto-rewriter ─────────────────────────────
    from ui.emojis import premium_text

    # 16a. Known emojis get wrapped in <tg-emoji>
    rewritten = premium_text("📊 <b>DASHBOARD</b>\n👤 David")
    if "<tg-emoji emoji-id=" not in rewritten or "<b>DASHBOARD</b>" not in rewritten:
        print(f"FAIL: premium_text didn't wrap known emojis: {rewritten!r}")
        failures += 1
    else:
        print("PASS: premium_text wraps known emojis in <tg-emoji>")

    # 16b. No double-wrap — existing <tg-emoji> blocks are preserved.
    pre_wrapped = '<tg-emoji emoji-id="123">📊</tg-emoji> Test'
    out = premium_text(pre_wrapped)
    if out.count("<tg-emoji") != 1:
        print(f"FAIL: premium_text double-wrapped existing <tg-emoji>: {out!r}")
        failures += 1
    else:
        print("PASS: premium_text does not double-wrap existing <tg-emoji> blocks")

    # 16c. Unknown emoji char → left as-is, no crash
    weird = "\U0001FAE7 custom"  # Unicode 14 "bubbles" — unlikely in our DB.
    out3  = premium_text(weird)
    if "<tg-emoji" in out3:
        print(f"PASS: premium_text wrapped unknown glyph (present in DB): {out3!r}")
    elif weird in out3:
        print("PASS: premium_text leaves unknown chars untouched")
    else:
        print(f"FAIL: premium_text mangled unknown chars: {out3!r}")
        failures += 1

    # 16d. HTML tags not rewritten — tag text isn't scanned for emojis.
    html = '<a href="x?q=📊">link</a>'
    out4 = premium_text(html)
    if 'href="x?q=📊"' not in out4:
        print(f"FAIL: premium_text rewrote emoji inside HTML tag: {out4!r}")
        failures += 1
    else:
        print("PASS: premium_text leaves emoji inside HTML tags alone")

    # 16e. Buttons now omit fallback char when icon_custom_emoji_id set.
    btn_clean = create_button("Start Ads", "rocket", "m:start", style="SUCCESS")
    if btn_clean.text.strip() != "Start Ads":
        print(f"FAIL: button text still has fallback emoji: {btn_clean.text!r}")
        failures += 1
    elif not btn_clean.icon_custom_emoji_id:
        print("FAIL: button lost icon_custom_emoji_id")
        failures += 1
    else:
        print("PASS: button text is clean; icon_custom_emoji_id carries the glyph")

    # ── Owner-only access gate ───────────────────────────────────
    # The bot is now single-admin: only OWNER_ID is allowed in.
    if not main.has_access(main.OWNER_ID):
        print("FAIL: owner denied access by has_access()")
        failures += 1
    elif main.has_access(main.OWNER_ID + 1):
        print("FAIL: non-owner granted access by has_access()")
        failures += 1
    else:
        print("PASS: has_access allows owner and rejects everyone else")

    return failures


if __name__ == "__main__":
    n_fail = asyncio.run(run_tests())
    if n_fail:
        print(f"\n{n_fail} failure(s)")
        sys.exit(1)
    print("\nAll smoke tests passed.")
