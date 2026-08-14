# Branch roadmap: issue 37

> Type: working—deleted at merge

Issue: #37 — add the stream-branch terms to
docs/reference/terminology-map.md.
Branch: issue-37-terminology-entries, off 'dev' at 9e8750f.
Status: awaiting-review.

## Change summary

One file changed: docs/reference/terminology-map.md. Six rows added at
the end of the "Term bindings" table. The 30 rows that were there
before are unchanged. The change is docs-only: every diff path is
under docs/, so the pytest and ruff gates do not apply.

The first version added five rows, two of them with a 待裁 placeholder.
The user then ruled on the pending bindings. The rows below are the
final state. No placeholder is left.

| English | Traditional Chinese | Ruling or corpus source |
|---|---|---|
| veil | 暫定界遮罩 | user ruling; the word 遮罩 from sweep.py:383 |
| stream frame source | 串流幀源 | runtime/entry.py:109 |
| roster capture | 名冊採集 | runtime/roster_capture.py:1, sweep_scan.py:281 |
| segment | 分段 | scripts/sweep_scan.py:9 |
| settle | 幀差取樣 | user ruling |
| blind sleep | 盲睡 | docs/record/roadmap.md, 0807 entry, in git history |
| projection | 透視投影 | runtime/projection.py:1, decisions.md:936 |

The English side changed with the rulings. The term "roster stage" is
gone: it bound two concepts at once, so it is now roster capture (the
action) and segment (the phase of the run). The term blind sleep is
new; it names the older sense of the word settle.

## Evidence for each row

- veil ↔ 暫定界遮罩 (short form 界遮罩). User ruling. The veil is not
  the border: it is the cover over the cells outside the provisional
  border, for one frame. The word 遮罩 comes from the docstring at
  sweep.py:383: 「這裡算的是單幀讀數，只夠當「這一窗別點過去」的遮
  罩，不進帳本、不寫地標」. The data keeps its own word 暫定界格
  (sweep.py:373 「暫定界格索引」, sweep.py:669). The Meaning column
  keeps the term clear of the two masks that exist: the coverage mask
  (coverage.py:1493,1497) and the mask that chases the danger-band
  shapes (device.py:153). The behaviour comes from plan_window at
  sweep.py:688: a covered cell continues before ledger.chart, so it
  gets no tap, no blocked, no inferred, and no chart entry.
- stream frame source ↔ 串流幀源. entry.py:109 writes 「串流幀源取幀
  只要 11ms」, which is the term itself. The head noun 幀源 is already
  the word for the single frame source: sweep_scan.py:106,
  decisions.md:777-778 (0806 D5 ruling, 「單一幀源」). 串流 is the
  settled word for stream: stream/__init__.py:1, stream/source.py:1,
  decisions.md:1204.
- roster capture ↔ 名冊採集. roster_capture.py:1 opens with 「名冊採
  集：戰鬥選單「部隊資訊」逐格點開詳情」; the runner in
  scripts/sweep_scan.py:281 has 「名冊採集＋帳本落檔」. The 0810
  ruling (decisions.md:1232-1233) states the same concept. The row
  cites the class RosterCapture and the journal events roster_capture
  (roster_capture.py:551) and roster_capture_summary
  (roster_capture.py:227).
- segment ↔ 分段. scripts/sweep_scan.py:9 writes 「分段停點：select /
  prep / stage_info / map / grid / zero / sweep / roster」, which is
  the STAGES tuple at scripts/sweep_scan.py:62 and the values of
  --stop-after. The same word names a phase of a run in the code
  (stage/state.py:48, stage/survey.py:21 「分段進度」) and in the
  ledger (decisions.md:890 「分段停點做在可測層」). The Meaning column
  states that this is not the sense of stage ↔ 關卡, and that the
  STAGES tuple holds both senses, because its member stage_info names
  the 關卡 information screen.
