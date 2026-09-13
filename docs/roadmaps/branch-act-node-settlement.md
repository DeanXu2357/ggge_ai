# Branch roadmap: the act, redesigned from the board down

> Type: working—deleted at merge

Branch 'act-node-settlement', off 'dev' 619fc9e, opened 2026-09-08.
The design below is the result of the review of 2026-09-09. It
replaces the design of 2026-09-08 (in the git history of this file),
whose implementation reached 540fda6 plus an uncommitted tree and
passed its tests, and which the user rejected as structurally wrong.
Every ruling below is the user's unless marked 'open' or 'proposal'.

## 1. What is wrong today (confirmed 2026-09-09)

1. 'board.Act' checks nothing and shapes nothing. It hands the
   decision to 'system.Commit' and installs what comes back.
   (The ruling of 2026-09-09 also faulted the clone inside 'Commit'
   and inside 'system.Advance'; the user reversed that part on
   2026-09-10, see section 2.)
2. The parse hands over questions as data. A node carries 'alive'
   ids, 'charged', 'spendsEN' and 'takes'; 'settleNode' interprets
   the flags. The rule 'a counter fires only while both units live'
   is written by the parse into an id list, and the settlement knows
   no rule of its own.
3. 'battle.Decision' cannot state the two sides. Supporters travel
   as id lists and the engine picks their weapon; the counter weapon
   is optional and the engine picks one; the defender side hides in a
   nested 'ResponseAttack'.
4. The dice are two positional lists whose layout depends on the
   shape of the old decision.
5. The output labels a strike with 'StrikeKind', carries no fact
   about how the activation ended, and carries no terminal values.

Deferred until the act runs right (user ruling): the stateful
'receiver', the duplicate of the parse in 'prepare.go' that 'Menu'
still reads, the positional read in 'endActivation'. They are
repaired the same way afterwards, not on this pass.

## 2. The board: orchestration

'board.Act' owns four steps and nothing else:

1. Check the input: every id names a thing of the board, the kind
   matches the fields it carries.
2. Hand the two columns to 'system.Commit'. A system is a
   function from a values column to a new values column: it clones
   the column it receives, writes the clone, and answers the clone.
   'Commit' answers the column after the exchange and after the
   rotation that the end of the activation causes, if any. The board
   clones nothing, never hands a system a column it may write, and
   does not know the turn package (user ruling 2026-09-10: whether
   the phase rotates is a fact of the settlement, so 'Commit' calls
   'system.Advance' from its last segment; the board does not).
3. On success install the answered column as the values column. On
   any error install nothing: an error carries no column.
4. Shape the result of the engagement into the output type.

Ruling of 2026-09-10, which reverses step 2 of 2026-09-09 (board
makes a scratch, systems write it in place): the signature of a
system is its contract. A function that answers a new column cannot
write the column it received, so the caller needs no comment, no
marker type and no method to learn that; and the atomicity of the
act sits in the signature, not in the orchestrator. The cost is one
clone in each system, two for one act. The user judged that cost
no reason.

The board is the engine of the whole battle, so the board holds the
random source: 'board.New(seed)'. 'Load' does not change. The
handler passes no dice.

'system' is pure logic over the columns it receives. It holds no
state of its own between calls and writes only the clone it answers.

## 3. The input of 'Board.Act'

Every unit id is a session unit id: the position of the unit in the
roster of this session, assigned by 'Load'. A new session gives the
same mech and pilot a different unit id. Every weapon id is the
position of the weapon in the weapon list of the unit that fires it.

