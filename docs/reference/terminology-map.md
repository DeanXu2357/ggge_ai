# Terminology map

> Type: reference—drift is a bug

This file records the words that were ambiguous inside the project
and the reading the user settled. Use one term for one concept. When
you write English, use the English column. When you write Chinese,
use the Traditional Chinese column. Do not create a new translation
for a bound concept.

A row is admitted only when the word is ambiguous inside the project,
the user settled the reading, and the code and the spec cannot settle
it. A Go identifier, a package, a file, a wire field or a step inside
one function is never a row. A row holds the two names and one
sentence that states the settled reading; a Go pointer, a date or a
history goes in the commit message or in docs/record/decisions.md.
The full tests are in the Terminology section of CLAUDE.md.

New project text is English (0811 user ruling): replies to the user,
docs/, and commit messages. The frozen Chinese corpus (old entries in
docs/record/decisions.md, plus retired documents in git history)
stays in Traditional Chinese.

## Term bindings

For a metaphor term (island, mainland, ghost, starfield): define the
term at its first use in each document, then use the short form.

| English | Traditional Chinese | Meaning |
|---|---|---|
| stage | 關卡 | One playable mission in the game. Not a step of a run |
| grid | 格網 | The in-game board grid, the '顯示方格' overlay |
| island | 島嶼 | The holding area for observations whose positions are unknown after a localization break |
| mainland | 大陸 | The trusted-position side of the knowledge map, opposite of the island |
| ghost | 幽靈 | A false item with no real counterpart on screen; name the kind: a false shift candidate, a false unit detection, or a false peak |
| starfield | 星空 | The dark background outside the map, with no grid cells. Not "sparse sightings" |
| veil | 暫定界遮罩 | The provisional border gate: the cover drawn for one frame over the cells outside the provisional bounds. Short form 界遮罩 after the first use. Not the coverage mask and not the mask of the danger-band shapes |
| settle | 幀差取樣 | Sample after the frame difference falls, or at the deadline, whichever is first. Not 收斂, because a long animation can release at the deadline without becoming still. Accepted alternate reading: 收斂取樣 |
| blind sleep | 盲睡 | A fixed-time wait that measures nothing; it keeps the English word settle in old names but is not the settle primitive |
| projection | 透視投影 | The fixed planar homography of the board. Not the bare word 投影, which board.py uses for the row and column sums |
| allowance | 額度 | How many times a unit may take an action in a battle: a support attack, a support defense, or a chance step. Not a count: nothing is tallied |
| sandbox | 沙盤 | The program's own simulation of one stage battle: the board and the page, never a Python rule module |
| expectiminimax | expectiminimax | Keep the English form in Chinese text: there is no Chinese binding |
| first strike | 先攻 | The weapon trait marked by the orange '先發攻擊' label above the portrait |
| activation | 啟動 | One action of one unit in one phase. Not 行動, which the frozen corpus holds for the kind of a response attack and for the defense multiplier |
| response attack | 應戰 | The answer of the defender to one strike. Not 'reaction', which is the pilot value 反應值; do not use 'reaction' or 'response' alone for this concept |
| response attack stance | 應戰姿態 | The defense the target picks in a response attack. The game UI words are 閃避 for 'dodge', 防禦 for 'defend', 防禦（盾牌）for 'shield' and 反擊 for 'counter'; the value 'none' has no game UI word, and the battle page writes 無反應 |
| support defender | 支援防禦者 | A unit that takes a strike for a unit of its own faction. Not 'interceptor' 攔截者, a sandbox name; the game labels it 支援防禦 |
| mech | 機體 | The machine of a unit. Do not write "unit attack" or "unit defense" for the attack and the defense of a mech |
| pilot | 駕駛 | The character that rides the mech: 射擊值 'ranged', 格鬥值 'melee', 覺醒值 'awaken', 守備值 'defense', 反應值 'reaction'. The datamine names a pilot "character" |
| pending ruling | 待裁 | The marker for an item that needs a ruling from the user, not more evidence. Write the English form in new text; the Chinese form stays in the frozen record |
| defense multiplier | 防禦行動倍率 | The multiplier of the response attack stance in formula 10. A shield is a second cut on top of the defense, not a stance of its own |
| direct weapon | 直射武裝 | A weapon that strikes one unit and that an exchange resolves; the opposite of a map weapon |
| apply shape | 施放形狀 | The cells where the center of a map weapon or a skill can sit. Not the effect shape: the apply shape picks the center, the effect shape spreads from it |
| effect shape | 效果形狀 | The cells that a map weapon or a skill acts on, spread from the chosen center. Not the apply shape |
| hit rate | 命中率 | The percent chance that one strike lands, the number the attack forecast screen shows. Not the weapon accuracy |
| weapon accuracy | 武裝命中值 | A fixed value of one weapon, the same against every target; the datamine names it 'hit_rate' |
| unit role | 類型 | The enum 'role' of a unit row and of a pilot row of the datamine: 1 攻擊型, 2 耐久型, 3 支援型; the filter '類型' of the game |
| weapon category | 武裝類別 | One of 射擊, 格鬥, 覺醒 of a weapon. Not a tag, not an attack attribute, not the datamine 'type' (normal, Ex, map) and not the damage attribute 'weapon_attr' (物理, 光束, 特殊) |

## Legacy Chinese corpus key

The frozen Chinese corpus uses the terms below. The 0802 ruling
replaced banned direct-translation terms with them; the full ruling
tables are in this file's git history (0803 version). When new
English text needs one of these concepts, add an English binding to
the table above in the same change.

| Chinese term | Meaning |
|---|---|
| 合理範圍閘／合理範圍檢查 | The check that a measured shift has the same axis and sign as the command, with an upper bound on the ratio |
| 佐證來源／多路佐證裁決／無佐證 | Independent measurement sources (grid phase, unit arrangement, correlator, map edge) that confirm each other; accept a result only on agreement |
| 單位排列比對 | Matching the relative positions of on-screen units as a pattern; used for relocalization after a localization break |
| 邊緣回彈 | The camera bounce the game applies at the map edge |
| 待掃格 | An in-bounds cell next to the mapped area, not yet scanned; "no 待掃格" means the scan is complete |
| 定位中斷 | One step of the dead-reckoning chain has an untrusted measurement; later positions cannot attach to the world map |
