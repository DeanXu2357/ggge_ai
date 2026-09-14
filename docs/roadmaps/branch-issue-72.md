# Branch roadmap: issue 72, the abilities of the mech and the pilot

> Type: working—deleted at merge

Branch 'issue-72-ability-lines', off 'dev' b2132c3, opened 2026-09-14.
It carries this roadmap alone from 'issue-72-ability-hooks' (59903ae,
off dev 4eb94b0, opened 2026-09-08): dev restructured the act between
the two bases ('Act' reads an 'Action' with stated behaviors and
answers events; 'engagement' and 'turn' merged into 'system'; the
strikes are scheduled once in 'scheduleAct' and fired in
'exchange.fire'), so the code of that branch is a source of parts and
not a base. 'issue-72-ability-model' (46ef3e0), 'issue-72-abilities'
(88b5e8c, holds a catalog of 111 real lines under
'engine/catalog/data') and 'issue-72-mech-pilot-unit' (9cad225) stay
as sources of parts and are not merged.

The branch covers the engine model, the wire form, the Python mirror,
the goldens and the spec. The catalog and the converter (issue points
4 and 5) are not on this branch.

## Method: scenario first, in small steps

The order the user set on 2026-09-14, which replaces the order of
2026-09-08:

1. Write the scenario of one ability as a test of package 'system'
   ('engine/battle/system/ability_test.go'), on the helpers the
   package already has ('squad', 'accepted', 'strikes'), driven
   through 'Commit' and read from the 'StrikeEvent' list. The
   abilities live in 'system', so the test lives there too; a test
   through 'battle.Board' (the ruling of 2026-09-08) is retired.
2. Lay the hook points in 'system' under that test.
3. Put the implementation of the kinds under 'engine/battle/system/
   abilities'.
4. Check the hook points against the next real line of the sample
   (Section 4); widen when the line needs it.

Every step is as small as the test allows. The questions on the
formula slots, on the assembly rule and on the wire are decided one
kind at a time, when the line that needs the answer is the next line.

A scenario asserts a relation, not a hand-computed number: the board
with the line gives the same outcome as the board with the stat
already changed, or the same outcome as the board without the line
when the condition does not hold.

Roles need no field on a strike: 'shooterID != ownerID' is a support
attack (in the 'attacker_support' or 'defender_support' segment),
'struckID != aimedID' is a support defense, and the segment tells the
main strike from the counter (ruling 2026-09-14).

## Terms

| Term | Meaning |
|---|---|
| ability | One effect line on the mech or on the pilot. One compound ability of the game is several lines. 能力詞條 |
| ability kind | What the line changes: 'mech_attack_percent', 'support_attack_plus'. Each kind is one struct with its own fields, effect and condition alike. Go: 'battle.AbilityKind'. 能力效果種類 |
| condition | The fields of a line that must hold for the line to count. There is no condition object: the fields sit flat on the line, and the kind judges them in its hook. 生效條件 |
| hook | One method a kind implements for one moment of the game, named from the point of view of the holder. 時機介面 |
| exchange | Every strike of one engagement: the support attacks of the attacker, the main strike, the reply of the defender. 攻防 |
| strike | One weapon fired once at one receiver: a support strike, the main strike, the counter. 打擊 |
| assembly | The step that fills the maxima and the counts when a unit enters the board. Go: 'deploy.Assemble'. 組裝 |

'trigger' (觸發時機) is retired: the moment a line fires is the hook
it implements (ruling 0907).

## Section 1. The model shape

One ability line is one kind with its own flat fields. The wire form
is the struct itself:

    {"kind": "mech_attack_percent",  "enemy_tags": [1101], "percent": 20}
    {"kind": "mech_defense_percent", "enemy_tags": [1101], "percent": 20}

No 'trigger' key, no 'condition' sub-object (rulings 0907 and 0908):
「每個 ability 的實作裏面怎麼判斷 condition 是各自的事情，所以扁平的把
MechAttackPercent 和 MechDefensePercent 需要的變數帶進去就好」. Which
fields a kind carries is decided by the scenario that introduces the
kind, not ahead of it.

The per-kind wire struct lives in 'engine/battle/ability.go' with its
JSON tags; the value of 'kind' picks the struct when a list of lines
is decoded. The engine kind adds the hooks to the same fields (a
defined type over the wire struct, or the wire struct itself; the
implementation step decides).

