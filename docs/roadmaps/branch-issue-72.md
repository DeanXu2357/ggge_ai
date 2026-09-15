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

The branch covers the engine model. The wire form, the Python mirror,
the goldens and the spec wait for the shape of the communication
(ruling 2026-09-14); the catalog and the converter (issue points 4
and 5) are not on this branch.

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
| assembly | The step that builds the two columns of a battle from the wire state and judges it. Go: 'system.Assemble'. 組裝 |

'trigger' (觸發時機) is retired: the moment a line fires is the hook
it implements (ruling 0907).

## Section 1. The model shape

A line is a value that holds its numbers and its own state, and a
unit carries its lines in the value column (ruling 2026-09-14). One
line of the game is one type in 'engine/battle/ability/lines'; it
implements 'ability.Line' ('Clone') and the hook method of each
moment it acts in ('OnAttack', 'OnDefend'). When a unit takes its
lines ('UnitValue.SetAbilities'), 'ability.HooksOf' puts each hook
method on the chain of its moment ('UnitValue.Hooks'); the chains
are derived from the lines, and 'Values.Clone' clones the lines and
binds the copies again, so a copy of the value column owns its
lines and their state. This is the shape of 'UnitValue.Skills': the definition
and the uses of a skill travel together in the value column.

    lines.MechAttackPercentAgainstTag{EnemyTag: 1015, Percent: 15}
    lines.MechDefensePercentAgainstTag{EnemyTag: 1015, Percent: 15}

One type is one specific line of the game, condition included: "ATK
+15% against enemies with a tag" and "ATK +15%" are two types. A
condition is judged inside the hook, a cap ("up to 15%") is clamped
inside the hook, and a once-per-battle line keeps its own flag as a
field: the responsibility of a line is in its type, and no field of
a line reaches 'UnitValue'.

No kind enum, no registry, no data struct apart from the line
itself. 'def' holds 'Mech.Tags' and nothing of the lines.

The wire form is not decided (ruling 2026-09-14: the shape of the
communication is not known yet), so no line reaches 'battle', the
Python mirror or a golden on this branch until it is. When it is,
the lines travel in the unit the way 'skills' do, and 'Load' builds
them with 'SetAbilities'.

The rows of Section 4 are the candidates, one type for each row
that a scenario covers.

### The condition facts a line reads

The facts of the datamine that a line may read, bound to datamine
ids and never to display text (ruling 0829):