Shape (ruled 2026-09-10, not yet in the code; 'ResponseAttack'
keeps its owner in the name, ruling of 2026-08-28):

    Action
      actor_id
      move_to              optional: the anchor to move to first
      attack               optional: the attacker side
      response_attack      optional: the defender side, with attack

    Attack (the attacker side)
      weapon_id
      target_id
      stated               optional: the stated behaviors of the main strike
      support_attackers    [{unit_id, weapon_id, stated}], in order
      support_defender_id  optional: the unit that takes the counter

    ResponseAttack (the defender side)
      stance               dodge | defend | counter | none
      weapon_id            the counter weapon; present iff stance is counter
      stated               optional: the stated behaviors of the counter
      support_attackers    [{unit_id, weapon_id, stated}], in order
      support_defender_id  optional: the unit that takes the main
                           strike and the salvo

    MapAttack (the map-attacker side)
      map_weapon_id
      anchor               the target cell
      direction            the facing; the area reads the anchor or the
                           direction, and the map weapon decides which,
                           so the struct carries both

    Stated
      crit                 bool: the critical of the shooter
      hit                  bool: the strike lands on the unit struck

A stated behavior rides on the strike it belongs to. A strike with no
'stated' draws both behaviors from the random source of the board;
a strike with one states both (user ruling 2026-09-10: two plain
bools, the option sits on the strike and not on the field; 'hit' and
not 'evade', because the pair rides on the weapon and reads from the
shooter's side). A stated behavior that the rates of that moment give
no chance of is refused (a critical at rate 0, a hit at hit rate 0, a
miss at hit rate 1), in both directions. The stated pair of a strike on a unit
at 0 HP is read like any other.

The action carries no 'kind'. What the act does follows from the fields it carries: a 'move_to' alone is a reposition, no field at all is a standby, an 'attack' with its 'response_attack' is an attack (user ruling 2026-09-11: 'ActionKind' belongs to 'Decision'; 'Action' expresses itself by presence). The map attack fields and the flow that reads them are the next step.

The caller names every weapon. The engine picks no support weapon and
no counter weapon. The parse verifies that the named weapon reaches
and that the unit can pay for it.

The order of 'support_attackers' is the order the salvo settles. The
game has not answered which supporter fires first; the order of the
request is the placeholder the user set on 2026-09-08. A measurement
replaces it.

Gone with the old decision: 'battle.Dice', 'Stated', 'ServerDraw',
'DecodeOutcomes', 'CritRate', the fields 'Hit', 'CounterHit',
'SupportHit', 'Amount', 'Aim' (nothing reads them today), and
'ResponseAttack' as a nested type.

## 4. The engagement: parse, then settle

### Parse

The parse reads the action and the board as the act begins, and it
answers the facts of the two sides, fully resolved:

- attacker side: the actor, its anchor after the move, the main
  weapon, the target, the supporters with their weapons, the unit
  that takes the counter (if named)
- defender side: the stance, the counter weapon (if the stance is
  counter), the supporters with their weapons, the unit that takes
  the strike (if named)

The parse refuses, and the act ends with an error and no write:

- an id that names nothing; a unit that is destroyed, off phase, or
  has acted; a target that is no foe
- a weapon that does not reach, or that the unit cannot pay for
  (main, every supporter, the counter)
- a supporter with no support attack charge; a support defender with no
  support defend charge or out of support reach; a support defender named
  by a defender that defends
- a unit named two times on one side; more supporters than the cap
- a move the unit does not reach, or a move before a weapon that
  fires not after a move
- a stance that fires a weapon it should not, or names none when it
  should

Charges and energy are parse facts: each unit appears once in the
exchange and nothing in the exchange drains a unit before its own
strike, so the settlement judges neither. The parse answers facts and
no condition.

### Settle

The settlement walks the game order. Each segment is one function
with its own rule, judged from the working column as the segment
begins. Nothing waits for the end: every strike settles its own
consumption when its weapon applies.

| Segment | Fires when | The unit struck |
|---|---|---|
| 0 begin | always | the actor moves to its anchor |
| 1 attacker salvo | always, in order | the support defender of the defender if named (the whole salvo and the main strike land on it, in the defend stance); else the target, by its stance |
| 2 main strike | always | as segment 1 |
| 3 defender salvo | the target lives | the actor itself (open: whether the support defender of the actor takes a support strike is unmeasured; the current code says no) |
| 4 counter | the target lives and its stance is counter | the support defender of the actor if named and it holds a charge, in the defend stance; else the actor with no multiplier |
| 5 end | always | a kill in segment 1 or 2 (the support defender or the target), the actor alive, chance steps left: one chance step less and 'acted' stays false; else 'acted'. Then, when no unit of the side is pending, the phase rotates ('system.Advance'); each rotation is a phase event with the resets as effects |

One reason exists for a strike that does not fire: the target is
destroyed, and then segments 3 and 4 do not run. Every other strike
fires. In particular:

- The main strike fires on a target the salvo destroyed.
- The counter fires on an actor the defender salvo destroyed.
- No strike ever lands on a support attacker inside the exchange.

Every strike runs the same steps:

1. read the two behaviors of this strike, stated or drawn
2. judge the hit: a hit is a strike that was not evaded; the hit
   rate reads the target of the strike, and the dodge stance of the
   target, even when a support defender takes it
3. judge the critical
4. compute the damage with the multiplier of the unit struck
5. if the unit struck has HP above 0: take the HP, apply the debuff
   of the weapon (same kind: the larger magnitude stands, the fresh
   one takes the last place). A unit at 0 HP takes nothing, and the
   strike still counts as landed.
6. the shooter pays: the weapon energy, and one support attack charge
   for a supporter. The counter pays on a miss as well (open:
   current code, unmeasured).
7. a support defender pays one support defend charge on the first strike
   that lands on it in this exchange; a miss pays nothing

The stance of the target applies to the hit rate (dodge) and to the
multiplier (defend, with the shield). A support defender takes every strike
in the defend stance.

This branch places no ability moment and shapes nothing for one
(user ruling 2026-09-09). Issue #72 adds its calls later.

## 5. The output of 'Board.Act'

Three parts. The first excludes the other two.

1. The business error, as the Go 'error' of 'Board.Act': the actor
   does not exist, cannot act, the weapon does not reach, and every
   refusal of section 4. The handler maps it to a protocol code.
2. The events, in settlement order. One event is one thing the game
   shows: a move, a strike, the end of the activation, a phase
   rotation. Each carries its cause and its effects.
3. The terminal values of the units this act affected: every unit an
   effect landed on, with its whole value column after the act.

The result carries no echo of the request (user ruling 2026-09-10:
'ActResult' holds no 'request'). The caller holds the action it sent,
so a reader that must tell a stated behavior from a drawn one matches
an event against that action, not against a copy in the result.

The events (ruled 2026-09-10, not yet in the code):

    move            actor_id, from, to
    strike          segment (attacker_support | main | defender_support | counter),
                    shooter_id, weapon_id, aimed_id, struck_id,
                    fired, landed, critical, damage, effects
    activation_end  actor_id, effects (acted, or chance_steps)
    phase           turn, phase, effects (the resets of the side)

    effect          unit_id, and the fields that changed, each as
                    from and to: hp, en, sp, pos, acted, chance_steps,
                    support_attack_charges, support_defend_charges,
                    debuffs, map_weapon_ammo

'segment' is a label of the output ('stage' is bound to 關卡 in the
terminology map). No variable of the settlement carries it: each
segment writes the label of its own events. 'StrikeKind' leaves the
code base.

A strike that does not fire is an event with 'fired' false, a reason,
and no effects. A kill is an effect whose 'hp' reaches 0, not a field
of the strike.

'landed' and 'critical' are the result of the strike, not the stated
input: 'landed' true is a strike that hit, 'critical' true is a
critical, from a stated behavior or from a draw alike (user ruling
2026-09-10, to keep them apart from 'Stated{hit, crit}' on the
action). The event carries no mark of stated against drawn; a reader
tells them apart by matching the event against the action it holds.

The effect is one struct per unit with optional typed fields, not a
list of field names (user ruling 2026-09-10, after a side-by-side of
the two shapes on one example: the field name is the JSON key in the
typed form and a string value in the list form, and only the typed
form lets the Go and Python codecs check the field set). A skill or
a map attack adds an event value and reuses the effect.

Go shape ('engine/battle/result.go', step 3): 'ActResult{Events,
Units}'; 'Event' is an interface with one method
'EventKind()', and 'MoveEvent', 'StrikeEvent', 'ActivationEndEvent'
and 'PhaseEvent' carry their kind in the field 'event' of the wire;
'Effect' holds '*Change[T]' per field, nil when the field did not
change; 'UnitValues' is the value column of one unit with its
'unit_id' and no content field. Two choices of the session, open to
the user: the interface instead of one struct with a pointer per
kind, and 'UnitValues' instead of the whole 'battle.Unit' (which
would resend the mech and the pilot).

