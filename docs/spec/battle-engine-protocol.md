# Battle engine protocol

> Type: spec—the authoritative description of an implemented mechanism or format

The battle engine is one Go process. It holds the board of one
battle. It answers commands on stdin and stdout. This document is
the contract between the engine and its clients.

The engine holds no game logic in this document. The commands that
carry the rules are declared here and are implemented by the later
issues of the port (#60 to #68).

## Process model

- One process holds one battle. A client that must run two
  battles starts two processes.
- The engine is the authority for the board. A client keeps no
  second copy of the board.
- The engine holds the operation history of the battle. The
  command 'rollback' removes the last entry.
- 'init' plus the sequence of the commands that change the board
  reproduce the battle. The engine holds no other input.

## Transport

- One JSON object on one line. This applies to a request and to a
  response.
- Request: 'id', 'cmd', 'payload'.
- Response, success: 'id', 'ok' true, 'payload'.
- Response, failure: 'id', 'ok' false, 'error' with 'code' and
  'message'.
- The 'id' of a response is equal to the 'id' of its request.
- The engine answers one request with one response. The engine
  sends no unsolicited message.
- EOF on stdin stops the process with status 0.

Error codes:

| Code | Meaning |
|---|---|
| unknown_command | The engine does not know the command name |
| not_implemented | The command is declared, but its issue is not merged |
| bad_request | The payload does not match the schema |
| no_session | The command needs a board, and 'init' did not run |
| illegal_state | The board does not permit the command now |
| illegal_action | The named action or reaction is not legal |
| empty_history | 'rollback' found no entry |
| already_acted | The unit acted in this turn; the command answers |

An error response does not stop the process. An error response does
not change the board.

## Commands

### hello

Purpose: the version and the command list of the build.

Request: no fields. Response: 'protocol', 'commands'. Each entry of
'commands' carries 'name' and 'implemented'.

### ping

Purpose: a liveness check. Request and response carry no fields.

### init

Purpose: build the board of one battle.

Request:

| Field | Content |
|---|---|
| board | The width and the height |
| enemies | The enemy units, with their cells |
| victory | The victory conditions of the stage |
| events | The stage event table |
| deploy_cells | The cells that accept an ally unit |
| rules | The rule overrides of the stage |
| seed | The seed of the session random source |

Response: 'turn', 'phase', 'deploy_open'.

'init' on a live session replaces the battle. The history starts
again.

'init' is not implemented. The section 'Terrain' holds one open
requirement for the issue that implements it: 'board' must carry
the terrain of the map.

Refusals: bad_request.

### deploy_cells

Purpose: the cells that accept an ally unit now.

Request: no fields. Response: 'cells'.

Refusals: no_session; illegal_state when the deploy phase is over.

### place

Purpose: put one ally unit on the board.

Request: 'unit' (the full unit payload) and 'cell'.
Response: 'placed' (the unit ids on the board) and 'cells' (the
cells that still accept a unit).

Refusals: no_session; illegal_state when the deploy phase is over;
illegal_action when the cell is not a deploy cell, when the cell
holds a unit, or when the unit id is on the board.

### roster

Purpose: the current state of every unit, both factions.

Request: no fields. Response: 'units'.

Refusals: no_session.

### reach

Purpose: the cells that one unit can move to.

Request: 'unit_id'. Response: 'cells'.

The cells are anchor cells: on each one, the whole footprint of the
unit stands on free cells of the board. The section 'Board
geometry' holds the rule.

The cells come in a deterministic order: the column first, the row
second. A client reads a list, not a set.

Refusals: no_session; illegal_action for an unknown unit id.

### actions

Purpose: what one unit carries.

Request: 'unit_id'. Response: 'unit', 'move_cells', 'weapons',
'skills', and 'error' when a state stops the unit from acting.

The command reports. It selects nothing and it removes nothing. It
reads no target, no band and no resource: a weapon with no energy
left, and a weapon that reaches no unit from the cell of today,
stay in the list. The client draws the bands from these fields, the
user picks the move, the weapon and the target, and 'act' judges
the pick.

'unit' holds 'unit_id', 'faction', 'pos', 'size', 'hp', 'max_hp',
'en', 'en_max', 'move_range' and 'acted'.

'move_cells' holds the cells that 'reach' answers, in the same
order.

A weapon entry holds 'name', 'range_min', 'range_max', 'en_cost',
'ammo', 'accuracy', 'can_counter', 'map_weapon' and
'usable_after_move'. A null
'ammo' is a weapon that spends no ammunition. The entry carries no
power: the engine drops the power of a weapon when it reads the
state.

The entry carries no weapon ability. The section 'Weapon abilities'
holds the gap and the reason.

A skill entry holds 'kind', 'amount', 'uses', 'ends_activation',
'usable_after_move', 'range_min', 'range_max', 'blast' and
'affects'.

A unit that acted keeps the whole payload. Its 'error' holds the
code 'already_acted' and a message.

Refusals: no_session; illegal_action for an unknown unit id;
illegal_state when the unit is destroyed; illegal_state when the
phase of the unit is not the current phase.

### reactions

Purpose: the legal reactions of one defender against one planned
strike.

The client calls this command before it sends 'act'. The attacker
chooses the action first. The client does not send that action yet.
The client asks for the reactions of the defender, and it sends the
action and the reaction together in one 'act'.

Request:

| Field | Content |
|---|---|
| action | The action of the attacker |
| defender_id | The unit that takes the strike |

The engine reads the cell of 'move_to' of the action. The engine
does not read the current cell of the attacker. A client can
therefore ask about a move that did not occur. An action with no
'move_to' fires from the cell of today.

Response: 'defender' and 'attacker'.

'defender' holds 'unit_id', 'reactions', 'support_defenders' and
'support_attackers'. 'attacker' holds 'unit_id',
'support_defenders' and 'support_attackers'.

The list 'reactions' holds dodge, defend, one entry for each weapon
of the defender that can counter and reaches the attacker, and
'none'. The stance 'none' is the unit that stands and takes the
strike. The list holds no 'shield': the shield of a unit settles
during the damage, in 'act'.

Only an action of the kind 'attack' asks the defender anything. A
map attack permits no reaction, and no other kind of action reaches
a unit, so the command refuses every other kind. A client that runs
one of them sends 'act' and no question.

A reaction entry holds the forecast 'incoming': what the strike of
the attacker does to the defender under that stance. A counter
entry also holds the forecast 'counter': what the counter does to
the attacker. A stance entry reads no support unit. An interceptor
changes no outcome of the stance, so each interceptor carries its
own forecast in 'support_defenders'.

A support defense entry holds 'unit_id' and the forecast
'incoming': what the strike does to that interceptor. A support
attack entry holds 'unit_id', 'weapon' and the forecast 'strike':
what the shot of that unit does to its foe. The support attackers
of the defender fire at the attacker, and the support attackers of
the attacker fire at the defender.

A forecast holds 'hit_rate', 'damage' and 'kill'. 'damage' is the
conservative lower bound of the damage: no critical hit and no
bonus beside the debuffs the target carries. A weapon and a mech
that stack the critical rate to 100 percent are the one exception,
and the bound then holds the critical damage. 'kill' is true when
the bound is at least the hit points of the target. The hit roll is
no part of 'kill': a 'kill' of the dodge stance reads "the strike
destroys this unit when it lands".

A field that the engine cannot answer for that entry is null. Two
entries hold such a field. The entry of an interceptor of the
defending side holds no 'hit_rate': the stance of the defender
settles that hit roll, so the rate stands beside the stance entry.
The entry of an interceptor of the attacking side holds no forecast
at all: it takes the counter, and which weapon counters is the pick
of the defender.

The forecast of a support attack entry reads no stance of its foe,
because the foe picks the stance after this answer.

Refusals: no_session; bad_request when the action stands outside
the contract; illegal_action for an unknown unit id, a destroyed
unit, an action of a kind other than 'attack', a weapon the
attacker does not carry, and a weapon that does not reach the
defender from that cell.

### act

Purpose: run one action and write the result to the board.

Request:

| Field | Content |
|---|---|
| unit_id | The unit that acts |
| action | The action of the unit |
| reaction | The reaction of the defender |
| dice | The dice input |

The field 'action' holds the move of the unit. The engine resolves
the move first and the action second; the section 'Unit payload,
action, and reaction' holds the rule.

The field 'reaction' is necessary for an action of the kind
'attack', because such an action always gives a list. The field is
not permitted for every other kind.

The client names every support unit of the engagement, and the
engine names none. The action holds 'support_attackers', the units
of the side of the actor that join the strike, and
'support_defender', the unit that takes a counter strike for the
actor. The reaction holds the same two fields for the defending
side: 'support_attackers' join the answer of the defender, and
'support_defender' is the interceptor that takes the strike in
place of the defender. Each list holds the unit ids that
'reactions' reports, and no unit two times.

A defender that defends takes the strike itself and names no
interceptor. A defender that carries a shield defends with the
shield: the reaction menu offers no shield stance, so the shield
multiplier applies to the defend stance of that unit. Whether the
game pairs an interceptor with the stand is not measured; the
engine permits it.

The rules cap the number of support attackers of one strike. A unit
that the engagement destroys or drains before its own shot fires
nothing.

The field 'dice' holds 'mode'. The value 'forced' also holds
'outcomes': the engine reads one outcome for each chance event, in
the resolution order. The value 'sampled' holds no outcome: the
engine draws from the session random source of 'init'.

Response: 'events' (the resolution in order) and 'board' (the new
summary).

The command judges the pick against the rules of the mechanism, and
not against a list of actions: the reporting commands read the same
rules, so a pick that the report offers passes here. A refusal
leaves the board as it was.

The command resolves no action of the kind 'map_attack'. The area
of a map weapon is a shape of that weapon, and no contract of this
repository holds that shape. The engine refuses the kind until the
shape lands.

Refusals: no_session; illegal_state when the phase of the unit is
not the current phase, or when the unit acted in this turn;
illegal_action for a target that is no foe, a weapon the unit does
not carry, a weapon the unit cannot pay for, a weapon that does not
reach the target, a support unit that cannot join or intercept, a
support attacker list above the cap of the rules, a reaction that
breaks a rule of the stance, an absent necessary reaction, a short
'outcomes' list, an action that carries 'move_to' when its weapon
or its skill holds 'usable_after_move' false, and an anchor that
the unit does not reach.

### rollback

Purpose: remove the last entry of the operation history.

'rollback' removes the last command that changed the board. The
commands 'act', 'place', and 'set_unit' write such an entry.

Request: no fields. Response: 'undone' (the command name and its
payload) and 'board'.

Refusals: no_session; empty_history.

### set_unit

Purpose: write values into one unit, without the turn rules.

This command serves a formula check: an operator sets the values
that the device shows, and then runs one engagement.

Request: 'unit_id' and 'fields' (the values to change: the cell,
the HP, the EN, the weapons, the unit values, the pilot values, the
debuffs).

Response: 'unit'.

Refusals: no_session; illegal_action for an unknown unit id, or
for a cell that holds another unit.

### advice

Purpose: the decision of the advisor for one faction.

Request: 'faction', 'budget', 'algo', and 'goal'. The field 'goal'
is optional: the engine uses the victory conditions of 'init' when
the request holds no goal.

Response: a 'Verdict'.

The engine answers when the faction holds a decision that waits.
An ally reaction against an enemy strike is such a decision, and
the phase of that moment is the enemy phase. The gate is the
decision, not the phase.

Refusals: no_session; illegal_state when the faction holds no
decision that waits.

### certify

Purpose: the guarantee of one action.

Request: 'action'. Response: 'guarantee'.

### export and load

Purpose: the snapshot of the session, for a run log, a replay, and
a differential test.

'export' takes no field and gives 'state' and 'history'. 'load'
takes the same two fields and replaces the session.

The state carries 'phase'. A state without that field is a
bad_request.

## Board geometry

A cell is a pair of integers: the column first, the row second.

A unit covers a rectangle of cells. This rectangle is the
footprint. The field 'size' holds the width and the height of the
footprint, in the axis order of a cell. The field 'pos' holds the
anchor cell: the cell of the footprint with the least value on each
axis. A unit does not turn. A footprint of 2 by 3 stays 2 by 3, and
the board decides which units carry which size.

A payload that carries no 'size' gives the unit one cell.

A unit moves on the four orthogonal steps. One step costs one point
of the move range. A diagonal cell costs two steps. Range reads the
same steps.

The distance between two units is the least distance between a cell
of the one footprint and a cell of the other footprint. Two
footprints that touch are at distance 1. Two footprints that share
a cell are at distance 0. Two units of one cell give the distance
of the two cells.

Every range answer reads this distance: the band of a weapon, the
band of a skill, the blast of a skill, and the move range that lets
a support unit join. A weapon with a 'range_min' of
2 does not fire at a foe that touches the footprint, because that
foe is at distance 1.

A unit moves as one body. Each step of the path carries the whole
footprint. An anchor is a destination only when every cell of the
footprint is on the board and holds no other unit. A cell of an
enemy or of a third party stops the path. A cell of an ally lets
the path through and is no destination.

The Python side holds no geometry of its own. It carried the
eight king steps and one cell for every unit, and it retired with
the rest of the Python rules (issue #73). A golden case that the
Python side wrote therefore compares no result that reads the
distance or the footprint, and a golden case that compares a
reaction list holds units of one cell in one row. The 'actions'
command left the comparison with issue 63: it reports what one unit
carries, and the Python side holds no such answer.

## Types

### Verdict

| Field | Content |
|---|---|
| action | The chosen action, or the chosen sequence of one turn |
| expected_value | The value of the chosen action |
| guarantee | KILL or NONE |
| diagnostics | The statistics of the search |

A 'guarantee' of NONE says that the engine holds no certificate. It
does not say that the action fails.

### Goal parameters

| Field | Content |
|---|---|
| victory | destroy_all, destroy_target, or reach_cell, with its parameters |
| score | The score constraints: the survival of every unit, and the HP limit |

The goal selects the statistic of the leaf evaluation.

### Budget

| Field | Content |
|---|---|
| time_ms | The limit in milliseconds |
| nodes | The limit in nodes |

An exhausted budget gives the best action of that moment. The
diagnostics record the exhaustion.

### Unit payload, action, and reaction

The authority for these three schemas is the Go package
'engine/protocol'. 'src/ggge_ai/engine/state.py' holds the same
structs in Python and 'src/ggge_ai/engine/codec.py' writes the
wire form from them. The contract names the payload of one
activation 'action'; the struct names the same thing 'Decision'.
The Go type keeps the struct name, and the wire field keeps the
contract name.
The enum of the kinds of one action is 'ActionKind' on both sides.
The enum holds no kind of movement. Its wire field is 'kind', and
its value set is frozen.

The resolution order of one activation: the move first, then the
action. The move is the field 'move_to' of the action. Every effect
that reads a cell reads the cell after the move. There is no
exception to this order.

An action does not always carry a move. The permission is the field
'usable_after_move' of the weapon of the action, or of its skill.
A true value permits a move in the same activation; a false value
makes the action pre-move only. The permission is a property of
that weapon or that skill, not of the kind of the action: a map
weapon is a common holder of a false value, but some map weapons
fire after a move, and some skills of the source 'pilot' or 'crew'
hold a false value (user ruling 2026-08-20).

A skill carries its area in four fields. The fields 'range_min'
and 'range_max' hold the distance from the caster to the center of
the area. The field 'blast' holds the radius around the center, in
the distance of the section 'Board geometry'; a blast of 0 is one
cell. The field 'affects' holds the
faction filter of the units in the area: 'ally', 'enemy', or 'all'.
The center travels in the field 'aim' of the action, and a single
target travels in the field 'target_id'; the action carries no
other field for the area.

The value set of 'affects' holds no 'self'. A skill that acts on
the caster alone is a 'range_min' of 0, a 'range_max' of 0, a
'blast' of 0 and an 'affects' of 'ally': the area is the cell of
the caster, and the caster is an ally in its own cell. A 'self'
value would make a second way to write the same area.

The fields 'pos' and 'size' of a unit hold its footprint. The
section 'Board geometry' holds their meaning.

The rules of the wire form:

- A cell is a JSON pair, in the order of the Python tuple.
- The center of an area effect is on the wire, in the field 'aim'.
  The engine does not derive the center from the cell of the actor.
- Every field of the type is on the wire. A field that holds no
  value is null.
- A field with three values keeps its three values: 'hit' is true,
  false, or null. Null says that the caller settles that node
  somewhere else.
- The stance 'none' is on the wire: it is the unit that stands and
  takes the strike. The stance 'shield' is not. A payload that
  carries 'shield' is a decode error.
- A decode and an encode of one payload give the same bytes a
  second time.
- The trigger and the effect of a stage event stay free objects.
  The issue that runs the event table reads them.

A field that 'engine/state.py' holds and the Go struct does not is
a test failure: 'tests/test_engine_codec.py' compares the fields of
the dataclass with the JSON tags of the Go struct.

The Go struct can hold a field that 'engine/state.py' does not.
Such a field carries a rule that the Python side never held. It is
optional on the wire: a payload that omits it keeps the behavior of
the build before the field. The test names each one in
'ENGINE_ONLY', so a Go field that nobody declared is still a test
failure.

### The final panel and the base data

A unit is a pilot that rides a mech. The payload carries two
levels of values, and they are not the same numbers.

The final panel is what the game shows for the deployed unit. The
fields 'hp', 'en', 'move_range' and 'weapons' of the unit carry
it, together with 'unit_attack', 'unit_defense', 'mobility',
'pilot_attack', 'pilot_defense' and 'reaction'. Every rule of the
board reads the final panel.

The base data is what the mech and the pilot supply to the
computation of the final panel. An ability of the mech or of the
pilot can change what the unit ends up with, so the base copy and
the final panel can differ (user ruling 2026-08-21).

The mech carries its base copy in four optional fields:

| Field | Content |
|---|---|
| mech_hp | The hit points of the mech |
| mech_en | The energy of the mech |
| mech_move_range | The movement range of the mech |
| mech_weapons | The weapons of the mech, in the weapon payload |

These four are engine-only. A payload that omits them leaves the
base copy of the mech empty. It does not fill the base copy from
the final panel. No code derives the one level from the other
today, so a producer that reads the panel of the game alone sends
the panel alone.

The Go types keep the two levels apart by the struct that holds
the field, and not by the name of the field: 'battle.Unit' holds
the final panel, and 'battle.Mech' and 'battle.Pilot' hold the
base data. 'Mech.HP' is the base copy, and 'Unit.HP' is the panel.

### Terrain

Terrain belongs to a cell. The five kinds are 'space',
'atmospheric', 'ground', 'surface' and 'underwater'. One stage map
can hold more than one kind.

The state carries the terrain of the map in two optional fields:

| Field | Content |
|---|---|
| terrain | The kind that every cell of the map takes |
| terrain_cells | The cells that take another kind |

Each entry of 'terrain_cells' holds 'cell' and 'terrain'. A state
with no 'terrain' puts the whole map in space. A terrain name
outside the five is a decode error.

No rule of the engine reads the terrain today. The state carries
the terrain of each cell so that the rule has its data when it
lands. What reads it is a weapon ability, and the section 'Weapon
abilities' holds that gap.

The rules payload carries no terrain. One stage held one terrain
value until 2026-08-26.

Open, for the issue that implements 'init': the field 'board' of
the request must carry the terrain of the map, in the same two
fields that the state carries above. The user ruled on 2026-08-21
that the terrain of each cell arrives when the board is built.
Today 'board' carries the width and the height alone, and 'init'
is not implemented.

### Weapon abilities

A weapon ability is one named ability of one weapon, positive or
negative. The user ruled on 2026-08-26 that the effects the engine
missed are abilities of a weapon, and not rules of the board:

- '對水中目標傷害減半' divides the damage of that weapon when the
  cell of the target holds the terrain 'underwater'. It reads the
  cell of the target.
- '攻方自身在水中時不可使用' forbids the weapon while the cell of
  the attacker holds that terrain. It reads the cell of the
  attacker.
- A map weapon fires before the move and ends the activation of
  the unit. An ability lifts the first half.

The engine models a closed set of ability kinds. A weapon that
carries a kind outside the set resolves as a weapon with no
ability: the damage divides by 1 and the weapon fires. A new
ability of the game adds a kind to the set. It never adds a field
to the weapon entry, because the abilities of the game are open
and the fields of a contract are not.

The wire carries no ability today, and no ability kind is modelled.
Issue #80 builds the model and adds the field of the weapon entry
that holds the list. Until then the engine passes 1 for the terrain
correction of every weapon
('StrikeDamage' in 'engine/battle/strike.go').

### Differential cases

'tests/fixtures/engine/' holds the cases. Python writes them, and
the Go tests in 'engine/differential' read the same file and
compare. One case file holds:

| Field | Content |
|---|---|
| name | The name of the case, equal to the file name |
| note | What the board carries |
| setup | The rules, the event table, and the board |
| checks | The list of the checks |

Each check names an 'op', its 'input', and the 'expect' that the
Python side produced while it still held the rules. An op that the
Go build does not implement is skipped, not failed, so a port issue
finds its checks waiting. The files are frozen: the writer retired
with the Python rules (issue #73), and no process writes them
again. A case that the engine must not keep is deleted, never
regenerated.

Float comparison: the two sides compare with a relative tolerance
of 1e-9 and an absolute floor of 1e-12. A number that one side
copies from the other matches bit for bit, because both write the
shortest decimal that reads back as the same double. A number that
each side computes does not: the two runtimes call different libm
code for 'exp', and the results part in the last bits. The
tolerance hides no wrong formula, because a wrong formula misses by
far more, and it hides no wrong integer, because the smallest
difference between two integers is 1.

## Evolution

- A change adds a field. A change does not give a new meaning to a
  field that exists.
- A change that adds a field raises the protocol version.
- 'hello' gives the version and the command list. A client reads
  them before it sends a command that it does not know to be
  implemented.