| Fact | Where it sits |
|---|---|
| the HP of the holder, in percent of its maximum | the unit value |
| the MP tier of the holder | the unit value (issue #54) |
| the tags of the pilot; the tags, the type, the id, the series of the mech | the content ('mech_type' is the datamine 'unit_role': 1 攻擊型, 2 耐久型, 3 支援型) |
| the tags of the mech on the other end of the strike | 'Strike.Other' |
| the attributes and the categories of the weapon of the strike | 'Strike.Weapon' |
| the role of the holder in the strike | read from the strike fields (Method) |

A fact is read before each strike, not once before the exchange.
Evidence: docs/reference/combat-formulas.md, case 11: the debuff a
support attack lands is read by the counter of the same exchange, so
the game reads each strike from the state of that moment.

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

The contract is 'engine/battle/ability', which imports 'def' alone.
One moment of the game is one context type: the facts a hook reads
and the values a hook may change, in one struct. A hook reads and
writes the context freely; the chain of a moment runs the hooks in
the order of the lines.

    type Line interface { Clone() Line }
    type AttackUnitHook interface { OnAttack(a *AttackContext) }
    type DefendUnitHook interface { OnDefend(d *DefendContext) }

    type Unit struct { Mech *def.Mech; Pilot *def.Pilot; HP, MaxHP int }

    type AttackContext struct {                  // the strike the attacker fires
        Attacker, Defender Unit
        Weapon             *def.Weapon

        MechAttackPercent, MechMobilityPercent                   float64
        PilotRangedPercent, PilotMeleePercent, PilotAwakenPercent float64
    }
    type DefendContext struct {                  // the strike the defender takes
        Attacker, Defender Unit
        Weapon             *def.Weapon

        MechDefensePercent, MechMobilityPercent   float64
        PilotDefensePercent, PilotReactionPercent float64
    }
    type AttackHook func(a *AttackContext)
    type DefendHook func(d *DefendContext)
    type Hooks struct { OnAttack []AttackHook; OnDefend []DefendHook }

The chains bind the methods of the lines of one value column. A
bound method points at one copy of a line, so a chain built before
'Clone' would write the state of the original; that is why the
clone binds its copies again, and why a chain never sits in the
content. 'engine/battle/state/ability_test.go' pins this.

Order. Every value of a strike context is a percent sum: each hook
adds its own share, and the engine multiplies the base one time and
floors ('scaled' in 'system/strike.go'). Addition commutes, so the
order of a chain does not change a strike. The moment a line has to
read the total of the others (none in the sample), the contract
gains a second stage after the sums, and the chain stays as it is.

'Unit' is a copy of the facts, not 'state.Unit': the contract does
not depend on 'state', and a hook cannot reach the value column.

Which unit is 'Defender'. 'system' builds the context for each
computation: for the hit rate the defender is the aimed unit, for
the damage it is the struck unit. The two differ when a support
defender covers the target, so a line that reads the enemy reads
the guard in the damage and the target in the hit rate. That this
is what the game does is a hypothesis; the reference document does
not say which unit an "Advantage" line reads when a guard covers.

The two zones of the damage formula. The stats ('MechAttack',
'PilotAttack', 'MechDefense', 'PilotDefense') enter the ratio and
sigmoid terms, which are not linear, so a percent on a stat changes
the input of those terms; the damage percents enter ⑨ '1 + Σ增傷 −
Σ減傷', linear on the result. The two are different zones by the
shape of the formula, not by a ruling. Inside the stat zone the
unconditional lines ("Increased ATK LV 3", trait type 7) and the
conditional lines ("Advantage", trait type 7 with a condition) are
the same trait type of the datamine, and Atlas Gundam (EX) carries
both in one ability; so they are one sum, evaluated in each strike:
floor(base × (100 + Σpermanent + Σconditional) / 100). A unit stores
no scaled stat; the base of 'def' is the input of every strike (the
0829 ruling, confirmed 2026-09-15 from the formula). 4200 with ATK
+15% and Advantage +15% gives 5460, and not 4830 × 1.15 = 5554; the
difference is a forecast reading on the device, which is the
measurement that would refute this.

| Moment | Call point | Values today | Values the checklist will need |
|---|---|---|---|
| Attack | 'attackerSide' in 'system/strike.go', for every damage, hit rate and forecast | mech attack, mobility, pilot ranged, melee, awaken % | damage dealt; accuracy; EN cost; range |
| Defend | 'defenderSide', same | mech defense, mobility, pilot defense, reaction % | damage taken; evasion |
| assembly (not built) | 'system.Assemble' | — | max HP, max EN, support attack, support defend, chance step, move, MP; the MP hook clamps to 'MPMax' itself. Only for what happens one time when the unit enters; a stat percent is never an assembly line |
| phase start (not built) | 'beginPhase' in 'system/turn.go' | — | none in the sample |

Legality (EN cost, reach) is read at the schedule by the same
function that the settlement reads it with; the strike struct holds
identities only and no number (ruling 2026-09-14).

## Section 3. The scenarios

Each scenario drives 'battle.Board' only. The order, each one adding
the kinds it needs:

1. The "Advantage" pair both ways (green): B carries the two lines
   'MechAttackPercentAgainstTag{1015, 15}' and
   'MechDefensePercentAgainstTag{1015, 15}', A carries tag 1015. In one exchange the main strike A→B does the
   damage of a defender whose defense is already scaled, and the
   counter B→A the damage of an attacker whose attack is already
   scaled. A without the tag: both strikes equal the board without
   the lines. The negative scenario: B carries the tag itself and the
   hooks against it, A carries no tag; the exchange equals the board
   without the hooks, so the hook reads the enemy and not itself.
2. Cover: A→B, C covers with a defense line on 'strike_roles'
   ['support_defense']; C's line counts, B's does not, the damage
   reads C.
3. The HP conditions (green): the "HP full" defense bonus is read
   at each strike, so a support attack that lands takes it off the
   main strike and a support attack that misses leaves it; the
   "HP 25% or below" attack bonus holds at the threshold and not
   one HP above; the "HP 50% or below" defense bonus scales the
   strike taken. The comparison is in integers, HP × 100 against
   the threshold × MaxHP.
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
10. Stacking (green): two lines on one stat add before the one
    multiplication (4200 with +15% and +12% gives 5334), and a
    conditional line joins the same sum (ATK +15% with Advantage
    +15% against a tagged enemy gives 5460).
11. The unconditional percent lines (green): each of the eight
    stat lines gives the exchange, or the hit rate, of the unit
    whose stat is already scaled; the mobility line acts on both
    sides.

Behaviors of the rejected branch that the scenarios must carry: the
eligibility of a supporter reads the target (the menu cannot know
the cover) while the effect reads the struck unit; 'able' drops a
supporter silently at the write; the counter re-judges EN and reach
at the write; the support salvo rolls against the role of the struck
unit; a zero maximum is refused (ruling 2026-09-15, which retires the
fill of 0831) and assembly recomputes
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
| mech | 'mech_attack_percent' | — | 5 | Increased ATK LV 3 | 'lines.MechAttackPercent', scenario 11 |
| mech | 'mech_attack_percent' | 'enemy_tags' | 2 | Advantage: Principality of Zeon LV 1 | 'lines.MechAttackPercentAgainstTag', scenario 1 |
| mech | 'mech_attack_percent' | 'hp_rate_lte' | 1 | (HP conditions) Increased ATK LV 3 | 'lines.MechAttackPercentAtHPRateAtMost', scenario 3 |
| mech | 'mech_attack_percent' | 'vigor_min' | 1 | (Cnd: Vigor) Increased ATK & MOB LV 3 | |
| mech | 'mech_defense_percent' | — | 1 | Increased DEF LV 3 | 'lines.MechDefensePercent', scenario 11 |
| mech | 'mech_defense_percent' | 'enemy_tags' | 2 | Advantage: EFSF (U.C.) LV 1 | 'lines.MechDefensePercentAgainstTag', scenario 1 |
| mech | 'mech_defense_percent' | 'hp_rate_gte' | 1 | (HP conditions) Increased DEF LV 2 | 'lines.MechDefensePercentAtHPRateAtLeast', scenario 3 |
| mech | 'mech_defense_percent' | 'hp_rate_lte' | 1 | (HP conditions) Increased DEF LV 2 | 'lines.MechDefensePercentAtHPRateAtMost', scenario 3 |
| mech | 'mech_mobility_percent' | — | 2 | Increased MOB LV 1 | 'lines.MechMobilityPercent', scenario 11 |
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
| pilot | 'pilot_awaken_percent' | — | 5 | Newtype LV 4 | 'lines.PilotAwakenPercent', scenario 11 |
| pilot | 'pilot_defense_percent' | — | 5 | Increased Defense LV 1 | 'lines.PilotDefensePercent', scenario 11 |
| pilot | 'pilot_melee_percent' | — | 3 | Increased Melee LV 1 | 'lines.PilotMeleePercent', scenario 11 |
| pilot | 'pilot_ranged_percent' | — | 7 | Increased Ranged LV 1 | 'lines.PilotRangedPercent', scenario 11 |
| pilot | 'pilot_reaction_percent' | — | 4 | Newtype LV 4 | 'lines.PilotReactionPercent', scenario 11 |
| pilot | 'revive_once' | 'mech_ids' | 2 | EX Character Ability (Char Aznable); one row is the companion row 84 | not read |
| pilot | 'squad_attack_percent_per_member' | 'mech_ids' | 2 | EX Character Ability (Io Fleming) | not read |
| pilot | 'squad_grant' | 'mech_ids' | 4 | EX Character Ability (Oliver May) | not read |
| pilot | 'support_attack_plus' | — | 6 | Support Attack / Counter Support LV 4 | |
| pilot | 'support_defend_plus' | — | 5 | Support Defense LV 4 | |
| pilot | 'weapon_en_cost_percent' | 'mech_type', 'strike_roles' | 2 | Support Attack / Counter Support LV 4 | |

Facts the table shows:

- A line carries at most two condition fields.
- Every line of the sample carries one tag id at most, so a line
  type holds one tag and not a list (ruling 2026-09-14).
- 'enemy_tags' is the datamine field of the "Advantage" pair: the attack half
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

## Section 5. The plan of the lines

The rows of Section 4, grouped by the mechanism each group needs,
in the order of the work (set 2026-09-15). A group is done when
every row of it is ticked in Section 4.

| Group | Lines | Rows | Mechanism | Status |
|---|---|---|---|---|
| A0 Advantage | ATK and DEF % against an enemy tag | 4 | the strike hooks | done, scenario 1 |
| A1 Unconditional stat % | mech ATK/DEF/MOB, pilot ranged/melee/awaken/defense/reaction | 45 | the strike hooks, every stat slot | done, scenario 11 |
| A2 HP conditions | ATK % at HP ≤ 25, DEF % at HP full, DEF % at HP ≤ 50 | 3 | none new: 'ability.Unit' carries HP and MaxHP; the scenario pins that each strike reads the HP of its moment | done, scenario 3 |
| A3 Facts of the holder | pilot lines on 'mech_tags' (damage dealt and taken, MP), mech line on 'pilot_tags' (move), 'mech_type', 'mech_ids', 'mech_series' | 22 | carriers: 'def.Pilot.Tags', 'def.Mech.Type', 'def.Mech.ID', 'def.Mech.Series'; the damage slots of ⑨ | |
| A4 Unconditional strike % | damage dealt, accuracy, evasion | 10 | slots: damage dealt and taken into ⑨ with the debuffs; accuracy and evasion as points of the hit rate ('雙方能力補正'); the reading of each slot is a hypothesis until a device forecast confirms it | |
| A5 Weapon conditions | I-Field, physical damage reduced | 4 | 'def.Weapon.Attributes' (physical, beam, special); the context carries the weapon already | |
| A6 Role conditions | DEF % on support defense, ATK % on support attack | 5 | 'Role' on the contexts, read from the strike fields (shooter ≠ owner, struck ≠ aimed, the segment) | |
| B Legality | EN cost % on support, special weapon range +1 | 3 | the cost and the reach of a weapon read through one hook at the menu, the schedule and the settlement | |
| C Assembly | max HP %, max EN %, support attack +1, support defend +1, move +1, MP +n | 21 | an assembly hook in 'system.Assemble', for what happens one time when a unit enters; the lines must reach the unit before it enters, so the wire or a Go door for 'place' comes first | |
| F MP | ATK and MOB % at vigor, special weapon range at vigor, MP +n | 4 | 'UnitValue.MP' and the wire 'mp'; issue #54 | |
| D Wound | revive once | 2 | a wound hook after the HP write and before the kill; the line keeps its own flag | not read |
| E Squad | squad grant, ATK % per member | 6 | a squad model | not read |
| — | HP supply %, debuff effect % | 2 | issues #79 and #80 | not read |

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
- 2026-09-14 (c956639): the first scenario, the "Advantage" pair, in
  'engine/battle/system/ability_test.go' with testify; the line
  structs and the carriers on 'def.Mech'. The wire types that came
  with it left again: the wire form is not decided.
- 2026-09-14: the hook points, after three rejected shapes (a shared
  sum type; a registry that binds a data struct to its
  implementation at each strike; a kind enum in 'def'). The contract
  'engine/battle/ability' ('Unit', 'Attack', 'Defend', 'AttackHook',
  'DefendHook', 'Hooks', 'Line'), the line types in
  'engine/battle/ability/lines', the lines and their chains in
  'state.UnitValue' ('SetAbilities', rebuilt by 'Clone'); 'system'
  builds the context and runs the chain. The scenario is
  green, with a negative scenario that fails on a hook that reads
  its own tags.
- 2026-09-14: the branch reopened as 'issue-72-ability-lines' off dev
  b2132c3 with this roadmap alone. Two preparations landed on the
  branch first: the support defender of the actor takes the support
  attacks of the defender side (2bbdb6f), and the stated behaviors
  are checked after the schedule in 'Commit' (0325d76). The method
  changed to tests in 'system' in small steps; Section 4 lists the
  112 lines of the sample as the checklist.
- 2026-09-15: 'system.Assemble' builds the two columns from the wire
  state ('validate' moved from 'board') and refuses a zero maximum
  instead of filling it; 'board.Load' hands the candidate over and
  keeps the columns.
- 2026-09-15 (f30b1f7 and after): one assembly, two origins. 'Fresh'
  ('init' through 'board.Open') sets every value of a unit to its
  default from the content and refuses a stated value; 'Resumed'
  ('load' through 'board.Load') takes every value as given and
  judges it against its maximum. Four goldens carried an ammunition
  count above an 'ammo_max' of zero; their 'ammo_max' is 3 now.
- 2026-09-15: the eight unconditional stat percent lines, as strike
  hooks in the same sums as the conditional lines, after a first
  version as assembly lines that wrote the unit was withdrawn: the
  formula has two zones (the stats, and ⑨), and the datamine gives
  the conditional and the unconditional lines of one stat the same
  trait type, so they are one sum.
- 2026-09-15: the three HP-condition lines and scenario 3, which
  pins the reading of each strike from the state of its moment;
  Section 5 records the plan of the groups.