## 6. Acceptance

The user and the session define the scenarios together. Each
scenario is one Go test in 'engine/battle/', package 'battle_test',
that builds the units, calls 'Load', calls 'Act', and asserts on the
parts of the output and on 'State()'. No test reaches an
internal name of 'system', 'state' or 'board'.

The tests of 'commit_test.go', 'resolver_test.go' and
'strike_test.go' that reach internal structure are deleted, not
rewritten. The tests of 'formula', 'geometry' and 'state' stay; the turn
tests moved into 'system' with their package.

A green run is the floor. Acceptance is the user reading each
scenario against the rules of section 4 and the output of section 5.

Scenario list (for engine/battle/act_scenarios_test.go, drafted
2026-09-10, not yet written; the user reviews it against sections 4
and 5):

1. A plain attack, no response: one main strike, the target takes
   the damage, the actor pays the energy and 'acted'.
2. Attack with a counter: both strikes fire, both pay, nobody dies.
3. The salvo destroys the target: the main strike still fires on the
   target at 0 HP and pays; segments 3 and 4 do not run; the actor
   gains a chance step.
4. The defender salvo destroys the actor: the counter still fires on
   the actor at 0 HP; no chance step.
5. A support defender for the defender: the whole salvo and the main
   strike land on it; the first hit spends its charge; a later hit
   spends none; the target is untouched; if the support defender falls the
   later strikes still land on it.
