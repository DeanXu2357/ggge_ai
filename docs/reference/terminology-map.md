# Terminology map

> Type: reference—drift is a bug

This file is the project dictionary. Use one term for one concept.
When you write English, use the English column. When you write
Chinese, use the Traditional Chinese column. Do not create a new
translation for a bound concept. When a concept has no entry, add the
binding in the same change that introduces the term.

New project text is English (0811 user ruling): replies to the user,
docs/, and commit messages. The frozen Chinese corpus (old entries in
docs/record/decisions.md, plus retired documents in git history)
stays in Traditional Chinese.

## Term bindings

For a metaphor term (island, mainland, ghost, starfield): define the
term at its first use in each document, then use the short form.

| English | Traditional Chinese | Meaning |
|---|---|---|
| device | 實機 | The physical USB phone R5CRC37JBYJ |
| device screenshot | 實機截圖 | A screenshot captured from the device |
| run log | 流水帳 | The structured output in data/runs/<timestamp>/ |
| pause snapshot | 暫停快照 | Retired 0812: split into the device state file and the branch roadmap; history in git (docs/record/roadmap.md) |
| resume point | 恢復點 | The step where the next session starts work |
| session start / end of session | 開工／收工 | The start and the end of a work session |
| gate | 閘門 | A check that must pass before a commit (pytest, ruff) |
| docs-only change | 純文件變更 | A change whose diff paths are all in docs/ |
| stage | 關卡 | One playable mission in the game |
| abandon battle | 棄戰 | Leave a battle through the in-game retreat flow |
| sighting | 目擊 | A unit observation recorded during a scan |
| grid | 格網 | The in-game board grid (the '顯示方格' overlay) |
| screen name | 畫面名 | The classifier label for the current screen |
| requirements document | 需求文件 | A document that answers "why" and states the problem as outcomes; see the CLAUDE.md section 'Requirements documents' |
| gain | 增益 | Standard Taiwanese engineering term (0802 ruling: retained) |
| odometry | 里程計 | Standard Taiwanese engineering term (0802 ruling: retained) |
| island | 島嶼 | The holding area for observations whose positions are unknown after a localization break; they merge back after relocalization |
| mainland | 大陸 | The trusted-position side of the knowledge map, opposite of the island |
| ghost | 幽靈 | A false item with no real counterpart on screen; name the kind: a false shift candidate, a false unit detection, or a false peak |
| starfield | 星空 | The dark background outside the map, with no grid cells. Not "sparse sightings" (0803 audit: all 20 uses mean the outside background) |
| integration branch | 整合分支 | The long-lived branch 'dev'; task branches start from it and merge into it |
| task branch | 任務分支 | The branch 'issue-N-slug' for one GitHub issue |
| primary checkout | 主目錄 | The directory /home/poyu/workspace/project/ggge_ai; rests on 'dev'; hosts the device lock and the device state file |
| worktree | 工作樹 | A git worktree under /home/poyu/workspace/project/ggge_ai-worktrees/; every session develops in one |
| branch roadmap | 分支路線圖 | The working document docs/roadmaps/branch-issue-N.md; progress log during development, review artifact at review, deleted at merge |
| device lock | 裝置鎖 | The untracked file docs/record/device.lock; serializes device access across sessions |
| device state file | 裝置狀態檔 | The untracked file docs/record/device-state.md; the current device snapshot only |
| state block | 狀態區塊 | The 'Session state' section in an issue body: branch, roadmap, status |
| review artifact | 審查對照物 | The document the user reads to review a branch; the branch roadmap at awaiting-review |
| veil | 暫定界遮罩 | The provisional border gate: the cover drawn for one frame over the cells outside the provisional bounds (provisional_bounds in runtime/sweep.py). A covered cell is not tapped, not blocked, not inferred, and not charted; the next window enumerates it again. The bounds themselves stay 暫定界格. Short form 界遮罩 after the first use. Not the coverage mask (runtime/coverage.py), and not the mask of the danger-band shapes (runtime/device.py) |
| stream frame source | 串流幀源 | The scrcpy plus v4l2 frame path in ggge_ai/stream/; selected with 'sweep_scan.py --stream', in place of the adb screenshot path |
| roster capture | 名冊採集 | Open the detail page of every unit in the '部隊資訊' roster and keep one frame for each page: runtime/roster_capture.py, the class RosterCapture, the journal events roster_capture and roster_capture_summary |
| segment | 分段 | A phase of a run, and the section of code that runs it: the members of the STAGES tuple in scripts/sweep_scan.py and the values of --stop-after ('分段停點' in the same file). This is a different sense from stage ↔ 關卡. STAGES holds both senses today: its member stage_info names the 關卡 information screen |
| settle | 幀差取樣 | Sample after the frame difference falls: await_still in runtime/settle.py polls the difference of the frames pixel by pixel (interval SETTLE_POLL_S) and takes the frame when the fraction of moving pixels goes under the threshold, or when the deadline (SETTLE_WAIT_S) arrives, whichever is first. The settle journal event records which of the two in its 'converged' field. The name does not use 收斂, because an event after a tap can be a long animation that does not become still, and the primitive releases at the deadline. Accepted alternate reading: 收斂取樣, because the release at the deadline is a defined convergence point |
| blind sleep | 盲睡 | The fixed-time wait that the settle primitive replaces. Examples: board.PAN_SETTLE_S, ROSTER_SETTLE_S and SETTLE_ROUNDS in stage/survey.py, settle_s in battle/map_view.py, ABANDON_SETTLE_ATTEMPTS and ABANDON_SETTLE_INTERVAL_S in runtime/entry.py. It measures nothing. These names keep the English word settle although they are not the settle primitive |
| projection | 透視投影 | The fixed planar homography of the board (runtime/projection.py): world isometric grid to screen grid-line positions. Not the bare word 投影, which board.py uses for the row and column sums |
| battle engine | 戰局引擎 | The Go process that holds the board of one battle and answers commands on stdin and stdout. It carries the simulation and the search. The contract is docs/spec/battle-engine-protocol.md |
| sandbox | 沙盤 | The program's own simulation of one stage battle: our model of the mechanisms that the game runs on the device. The rules live in the Go engine (engine/); the Python side holds the contract, the client and the fake (ggge_ai/engine/). The word names the board and the page, never a Python rule module |
| scenario file | 情境檔 | The JSON stage layout that stage/scenario.py reads into a starting board: who stands where, the rules overrides, the event table. Unit values come from the intel store |
| advisor | 顧問 | The inner tactical layer that appraises a state and prices candidate actions: the 'Advisor' protocol in stage/advise.py. It advises the planning layer; it does not plan |
| expectiminimax | expectiminimax | The search above the sandbox that the advisor runs; the chance nodes carry the hit and the crit rolls. Keep the English form in Chinese text: there is no Chinese binding |
| play mode | 操作模式 | The battle page mode that plays the board under the turn rules: only units of the current phase faction accept commands, and every change goes to the engine through 'EngineSession' |
| edit mode | 編輯模式 | The battle page mode that writes unit values into the board without the turn rules, for a formula check. The engine command is 'set_unit'. Not implemented: issue #43 owns it |
| operation history | 操作史 | The ordered list of the operations of one sandbox session, the edit-mode changes included; undo removes the last entry and restores the snapshot before it. The battle engine holds the same list: 'act', 'place', and 'set_unit' write an entry, and 'rollback' removes the last one |
| first strike | 先攻 | The weapon trait that puts a strike into an extra queue before the normal resolution order; the mark is the orange '先發攻擊' label above the portrait. The sandbox has no first-strike queue today |
| Ex weapon | Ex 武裝 | The weapon of a UR unit. Its judgment is above all abilities: the attack always hits, and it ignores some kinds of damage reduction (user ruling 2026-08-14; which kinds is open) |
| support crew skill | 支援人員技能 | A skill that any unit in the team can trigger; the team can use each one one time in each stage. The effect covers the units in range |
| pilot skill | 駕駛技能 | A skill that consumes pilot SP; the effect applies to the unit that the pilot rides |
| mech skill | 機體技能 | A skill that the mech triggers at no cost; the effect applies mostly to the mech itself. The wire keeps 'unit' as the value of the skill source; the term names the level, and the level is the mech |
| skill source | 技能來源 | Who supplies a skill: the field 'source' of 'Skill' (engine/state.py). The three values bind to the three rows above: 'pilot' is the 駕駛技能 row, 'crew' is the 支援人員技能 row, and 'mech' is the 機體技能 row. Two values were renamed on 2026-08-26: 'unit' became 'mech', because a unit is a pilot and a mech together and a machine skill comes from the mech alone; 'character' became 'pilot', because the engine names that level 'Pilot' everywhere else and one concept takes one term. The source does not decide the timing of the skill: 'usable_after_move' is a field of each skill |
| affects | 作用陣營 | The faction filter of the area of a skill: the field 'affects' of 'Skill'. The values are 'ally', 'enemy' and 'all'. There is no 'self' value: a skill that acts on the caster alone carries a range of 0, a blast of 0 and 'ally', because the caster is an ally in its own cell. The Chinese term keeps 陣營, which battle-prep-ui.md holds for the same sense of faction |
| engine session | 引擎工作階段 | The class 'EngineSession' in engine/session.py. It holds one battle, sends the start state to the engine and asks the engine every question. It holds no rule: a question that needs one goes on the wire |
| capability payload | 能力酬載 | The answer of the engine command 'actions': what one unit carries. It holds the status of the unit, the cells it can move to, its weapon list and its skill list. The command judges no move and no target; 'act' judges the choice of the client |
| engagement payload | 交戰酬載 | The answer of the engine command 'response_attacks': the response attack options of the defender against one planned strike, and the support units of the two sides, each one with its forecast |
| action | 行動 | The wire name of the payload of one activation in the battle engine contract. The Python struct names the same thing 'Decision' (engine/state.py). The Go struct keeps the model name, and the wire field keeps the contract name; 'engine/protocol/state.go' holds the pair |
| action kind | 行動種類 | The kinds of one action of an activation: attack, map_attack, reposition and standby. The type is 'ActionKind', in 'engine/protocol/state.go' and in its Python mirror 'engine/contract.py'. The enum holds no kind of movement, and the engine name says so. It holds no skill either: the values 'skill_heal' and 'skill_en_refill' put an effect in the set of the kinds of action, and the user retired them on 2026-08-26. The wire field is 'kind'. Not 行動類型, which the frozen corpus holds for the kind of a response attack in battle-prep-ui.md |
| skill kind | 技能種類 | What one skill is: the field 'kind' of 'Skill'. The set is open, and the engine validates nothing and resolves nothing, because no contract says what a skill does (issue #81). Go: the type 'SkillKind'. It is not an 'ActionKind' |
| activation | 啟動 | One action of one unit in one phase. It ends when the 'acted' flag of that unit becomes true. Not 行動, which the frozen corpus holds for two other senses: 行動類型 names the kind of a response attack in battle-prep-ui.md, and 防禦行動倍率 names the defense multiplier in combat-formulas.md |
| response attack | 應戰 | The answer of the defender to one strike: its stance, its weapon, its support defender and its support attackers. Go type 'ResponseAttack'; wire field 'response_attack' of the action; command 'response_attacks'. Renamed from 'reaction' on 2026-08-28 because 'reaction' is the pilot value 反應值 (the game's word, 'pilot.reaction' on the wire); do not use 'reaction' or 'response' alone for this concept |
| response attack stance | 應戰姿態 | The defense the target picks in a response attack: the 'Stance' enum. The contract holds it in 'engine/protocol/state.go' and in 'engine/contract.py', and the Go model holds the same five values in 'engine/battle/board/model.go'. The value 'none' is the unit that stands and takes the strike; the command 'response_attacks' answers with it. The command answers with no 'shield': the shield of a unit settles during the damage, in 'act'. The game UI words are 閃避 for 'dodge', 防禦 for 'defend', 防禦（盾牌）for 'shield' and 反擊 for 'counter'. The value 'none' has no game UI word; the battle page writes 無反應 |
| support defender | 支援防禦者 | A unit that can take a strike for a unit of its own faction: alive, a support defense charge left, within its own move range of the cell the covered unit stands on after its move. The engine reports every one of them and the client names the one that takes the strike; the named one takes the strike in the defend stance. One on the attacking side carries 'support_defend_when_attack' and takes the counter strike. Go: 'supportDefenders' and 'namedSupportDefender' of the package 'engine/battle/board'. The retired name 'interceptor' 攔截者 came from the Python sandbox, not from the game, which labels it 支援防禦 (user ruling, 2026-08-26). The unit carries no reduction of its own: 'interception_reduction' is retired, and the per-mech 「支援防禦時減輕 X%」 waits for the ability model of issue #80 |
| support attacker | 支援攻擊者 | A unit that can join a strike of a unit of its faction: alive, a support attack charge left, within its own move range of the supported unit, with a weapon that reaches the foe. The engine reports every one of them and the client names the units that join, up to the cap of the rules. The strike of one such unit is a support attack; the mechanism holds no scenario beside it. Go: 'supportAttackers' of the package 'engine/battle/board' |
| forecast | 預測 | What one strike does to one unit, in the answer of 'response_attacks': the hit rate, the damage and the kill mark. The damage is the conservative lower bound, and the kill mark is true when that bound is at least the hit points of the target. Go: 'Forecast' in 'engine/battle/board/results.go' and in 'engine/protocol/types.go'. Not the attack forecast screen of the game, which docs/reference/battle-prep-ui.md holds |
| manual roll | 手動擲骰 | The dice input that names each outcome by hand: 'dice.mode' is 'forced' and 'outcomes' holds one outcome for each chance event, in the resolution order. The page does not offer it: it cannot know that order before the engine answers. Go: 'ManualRoll' |
| server draw | 伺服器抽骰 | The dice input that the engine draws: 'dice.mode' is 'sampled', and the engine reads its own random source. The page holds no hit rate and no random source of its own. Go: 'ServerDraw' |
| footprint | 外形 | The rectangle of cells that one unit covers on the board. The field 'size' of a unit holds its width and its height. A unit does not turn. The rule is in docs/spec/battle-engine-protocol.md, section 'Board geometry' |
| anchor cell | 錨點格 | The cell of a footprint with the least value on each axis. The field 'pos' of a unit holds it. The command 'reach' answers anchor cells. Short form 錨點 after the first use |
| unit | 單位 | One deployed piece on the board: a pilot that rides a mech. It is the current state of the pairing, and it records state and the maxima of state: 'hp', 'max_hp', 'en', 'en_max', 'sp', 'sp_max', the position, the charges. It takes no part in a computation. The Go type 'Unit' in engine/battle/board holds the state and the two data fields 'Pilot' and 'Mech' (user ruling 2026-08-28). A unit exists only on a board
| mech | 機體 | The machine of a unit. It exists outside a stage. It holds 'hp', 'en', 'attack', 'defense', 'mobility', 'move_range' and 'weapons'. The Go type is 'Mech'; the wire object is 'mech'. A rule reads the mech at computation time. Do not write "unit attack" or "unit defense" for the attack and the defense of a mech
| pilot | 駕駛 | The character that rides the mech. It exists outside a stage. It holds 射擊值 'ranged', 格鬥值 'melee', 覺醒值 'awaken', 守備值 'defense', 反應值 'reaction' and the skill point pool 'sp'. The Go type is 'Pilot'; the wire object is 'pilot'. A rule reads the pilot at computation time; the reaction value drives evasion (docs/reference/combat-formulas.md). The datamine names a pilot "character"
| final panel | 最終面板 | Retired 0828. The 0821 reading was a stored, combined level on the unit that every rule reads. The user ruled on 2026-08-28 that no such level exists: the unit records state, and a rule reads the pilot and the mech at computation time. History in docs/record/decisions.md
| base data | 基礎資料 | Retired 0828 with 'final panel'. The values of the pilot and of the mech are simply the pilot and the mech; there is no second copy on the unit
| pending ruling | 待裁 | The marker for an item that needs a ruling from the user, not more evidence. Write the English form in a new issue, a new document, and a commit message. The Chinese form appears three times in the frozen record docs/record/decisions.md; leave those alone |
| ratio correction | 比率補正 | The formulas 1 and 2 of docs/reference/combat-formulas.md. Formula 1 is the pilot attack minus the pilot defense, over 5000. Formula 2 is the mech attack minus the mech defense, each over 10, over 5000. Both clamp at zero. Go: 'pilotRatio' and 'mechRatio' |
| sigmoid correction | 函數補正 | The formulas 3 and 4. Each one is one over one plus the exponential of the scaled gap between the defense and the attack. Formula 3 reads the pilot values and formula 4 reads the mech values. Each one gives one half at equal values. Go: 'pilotSigmoid' and 'mechSigmoid' |
| attack correction | 攻擊補正 | Formula 6. It is the logistic term of the mech attack and the pilot attack of the attacker. It scales the base damage up |
| defense correction | 防禦補正 | Formula 7. It is the logistic term of the mech defense and the pilot defense of the defender. It scales the base damage down |
| base damage | 基礎傷害 | Formula 5 of docs/reference/combat-formulas.md: the weapon power times the sum of the two ratio corrections and the two sigmoid corrections. Go: 'BaseDamage' in engine/battle/board |
| combat base damage | 戰鬥基本傷害 | Formula 8: the base damage times one plus the attack correction plus the defense correction, divided by the terrain correction. Go: 'CombatBaseDamage' |
| damage scale | 傷害增減補正 | Formula 9: one plus the sum of the bonuses minus the sum of the penalties. Go: 'DamageScale' |
| final damage | 最終傷害 | Formula 10: the combat base damage times the damage scale times the defense multiplier. Go: 'FinalDamage' |
| critical damage | 暴擊傷害 | Formula 11: the final damage times the critical multiplier. Go: 'CriticalDamage' |
| defense multiplier | 防禦行動倍率 | The multiplier of the response attack stance in formula 10: 1.0 with no defense, 0.8 for 'defend'. A shield is a second cut on top of the defense and not a stance of its own, so a shielded defender pays 0.8 times 0.8. Go: 'NoDefenseMultiplier', 'DefendMultiplier', 'ShieldMultiplier' in 'engine/battle/board/rules.go'. They are constants of the title: no stage overrides one, and the wire carries no rules payload (user ruling, 2026-08-26) |
| critical multiplier | 暴擊倍率 | The multiplier of formula 11: 1.1 normal, 1.2 at high morale, 1.3 for a super attack. Go: 'CritNormal', 'CritHighMorale', 'CritSuper' |
| terrain correction | 地形補正 | The divisor of formula 8. It is the effect of a weapon ability that reads the terrain of the cell of the target. It is not a property of the map and not the terrain adaptability of the mech. A weapon that carries no such ability divides by 1, which is 1214 of the 1235 rows of the datamine. The engine passes 1 for every weapon until the ability model lands (issue #80). Two designs are retired: the scalar 'Rules.terrain', which held one value for a whole stage, and the weapon fields 'terrain_damage' and 'unusable_in' |
| terrain | 地形 | The kind of ground of one cell. The five kinds are 宇宙, 空中, 地上, 水上, 水中 (space, atmospheric, ground, surface, underwater). A stage map can hold more than one kind; the 0814 ruling that said otherwise is withdrawn (2026-08-21). Go: the type 'Terrain' in engine/battle/board, with the wire names space, atmospheric, ground, surface and underwater. A cell takes the default kind of the board unless the board names an override for it: the wire fields 'terrain' and 'terrain_cells' of the state |
| terrain adaptability | 地形適性 | The rating of a mech for one terrain: ○ can deploy, △ can deploy with half movement in that terrain, － cannot enter. This title has no S to D ranks. It gates deployment and movement only; it does not enter the damage formula or the hit rate |
| weapon ability | 武裝能力詞條 | One named ability of one weapon, positive or negative. An ability can read what no field of the weapon holds: the terrain of the cell of the target ('對水中目標傷害減半'), the terrain of the cell of the attacker ('攻方自身在水中時不可使用'), or the permission to fire after a move. The engine models a closed set of ability kinds and ignores every kind outside it, so a weapon that carries an unmodelled ability resolves as a weapon with no ability at all. A new ability of the game adds a kind; it never adds a field to 'Weapon' (user ruling, 2026-08-26). Issue #80 builds the model |
| hit rate | 命中率 | The percent chance that one strike of one attack lands, clamped to 0 to 100. This is the number the attack forecast screen shows; it is computed for each engagement and it is not the weapon accuracy. It reads the mobility of each mech, and the pilot attack of the attacker against the pilot reaction of the defender. The hit probability is the rate over 100. Go: 'HitRatePercent', 'HitProbability' |
| weapon accuracy | 武裝命中值 | A fixed value of one weapon, the same against every target. The wire field is 'accuracy' of 'Weapon'; the datamine names it 'hit_rate' and holds only the four values 90, 95, 100 and 105. It is the base term of the hit rate: the user ruled on 2026-08-21 that the fitted constant 96.45 of the published formula is this value. The ruling waits for a device check |
| ability correction | 能力補正 | The additive term of the hit rate, holding the ability corrections of both sides and the dodge penalty. It does not hold the weapon accuracy, which is the base term. The dodge penalty is a placeholder, because docs/reference/combat-formulas.md lists the dodge correction as not yet measured; the sandbox still adds the weapon accuracy here, which double counts it |
| phase | 階段 | One faction's slot of a turn: ally, third_party, enemy, in that order; the field phase of the state and of the summary |
| turn cycle | 回合循環 | The rotation of the phases ally, third_party, enemy, and the turn counter; docs/spec/battle-engine-protocol.md section 'Turn cycle'; Go: 'Board.Act', 'Board.Advance' in engine/battle/board/turn.go |
| phase start | 階段開始 | The moment the phase of one faction opens: the activations come back, the EN regenerates, the debuffs of one full round expire; Go: 'beginPhase' |
| pending unit | 待啟動單位 | A living unit of the faction of the phase that did not act in this phase; the summary field 'pending'; Go: 'Board.Pending' |
| session random source | 對局亂數源 | The PCG source that the 'seed' of 'init' or 'load' builds and every server draw reads; Go: 'ServerDraw' |
| command mode | 指令模式 | One battle through the commands of the engine, with no page: the loop of src/ggge_ai/engine/play.py and the script scripts/play_battle.py (user ruling 2026-08-27) |
| gone | 全滅 | The summary field that names the sides with no living unit, 'ally' and 'enemy', in that order. The engine judges no end of the battle; the client stops on this field (user ruling 2026-08-27). It rides the board summary of 'act' and the answer of 'export'. Go: 'Board.Gone' in engine/battle/board/turn.go |
| rotation | 階段輪轉 | One move of the phase to the next entry of the phase order, with the phase start that the move opens. The move from the enemy phase to the ally phase adds one to the turn. Go: the type 'Rotation'; the wire carries one move as the 'phase' event of 'act' |
| datamine | 資料挖掘資料 | The master data of the game that the site soshage publishes over its public JSON API. The source, its addresses and its row counts are in docs/reference/datamine-source.md. The datamine is a second channel next to the screen, and it is never the authority for a live decision |
| data version stamp | 資料版本 | The value that 'GET /ggetapi/version' of the datamine returns, for example '202608161248'. The crawler names the dump directory with it, so a game patch gives a new directory instead of a silent change |
| datamine store | 資料挖掘庫 | The directory data/datamine/<data version stamp>/ that scripts/crawl_datamine.py writes. It holds one file for each source plus 'manifest.json'. It is gitignored, and two runs against one stamp write the same bytes |
| datamine sample store | 資料挖掘樣本庫 | The directory docs/reference/datamine-samples/<data version stamp>/ that holds a hand-picked sample of the per-id forms of the datamine, in the repository. It exists so that a task can read the shape of a unit, a pilot or a support crew without a crawl |
| unit role | 類型 | The enum 'role' of a unit row and of a pilot row of the datamine: 1 攻擊型, 2 耐久型, 3 支援型. It is the filter '類型' of the game and of the site. A pilot ability can require the unit role of the mech the pilot rides |
| weapon category | 武裝類別 | One of the three categories 射擊, 格鬥, 覺醒 of a weapon. The damage reads the pilot value of the category; a weapon with more than one reads the highest of them (user ruling 2026-08-28). Go: 'WeaponCategory'; the wire field is 'categories' of 'Weapon', values 'ranged', 'melee', 'awaken'; the datamine enum is 'attack_attr' (docs/reference/datamine-source.md). Do not name it a tag or an attack attribute: the user rejected 'AttackTag' on 2026-08-28 because the name must say it is the category of the weapon. It is not the datamine 'type' (normal, Ex, map) and not the damage attribute 'weapon_attr' (物理, 光束, 特殊) |

Retired name — 'solver': the word names only the deleted legacy
stack (ruling 2026-08-14). The current implementation is the
expectiminimax advisor, class name 'ExpectiminimaxAdvisor'
(issue #44). Do not name new code 'solver'.

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
