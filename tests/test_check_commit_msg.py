"""commit-msg 閘門的規則對帳：合規訊息零抱怨、每條違規各自被指名。"""

from __future__ import annotations

from scripts.check_commit_msg import check

GOOD = """Reject stale roster tab reads on the enemy census

The tab selector trusted a screen classification that stays true
across the close animation, so a swallowed tap read the previous
faction's roster and reported zero enemies. Judge the faction
button highlight instead, measured at B-R 118-150 selected
against 19-24 unselected on live frames.

Evidence: run 20260811-035940, issue #26.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MhAMxKgXqtrhfTeX1BfWKX"""


def test_compliant_message_passes():
    assert check(GOOD) == []


def test_subject_length_and_period_and_parens():
    subject = "Repair the roster tab selection so the enemy census reports every unit."
    problems = check(subject)
    assert any("上限 50" in p for p in problems)
    assert any("句點" in p for p in problems)
    assert any("括號" in p for p in check("Repair tab selection (enemy census)"))


def test_capital_and_imperative_and_single_word():
    assert any("開頭要大寫" in p for p in check("repair the roster tab selection"))
    assert any("祈使句" in p for p in check("Fixed the roster tab selection"))
    assert any("太短" in p for p in check("Update queue.c"))


def test_blank_line_and_body_width():
    glued = "Repair the roster tab selection\nThe tab selector trusted a stale read."
    assert any("空白行" in p for p in check(glued))
    long_body = "Repair the roster tab selection\n\n" + "word " * 20
    assert any("內文上限 72" in p for p in check(long_body))


def test_trailer_and_bare_url_exempt_from_width():
    trailer = (
        "Repair the roster tab selection\n\n"
        "Judge the highlight instead of the screen class.\n\n"
        "Claude-Session: https://claude.ai/code/session_01MhAMxKgXqtrhfTeX1BfWKX\n"
        "https://claude.ai/code/session_01MhAMxKgXqtrhfTeX1BfWKXaaaaaaaaaaaaaaaaaaaa"
    )
    assert check(trailer) == []


def test_backtick_and_chinese_and_british_spelling():
    assert any("backtick" in p for p in check("Repair the `roster` tab selection"))
    assert any("非英文" in p for p in check("Repair 名冊 tab selection"))
    assert any("英式拼法" in p for p in check("Recentre the aim on measured centre"))


def test_quotes_exempt_identifiers_and_ui_terms():
    quoted = (
        "Repair the roster tab selection\n\n"
        "The '顯示方格' toggle drives 'relocalise', so 'SCREEN_CENTRE' stays as is."
    )
    assert check(quoted) == []


def test_git_comments_and_scissors_are_stripped():
    noisy = (
        "Repair the roster tab selection\n"
        "# Please enter the commit message for your changes.\n"
        "\n"
        "Judge the highlight instead of the screen class.\n"
        "------------------------ >8 ------------------------\n"
        "diff --git a/src/x.py b/src/x.py\n"
        "-    這行中文與 `backtick` 在 diff 裡，不該被判違規\n"
    )
    assert check(noisy) == []