6. All strikes on the support defender miss: its charge stays.
7. A support defender for the actor: the counter lands on it in the defend
   stance; the defender salvo lands on the actor.
8. Stated behaviors: a stated miss and a stated critical settle as
   stated; a stated critical at rate 0 is refused before any write.
9. Two supporters on each side, in the named order: the events keep
   the order of the request and each supporter pays its own energy
   and charge right after its strike.
10. Refusals leave the board unchanged: a supporter without a charge,
    a weapon that does not reach, a unit named twice, a defender that
    defends and names a support defender.
11. Reposition and standby: a move event and an activation end, no
    strike.
12. The last unit of a phase acts: the phase event follows the
    activation end with the resets as effects.
13. A debuff weapon lands twice: the larger magnitude stands.

## 7. Not in scope

- The wire and the handler. The engine shape settles first; the
  handler, 'play.py', the protocol spec and the goldens follow in a
  later step of this branch or a later branch, as the user rules
  then.
- 'system.Menu' and 'prepare.go'.
- The critical rate. No rule computes one; a stated critical is
  refused until one lands.
- The ability moments of issue #72.
- Map attacks and skills: refused as today; the output shape leaves
  them a place.
- The mechanism where the defender side strikes the actor before the
  main strike (user, 2026-09-09: a separate mechanism, later).

## 8. Gates

From 'engine/': 'gofmt -l .', 'go vet ./...', 'go test -race ./...'.
From the root: 'uv run pytest -q', 'uv run ruff check src tests
scripts'. The goldens under tests/fixtures/engine stay byte-identical
until the wire step changes them on purpose.

## 9. Status

Steps, in order. Each step is one change the user reads before the
next starts.

- 2026-09-10: the code stands at db4042a. The implementation that
  section 9 of the 2026-09-10 text called green was discarded; the
  branch redoes the design in small steps.
- 2026-09-10, step 1 (reverted the same day): the clone moved out of
  'Commit' and 'Advance' into 'board.Act', as section 2 of
  2026-09-09 ruled. The user then ruled the reverse (section 2,
  ruling of 2026-09-10) and the change was dropped; the code of
  db4042a already has that shape.