### The kinds

The vocabulary 'battle.AbilityKind' names 26 kinds, from the catalog
of the old branch. A kind gets its struct when a scenario needs it.

Read by a rule at the end of the branch (21): 'mech_attack_percent',
'mech_defense_percent', 'mech_mobility_percent',
'pilot_ranged_percent', 'pilot_melee_percent',
'pilot_awaken_percent', 'pilot_defense_percent',
'pilot_reaction_percent', 'max_hp_percent', 'max_en_percent',
'accuracy_percent', 'evasion_percent', 'damage_dealt_percent',
'damage_taken_percent', 'weapon_en_cost_percent',
'support_attack_plus', 'support_defend_plus', 'chance_step_plus',
'mp_plus', 'move_range_plus', 'special_weapon_range_plus'.

Present and not read (5): 'squad_grant',
'squad_attack_percent_per_member' (needs a squad model),
'revive_once' (needs a once flag in the unit value),
'hp_supply_percent' (issue #79), 'debuff_effect_percent' (issue #80).

A 'percent' field is the signed change: 'damage_taken_percent' -15
is 15% less damage taken. A 'count' field is a whole number.

### The condition vocabulary

The field names a line may carry, bound to datamine ids and never to
display text (ruling 0829). The catalog of 88b5e8c shows at most two
of them on one line, in 13 combinations.

| Field | Holds when |
|---|---|
| hp_rate_lte, hp_rate_gte | the HP of the holder, in percent of its maximum, is at or below / at or above the value |
| vigor_min | the MP of the holder reaches the tier |
| pilot_tags | the pilot carries one of the tags |
| mech_type, mech_tags, mech_ids, mech_series | the mech carries the type / one of the tags / its id is listed / one of the series |
| enemy_tags | the mech of the other unit of the strike carries one of the tags |
| enemy_weapon_attributes, enemy_weapon_categories | the weapon fired at the holder carries one of the values |
| strike_roles | the role of the holder in this strike is listed |
| squad_tags | never; the engine holds no squad |

'mech_type' is the datamine 'unit_role' (1 攻擊型, 2 耐久型, 3
支援型); the name follows the term 類型 of the terminology map.

A condition is read before each strike, not once before the
exchange. Evidence: docs/reference/combat-formulas.md, case 11: the
debuff a support attack lands is read by the counter of the same
exchange, so the game reads each strike from the state of that
moment.

### The unknown line

A line whose kind is not in the set is carried and read by no hook;
the encoder writes it back as it came (ruling 0903, the rule of
issue #80).

### The carriers

| Type | New fields |
|---|---|
| battle.Mech (wire) | id, type, tags, series, abilities |
| battle.Pilot (wire) | id, tags, abilities |
| battle.Weapon (wire) | attributes ('physical', 'beam', 'special') |
| battle.Unit (wire) | mp |
| def.Mech, def.Pilot, def.Weapon | the same facts |
| state.UnitContent | MoveRange (filled at assembly), Abilities |
| state.UnitValue | MP |

The Python mirror ('src/ggge_ai/engine/state.py', the codec, the
mirror test) gains the same fields in the same commit as the wire,
and the goldens under tests/fixtures/engine gain the keys.

### MP facts (user, 2026-09-04, first hand)

MP maximum 12. Initial value 0 or 1, not settled. At 9 or 10 (not
settled) the unit enters 超強勢 ('super_high'); at 12 it enters
超一擊 ('supercharged'). What the two states do is not known.
Constants: 'MPMax' 12, 'VigorSuperHighMP' 10 (marked),
'VigorSuperchargedMP' 12, 'MPInitial' 0 (marked). Issue #54 owns the
system.

## Section 2. The hooks

The moments come from the exchange the game resolves
(docs/reference/combat-formulas.md, 交戰結算順序): the support salvo
of the attacker, the main strike on the receiver (the target, or the
support defender that covers it), the death check, then the support
attacks of the defender and its counter. Each strike reads the state
of its moment, so the hooks of a strike run once for each strike.

Two patterns carry the design: the additive percent bucket (every
source adds, the system multiplies once; the stacking rule measured
0829) and combat hooks named from the point of view of the holder
(Pokémon Showdown 'onModifyAtk' against 'onSourceModifyAtk', Slay the
Spire 'atDamageGive' against 'atDamageReceive'). The name of the
hook is the subject: the holder is always 'self'.

    AtAssembly   ApplyAtAssembly(self Unit, sum *AssemblySum)
    AtPhaseStart ApplyAtPhaseStart(self Unit)
    BeforeAttack ApplyBeforeAttack(self, target Unit, weapon *def.Weapon, selfRole, targetRole battle.StrikeRole, sum *AttackSum)
    BeforeDefend ApplyBeforeDefend(self, attacker Unit, weapon *def.Weapon, selfRole, attackerRole battle.StrikeRole, sum *DefendSum)
    AfterAttack  ApplyAfterAttack(self, target Unit, weapon *def.Weapon, landed bool, damage int)
    AfterDefend  ApplyAfterDefend(self, attacker Unit, weapon *def.Weapon, landed bool, damage int)

| Hook | Runs for | Call point | Adds to |
|---|---|---|---|
| ApplyAtAssembly | the unit that enters | deploy.Assemble, once | AssemblySum: max HP %, max EN %, support attack, support defend, chance step, move, MP |
| ApplyAtPhaseStart | each unit of the opening faction | turn.beginPhase | writes the value directly |
| ApplyBeforeAttack | the unit that fires the strike | every time a strike is judged or computed | AttackSum: mech attack, pilot ranged, melee, awaken, mobility, damage dealt, accuracy, EN cost, range |
| ApplyBeforeDefend | the unit that takes the strike (the support defender when one covers) | same | DefendSum: mech defense, pilot defense, pilot reaction, mobility, damage taken, evasion |
| ApplyAfterAttack | the unit that fired | after the wound of its strike | writes the value directly |
| ApplyAfterDefend | the unit that took the strike | after the wound writes HP, before the kill is judged | writes the value directly |

The walk is a method of 'state.Unit', one for each hook; each walks
'unit.Abilities' and calls the lines that implement the hook. The
order of a strike is the order of the game: the attack sum of the
attacker, the defend sum of the defender, then the formula. The
formula reads the attack sum of the attacker and the defend sum of
the defender only. A hook adds its share; the system multiplies once
and floors, in integer arithmetic. The order of the lines does not
change the result.

The exact signatures are a proposal until the scenarios pin them:
「先別收斂」(user, 2026-09-08).

The skill seam, stated and not built: a buff a skill lands is a
modifier with a lifetime on the unit value, the way 'Debuffs' is
today; it implements the same hooks and the walk reads it next to
'Abilities'. The MP changes of the game are a system rule of issue
#54, not a line.

## Section 3. The scenarios

Each scenario drives 'battle.Board' only. The order, each one adding
the kinds it needs:

1. Killer tags both ways: B carries 'mech_attack_percent' and
   'mech_defense_percent' 20 with 'enemy_tags' [1101], A carries tag
   1101. In one exchange the main strike A→B does the damage of a
   defender whose defense is already scaled, and the counter B→A the
   damage of an attacker whose attack is already scaled. A without
   the tag: both strikes equal the board without the lines.
2. Cover: A→B, C covers with a defense line on 'strike_roles'
   ['support_defense']; C's line counts, B's does not, the damage
   reads C.
3. The "HP full" defense bonus is gone for the main strike after a
   support attack lands ('hp_rate_gte' 100, read before each strike).
4. I-Field: 'damage_taken_percent' on 'enemy_weapon_attributes'
   ['beam'] and 'enemy_weapon_categories' ['ranged']; a physical
   weapon is not reduced; the line of the attacker reads no weapon of
   its own.
5. The support-role EN discount applies to the supporter alone and
   the write spends the discounted cost; the counter reads its cost
   and its reach at the moment it fires.
6. 'special_weapon_range_plus' on 'vigor_min': the menu, the
   response attack options and the counter pick all reach one cell
   farther; the actions list shows the reach.
7. Assembly: one pilot on two mechs gives two units with different
   maxima and support counts; 'move_range_plus' on 'pilot_tags'
   widens the reachable cells; 'mp_plus' raises the initial MP.
8. Mobility both ways: a mobility line on the defender lowers the
   hit rate, on the attacker raises it.
9. An unknown kind changes no number and comes back from 'State' as
   it went in.
10. Stacking: two lines on one stat add before the one
    multiplication (12121 with +15% and +12% gives +3272).

Behaviors of the rejected branch that the scenarios must carry: the
eligibility of a supporter reads the target (the menu cannot know
the cover) while the effect reads the struck unit; 'able' drops a
supporter silently at the write; the counter re-judges EN and reach
at the write; the support salvo rolls against the role of the struck
unit; assembly fills a zero maximum only (ruling 0831) and recomputes
'MoveRange' and 'MP' on every call; geometry and support read
'MoveRange' from the content.

Deferred to a later issue: the base chance step of every pilot
('ChanceStepsMax' = 1 + Σ), because four goldens hold
'chance_steps_max' 0 (ruling of the rejected branch, kept).

## Section 4. The lines of the sample

The 112 trait rows of the ten UR mechs and their ten pilots
(docs/reference/datamine-samples/202608161248 on 88b5e8c), sorted by
side, kind and condition fields. A row of the table is one shape; the
count is the number of lines of that shape. The status column is
ticked when a scenario covers the shape. The mapping of 'trait_type'
to kind and of the datamine condition to the field is the one of
docs/reference/datamine-source.md on 88b5e8c.

| Side | Kind | Condition fields | Lines | Example | Status |
|---|---|---|---|---|---|
| mech | 'accuracy_percent' | — | 2 | Psycho-Frame LV 1 | |
| mech | 'damage_taken_percent' | 'enemy_weapon_attributes' | 1 | Physical Damage Reduced LV 3 | |
| mech | 'damage_taken_percent' | 'enemy_weapon_attributes', 'enemy_weapon_categories' | 3 | I-Field LV 3 | |
| mech | 'evasion_percent' | — | 4 | Increased EVA LV 1 | |
| mech | 'max_en_percent' | — | 2 | Increased Max EN LV 3 | |
| mech | 'max_hp_percent' | — | 5 | Increased Max HP LV 3 | |
| mech | 'mech_attack_percent' | — | 5 | Increased ATK LV 3 | |
| mech | 'mech_attack_percent' | 'enemy_tags' | 2 | Advantage: Principality of Zeon LV 1 | |
| mech | 'mech_attack_percent' | 'hp_rate_lte' | 1 | (HP conditions) Increased ATK LV 3 | |
| mech | 'mech_attack_percent' | 'vigor_min' | 1 | (Cnd: Vigor) Increased ATK & MOB LV 3 | |
| mech | 'mech_defense_percent' | — | 1 | Increased DEF LV 3 | |
| mech | 'mech_defense_percent' | 'enemy_tags' | 2 | Advantage: EFSF (U.C.) LV 1 | |
| mech | 'mech_defense_percent' | 'hp_rate_gte' | 1 | (HP conditions) Increased DEF LV 2 | |
| mech | 'mech_defense_percent' | 'hp_rate_lte' | 1 | (HP conditions) Increased DEF LV 2 | |
| mech | 'mech_mobility_percent' | — | 2 | Increased MOB LV 1 | |
| mech | 'mech_mobility_percent' | 'vigor_min' | 1 | (Cnd: Vigor) Increased ATK & MOB LV 3 | |
| mech | 'move_range_plus' | 'pilot_tags' | 1 | (Cnd: Tag) Increased MOV LV 1 | |
| mech | 'special_weapon_range_plus' | 'vigor_min' | 1 | (Cnd: Vigor) Special Weapon Max Range Up LV 1 | |
| pilot | 'damage_dealt_percent' | — | 4 | Increased Damage Dealt LV 3 | |
| pilot | 'damage_dealt_percent' | 'enemy_tags' | 1 | EX Character Ability (Amuro Ray) | |
| pilot | 'damage_dealt_percent' | 'mech_tags' | 8 | EX Character Ability | |
| pilot | 'damage_taken_percent' | 'enemy_tags' | 1 | EX Character Ability (Amuro Ray) | |
| pilot | 'damage_taken_percent' | 'mech_tags' | 8 | EX Character Ability | |
| pilot | 'debuff_effect_percent' | 'mech_ids' | 1 | EX Character Ability (Kou Uraki) | not read, issue #80 |
| pilot | 'hp_supply_percent' | 'mech_ids' | 1 | EX Character Ability (Oliver May) | not read, issue #79 |
| pilot | 'mech_attack_percent' | 'mech_type', 'strike_roles' | 1 | (When supporting) Increased ATK LV 5 | |
| pilot | 'mech_defense_percent' | 'mech_type', 'strike_roles' | 3 | Support Defense LV 4 | |
| pilot | 'mech_defense_percent' | 'strike_roles' | 1 | EX Character Ability (Amuro Ray) | |
| pilot | 'mp_plus' | 'mech_tags' | 2 | EX Character Ability | |
| pilot | 'pilot_awaken_percent' | — | 5 | Newtype LV 4 | |
| pilot | 'pilot_defense_percent' | — | 5 | Increased Defense LV 1 | |
| pilot | 'pilot_melee_percent' | — | 3 | Increased Melee LV 1 | |
| pilot | 'pilot_ranged_percent' | — | 7 | Increased Ranged LV 1 | |
| pilot | 'pilot_reaction_percent' | — | 4 | Newtype LV 4 | |
| pilot | 'revive_once' | 'mech_ids' | 2 | EX Character Ability (Char Aznable); one row is the companion row 84 | not read |
| pilot | 'squad_attack_percent_per_member' | 'mech_ids' | 2 | EX Character Ability (Io Fleming) | not read |
| pilot | 'squad_grant' | 'mech_ids' | 4 | EX Character Ability (Oliver May) | not read |
| pilot | 'support_attack_plus' | — | 6 | Support Attack / Counter Support LV 4 | |
| pilot | 'support_defend_plus' | — | 5 | Support Defense LV 4 | |
| pilot | 'weapon_en_cost_percent' | 'mech_type', 'strike_roles' | 2 | Support Attack / Counter Support LV 4 | |

Facts the table shows:

- A line carries at most two condition fields.
- 'enemy_tags' is the field of the "Advantage" pair: the attack half
  has the datamine target 'AttackTarget' with the tags, the defense
  half has 'ActiveAttacker' with no tags and takes the tags of the
  attack half. Both halves read the tag of the other unit of the
  strike.
- 'mech_tags' on a pilot line reads the tags of the mech the pilot
  rides ("When piloting units with specified tags"); 'pilot_tags' on
  a mech line reads the tags of the pilot ("When the piloting
  character has a specified tag"). The two lists are two lists in
  the datamine ('unit_tags' and 'character_tags_id').
- "One-Shot Killer" is a tag of the mech list (id 1082 on Gouf Custom
  (EX)), not an ability.

## Gates

From 'engine/': 'gofmt -l .', 'go vet ./...', 'go test -race ./...'.
From the root: 'uv run pytest -q', 'uv run ruff check src tests
scripts'. Every existing Go test name stays. A golden changes only
when a wire key lands, and then in the same commit.

## Progress log

- 2026-09-08: branch opened off dev 4eb94b0 with the roadmap, the
  vocabulary and the first ability ('mech_attack_percent',
  'mech_defense_percent' with 'enemy_tags'). The first scenario is
  written and shown to the user before any model code.
- 2026-09-08 (7e29715): the carriers of the two kinds landed.
  'battle.Mech' gains 'tags' and 'abilities'; 'battle.Abilities'
  picks the struct of a line by its kind and carries an unknown kind
  as it came; 'def.Mech' and the state conversion hold the same two
  facts; the Python mirror, the goldens and the spec follow, at
  protocol version 2.1. No hook and no effect: the carriers only.
- 2026-09-08: the first scenario file entered the tree,
  'engine/battle/ability_scenarios_test.go' (package 'battle_test').
  The branch is red by design on one test:
  'TestAnEnemyTagLineScalesTheDefenseInTheMainStrikeAndTheAttackInTheCounter'
  fails because no hook reads a line yet. The other two tests of the
  file pass, and every other test of the repository stays green.
- 2026-09-14: the branch reopened as 'issue-72-ability-lines' off dev
  b2132c3 with this roadmap alone. Two preparations landed on the
  branch first: the support defender of the actor takes the support
  attacks of the defender side (2bbdb6f), and the stated behaviors
  are checked after the schedule in 'Commit' (0325d76). The method
  changed to tests in 'system' in small steps; Section 4 lists the
  112 lines of the sample as the checklist.
