"""commit-msg 閘門：機械可判定的 commit message 規則。

判斷型規則（祈使句、what/why、參照是否齊全、敘述夠不夠詳細）不在這裡，
歸 CLAUDE.md 的 Writing discipline 節，由作者負責。

坑：
- **引號內一律豁免拼字與非英文檢查**。程式識別字用英式拼法（'relocalise'、
  'SCREEN_CENTRE'、'centred'）與遊戲 UI 詞（'顯示方格'、'應戰'）都只能照原樣
  寫，所以引號是唯一的逃生口——這也正是「禁用 backtick、改用單雙引號」那條
  規則的用途。
- **祈使句不做構詞判定**。'Speed up ...' 的 Speed 以 ed 結尾、'Bring ...' 的
  Bring 以 ing 結尾，構詞猜測會誤殺;只擋一份明確的非祈使句開頭字表。
- trailer 行（Co-Authored-By、Claude-Session）與單一不可斷 token（URL／路徑）
  豁免 72 欄上限：harness 強制的 session URL 本身就超過。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SUBJECT_MAX = 50
BODY_MAX = 72
SCISSORS = "------------------------ >8 ------------------------"

NON_IMPERATIVE = frozenset(
    """fixed fixes added adds updated updates removed removes changed changes
    refactored refactors implemented implements improved improves created creates
    deleted deletes moved moves renamed renames bumped bumps documented documents
    corrected corrects reverted reverts""".split()
)

BRITISH = frozenset(
    """colour colours behaviour behaviours centre centres centred organise
    organised initialise initialised analyse analysed licence catalogue
    normalise normalised serialise optimise optimised recognise recognised
    localise localised relocalise cancelled travelled labelled modelling
    favour honour defence offence""".split()
)

CJK = re.compile(r"[　-〿一-鿿豈-﫿＀-￯]")
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
TRAILER = re.compile(r"^[A-Z][A-Za-z0-9-]*: \S")
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def strip_noise(text: str) -> str:
    body, _, _ = text.partition(SCISSORS)
    kept = [line for line in body.splitlines() if not line.startswith("#")]
    while kept and not kept[0].strip():
        kept.pop(0)
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept)


def mask_quoted(line: str) -> str:
    return QUOTED.sub(lambda m: " " * len(m.group()), line)


def check_subject(subject: str) -> list[str]:
    problems = []
    if len(subject) > SUBJECT_MAX:
        problems.append(f"標題 {len(subject)} 字元，上限 {SUBJECT_MAX}：{subject}")
    if subject[:1].isalpha() and not subject[:1].isupper():
        problems.append(f"標題開頭要大寫：{subject}")
    if subject.endswith("."):
        problems.append(f"標題不以句點結尾：{subject}")
    if "(" in subject or ")" in subject:
        problems.append(f"標題不用括號，補述請移到內文：{subject}")
    words = subject.split()
    if len(words) < 3:
        problems.append(f"標題太短，要具體描述變更而非 'Update queue.c'：{subject}")
    if words and words[0].lower().strip(":") in NON_IMPERATIVE:
        problems.append(f"標題用祈使句（Fix 而非 Fixed／Fixes）：{words[0]}")
    return problems


def check_body(lines: list[str]) -> list[str]:
    problems = []
    for number, line in enumerate(lines, start=3):
        if len(line) <= BODY_MAX or TRAILER.match(line) or len(line.split()) == 1:
            continue
        problems.append(f"第 {number} 行 {len(line)} 字元，內文上限 {BODY_MAX}")
    return problems


def check_language(lines: list[str]) -> list[str]:
    problems = []
    for number, line in enumerate(lines, start=1):
        masked = mask_quoted(line)
        if CJK.search(masked):
            problems.append(f"第 {number} 行有引號外的非英文字：{CJK.search(masked).group()}")
        for word in WORD.findall(masked):
            if word.lower() in BRITISH:
                problems.append(f"第 {number} 行用英式拼法 '{word}'，改美式或加引號引用識別字")
    return problems


def check(text: str) -> list[str]:
    message = strip_noise(text)
    lines = message.splitlines()
    if not lines:
        return ["commit message 是空的"]
    problems = check_subject(lines[0])
    if len(lines) > 1:
        if lines[1].strip():
            problems.append("標題與內文之間要有一行空白行")
        problems.extend(check_body(lines[2:]))
    if "`" in message:
        problems.append("禁用 backtick（部分終端機顯示不出），改用單引號或雙引號")
    problems.extend(check_language(lines))
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_commit_msg.py <commit-msg-file>", file=sys.stderr)
        return 2
    problems = check(Path(argv[1]).read_text(encoding="utf-8"))
    if not problems:
        return 0
    print("commit message 不合規則（見 CLAUDE.md 的 Writing discipline 節）：", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