- 2026-09-10, step 2 (in the tree, not committed): 'Board.Act' reads
  'battle.Action' (section 3) and no dice. Details:
  - 'battle.Action', 'Attack', 'ResponseAttack', 'SupportAttacker' and
    'Stated' in 'engine/battle/action.go'. 'battle.Decision' stays for
    the question 'response_attacks' (user ruling 2026-09-10: the act
    replaces the decision in 'Act' alone); its field 'response_attack'
    now carries the new 'ResponseAttack' type, and 'Menu' reads the
    decision with no support field and no response, as before.
  - 'battle.Dice', 'Forced', 'ManualRoll', 'ServerDraw',
    'DecodeOutcomes' and 'Node' are deleted. The board holds the
    random source: 'board.New(seed)'. A refused act puts the source
    back where it stood.
  - 'system.Commit(board, action, draw)' answers a new column;
    'prepare.go' shrinks to what 'Menu' reads (actor, anchor,
    weapon, target).
  - The settlement is cleared (user, 2026-09-10: 「先清空 Commit 裡面
    的實作，以及底下的私有函式……維持最乾淨的狀態避免之後的改寫被
    之前的思路所影響」). 'Commit' is a stub that panics after nothing;
    the old write, 'judge', 'receiver', 'wound', 'applyDebuff',
    'endActivation', 'salvo' and 'counterStrike' are gone. The settle
    step writes section 4 from a clean file.
  - The parse of section 4 ('parse.go') is cleared as well (user,
    2026-09-10). 'prepare.go' keeps the parse that 'Menu' reads.
  - Tests: every test that reached the parse, the write or
    'Board.Act' is deleted, and section 6 replaces them. The dice
    tests and the 'counterWeapon' test are deleted; 'action_test.go'
    is added; 'strike_test.go' keeps its own board.

- 2026-09-10, step 3 (in the tree): the output types of section 5
  in 'engine/battle/result.go', with a wire-shape test. 'Commit'
  answers '[]battle.Event' (still a stub); 'board.Act' shapes the
  the events of the engagement and the terminal values of every
  unit an effect names, by unit id (the request echo was dropped on
  2026-09-10). The
  board no longer calls 'system.Advance' (user ruling 2026-09-10,
  section 2): the rotation belongs to segment 5 of the settlement,
  and 'system.Advance' must then answer the resets it writes as the
  effects of a 'PhaseEvent'. The old
  'ActResult', 'StrikeEvent', 'PhaseEvent' of 'responses.go' and
  'Trace', 'Strike', 'StrikeKind' of 'engagement/results.go' are
  deleted.

Out of the verification of this change (user ruling 2026-09-10):
the wire, the handler and the Python side. Once the shape of
'Board.Act' changes, 'engine/protocol' and 'engine/server' stop
compiling against the new contract, and the gates of section 8
apply to 'engine/battle/...' alone on this branch.

- 2026-09-13, step 4 (2e55c12): the refusal step of section 4, as
  'check' inside 'commit.go'. The user ruled three things on the way:
  the parse answers no data (no intermediate type; the segments read
  'Action' by presence and 'check' answers an error alone); a private
  function with one caller earns no file of its own; and the tests of
  this branch target 'Commit' in its own package ('commit_test.go'),
  because a black-box suite over 'Board.Act' is an integration test
  and not the unit test of the step. The scenario suite of section 6
  was written, reviewed, and removed; section 6 is superseded on the
  test surface (the scenario list stays the acceptance checklist).
  An accepted action answers a copy of the column and no event until
  the settlement lands.

- 2026-09-13, step 5: 'engagement' and 'turn' merge into one package
  'engine/battle/system' (user ruling: the two behavior systems
  differ in scenario alone). A move with no behavior change: the
  entries the board calls each stand in their own file ('commit.go',
  'menu.go', 'advance.go', 'pending.go', 'gone.go', 'activatable.go',
  'living_unit.go'); the checks of step 4 sit in 'check.go' until the
  settlement step sorts the functions of the act by responsibility.
  The older helpers ('prepare.go', 'support.go', 'strike.go',
  'model.go') are not touched: the user ruled that their necessity is
  judged one by one while the settlement is written. The spec
  'battle-engine-protocol.md' received the path renames alone; its
  text on the mechanism waits for the wire step of section 7.
