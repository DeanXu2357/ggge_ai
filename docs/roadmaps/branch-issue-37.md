# Branch roadmap: issue 37

> Type: working—deleted at merge

Issue: #37 — add the five stream-branch terms to
docs/reference/terminology-map.md.
Branch: issue-37-terminology-entries, off 'dev' at 9e8750f.
Status: awaiting-review.

## Change summary

One file changed: docs/reference/terminology-map.md. Five rows added
at the end of the "Term bindings" table. The 30 rows that were there
before are unchanged. The change is docs-only: every diff path is
under docs/, so the pytest and ruff gates do not apply.

| English | Traditional Chinese | Source of the binding |
|---|---|---|
| veil | 待裁 | no Chinese term in the corpus |
| stream frame source | 串流幀源 | runtime/entry.py:109 |
| roster stage | 名冊採集 | runtime/roster_capture.py:1, sweep_scan.py:281 |
| settle | 待裁 | no Chinese term in the corpus |
| projection | 透視投影 | runtime/projection.py:1, decisions.md:936 |

## Corpus evidence for each Chinese binding

- veil. The only Chinese use is decisions.md:1256 in the 0811 ruling:
  「①veil 硬閘單幀即生效」. The word stays English inside Chinese
  prose. The Chinese words near it name the data, not the gate:
  sweep.py:669 calls the value 「暫定界格」and sweep.py:373 returns
  「暫定界格索引」. A gate has no name in Chinese yet, so the row
  says 待裁. See the contention points.
- stream frame source. entry.py:109 writes 「串流幀源取幀只要
  11ms」, which is the term itself. The head noun 幀源 is already the
  word for the single frame source: sweep_scan.py:106 and
  decisions.md:777-778 (the 0806 D5 ruling, 「單一幀源」).
  串流 is the settled word for stream: stream/__init__.py:1,
  stream/source.py:1, decisions.md:1204. This binding needs no
  invention.
- roster stage. The stage runner in scripts/sweep_scan.py:281 has the
  docstring 「名冊採集＋帳本落檔」, and roster_capture.py:1 opens
  with 「名冊採集：戰鬥選單「部隊資訊」逐格點開詳情」. The 0810
  ruling (decisions.md:1232-1233) states the same concept with
  「進部隊資訊名冊逐台讀敵我全部詳情頁」and names the new step in
  English ("sweep_scan 尾端新 stage"). 名冊採集 is therefore the
  corpus name for the concept.
- settle. settle.py:1 states the module as 「感知節奏原語：幀差量測
  與「等畫面收斂再取樣」」; roster_capture.py:4 and sweep.py:952-953
  use 「幀差收斂」for the measurement; settle.py:17 uses 「盡力靜
  置」for the semantics. The 0809 rulings (decisions.md:1204-1215)
  write the primitive itself in English: 「settle 耗時入帳」,
  「nav settle 提速」. No Chinese noun names the primitive, so the
  row says 待裁. See the contention points.
- projection. projection.py:1 opens with 「盤面透視投影：世界等距格
  網 → 螢幕格線位置」and states 「固定的平面單應性」. The 0803 late
  ruling (decisions.md:936) uses the same term: 「未建模的透視投
  影」. The row binds 透視投影, not the bare 投影, because board.py
  (lines 289, 395, 425-428) uses 投影 for the row and column sums
  that find the grid-line peaks. The Meaning column states this
  difference.

## Contention points

The user must rule on the Chinese side of two terms. The rows carry
待裁 until then.

1. veil. Candidates:
   - 暫定界閘 — keeps the gate sense; pairs with 暫定界格, the word
     already in sweep.py.
   - 暫定邊界閘 — the same, with the full word for border.
   - veil (no translation) — makes the current practice official; the
     0811 ledger and the code already do this.
2. settle. Candidates:
   - 靜置 — the word settle.py:17 uses for the semantics
     (「盡力靜置」).
   - 幀差收斂 — the word the call sites use; states the mechanism,
     but is a noun phrase, not a verb.
   - settle (no translation) — makes the current practice official;
     the 0809 rulings already do this.

One more item needs a confirmation, not a ruling:

3. roster stage. The binding 名冊採集 comes from the corpus, but the
   two sides are not word for word: the Chinese head noun is 採集
   (capture), not stage. A word-for-word binding is not available,
   because the map already binds stage to 關卡, the game mission.
   Reject the row if you want a different head noun.

## Commits

- f21af99 Add the branch roadmap for issue 37
- fefa8f1 Bind the five stream-branch terms in the term map
