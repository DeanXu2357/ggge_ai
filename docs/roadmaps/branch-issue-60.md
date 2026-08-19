# Branch roadmap: issue 60, the state codec and the UI client

> Type: working—deleted at merge

## Change summary

The engine holds the state types, a command registry, and the
differential harness. The web UI can talk to the engine. The branch
lands no game rule.

New, Go:

- 'engine/protocol/state.go': the nine types of
  'sandbox/model.py', field for field.
- 'engine/server/registry.go': 'Register' binds one declared name
  to one handler.
- 'engine/differential/': the case reader and the comparison.

New, Python:

- 'src/ggge_ai/engine/codec.py': the same wire form, written from
  the model.
- 'scripts/write_engine_fixtures.py': it writes the cases, and
  '--check' reports a stale file.
- 'tests/fixtures/engine/': four boards.

Changed:

- 'engine/protocol/types.go': the three raw aliases are gone. The
  request and the response structs hold real types.
- 'src/ggge_ai/sandbox/facade.py': 'engine_state()'.
- 'scripts/sandbox_ui.py': the flag '--engine' starts the process,
  pushes the board, and asks the declared queries.
- 'docs/spec/battle-engine-protocol.md': the wire form of the state,
  the case-file format, and the float rule. The forward reference
  of issue #59 is now filled.
- 'docs/reference/terminology-map.md': the term 'action', and the
  term 'action kind'.
- 'engine/protocol/state.go': the enum 'MoveKind' is now
  'ActionKind', and the lookup map 'moveKinds' is now
  'actionKinds'. The wire values and the JSON tags do not change.
- 'docs/spec/battle-engine-protocol.md': the resolution order of
  one activation, the rule of the field 'aim', and the name pair
  of the enum.
- 'src/ggge_ai/sandbox/model.py': 'Weapon' holds
  'usable_after_move'. 'Skill' holds 'source', 'usable_after_move',
  'range_min', 'range_max', 'blast' and 'affects'. Two new enums:
  'SkillSource' and 'SkillAffects'.
- 'engine/protocol/state.go': the same fields, and the two enums
  with a decoder that refuses a value outside the contract.
- 'src/ggge_ai/engine/codec.py': the encoders and the decoders of
  the new fields; 'tests/fixtures/engine/' rewritten.
- 'docs/spec/battle-engine-protocol.md': the timing rule of an
  action, the area fields of a skill, and the refusal of 'act' for
  a move that the weapon or the skill does not permit.
- 'docs/reference/combat-formulas.md': the map weapon timing is
  per weapon. The 2026-07-13 reading stays as superseded text.
- 'docs/reference/terminology-map.md': the terms 'skill source'
  and 'affects'.

## Call chain

'Sandbox.engine_state' calls 'codec.encode_state'. The UI sends
that payload with 'load'. The engine answers 'not_implemented', and
the page keeps its Python rendering.

A port issue calls 'server.Register' in an init function of its own
file. 'hello' reads the same registry, so its answer cannot drift
from the dispatch.

A differential case names an op, its input, and the output that
Python produced. A Go test runs the op and compares. An op that
this build does not hold is skipped.

## Contention points

1. The stance 'none' is a decode error, on both sides. The
   contract says the reaction list holds no decline option, and
   'sandbox/model.py' still holds the member. The codec raises at
   the boundary rather than passing the value.
2. Field parity is a Python test that reads the JSON tags of the
   Go struct. The authority is 'sandbox/model.py', so the gate that
   a Python change runs must be the gate that breaks. A generated
   field list would add a third file that goes stale.
3. Floats compare with a relative tolerance of 1e-9 and an
   absolute floor of 1e-12. Two runtimes call different libm code
   for 'exp'. A wrong formula misses by far more than the
   tolerance, and the smallest difference between two integers is
   1.
4. The UI pushes with 'load', not with 'init' and 'place'. A
   scenario board holds units that already stand on the field;
   'init' and 'place' are the deploy path.
5. 'Register' panics on a name outside the contract and on a
   second binding of one name.
6. The wire name is 'action' and the Go type name is 'Decision'.
   The contract and the model disagree, and each keeps its own
   name. The terminology map holds the binding.
7. The enum lists the kinds of one action, not kinds of movement,
   so the engine names it 'ActionKind'. The model keeps 'MoveKind'
   until a Python change lands. A proposal to carry the move
   timing in the enum, as paired members with the suffix
   'AfterMove', is rejected: 'move_to' already records the move,
   and a second record needs an invariant that every consumer
   maintains. The timing of a skill belongs in 'Skill', as a
   predicate.
8. The 'Skill' fields for the source of a skill and for the
   timing predicate landed in this branch (user ruling 2026-08-20).
   The contract shape only: nothing reads the new fields.
9. Known divergence, deliberate: the data says the timing is per
   weapon and per skill, and 'step()' in 'sandbox/model.py' still
   holds the rule per kind. The line 'decision.kind is not
   MoveKind.MAP_ATTACK' drops 'move_to' for every map weapon.
   'legal_skills', 'legal_map_attacks' and 'legal_attacks' do not
   read 'usable_after_move' either, and the Go engine implements
   no refusal. Enforcement belongs to a later issue.
10. The value set of 'affects' holds no 'self'. A skill that acts
   on the caster alone is a zero range with a zero blast and the
   value ally. The overload is removed, not special-cased.
11. The wire value of the source of a character skill is
   'character'; the terminology map binds the concept as 'pilot
   skill' (駕駛技能). The map now records the pair.

## Verification

- cd engine && go vet ./... : no finding.
- cd engine && go test ./... : ok, three packages.
- uv run ruff check src tests scripts : all checks passed.
- uv run pytest -q : 1109 passed, 4 skipped.

After the rename of the enum:

- cd engine && go vet ./... : no finding.
- cd engine && go test ./... : ok, three packages.
- gofmt -l engine : no file.
- grep for the old names in the Go tree : no match.
- uv run ruff check src tests scripts : all checks passed.
- uv run pytest -q : 1109 passed, 4 skipped.

The parity test reads 'engine/protocol/state.go', but it parses
the struct lines only. The rename of the enum is invisible to it.

After the area fields and the timing fields of a skill:

- cd engine && go vet ./... : no finding.
- cd engine && go test ./... : ok, three packages.
- gofmt -l engine : no file.
- uv run ruff check src tests scripts : all checks passed.
- uv run pytest -q : 1110 passed, 4 skipped. One new test:
  a skill enum outside the contract stops the decode.

Negative controls: a new field on the Python dataclass fails both
parity tests; a hand-edited golden value fails the differential
with the field path and the two numbers.

One item has no test: the engine badge of the web page. The
subagent called '/api/engine' over HTTP with the real executable
and read the answer, but no test renders the badge.

## Merge note

This branch and 'issue-66-decide-contract' both change
'src/ggge_ai/sandbox/facade.py'. They hold different regions of the
file. Merge 'issue-66-decide-contract' first.
