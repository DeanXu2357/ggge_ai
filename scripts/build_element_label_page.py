"""Build the page where the user rules, frame by frame, the state of an interpreter element.

Usage: uv run python scripts/build_element_label_page.py <element> data/labeled <template html> <out dir>

The page shows the area around the element on every labeled frame, ordered by the
element score, without the score. The full frames go to <out dir>/full/.
"""

import base64
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ggge_ai_2.interpreter.elements.menu_key import MENU_LINES_REGION, menu_key_white_share
from ggge_ai_2.interpreter.elements.region import Region
from ggge_ai_2.interpreter.elements.round_button import round_ring_coverage
from ggge_ai_2.interpreter.elements.top_left_title import TITLE_REGION, title_ious
from ggge_ai_2.interpreter.elements.turn_box import TURN_BOX_REGION, turn_box_white_share

ROUND_BUTTON_BOX: Region = (0.825, 0.741, 0.936, 0.981)
CONTEXT_SCALE = 0.8
FULL_SIZE = (1170, 540)
UNCLEAR = ("unclear", "判不了", "unclear")


@dataclass(frozen=True)
class Element:
    region: Region
    score: Callable[[np.ndarray], float]
    context: Region
    title: str
    question: str
    values: tuple[tuple[str, str, str], ...]


ELEMENTS = {
    "turn_box": Element(
        TURN_BOX_REGION,
        turn_box_white_share,
        (0.0, 0.0, 0.26, 0.15),
        "TURN 框逐幀判例",
        "請判斷這一幀有沒有 TURN 框。",
        (("present", "有", "yes"), ("absent", "無", "no"), UNCLEAR),
    ),
    "menu_key": Element(
        MENU_LINES_REGION,
        menu_key_white_share,
        (0.70, 0.0, 1.0, 0.15),
        "≡ 選單鍵逐幀判例",
        "請判斷這一幀右上角的 ≡ 選單鍵：<b>亮</b>（可以點）、<b>暗</b>（在但變暗），或<b>無</b>（畫面上沒有這個鍵）。",
        (("lit", "亮", "yes"), ("dark", "暗", "mid"), ("absent", "無", "no"), UNCLEAR),
    ),
    "top_left_title": Element(
        TITLE_REGION,
        lambda image: max(title_ious(image).values()),
        (0.0, 0.0, 0.30, 0.16),
        "左上戰鬥標題逐幀判例",
        "請判斷這一幀左上角的戰鬥標題（TURN 框上方那一行白字）寫什麼。"
        "標題不在選項裡時選<b>其他標題</b>，畫面上沒有這種標題時選<b>無</b>。",
        (
            ("player_phase", "我軍回合", "yes"),
            ("unit_move", "單位移動", "yes"),
            ("select_weapon", "選擇武裝", "yes"),
            ("battle_prep_attack", "戰鬥準備 -攻擊-", "yes"),
            ("battle_prep_response", "戰鬥準備 -應戰-", "yes"),
            ("enemy_phase", "敵軍回合", "yes"),
            ("skill", "技能", "yes"),
            ("other", "其他標題", "mid"),
            ("absent", "無", "no"),
            UNCLEAR,
        ),
    ),
    "round_button": Element(
        ROUND_BUTTON_BOX,
        round_ring_coverage,
        (0.76, 0.62, 1.0, 1.0),
        "右下圓鈕逐幀判例",
        "請照圓鈕上的字判斷這一幀右下角的大圓鈕是哪一種，畫面上沒有圓鈕時選<b>無</b>。",
        (
            ("select_weapon", "選擇武裝", "yes"),
            ("attack", "攻擊", "yes"),
            ("attack_out_of_range", "射程外攻擊", "mid"),
            ("select_action", "行動選擇", "yes"),
            ("activate", "發動", "yes"),
            ("start_battle", "開始戰鬥", "yes"),
            ("absent", "無", "no"),
            UNCLEAR,
        ),
    ),
}


def pixels(region, w, h):
    left, top, right, bottom = region
    return int(left * w), int(top * h), int(right * w), int(bottom * h)


def jpeg(image, quality):
    return cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()


def context(image, element: Element):
    h, w = image.shape[:2]
    x0, y0, x1, y1 = pixels(element.context, w, h)
    out = image[y0:y1, x0:x1].copy()
    bx0, by0, bx1, by1 = pixels(element.region, w, h)
    cv2.rectangle(out, (bx0 - x0 - 4, by0 - y0 - 4), (bx1 - x0 + 3, by1 - y0 + 3), (0, 220, 255), 2)
    out = cv2.resize(out, None, fx=CONTEXT_SCALE, fy=CONTEXT_SCALE, interpolation=cv2.INTER_AREA)
    return base64.b64encode(jpeg(out, 82)).decode()


def main(name: str, labeled: Path, template: Path, out: Path) -> None:
    element = ELEMENTS[name]
    rows = [
        json.loads(line)
        for line in (labeled / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    (out / "full").mkdir(parents=True, exist_ok=True)
    cases = []
    for row in rows:
        image = cv2.imread(str(labeled / "frames" / row["file"]))
        assert image is not None, row["id"]
        (out / "full" / f"{row['id']}.jpg").write_bytes(
            jpeg(cv2.resize(image, FULL_SIZE, interpolation=cv2.INTER_AREA), 78)
        )
        cases.append(
            {
                "id": row["id"],
                "screen": row["screen"],
                "auto": row["auto"],
                "power_save": row["power_save"],
                "transition": row["transition"],
                "score": element.score(image),
                "crop": context(image, element),
            }
        )
    cases.sort(key=lambda c: (-c["score"], c["id"]))
    for case in cases:
        del case["score"]
    config = {"collection": name, "values": [list(value) for value in element.values]}
    page = (
        template.read_text(encoding="utf-8")
        .replace("__TITLE__", element.title)
        .replace("__QUESTION__", element.question)
        .replace("/*CONFIG*/{}", json.dumps(config, ensure_ascii=False))
        .replace("/*CASES*/[]", json.dumps(cases, ensure_ascii=False))
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    print(out / "index.html", (out / "index.html").stat().st_size, len(cases))


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