- settle ↔ 幀差取樣. User ruling. The mechanism facts in the row come
  from settle.py: await_still (line 66) samples with the interval
  poll, measures frame_motion (the fraction of pixels over
  SETTLE_DIFF_NOISE), and returns when that fraction stays under
  stable for 'confirm' pairs, or when the deadline arrives (lines
  89-102). The SettleReport carries 'converged' (line 62), and the
  journal event settle records it (sweep_scan.py:1464-1472, with the
  field ctx nav or feedback). The user's reason for not naming the
  term after 收斂: an event after a tap can be a long animation that
  does not become still. The accepted alternate reading 收斂取樣 is in
  the row. The four call sites: entry.py:295 (stage title, before the
  slide-in ends), sweep_scan.py:1454 in settled() with confirm=2
  (navigation, journal ctx nav), sweep.judge_tap at sweep.py:973 (tap
  feedback, journal ctx feedback), and roster_capture.py:564 in
  _settled() (detail-page transitions).
- blind sleep ↔ 盲睡. The word comes from the 0807 improvement queue
  in docs/record/roadmap.md: 「③盲睡 settle（PAN_SETTLE_S=1.5 等常
  數）＝節奏地板，歸串流批次的幀差收斂解」. That file was deleted when
  the development flow started, so the source is git history: the
  document at d541bfc^ holds the line. The constants exist as the
  ruling states: board.PAN_SETTLE_S (board.py:179), ROSTER_SETTLE_S
  and SETTLE_ROUNDS (stage/survey.py:64,73), settle_s
  (battle/map_view.py:105,149,219), ABANDON_SETTLE_ATTEMPTS and
  ABANDON_SETTLE_INTERVAL_S (entry.py:495-496).
- projection ↔ 透視投影. Unchanged from the first version.
  projection.py:1 opens with 「盤面透視投影：世界等距格網 → 螢幕格線
  位置」and states 「固定的平面單應性」; decisions.md:936 uses 「未建
  模的透視投影」. The row binds 透視投影, not the bare 投影, because
  board.py (lines 289, 395, 425-428) uses 投影 for the row and column
  sums that find the grid-line peaks.

## Contention points

1. Residue of the word stage in the code. The journal event
   roster_stage_failed (roster_capture.py:222, sweep_scan.py:291) and
   the --stop-after value roster keep the word stage. The user ruled
   to leave them alone: a new event name is a schema change, and the
   old run journals would stop matching. The table binds the terms,
   not the identifiers.
2. The word 遮罩 has three uses in the corpus now: the veil, the
   coverage mask (coverage.py), and the mask that chases the
   danger-band shapes (device.py:153). Only the veil has a bound term.
   The other two get a term when a document needs one.
3. The blind sleep list is open, not closed. More parameters carry the
   word settle in their names than the six the ruling lists: settle_s
   on Tap, Swipe, and Key (device.py:58,69,75), settle_s in
   zoom.py:167 and entry.py:99, and NAV_SETTLE_INTERVAL_S
   (entry.py:534). The row says "Examples:" for that reason.

## Facts that do not match the rulings

- The ruling calls device.py:153 the colour mask. The text there is
  about the shape of the danger bands against the shape of the
  buttons: 「先問帶，不要逐一補遮罩去追帶的形狀」. It is a
  tappability mask, not a colour mask. The corpus does hold a colour
  mask, but in another place: decisions.md:519 「弧色遮罩」. The
  Meaning column states the device.py mask as the danger-band one.
- The ruling states SETTLE_POLL_S and SETTLE_WAIT_S as the interval
  and the deadline of await_still. Both are parameters of the
  function; the module constants are the values that most call sites
  pass. Two call sites pass other values: entry.py:295 passes
  STAGE_TITLE_SETTLE_S and STAGE_TITLE_POLL_S, and sweep.judge_tap
  defaults the interval to FEEDBACK_POLL_S with a deadline from its
  caller.
- Line numbers off by one in the ruling: settled() is defined at
  sweep_scan.py:1453 and calls await_still at 1454; _settled() is
  defined at roster_capture.py:563 and calls await_still at 564.
- Not verified: the figure from run 20260811-110638, 37 of 552
  feedback waits ending at the deadline. data/runs is untracked and
  lives in the primary checkout, which this session must not touch.
  The figure is not in the table; it stays here as the user gave it.

## Commits

- f21af99 Add the branch roadmap for issue 37
- fefa8f1 Bind the five stream-branch terms in the term map
- c007ec4 Rework the branch roadmap into the review artifact
- d3620f4 Settle the Chinese side of the new term rows
- 7d10648 Open the blind sleep list to more constants
