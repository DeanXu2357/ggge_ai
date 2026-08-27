# Turn cycle and the act command: implementation plan

> Type: working—deleted at merge

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Go engine runs the turn cycle around one activation and answers `init`, `act`, and `export`; `load` takes a seed; the sandbox page plays the ally phase through `act` against the built binary.

**Architecture:** `Board.Act` runs `Board.Apply` (the #64 engagement) and then rotates the phase while the side to act holds no pending unit; a rotation back to the ally side opens the next turn. The phase start resets the activation of the side, regenerates its EN, and expires the debuffs of one full round. The `act` handler runs on a clone of the board and installs the clone only when the whole run succeeds, so a refusal changes neither the board nor the place of the session random source in its stream. The dice of the wire are two `Dice` implementations: a manual roll that reads `outcomes`, and a server draw that reads the seeded source.

**Tech Stack:** Go 1.26 (`math/rand/v2` PCG), Python 3.12 with uv, pytest, the existing `engine/differential` fixture runner.

**Spec:** `docs/spec/battle-engine-protocol.md` (sections `init`, `act`, `export and load`, `Unit payload, action, and reaction`, `Differential cases`, `Evolution`), `docs/reference/combat-formulas.md` lines 191-195 (EN regeneration) and 269-273 (debuff duration), and the rulings in `docs/roadmaps/branch-issue-65.md`.

## Global Constraints

- Prohibition of the issue: read no Python game-rule code, port none, follow no structure of it. Read nothing under `/home/poyu/workspace/project/ggge_ai-worktrees/issue-65-turn-cycle` (the old branch). The authority is the spec, `combat-formulas.md`, and the user rulings in the roadmap.
- Ruling 2: the stage event table, the chance steps, and the support charges stay out. `init` stores `events` unread. No code resets `ChanceSteps`, `SupportDefendCharges` or `SupportAttackCharges` at a phase start.
- Ruling 5: EN regeneration is `ENMax * 10 / 100` in integer arithmetic (floor), capped at `ENMax`.
- Ruling 6: the engine refuses nothing on a finished board. The summary field `gone` names the sides with no living unit.
- Ruling 7: the page starts through `load` plus a seed; `init` lands per spec and is tested in Go only.
- One term for one concept (CLAUDE.md). Wire values stay `forced` and `sampled`; the prose terms are `manual roll` and `server draw` (terminology-map.md lines 85-86); the Go types are `ManualRoll` and `ServerDraw`. The existing `Forced` (node-keyed) stays for the differential `apply` op and is not a wire type.
- Comments: only a why-comment for a decision that looks wrong, or a warning for a special case. No flow comments, no history.
- Commit rules of CLAUDE.md; the hook `scripts/check_commit_msg.py` runs on every commit (`git config core.hooksPath .githooks` once in the worktree).
- Gates before every code commit: from `engine/`, `go vet ./...` and `go test ./...`; from the worktree root, `uv run pytest -q` and `uv run ruff check src tests scripts`. Run the gates in a subagent when they take long (0826 instruction); a docs-only commit skips them.
- Every wire change raises the protocol version once, to `1.3`, in `engine/protocol/envelope.go` and `src/ggge_ai/engine/contract.py` (Task 1 does it; no other task touches the version).
- Working directory of every command below: `/home/poyu/workspace/project/ggge_ai-worktrees/issue-65-turn-cycle-v2` (Go commands from its `engine/` subdirectory).

## Assumption stated for the user

"The web UI plays a battle end to end through the engine" cannot mean the full command flow in this branch: issue #78 owns the rebuild of `EngineSession.pending_decision`, `EngineSession.reaction_options`, and the page command menu on the reporting contract, and the page today builds a `reactions` request of the retired shape (`src/ggge_ai/engine/session.py:94-109`). This plan delivers: the page loads with a seed, posts every ally activation to `act` against the built binary, follows the rotation into the enemy phase, and shows the end of the battle from `gone`. The attack path through the page waits for #78. The Go tests and a Python test against the binary play battles to annihilation without the page.

## File map

| File | Responsibility |
|---|---|
| `engine/protocol/types.go` | Wire shapes: terrain of `init`, typed `act` answer, `BoardSummary`, `HistoryEntry`, seed of `export` and `load` |
| `engine/protocol/envelope.go` | `Version = "1.3"` |
| `engine/battle/dice.go` | `ManualRoll`, `ServerDraw` beside `Forced` |
| `engine/battle/rules.go` | `ENRegenPercent` replaces the unused `ENRegenFraction` |
| `engine/battle/clone.go` | `Board.Clone`, `Unit.Clone` |
| `engine/battle/turn.go` | `Board.Act`, `Board.Advance`, `Board.Pending`, `Board.Gone`, the phase start |
| `engine/battle/codec.go` | `DecodeInit`, `EncodeState`, `DecodeOutcomes`, `EncodeResolution`, `EncodeSummary` |
| `engine/server/session.go` | the session fields, `load` with the seed, `export` |
| `engine/server/init.go` | the `init` handler |
| `engine/server/act.go` | the `act` handler |
| `engine/differential/turn_test.go` | the `act` op of the hand-derived fixtures |
| `tests/fixtures/engine/turn_cycle_board.json`, `turn_pending_board.json` | hand-derived cases |
| `src/ggge_ai/engine/contract.py` | `PROTOCOL_VERSION = "1.3"` |
| `src/ggge_ai/engine/session.py` | the seed of `load` |
| `src/ggge_ai/engine/fake.py` | the summary shape, the seed |
| `scripts/sandbox_ui.py` | `--seed`, the end of the battle on the page |
| `tests/test_engine_turn.py` | the battle against the built binary |
| `tests/test_sandbox_ui.py`, `tests/test_engine_client.py` | seed, `gone`, the implemented set |
| `docs/spec/battle-engine-protocol.md`, `docs/reference/terminology-map.md` | the contract text |

---

### Task 1: Protocol 1.3

**Files:**
- Modify: `engine/protocol/types.go:64-67` (Board), `:224-227` (ActResponse), `:229-239` (history entry), `:267-279` (export, load)
- Modify: `engine/protocol/envelope.go:7`
- Modify: `src/ggge_ai/engine/contract.py:13`
- Test: `engine/protocol/state_test.go` (existing tests keep passing), `tests/test_engine_client.py:48` (reads `PROTOCOL_VERSION`)

**Interfaces:**
- Produces: `protocol.Board{Width, Height, Terrain string "terrain,omitempty", TerrainCells []TerrainCell "terrain_cells,omitempty"}`; `protocol.StrikeEvent`; `protocol.PhaseEvent`; `protocol.BoardSummary{Turn int, Phase Faction, Pending []string, Gone []Faction}`; `protocol.ActResponse{Events []any, Board BoardSummary}`; `protocol.HistoryEntry{Cmd string, Payload json.RawMessage}`; `protocol.ExportResponse{State, History []HistoryEntry, Seed int64}`; `protocol.LoadRequest{State, History []HistoryEntry, Seed int64}`; `protocol.Version == "1.3"`.

- [ ] **Step 1: Edit the types**

Replace the `Board` struct:

```go
type Board struct {
	Width        int           `json:"width"`
	Height       int           `json:"height"`
	Terrain      string        `json:"terrain,omitempty"`
	TerrainCells []TerrainCell `json:"terrain_cells,omitempty"`
}
```

Replace `ActResponse` and add the event and summary shapes next to it:

```go
// An entry of 'events' is a StrikeEvent or a PhaseEvent; the field 'event'
// tells them apart on the wire.
type StrikeEvent struct {
	Event     string `json:"event"`
	Strike    string `json:"strike"`
	ShooterID string `json:"shooter_id"`
	StruckID  string `json:"struck_id"`
	Weapon    string `json:"weapon"`
	Landed    bool   `json:"landed"`
	Damage    int    `json:"damage"`
	Killed    bool   `json:"killed"`
}

type PhaseEvent struct {
	Event string  `json:"event"`
	Turn  int     `json:"turn"`
	Phase Faction `json:"phase"`
}

type BoardSummary struct {
	Turn    int       `json:"turn"`
	Phase   Faction   `json:"phase"`
	Pending []string  `json:"pending"`
	Gone    []Faction `json:"gone"`
}

type ActResponse struct {
	Events []any        `json:"events"`
	Board  BoardSummary `json:"board"`
}
```

Add `HistoryEntry` above `RollbackRequest`, and make `Undone` an alias of it so `rollback` answers the same shape later:

```go
type HistoryEntry struct {
	Cmd     string          `json:"cmd"`
	Payload json.RawMessage `json:"payload"`
}

type Undone = HistoryEntry
```

Replace the export and load types:

```go
type ExportResponse struct {
	State   BattleState    `json:"state"`
	History []HistoryEntry `json:"history"`
	Seed    int64          `json:"seed"`
}

type LoadRequest struct {
	State   BattleState    `json:"state"`
	History []HistoryEntry `json:"history"`
	Seed    int64          `json:"seed"`
}
```

`RollbackResponse.Board` stays `json.RawMessage`; the rollback issue types it.

- [ ] **Step 2: Raise the version on both sides**

`engine/protocol/envelope.go:7`: `const Version = "1.3"`.
`src/ggge_ai/engine/contract.py:13`: `PROTOCOL_VERSION = "1.3"`.

- [ ] **Step 3: Build and run the Go tests**

Run from `engine/`: `go vet ./... && go test ./...`
Expected: ok for all four packages (no test reads the changed structs yet).

- [ ] **Step 4: Run the Python gates**

Run: `uv run pytest -q tests/test_engine_client.py tests/test_engine_codec.py && uv run ruff check src tests scripts`
Expected: pass. (`test_engine_client` builds the binary with `go build`; it needs `go` on PATH.)

- [ ] **Step 5: Commit**

```bash
git add engine/protocol/types.go engine/protocol/envelope.go src/ggge_ai/engine/contract.py
git commit -m "Carry the turn cycle fields on the wire

The answer of 'act' names its two event shapes and the board summary
with the pending units and the sides that are gone (user ruling
2026-08-27). 'export' and 'load' carry the seed, because a session
that loses the seed answers other numbers than the one that 'export'
read. The board of 'init' carries the terrain, which the spec listed
as the open requirement of the issue that implements 'init'.

Issue #65."
```

---

### Task 2: The two dice of the wire

**Files:**
- Modify: `engine/battle/dice.go` (append), `engine/battle/rules.go:24`
- Create: `engine/battle/dice_test.go`

**Interfaces:**
- Consumes: `battle.Node`, `battle.Dice` (`dice.go:3-16`).
- Produces: `func NewManualRoll(outcomes []bool) *ManualRoll`; `func (m *ManualRoll) Lands(Node, float64) bool`; `func (m *ManualRoll) Short() bool`; `func NewServerDraw(seed int64) *ServerDraw`; `func (d *ServerDraw) Lands(Node, float64) bool`; `func (d *ServerDraw) Clone() *ServerDraw`; `const ENRegenPercent = 10`.

- [ ] **Step 1: Confirm the probability range**

Run from `engine/`: `grep -n "func StrikeHitProbability" -A 12 battle/*.go` and `grep -n "dice.Lands" battle/resolve.go`.
Confirm that `Lands` receives a probability in `[0, 1]` (not a percent). If it receives a percent, `ServerDraw.Lands` must compare against `probability/100`; record which one you found in the roadmap progress log.

- [ ] **Step 2: Write the failing tests**

```go
package battle

import "testing"

func TestManualRollReadsTheOutcomesInOrderAndReportsAShortList(t *testing.T) {
	roll := NewManualRoll([]bool{true, false})

	if !roll.Lands(NodeStrike, 0.5) || roll.Lands(NodeCounter, 0.5) {
		t.Fatal("the two outcomes must come back in order")
	}
	if roll.Short() {
		t.Fatal("two reads of two outcomes are not short")
	}
	if roll.Lands(NodeStrike, 0.5) {
		t.Fatal("a read past the end must miss")
	}
	if !roll.Short() {
		t.Fatal("a read past the end must mark the roll short")
	}
}

func TestOneSeedGivesOneSequence(t *testing.T) {
	first, second := NewServerDraw(42), NewServerDraw(42)
	for i := 0; i < 64; i++ {
		if first.Lands(NodeStrike, 0.5) != second.Lands(NodeStrike, 0.5) {
			t.Fatalf("draw %d differs", i)
		}
	}
}

func TestTheDrawFollowsTheProbability(t *testing.T) {
	draw := NewServerDraw(7)
	if draw.Lands(NodeStrike, 0) {
		t.Fatal("probability 0 must miss")
	}
	if !draw.Lands(NodeStrike, 1) {
		t.Fatal("probability 1 must land")
	}
}

func TestACloneContinuesFromTheSamePlace(t *testing.T) {
	draw := NewServerDraw(3)
	draw.Lands(NodeStrike, 0.5)
	clone := draw.Clone()
	for i := 0; i < 32; i++ {
		if draw.Lands(NodeStrike, 0.5) != clone.Lands(NodeStrike, 0.5) {
			t.Fatalf("draw %d differs after the clone", i)
		}
	}
}

func TestACloneDoesNotMoveTheOriginal(t *testing.T) {
	draw := NewServerDraw(3)
	clone := draw.Clone()
	var fromClone, fromOriginal []bool
	for i := 0; i < 16; i++ {
		fromClone = append(fromClone, clone.Lands(NodeStrike, 0.5))
	}
	for i := 0; i < 16; i++ {
		fromOriginal = append(fromOriginal, draw.Lands(NodeStrike, 0.5))
	}
	for i := range fromClone {
		if fromClone[i] != fromOriginal[i] {
			t.Fatalf("draw %d: the original moved with the clone", i)
		}
	}
}
```

- [ ] **Step 3: Run the tests to see them fail**

Run from `engine/`: `go test ./battle/ -run 'ManualRoll|Seed|Draw|Clone'`
Expected: compile error, `NewManualRoll` undefined.

- [ ] **Step 4: Implement**

Append to `engine/battle/dice.go`:

```go
import "math/rand/v2"

type ManualRoll struct {
	outcomes []bool
	next     int
	short    bool
}

func NewManualRoll(outcomes []bool) *ManualRoll {
	return &ManualRoll{outcomes: outcomes}
}

func (m *ManualRoll) Lands(_ Node, _ float64) bool {
	if m.next >= len(m.outcomes) {
		m.short = true
		return false
	}
	landed := m.outcomes[m.next]
	m.next++
	return landed
}

func (m *ManualRoll) Short() bool {
	return m.short
}

type ServerDraw struct {
	source *rand.PCG
}

func NewServerDraw(seed int64) *ServerDraw {
	return &ServerDraw{source: rand.NewPCG(uint64(seed), 0)}
}

func (d *ServerDraw) Lands(_ Node, probability float64) bool {
	return rand.New(d.source).Float64() < probability
}

func (d *ServerDraw) Clone() *ServerDraw {
	state, err := d.source.MarshalBinary()
	if err != nil {
		panic(err)
	}
	source := rand.NewPCG(0, 0)
	if err := source.UnmarshalBinary(state); err != nil {
		panic(err)
	}
	return &ServerDraw{source: source}
}
```

(Move the `import` to the top of the file with the package clause.) `rand.PCG.MarshalBinary` never fails on a valid source; the panic marks a programming error, not a runtime condition.

In `engine/battle/rules.go`, replace `ENRegenFraction     = 0.10` with `ENRegenPercent      = 10`. Nothing reads the old name (`grep -rn ENRegenFraction engine/` must be empty after the edit).

- [ ] **Step 5: Run the tests**

Run from `engine/`: `go vet ./... && go test ./battle/`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/battle/dice.go engine/battle/dice_test.go engine/battle/rules.go
git commit -m "Add the manual roll and the server draw

The wire offers two dice inputs and the engine held only the
node-keyed 'Forced' of the fixtures. The manual roll reads the
'outcomes' list in the resolution order and reports a short list,
so the command can refuse after the run. The server draw reads one
PCG source that the seed builds, and its clone continues from the
same place, so a refused activation leaves the stream where it was.
The regeneration rule becomes an integer percent so the floor of
the user ruling of 2026-08-27 is exact integer arithmetic.

Issue #65."
```

---

### Task 3: A clone of the board

**Files:**
- Create: `engine/battle/clone.go`, `engine/battle/clone_test.go`
- Read: `engine/battle/model.go:113-179` (Debuff, Skill, Pilot, Mech, Unit), `:245-252` (Board)

**Interfaces:**
- Produces: `func (b *Board) Clone() *Board`; `func (u Unit) Clone() Unit`.

- [ ] **Step 1: Read the pointer fields**

Run from `engine/`: `sed -n 113,180p battle/model.go`. List every slice, map, and pointer inside `Unit`, `Skill`, `Mech`, `Weapon`. `Skill.Amount` is a `*float64` if the struct holds one; `cloneAmount` (`model.go:222`) copies it.

- [ ] **Step 2: Write the failing test**

```go
package battle

import "testing"

func TestACloneSharesNothingWithTheBoard(t *testing.T) {
	board, err := NewBoard(Bounds{High: Cell{4, 4}}, []Unit{{
		ID: "a1", Faction: FactionAlly, HP: 10, MaxHP: 10, EN: 5, ENMax: 5,
		Weapons: []Weapon{{Name: "w"}},
		Ammo:    map[string]int{"w": 3},
		Debuffs: []Debuff{{Kind: "defense", Magnitude: 0.1, AppliedPhase: 3}},
		Mech:    Mech{Weapons: []Weapon{{Name: "base"}}},
	}})
	if err != nil {
		t.Fatal(err)
	}
	board.TerrainCells = map[Cell]Terrain{{1, 1}: TerrainGround}
	board.Phase = FactionAlly

	clone := board.Clone()
	clone.Units[0].HP = 1
	clone.Units[0].Weapons[0].Name = "changed"
	clone.Units[0].Ammo["w"] = 0
	clone.Units[0].Debuffs[0].Kind = "changed"
	clone.Units[0].Mech.Weapons[0].Name = "changed"
	clone.TerrainCells[Cell{1, 1}] = TerrainSpace
	clone.Phase = FactionEnemy

	unit := board.Units[0]
	if unit.HP != 10 || unit.Weapons[0].Name != "w" || unit.Ammo["w"] != 3 ||
		unit.Debuffs[0].Kind != "defense" || unit.Mech.Weapons[0].Name != "base" {
		t.Fatalf("the board changed with its clone: %+v", unit)
	}
	if board.TerrainCells[Cell{1, 1}] != TerrainGround || board.Phase != FactionAlly {
		t.Fatalf("the board fields changed with the clone")
	}
}
```

Use the terrain constant names that `engine/battle/terrain.go` defines (check with `grep -n "Terrain = " battle/terrain.go`).

- [ ] **Step 3: Run the test to see it fail**

Run from `engine/`: `go test ./battle/ -run ACloneSharesNothing`
Expected: compile error, `Clone` undefined.

- [ ] **Step 4: Implement**

```go
package battle

import (
	"maps"
	"slices"
)

func (b *Board) Clone() *Board {
	out := *b
	out.Units = make([]Unit, len(b.Units))
	for index := range b.Units {
		out.Units[index] = b.Units[index].Clone()
	}
	out.TerrainCells = maps.Clone(b.TerrainCells)
	return &out
}

func (u Unit) Clone() Unit {
	u.Weapons = slices.Clone(u.Weapons)
	u.Skills = slices.Clone(u.Skills)
	for index := range u.Skills {
		u.Skills[index].Amount = cloneAmount(u.Skills[index].Amount)
	}
	u.Debuffs = slices.Clone(u.Debuffs)
	u.Ammo = maps.Clone(u.Ammo)
	u.Mech.Weapons = slices.Clone(u.Mech.Weapons)
	return u
}
```

Drop the `Skills` loop if `Skill` holds no pointer field. Add a line for any other pointer the read of Step 1 found.

- [ ] **Step 5: Run the tests**

Run from `engine/`: `go vet ./... && go test ./battle/`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/battle/clone.go engine/battle/clone_test.go
git commit -m "Clone a board with every slice and map of its units

The command 'act' runs on a copy and installs it when the whole run
succeeds, so a refusal changes no board. A shallow copy would share
the weapons, the ammo, the debuffs and the terrain cells with the
board, and a refused run would write into them.

Issue #65."
```

---

### Task 4: The turn cycle

**Files:**
- Create: `engine/battle/turn.go`, `engine/battle/turn_test.go`
- Read: `engine/battle/model.go:268-277` (PhaseOrder, PhaseIndex), `:340-353` (ByFaction), `engine/battle/resolve.go:41-52` (Apply)

**Interfaces:**
- Consumes: `Board.Apply(Decision, Dice) (Trace, error)`; `PhaseOrder`; `Board.PhaseIndex()`; `Board.ByFaction(Faction) []*Unit`; `ENRegenPercent`.
- Produces: `type Rotation struct{Turn int; Phase Faction}`; `type Resolution struct{Trace Trace; Rotations []Rotation}`; `func (b *Board) Act(Decision, Dice) (Resolution, error)`; `func (b *Board) Advance() []Rotation`; `func (b *Board) Pending(Faction) []*Unit`; `func (b *Board) Gone() []Faction`.

Rules, from the sources:

- Rotation: `PhaseOrder` is ally, third_party, enemy (`model.go:268`). After an activation, while the faction of the phase holds no pending unit, the phase moves to the next entry; the move from enemy to ally adds one to `Turn`. A board with no living unit does not rotate (no rotation would end).
- Pending unit: alive, of the faction, `Acted` false.
- Phase start (every rotation lands on one): every living unit of the faction gets `Acted = false` and `EN = min(ENMax, EN + ENMax*ENRegenPercent/100)` (combat-formulas.md:191-195, floor per ruling 5). Every living unit of every faction drops the debuffs whose `AppliedPhase + len(PhaseOrder) <= PhaseIndex()` (combat-formulas.md:269-273: one full round; hung at index p, gone when index p+3 begins).
- Not in scope (ruling 2): the chance steps, the support charges, the stage events.

- [ ] **Step 1: Write the failing tests**

```go
package battle

import (
	"reflect"
	"testing"
)

func turnBoard(t *testing.T, phase Faction, turn int, units ...Unit) *Board {
	t.Helper()
	board, err := NewBoard(Bounds{High: Cell{5, 4}}, units)
	if err != nil {
		t.Fatal(err)
	}
	board.Phase = phase
	board.Turn = turn
	return board
}

func unit(id string, faction Faction, x, y int) Unit {
	return Unit{
		ID: id, Faction: faction, Footprint: Footprint{Anchor: Cell{x, y}, Size: Size{1, 1}},
		HP: 100, MaxHP: 100, EN: 100, ENMax: 140, MoveRange: 1,
	}
}

func standby(id string) Decision {
	return Decision{UnitID: id, Kind: ActionStandby}
}

func TestPendingHoldsTheLivingUnitsOfTheSideThatDidNotAct(t *testing.T) {
	acted := unit("a2", FactionAlly, 1, 2)
	acted.Acted = true
	dead := unit("a3", FactionAlly, 1, 3)
	dead.HP = 0
	board := turnBoard(t, FactionAlly, 1, unit("a1", FactionAlly, 1, 1), acted, dead, unit("e1", FactionEnemy, 4, 4))

	var ids []string
	for _, pending := range board.Pending(FactionAlly) {
		ids = append(ids, pending.ID)
	}
	if !reflect.DeepEqual(ids, []string{"a1"}) {
		t.Fatalf("pending: %v", ids)
	}
}

func TestAnActivationWithAPendingSiblingDoesNotRotate(t *testing.T) {
	board := turnBoard(t, FactionAlly, 1, unit("a1", FactionAlly, 1, 1), unit("a2", FactionAlly, 1, 2), unit("e1", FactionEnemy, 4, 4))

	resolution, err := board.Act(standby("a1"), NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	if len(resolution.Rotations) != 0 || board.Phase != FactionAlly || board.Turn != 1 {
		t.Fatalf("rotated: %+v turn %d phase %s", resolution.Rotations, board.Turn, board.Phase)
	}
}

func TestTheLastActivationOfTheAllySideOpensTheEnemyPhase(t *testing.T) {
	board := turnBoard(t, FactionAlly, 1, unit("a1", FactionAlly, 1, 1), unit("e1", FactionEnemy, 4, 4))

	resolution, err := board.Act(standby("a1"), NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	want := []Rotation{{Turn: 1, Phase: FactionThirdParty}, {Turn: 1, Phase: FactionEnemy}}
	if !reflect.DeepEqual(resolution.Rotations, want) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	if board.Phase != FactionEnemy || board.Turn != 1 {
		t.Fatalf("turn %d phase %s", board.Turn, board.Phase)
	}
}

func TestTheLastActivationOfTheEnemySideOpensTheNextTurn(t *testing.T) {
	ally := unit("a1", FactionAlly, 1, 1)
	ally.Acted = true
	ally.EN = 130
	board := turnBoard(t, FactionEnemy, 1, ally, unit("e1", FactionEnemy, 4, 4))

	resolution, err := board.Act(standby("e1"), NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(resolution.Rotations, []Rotation{{Turn: 2, Phase: FactionAlly}}) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	got := board.Unit("a1")
	if got.Acted || got.EN != 140 {
		t.Fatalf("the phase start must reset the activation and cap the regeneration: %+v", got)
	}
	if enemy := board.Unit("e1"); !enemy.Acted || enemy.EN != 100 {
		t.Fatalf("the enemy side must keep its state until its own phase start: %+v", enemy)
	}
}

func TestThePhaseStartRegeneratesTenPercentOfTheMaximumFloored(t *testing.T) {
	ally := unit("a1", FactionAlly, 1, 1)
	ally.Acted = true
	ally.EN, ally.ENMax = 10, 513
	board := turnBoard(t, FactionEnemy, 1, ally, unit("e1", FactionEnemy, 4, 4))

	if _, err := board.Act(standby("e1"), NewManualRoll(nil)); err != nil {
		t.Fatal(err)
	}
	if got := board.Unit("a1").EN; got != 61 {
		t.Fatalf("EN: %d, want 10 + floor(51.3)", got)
	}
}

func TestADebuffExpiresWhenItsRoundEnds(t *testing.T) {
	ally := unit("a1", FactionAlly, 1, 1)
	ally.Acted = true
	ally.Debuffs = []Debuff{
		{Kind: "defense", Magnitude: 0.1, AppliedPhase: 3},
		{Kind: "attack", Magnitude: 0.2, AppliedPhase: 4},
	}
	enemy := unit("e1", FactionEnemy, 4, 4)
	enemy.Debuffs = []Debuff{{Kind: "defense", Magnitude: 0.3, AppliedPhase: 3}}
	board := turnBoard(t, FactionEnemy, 1, ally, enemy)

	if _, err := board.Act(standby("e1"), NewManualRoll(nil)); err != nil {
		t.Fatal(err)
	}
	if got := board.Unit("a1").Debuffs; !reflect.DeepEqual(got, []Debuff{{Kind: "attack", Magnitude: 0.2, AppliedPhase: 4}}) {
		t.Fatalf("ally debuffs at index 6: %+v", got)
	}
	if got := board.Unit("e1").Debuffs; len(got) != 0 {
		t.Fatalf("the expiry reads every side: %+v", got)
	}
}

func TestASideWithNoUnitIsSkipped(t *testing.T) {
	board := turnBoard(t, FactionEnemy, 2, unit("e1", FactionEnemy, 4, 4))

	resolution, err := board.Act(standby("e1"), NewManualRoll(nil))
	if err != nil {
		t.Fatal(err)
	}
	want := []Rotation{{Turn: 3, Phase: FactionAlly}, {Turn: 3, Phase: FactionThirdParty}, {Turn: 3, Phase: FactionEnemy}}
	if !reflect.DeepEqual(resolution.Rotations, want) {
		t.Fatalf("rotations: %+v", resolution.Rotations)
	}
	if board.Unit("e1").Acted {
		t.Fatal("the enemy phase start must give the unit its activation back")
	}
}

func TestGoneNamesTheSidesWithNoLivingUnit(t *testing.T) {
	dead := unit("e1", FactionEnemy, 4, 4)
	dead.HP = 0
	board := turnBoard(t, FactionAlly, 1, unit("a1", FactionAlly, 1, 1), dead)

	if got := board.Gone(); !reflect.DeepEqual(got, []Faction{FactionEnemy}) {
		t.Fatalf("gone: %v", got)
	}
	board.Unit("a1").HP = 0
	if got := board.Gone(); !reflect.DeepEqual(got, []Faction{FactionAlly, FactionEnemy}) {
		t.Fatalf("gone: %v", got)
	}
}

func TestABoardWithNoLivingUnitDoesNotRotate(t *testing.T) {
	last := unit("a1", FactionAlly, 1, 1)
	board := turnBoard(t, FactionAlly, 1, last)
	board.Unit("a1").HP = 0

	if got := board.Advance(); len(got) != 0 || board.Phase != FactionAlly || board.Turn != 1 {
		t.Fatalf("rotated on a dead board: %+v", got)
	}
}

func TestARefusedActivationChangesNothing(t *testing.T) {
	board := turnBoard(t, FactionAlly, 1, unit("a1", FactionAlly, 1, 1), unit("e1", FactionEnemy, 4, 4))

	if _, err := board.Act(standby("e1"), NewManualRoll(nil)); err == nil {
		t.Fatal("an enemy unit cannot act in the ally phase")
	}
	if board.Phase != FactionAlly || board.Unit("a1").Acted {
		t.Fatal("the board changed on a refusal")
	}
}
```

Add one battle to annihilation with forced hits. Read `engine/battle/resolve_test.go` for a helper that builds two units with a weapon in range of each other, and reuse its unit builder if one exists; otherwise build the two units with one weapon each (`Weapon{Name: "gun", Power: 5000, Range: RadiusRange{1, 3}, Accuracy: 100, CanCounter: true, UsableAfterMove: true}`) and the panel values of `tests/fixtures/engine/small_board.json` (`unit_attack` 4200, `unit_defense` 3900, `pilot_attack` 220, `pilot_defense` 190, `reaction` 205, `mobility` 310):

```go
func TestABattleRunsToAnnihilation(t *testing.T) {
	board := turnBoard(t, FactionAlly, 1, armed("a1", FactionAlly, 1, 1), armed("a2", FactionAlly, 1, 2), armed("e1", FactionEnemy, 2, 1))
	dice := Forced{AttackerSupport: true, DefenderSupport: true, Strike: true, Counter: true}

	for acts := 0; len(board.Gone()) == 0; acts++ {
		if acts > 100 {
			t.Fatal("no side is gone after 100 activations")
		}
		pending := board.Pending(board.Phase)
		actor := pending[0]
		targets := board.TargetsOf(actor)
		decision := standby(actor.ID)
		if len(targets) > 0 {
			decision = Decision{UnitID: actor.ID, Kind: ActionAttack, TargetID: targets[0].ID, Weapon: "gun",
				Reaction: &Reaction{Stance: StanceNone}}
		}
		if _, err := board.Act(decision, dice); err != nil {
			t.Fatalf("act %d: %v", acts, err)
		}
	}
}
```

`armed` is a test helper in the same file that returns `unit(...)` with the weapon and the panel values set. Check the field names of the panel in `Unit` (`model.go:155-179`: `Pilot.Attack`, `Mech.Attack`, or a flat field) and set them where `StrikeHitProbability` and the damage read them; the test needs a hit rate above zero and a damage above zero, nothing else. If `TargetsOf` filters by range, the units must stand within range 1-3; the cells above do.

- [ ] **Step 2: Run the tests to see them fail**

Run from `engine/`: `go test ./battle/ -run 'Pending|Rotate|Opens|Regenerates|Expires|Skipped|Gone|Annihilation|Refused'`
Expected: compile error, `Act` and `Pending` undefined.

- [ ] **Step 3: Implement**

`engine/battle/turn.go`:

```go
package battle

type Rotation struct {
	Turn  int
	Phase Faction
}

type Resolution struct {
	Trace     Trace
	Rotations []Rotation
}

func (b *Board) Act(decision Decision, dice Dice) (Resolution, error) {
	trace, err := b.Apply(decision, dice)
	if err != nil {
		return Resolution{}, err
	}
	return Resolution{Trace: trace, Rotations: b.Advance()}, nil
}

func (b *Board) Pending(faction Faction) []*Unit {
	var out []*Unit
	for index := range b.Units {
		unit := &b.Units[index]
		if unit.Faction == faction && unit.Alive() && !unit.Acted {
			out = append(out, unit)
		}
	}
	return out
}

// A board with no living unit keeps its phase: every side would stay empty,
// and the rotation would never end.
func (b *Board) Advance() []Rotation {
	if !b.anyAlive() {
		return nil
	}
	var out []Rotation
	for len(b.Pending(b.Phase)) == 0 {
		out = append(out, b.nextPhase())
	}
	return out
}

func (b *Board) nextPhase() Rotation {
	slot := (b.PhaseIndex() - b.Turn*len(PhaseOrder) + 1) % len(PhaseOrder)
	if slot == 0 {
		b.Turn++
	}
	b.Phase = PhaseOrder[slot]
	b.beginPhase()
	return Rotation{Turn: b.Turn, Phase: b.Phase}
}

func (b *Board) beginPhase() {
	now := b.PhaseIndex()
	for index := range b.Units {
		unit := &b.Units[index]
		if !unit.Alive() {
			continue
		}
		unit.Debuffs = expired(unit.Debuffs, now)
		if unit.Faction != b.Phase {
			continue
		}
		unit.Acted = false
		unit.EN = min(unit.ENMax, unit.EN+unit.ENMax*ENRegenPercent/100)
	}
}

func expired(debuffs []Debuff, now int) []Debuff {
	kept := debuffs[:0]
	for _, debuff := range debuffs {
		if debuff.AppliedPhase+len(PhaseOrder) > now {
			kept = append(kept, debuff)
		}
	}
	return kept
}

func (b *Board) anyAlive() bool {
	for index := range b.Units {
		if b.Units[index].Alive() {
			return true
		}
	}
	return false
}

func (b *Board) Gone() []Faction {
	var out []Faction
	for _, faction := range []Faction{FactionAlly, FactionEnemy} {
		if len(b.ByFaction(faction)) == 0 {
			out = append(out, faction)
		}
	}
	return out
}
```

- [ ] **Step 4: Run the tests**

Run from `engine/`: `go vet ./... && go test ./battle/ -race`
Expected: PASS. If `TestABattleRunsToAnnihilation` fails on legality, read the error message: the helper must satisfy `Board.Apply` (weapon in range, EN for the weapon, a reaction that the stance rules accept). Do not weaken the assertion.

- [ ] **Step 5: Commit**

```bash
git add engine/battle/turn.go engine/battle/turn_test.go
git commit -m "Run the turn cycle after one activation

The engine resolved one engagement and stopped. The phase now moves
while the side to act holds no pending unit, and the move from the
enemy side to the ally side opens the next turn. The phase start
gives the side its activations back and one tenth of the maximum
EN, floored (user ruling 2026-08-27, combat-formulas.md line 191),
and drops the debuffs of one full round on every side
(combat-formulas.md line 269). A board with no living unit keeps
its phase, because no rotation would end.

The chance steps, the support charges and the stage events wait for
the issue that gives them a shape (user ruling 2026-08-27).

Issue #65."
```

---

### Task 5: The codec of the new commands

**Files:**
- Modify: `engine/battle/codec.go` (append), `engine/battle/codec_test.go` (append)
- Read: `engine/protocol/state.go:247-256` (BattleState field types), `engine/battle/codec.go:9-71` (the enum maps), `:105-120` (decodeTerrain, decodeTerrainCells), `:616-621` (decodeBounds)

**Interfaces:**
- Consumes: `decodeUnits`, `NewBoard`, `decodeTerrain`, `decodeTerrainCells`, `EncodeUnits`, `EncodeCell`, `wireFactions`, `factions`; Task 4's `Resolution`, `Board.Pending`, `Board.Gone`; Task 1's protocol types.
- Produces: `func DecodeInit(*protocol.InitRequest) (*Board, error)`; `func EncodeState(*Board) protocol.BattleState`; `func DecodeOutcomes([]string) ([]bool, error)`; `func EncodeResolution(Resolution) []any`; `func EncodeSummary(*Board) protocol.BoardSummary`.

- [ ] **Step 1: Read the state field types and the terrain maps**

Run from `engine/`: `sed -n 240,260p protocol/state.go; sed -n 100,125p battle/codec.go; grep -n "terrains\|wireTerrains" battle/*.go`.
Note the type of `BattleState.Terrain` (a string or a pointer) and of `PendingEvents`; note whether an encode map for terrain exists. If none exists, build `wireTerrains` as the inverse of the decode map in the same `var` block that holds the other encode maps.

- [ ] **Step 2: Write the failing tests**

Append to `engine/battle/codec_test.go` (it is `package battle`; check the first line and the helper names it already holds, and reuse a state builder if one exists):

```go
func TestInitBuildsTheBoardOfTheEnemiesAtTurnOne(t *testing.T) {
	request := protocol.InitRequest{
		Board:   protocol.Board{Width: 6, Height: 5, Terrain: "ground", TerrainCells: []protocol.TerrainCell{{Cell: protocol.Cell{1, 1}, Terrain: "space"}}},
		Enemies: []protocol.Unit{{UnitID: "e1", Faction: protocol.FactionEnemy, Pos: protocol.Cell{4, 4}, HP: 10}},
		Seed:    9,
	}

	board, err := DecodeInit(&request)
	if err != nil {
		t.Fatal(err)
	}
	if board.Turn != 1 || board.Phase != FactionAlly {
		t.Fatalf("turn %d phase %s", board.Turn, board.Phase)
	}
	if board.Bounds != (Bounds{High: Cell{5, 4}}) {
		t.Fatalf("bounds: %+v", board.Bounds)
	}
	if board.DefaultTerrain != TerrainGround || board.TerrainCells[Cell{1, 1}] != TerrainSpace {
		t.Fatalf("terrain: %v %v", board.DefaultTerrain, board.TerrainCells)
	}
	if len(board.Units) != 1 || board.Units[0].ID != "e1" {
		t.Fatalf("units: %+v", board.Units)
	}
}

func TestInitRefusesABoardWithNoCell(t *testing.T) {
	if _, err := DecodeInit(&protocol.InitRequest{Board: protocol.Board{Width: 0, Height: 5}}); err == nil {
		t.Fatal("a width of 0 must fail")
	}
}

func TestEncodeStateRoundTripsThroughDecodeState(t *testing.T) {
	first := decodeFixtureState(t) // a helper that reads tests/fixtures/engine/debuff_ammo_board.json setup.state and calls DecodeState
	encoded := EncodeState(first)
	second, err := DecodeState(&encoded)
	if err != nil {
		t.Fatal(err)
	}
	again := EncodeState(second)
	a, _ := json.Marshal(encoded)
	b, _ := json.Marshal(again)
	if string(a) != string(b) {
		t.Fatalf("the second encode differs:\n%s\n%s", a, b)
	}
	if encoded.Turn != first.Turn || encoded.Phase != wireFactions[first.Phase] || encoded.Bounds == nil {
		t.Fatalf("state: %+v", encoded)
	}
}

func TestOutcomesReadHitAndMissOnly(t *testing.T) {
	got, err := DecodeOutcomes([]string{"hit", "miss", "hit"})
	if err != nil || !reflect.DeepEqual(got, []bool{true, false, true}) {
		t.Fatalf("%v %v", got, err)
	}
	if _, err := DecodeOutcomes([]string{"true"}); err == nil {
		t.Fatal("an outcome outside the two labels must fail")
	}
}

func TestTheResolutionEncodesStrikesThenRotations(t *testing.T) {
	events := EncodeResolution(Resolution{
		Trace:     Trace{{Kind: StrikeMain, ShooterID: "a1", StruckID: "e1", Weapon: "gun", Landed: true, Damage: 7, Killed: true}},
		Rotations: []Rotation{{Turn: 1, Phase: FactionEnemy}},
	})
	want := []any{
		protocol.StrikeEvent{Event: "strike", Strike: "strike", ShooterID: "a1", StruckID: "e1", Weapon: "gun", Landed: true, Damage: 7, Killed: true},
		protocol.PhaseEvent{Event: "phase", Turn: 1, Phase: protocol.FactionEnemy},
	}
	if !reflect.DeepEqual(events, want) {
		t.Fatalf("events: %+v", events)
	}
}

func TestTheSummaryNamesThePendingUnitsAndTheGoneSides(t *testing.T) {
	board := decodeFixtureState(t)
	for index := range board.Units {
		if board.Units[index].Faction == FactionEnemy {
			board.Units[index].HP = 0
		}
	}
	summary := EncodeSummary(board)
	if summary.Turn != board.Turn || summary.Phase != wireFactions[board.Phase] {
		t.Fatalf("summary: %+v", summary)
	}
	if !reflect.DeepEqual(summary.Gone, []protocol.Faction{protocol.FactionEnemy}) {
		t.Fatalf("gone: %v", summary.Gone)
	}
	if len(summary.Pending) == 0 {
		t.Fatal("the pending list must name the ally units that did not act")
	}
}
```

Write `decodeFixtureState` in the test file: `os.ReadFile("../../tests/fixtures/engine/debuff_ammo_board.json")`, unmarshal into `struct{ Setup struct{ State protocol.BattleState } }`, and `DecodeState`. Check first whether `codec_test.go` already holds a fixture reader and reuse it.

- [ ] **Step 3: Run the tests to see them fail**

Run from `engine/`: `go test ./battle/ -run 'Init|EncodeState|Outcomes|Resolution|Summary'`
Expected: compile error on the five undefined names.

- [ ] **Step 4: Implement**

Append to `engine/battle/codec.go`:

```go
func DecodeInit(request *protocol.InitRequest) (*Board, error) {
	if request.Board.Width < 1 || request.Board.Height < 1 {
		return nil, fmt.Errorf("the board %dx%d holds no cell", request.Board.Width, request.Board.Height)
	}
	units, err := decodeUnits(request.Enemies)
	if err != nil {
		return nil, err
	}
	bounds := Bounds{High: Cell{request.Board.Width - 1, request.Board.Height - 1}}
	board, err := NewBoard(bounds, units)
	if err != nil {
		return nil, err
	}
	if board.DefaultTerrain, err = decodeTerrain(request.Board.Terrain); err != nil {
		return nil, err
	}
	if board.TerrainCells, err = decodeTerrainCells(request.Board.TerrainCells); err != nil {
		return nil, err
	}
	board.Phase = FactionAlly
	board.Turn = 1
	return board, nil
}

func EncodeState(board *Board) protocol.BattleState {
	bounds := protocol.Bounds{EncodeCell(board.Bounds.Low), EncodeCell(board.Bounds.High)}
	return protocol.BattleState{
		Units:         EncodeUnits(board.Units),
		Phase:         wireFactions[board.Phase],
		Turn:          board.Turn,
		Bounds:        &bounds,
		PendingEvents: []string{},
		FiredEvents:   []string{},
		Terrain:       wireTerrains[board.DefaultTerrain],
		TerrainCells:  encodeTerrainCells(board.TerrainCells),
	}
}

func encodeTerrainCells(cells map[Cell]Terrain) []protocol.TerrainCell {
	keys := slices.SortedFunc(maps.Keys(cells), func(a, b Cell) int {
		if a[0] != b[0] {
			return a[0] - b[0]
		}
		return a[1] - b[1]
	})
	out := make([]protocol.TerrainCell, 0, len(keys))
	for _, cell := range keys {
		out = append(out, protocol.TerrainCell{Cell: EncodeCell(cell), Terrain: wireTerrains[cells[cell]]})
	}
	return out
}

func DecodeOutcomes(labels []string) ([]bool, error) {
	out := make([]bool, 0, len(labels))
	for index, label := range labels {
		switch label {
		case "hit":
			out = append(out, true)
		case "miss":
			out = append(out, false)
		default:
			return nil, fmt.Errorf("outcome %d is %q, and the contract holds 'hit' and 'miss'", index, label)
		}
	}
	return out, nil
}

func EncodeResolution(resolution Resolution) []any {
	out := make([]any, 0, len(resolution.Trace)+len(resolution.Rotations))
	for _, strike := range resolution.Trace {
		out = append(out, protocol.StrikeEvent{
			Event: "strike", Strike: string(strike.Kind),
			ShooterID: strike.ShooterID, StruckID: strike.StruckID, Weapon: strike.Weapon,
			Landed: strike.Landed, Damage: strike.Damage, Killed: strike.Killed,
		})
	}
	for _, rotation := range resolution.Rotations {
		out = append(out, protocol.PhaseEvent{Event: "phase", Turn: rotation.Turn, Phase: wireFactions[rotation.Phase]})
	}
	return out
}

func EncodeSummary(board *Board) protocol.BoardSummary {
	pending := []string{}
	for _, unit := range board.Pending(board.Phase) {
		pending = append(pending, unit.ID)
	}
	gone := []protocol.Faction{}
	for _, faction := range board.Gone() {
		gone = append(gone, wireFactions[faction])
	}
	return protocol.BoardSummary{Turn: board.Turn, Phase: wireFactions[board.Phase], Pending: pending, Gone: gone}
}
```

Adjust the `Terrain`, `PendingEvents` and `FiredEvents` types to what Step 1 found (a pointer field takes `&name`; an empty `Terrain` name maps to the zero value the decode map treats as the default). Use `TerrainCells: nil` when the map is empty if the round-trip test shows `omitempty` dropping an empty list on one side only.

- [ ] **Step 5: Run the tests**

Run from `engine/`: `go vet ./... && go test ./battle/`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/battle/codec.go engine/battle/codec_test.go
git commit -m "Encode the state, the resolution and the summary

'export' needs the board back on the wire, and no encoder of the
whole state existed: the differential op encoded the unit list
alone. 'init' reads the enemies and the terrain of the map into a
board at turn one, and the answer of 'act' reads the trace and the
rotations into the two event shapes of the contract. The terrain
cells encode in cell order so two encodes of one board give one
byte sequence.

Issue #65."
```

---

### Task 6: The commands init, act, export, and the seed of load

**Files:**
- Modify: `engine/server/session.go`
- Create: `engine/server/init.go`, `engine/server/act.go`, `engine/server/act_test.go`
- Modify: `engine/server/session_test.go` (append), `engine/server/server_test.go:71-74` (the built set)

**Interfaces:**
- Consumes: Task 5's codec functions; Task 2's dice; Task 3's `Board.Clone`; Task 4's `Board.Act`; `battle.DecodeDecision`, `battle.DecodeReaction` (`codec.go:366-411`); the error values `battle.ErrOffPhase`, `battle.ErrActed`, `battle.ErrNoUnit`, `battle.ErrDestroyed`, `battle.ErrIllegalAction`.
- Produces: the handlers `init`, `act`, `export`; the session fields.

- [ ] **Step 1: Read the decoders and the error values**

Run from `engine/`: `sed -n 360,415p battle/codec.go; grep -n "ErrIllegalAction\|ErrNoUnit\|ErrDestroyed\|ErrOffPhase\|ErrActed" battle/*.go | grep -v _test`.
Note the exact signatures of `DecodeDecision` and `DecodeReaction`.

- [ ] **Step 2: Write the failing tests**

`engine/server/act_test.go`:

```go
package server

import (
	"encoding/json"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

const twoSidesLine = `{"id":"l1","cmd":"load","payload":{"seed":5,"state":{` +
	`"units":[` +
	`{"unit_id":"a1","faction":"ally","pos":[1,1],"hp":100,"max_hp":100,"en":100,"en_max":140,"move_range":1},` +
	`{"unit_id":"a2","faction":"ally","pos":[1,2],"hp":100,"max_hp":100,"en":100,"en_max":140,"move_range":1},` +
	`{"unit_id":"e1","faction":"enemy","pos":[4,4],"hp":100,"max_hp":100,"en":100,"en_max":140}` +
	`],"phase":"ally","turn":1,"bounds":[[0,0],[5,4]],` +
	`"pending_events":[],"fired_events":[]},"history":[]}}`

func act(id, unit, kind, dice string) string {
	return `{"id":"` + id + `","cmd":"act","payload":{"unit_id":"` + unit + `","action":{"unit_id":"` + unit +
		`","kind":"` + kind + `"},"dice":` + dice + `}}`
}

func TestActWithNoBoardIsRefused(t *testing.T) {
	replies := serve(t, New(), act("a", "a1", "standby", `{"mode":"sampled"}`))
	if replies[0].OK || replies[0].Error.Code != protocol.CodeNoSession {
		t.Fatalf("reply: %+v", replies[0])
	}
}

func TestAStandbyAnswersNoEventAndThePendingSibling(t *testing.T) {
	replies := serve(t, New(), twoSidesLine, act("a", "a1", "standby", `{"mode":"sampled"}`))
	if !replies[1].OK {
		t.Fatalf("act: %+v", replies[1])
	}
	var answer struct {
		Events []json.RawMessage     `json:"events"`
		Board  protocol.BoardSummary `json:"board"`
	}
	if err := json.Unmarshal(replies[1].Payload, &answer); err != nil {
		t.Fatal(err)
	}
	if len(answer.Events) != 0 || answer.Board.Turn != 1 || answer.Board.Phase != protocol.FactionAlly {
		t.Fatalf("answer: %+v", answer)
	}
	if len(answer.Board.Pending) != 1 || answer.Board.Pending[0] != "a2" || len(answer.Board.Gone) != 0 {
		t.Fatalf("summary: %+v", answer.Board)
	}
}

func TestTheLastActivationRotatesAndTheEventsSayWhere(t *testing.T) {
	replies := serve(t, New(), twoSidesLine,
		act("a", "a1", "standby", `{"mode":"sampled"}`),
		act("b", "a2", "standby", `{"mode":"sampled"}`))
	var answer protocol.ActResponse
	if err := json.Unmarshal(replies[2].Payload, &answer); err != nil {
		t.Fatal(err)
	}
	if answer.Board.Phase != protocol.FactionEnemy || len(answer.Events) != 2 {
		t.Fatalf("answer: %+v", answer)
	}
	last, _ := json.Marshal(answer.Events[1])
	if string(last) != `{"event":"phase","turn":1,"phase":"enemy"}` {
		t.Fatalf("last event: %s", last)
	}
}

func TestAUnitOffPhaseIsIllegalState(t *testing.T) {
	replies := serve(t, New(), twoSidesLine, act("a", "e1", "standby", `{"mode":"sampled"}`))
	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalState {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestAUnitThatActedIsIllegalState(t *testing.T) {
	replies := serve(t, New(), twoSidesLine,
		act("a", "a1", "standby", `{"mode":"sampled"}`),
		act("b", "a1", "standby", `{"mode":"sampled"}`))
	if replies[2].OK || replies[2].Error.Code != protocol.CodeIllegalState {
		t.Fatalf("reply: %+v", replies[2])
	}
}

func TestAReactionOnAStandbyIsIllegalAction(t *testing.T) {
	line := `{"id":"a","cmd":"act","payload":{"unit_id":"a1","action":{"unit_id":"a1","kind":"standby"},` +
		`"reaction":{"stance":"none"},"dice":{"mode":"sampled"}}}`
	replies := serve(t, New(), twoSidesLine, line)
	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestAnAttackWithNoReactionIsIllegalAction(t *testing.T) {
	line := `{"id":"a","cmd":"act","payload":{"unit_id":"a1","action":{"unit_id":"a1","kind":"attack","target_id":"e1","weapon":"gun"},` +
		`"dice":{"mode":"forced","outcomes":["hit"]}}}`
	replies := serve(t, New(), twoSidesLine, line)
	if replies[1].OK || replies[1].Error.Code != protocol.CodeIllegalAction {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestAnOutcomeOutsideTheLabelsIsBadRequest(t *testing.T) {
	replies := serve(t, New(), twoSidesLine, act("a", "a1", "standby", `{"mode":"forced","outcomes":["yes"]}`))
	if replies[1].OK || replies[1].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[1])
	}
}

func TestARefusalLeavesTheBoardAndTheHistory(t *testing.T) {
	replies := serve(t, New(), twoSidesLine,
		act("a", "e1", "standby", `{"mode":"sampled"}`),
		`{"id":"x","cmd":"export","payload":{}}`)
	var export protocol.ExportResponse
	if err := json.Unmarshal(replies[2].Payload, &export); err != nil {
		t.Fatal(err)
	}
	if len(export.History) != 0 || export.State.Phase != protocol.FactionAlly || export.Seed != 5 {
		t.Fatalf("export after a refusal: %+v", export)
	}
}

func TestExportCarriesTheHistoryOfTheActivations(t *testing.T) {
	replies := serve(t, New(), twoSidesLine,
		act("a", "a1", "standby", `{"mode":"sampled"}`),
		`{"id":"x","cmd":"export","payload":{}}`)
	var export protocol.ExportResponse
	if err := json.Unmarshal(replies[2].Payload, &export); err != nil {
		t.Fatal(err)
	}
	if len(export.History) != 1 || export.History[0].Cmd != "act" {
		t.Fatalf("history: %+v", export.History)
	}
	var unit struct {
		UnitID string `json:"unit_id"`
	}
	if err := json.Unmarshal(export.History[0].Payload, &unit); err != nil || unit.UnitID != "a1" {
		t.Fatalf("payload: %s", export.History[0].Payload)
	}
	acted := map[string]bool{}
	for _, one := range export.State.Units {
		acted[one.UnitID] = one.Acted
	}
	if !acted["a1"] || acted["a2"] {
		t.Fatalf("state: %+v", acted)
	}
}

func TestInitOpensTurnOneWithTheEnemies(t *testing.T) {
	line := `{"id":"i","cmd":"init","payload":{"board":{"width":6,"height":5},` +
		`"enemies":[{"unit_id":"e1","faction":"enemy","pos":[4,4],"hp":10}],` +
		`"victory":[{"kind":"destroy_all"}],"events":{},"deploy_cells":[[0,0]],"seed":3}}`
	replies := serve(t, New(), line, `{"id":"x","cmd":"export","payload":{}}`)
	if !replies[0].OK {
		t.Fatalf("init: %+v", replies[0])
	}
	var opened protocol.InitResponse
	if err := json.Unmarshal(replies[0].Payload, &opened); err != nil {
		t.Fatal(err)
	}
	if opened.Turn != 1 || opened.Phase != "ally" || !opened.DeployOpen {
		t.Fatalf("init answer: %+v", opened)
	}
	var export protocol.ExportResponse
	if err := json.Unmarshal(replies[1].Payload, &export); err != nil {
		t.Fatal(err)
	}
	if export.Seed != 3 || len(export.State.Units) != 1 {
		t.Fatalf("export: %+v", export)
	}
}

func TestInitWithABadBoardIsBadRequest(t *testing.T) {
	replies := serve(t, New(), `{"id":"i","cmd":"init","payload":{"board":{"width":0,"height":5},"enemies":[]}}`)
	if replies[0].OK || replies[0].Error.Code != protocol.CodeBadRequest {
		t.Fatalf("reply: %+v", replies[0])
	}
}
```

One more test proves the seed through the command loop with an engagement. Use the setup state of `tests/fixtures/engine/engagement_board.json` and the decision of its first `apply` check whose `decision.kind` is `attack`: read the file in the test, build the `load` line with `"seed":11`, build the `act` line from the check (the `reaction` object of the decision goes into the request field `reaction`; the request `dice` is `{"mode":"sampled"}`), run it in two fresh servers, and assert the two `export` payloads are byte-equal:

```go
func TestOneSeedGivesOneBattleThroughTheCommandLoop(t *testing.T) {
	loadLine, actLine := engagementLines(t, 11)
	first := serve(t, New(), loadLine, actLine, `{"id":"x","cmd":"export","payload":{}}`)
	second := serve(t, New(), loadLine, actLine, `{"id":"x","cmd":"export","payload":{}}`)
	if !first[1].OK {
		t.Fatalf("act: %+v", first[1])
	}
	if string(first[2].Payload) != string(second[2].Payload) {
		t.Fatalf("two runs of one seed differ:\n%s\n%s", first[2].Payload, second[2].Payload)
	}
}
```

Write `engagementLines` in the test file: read `../../tests/fixtures/engine/engagement_board.json`, take `setup.state` and the first check with `op == "apply"` and `input.decision.kind == "attack"`, and marshal the two lines. Note in the roadmap which check it is.

Then the built set of `engine/server/server_test.go:71-74` gains `"init": true, "act": true, "export": true`.

- [ ] **Step 3: Run the tests to see them fail**

Run from `engine/`: `go test ./server/`
Expected: FAIL: `act` and `init` answer `not_implemented`, the hello test fails on the built set.

- [ ] **Step 4: Implement the session and load**

Replace `engine/server/session.go:13-15` and the `load` handler:

```go
type session struct {
	board       *battle.Board
	victory     []protocol.Victory
	events      json.RawMessage
	deployCells []protocol.Cell
	seed        int64
	draw        *battle.ServerDraw
	history     []protocol.HistoryEntry
}

func newSession(board *battle.Board, seed int64) *session {
	return &session{board: board, seed: seed, draw: battle.NewServerDraw(seed), history: []protocol.HistoryEntry{}}
}
```

Register `export` in the same `init()` as `load` and `reach`.

```go
func (s *Server) load(id string, payload json.RawMessage) protocol.Response {
	var request protocol.LoadRequest
	if err := decode(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	board, err := battle.DecodeState(&request.State)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	loaded := newSession(board, request.Seed)
	if request.History != nil {
		loaded.history = request.History
	}
	s.session = loaded
	return protocol.Ok(id, protocol.LoadResponse{})
}

func (s *Server) export(id string, payload json.RawMessage) protocol.Response {
	var request protocol.ExportRequest
	board, fail := boardOf(s, id, payload, &request)
	if fail != nil {
		return *fail
	}
	return protocol.Ok(id, protocol.ExportResponse{
		State:   battle.EncodeState(board),
		History: s.session.history,
		Seed:    s.session.seed,
	})
}
```

- [ ] **Step 5: Implement init**

`engine/server/init.go`:

```go
package server

import (
	"encoding/json"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func init() {
	Register("init", func(s *Server) Handler { return s.initBattle })
}

func (s *Server) initBattle(id string, payload json.RawMessage) protocol.Response {
	var request protocol.InitRequest
	if err := decode(payload, &request); err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	board, err := battle.DecodeInit(&request)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	opened := newSession(board, request.Seed)
	opened.victory = request.Victory
	opened.events = request.Events
	opened.deployCells = request.DeployCells
	s.session = opened
	return protocol.Ok(id, protocol.InitResponse{Turn: board.Turn, Phase: string(protocol.FactionAlly), DeployOpen: true})
}
```

(`init` is a reserved function name in Go; the method is `initBattle`.) The field `rules` of the request is decoded and unread: the engine takes every rule from a constant (`rules.go`).

- [ ] **Step 6: Implement act**

`engine/server/act.go`:

```go
package server

import (
	"encoding/json"
	"errors"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func init() {
	Register("act", func(s *Server) Handler { return s.act })
}

func (s *Server) act(id string, payload json.RawMessage) protocol.Response {
	var request protocol.ActRequest
	board, fail := boardOf(s, id, payload, &request)
	if fail != nil {
		return *fail
	}
	decision, err := activation(&request)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	if (decision.Kind == battle.ActionAttack) != (decision.Reaction != nil) {
		return protocol.Fail(id, protocol.CodeIllegalAction,
			"the reaction is necessary for an attack and not permitted for every other kind")
	}
	dice, manual, err := s.roll(&request.Dice)
	if err != nil {
		return protocol.Fail(id, protocol.CodeBadRequest, err.Error())
	}
	clone := board.Clone()
	resolution, err := clone.Act(decision, dice)
	if err != nil {
		return protocol.Fail(id, refusalCode(err), err.Error())
	}
	if manual != nil && manual.Short() {
		return protocol.Fail(id, protocol.CodeIllegalAction, "the 'outcomes' list is short")
	}
	s.session.board = clone
	if draw, ok := dice.(*battle.ServerDraw); ok {
		s.session.draw = draw
	}
	s.session.history = append(s.session.history, protocol.HistoryEntry{Cmd: "act", Payload: payload})
	return protocol.Ok(id, protocol.ActResponse{
		Events: battle.EncodeResolution(resolution),
		Board:  battle.EncodeSummary(clone),
	})
}

// The request names the unit two times, on the request and on the action.
// The two must agree; an empty action id takes the request id.
func activation(request *protocol.ActRequest) (battle.Decision, error) {
	if request.Action.UnitID == "" {
		request.Action.UnitID = request.UnitID
	}
	if request.Action.UnitID != request.UnitID {
		return battle.Decision{}, errors.New("'unit_id' and 'action.unit_id' name two units")
	}
	decision, err := battle.DecodeDecision(&request.Action)
	if err != nil {
		return battle.Decision{}, err
	}
	if request.Reaction != nil {
		reaction, err := battle.DecodeReaction(request.Reaction)
		if err != nil {
			return battle.Decision{}, err
		}
		decision.Reaction = &reaction
	}
	return decision, nil
}

func (s *Server) roll(dice *protocol.Dice) (battle.Dice, *battle.ManualRoll, error) {
	switch dice.Mode {
	case protocol.DiceForced:
		outcomes, err := battle.DecodeOutcomes(dice.Outcomes)
		if err != nil {
			return nil, nil, err
		}
		manual := battle.NewManualRoll(outcomes)
		return manual, manual, nil
	case protocol.DiceSampled:
		return s.session.draw.Clone(), nil, nil
	}
	return nil, nil, errors.New("'dice.mode' is not 'forced' or 'sampled'")
}

func refusalCode(err error) protocol.ErrorCode {
	if errors.Is(err, battle.ErrOffPhase) || errors.Is(err, battle.ErrActed) {
		return protocol.CodeIllegalState
	}
	return protocol.CodeIllegalAction
}
```

Match `DecodeDecision` and `DecodeReaction` to the signatures of Step 1 (a value or a pointer argument; a value or a pointer return). If `battle.Decision.Reaction` already comes filled by `DecodeDecision` from `request.Action.Reaction` (the wire `Decision` carries a `reaction` field), the request field wins when present, and an action that carries its own `reaction` while the request carries none keeps the action's; keep the necessity rule on the merged result. Check the name of the error code type in `envelope.go` (`ErrorCode` or `Code`) and of the dice mode constants in `types.go:22-27`.

- [ ] **Step 7: Run the tests**

Run from `engine/`: `go vet ./... && go test ./... -race`
Expected: PASS for all four packages. `TestAnAttackWithNoReactionIsIllegalAction` passes on the necessity rule before any weapon check.

- [ ] **Step 8: Commit**

```bash
git add engine/server/session.go engine/server/init.go engine/server/act.go engine/server/act_test.go engine/server/session_test.go engine/server/server_test.go
git commit -m "Answer init, act and export, and seed the session

'act' runs on a clone of the board and installs the clone when the
whole run succeeds. A refusal after the run, such as a short
'outcomes' list, then changes neither the board nor the place of
the server draw in its stream, which the contract asks of an error
response. 'load' takes the seed so the snapshot of 'export' reloads
into the same battle. 'init' stores the event table unread: the
issue that gives the table a shape reads it (user ruling
2026-08-27).

Issue #65."
```

---

### Task 7: Hand-derived differential cases

**Files:**
- Create: `tests/fixtures/engine/turn_cycle_board.json`, `tests/fixtures/engine/turn_pending_board.json`, `engine/differential/turn_test.go`
- Read: `tests/fixtures/engine/small_board.json` (the unit shape), `engine/differential/resolve_test.go:16-61` (the op pattern, `decodeInput`, `livingUnits`)

**Interfaces:**
- Consumes: `differential.Op`, `addOps`, `battle.DecodeState`, `battle.DecodeDecision`, `battle.DecodeOutcomes`, `battle.NewManualRoll`, `Board.Act`, `battle.EncodeSummary`, `livingUnits`.
- Produces: the op `act` with input `{"decision": Decision, "outcomes": [labels]}` and answer `{"turn", "phase", "pending", "units"}`.

The expectations come from the rules of Task 4 and the two document ranges; write them before the engine runs, and cite the lines in the `note`. A mismatch on the first run is a defect in the fixture or in the engine: reason it out, and do not paste the engine answer into the file.

- [ ] **Step 1: Write the op**

`engine/differential/turn_test.go`:

```go
package differential_test

import (
	"encoding/json"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/differential"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func init() {
	addOps(turnOps)
}

type actInput struct {
	Decision protocol.Decision `json:"decision"`
	Outcomes []string          `json:"outcomes"`
}

type actAnswer struct {
	Turn    int              `json:"turn"`
	Phase   protocol.Faction `json:"phase"`
	Pending []string         `json:"pending"`
	Units   []protocol.Unit  `json:"units"`
}

// The two turn-cycle cases are hand-derived from combat-formulas.md and the
// spec; the note of each file names the lines. No oracle wrote them.
var turnOps = map[string]differential.Op{
	"act": func(setup *differential.Setup, input json.RawMessage) (any, error) {
		var in actInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		board, err := battle.DecodeState(&setup.State)
		if err != nil {
			return nil, err
		}
		decision, err := battle.DecodeDecision(&in.Decision)
		if err != nil {
			return nil, err
		}
		outcomes, err := battle.DecodeOutcomes(in.Outcomes)
		if err != nil {
			return nil, err
		}
		if _, err := board.Act(decision, battle.NewManualRoll(outcomes)); err != nil {
			return nil, err
		}
		summary := battle.EncodeSummary(board)
		return actAnswer{Turn: summary.Turn, Phase: summary.Phase, Pending: summary.Pending, Units: livingUnits(board)}, nil
	},
}
```

- [ ] **Step 2: Write turn_cycle_board.json**

Copy the two units of `small_board.json` for the shape. The setup: `phase` `enemy`, `turn` 1 (phase index 5), bounds `[[0,0],[5,4]]`, `pending_events` `[]`, `fired_events` `[]`, `events` `{}`. Units:

- `ally_1`: pos `[1,1]`, `en` 100, `en_max` 140, `acted` true, `debuffs` `[{"kind":"defense","magnitude":0.1,"applied_phase":3}]`, the rest as `small_board.json`'s `ally_1`.
- `ally_2`: pos `[1,2]`, `en` 135, `en_max` 140, `acted` true, `debuffs` `[{"kind":"attack","magnitude":0.2,"applied_phase":4}]`.
- `enemy_1`: pos `[4,3]`, `en` 50, `en_max` 100, `acted` false, `debuffs` `[]`, `faction` `enemy`.

`note`: "Hand-derived, no oracle. The enemy side ends turn 1: the last activation rotates to the ally phase of turn 2 (phase index 6). Phase start: acted false and EN plus floor(en_max/10), capped (combat-formulas.md lines 191-195, floor per the user ruling of 2026-08-27). A debuff hung at phase index 3 is gone at index 6, one hung at index 4 stays (combat-formulas.md lines 269-273). The enemy side keeps its state until its own phase start."

Checks (plus the two codec checks `state` and `events` with `input` null and `expect` equal to the setup, as every file holds):

1. `act`, input `{"decision": {"unit_id":"enemy_1","kind":"standby", every other Decision field null (see small_board's apply checks for the full null shape)}, "outcomes": []}`. Expect: `turn` 2, `phase` `"ally"`, `pending` `["ally_1","ally_2"]`, `units` = the three units with these changes: `ally_1` `en` 114, `acted` false, `debuffs` `[]`; `ally_2` `en` 140, `acted` false, `debuffs` `[{"kind":"attack","magnitude":0.2,"applied_phase":4}]`; `enemy_1` `acted` true, `en` 50, everything else unchanged.
2. `act`, input `{"decision": {"unit_id":"enemy_1","kind":"reposition","move_to":[4,2], ...}, "outcomes": []}`. Expect: as check 1 with `enemy_1` `pos` `[4,2]`.

Read the exact null shape of a `Decision` on the wire from the `apply` checks of `engagement_board.json` and copy every key.

- [ ] **Step 3: Write turn_pending_board.json**

Setup: `phase` `ally`, `turn` 1, the same three units, but `ally_1` and `ally_2` `acted` false, `debuffs` `[]`, `en` 100 and 135; `enemy_1` `acted` false.

`note`: "Hand-derived, no oracle. An activation with a pending sibling rotates nothing: the phase, the turn, the EN and the debuffs stay (the phase start runs only on a rotation)."

Checks: `state`, `events`, and one `act`: `ally_2` standby, outcomes `[]`. Expect `turn` 1, `phase` `"ally"`, `pending` `["ally_1"]`, `units` with `ally_2` `acted` true and nothing else changed.

- [ ] **Step 4: Run the differential tests**

Run from `engine/`: `go test ./differential/ -run Golden -v 2>&1 | tail -30`
Expected: PASS with the two new cases and 3 `act` checks ran, 0 skipped. If a check fails, compare the expectation against the rules in Task 4 and the document lines; fix the side that breaks the rule.

- [ ] **Step 5: Run the whole gate and commit**

Run from `engine/`: `go vet ./... && go test ./...`. Run from the root: `uv run pytest -q tests/test_engine_codec.py` (the fixture files are not read by Python; the run confirms nothing else broke).

```bash
git add tests/fixtures/engine/turn_cycle_board.json tests/fixtures/engine/turn_pending_board.json engine/differential/turn_test.go
git commit -m "Freeze two hand-derived turn cycle cases

The Python oracle is retired and the issue forbids a run of it, so
the two cases come by hand from combat-formulas.md lines 191-195
and 269-273 and the rules of the spec (user ruling 2026-08-27). The
decisions are a standby and a reposition, so no damage number
enters: the engagement cases of #64 already hold those. The note of
each file names the source lines.

Issue #65."
```

---

### Task 8: The Python side: the seed, the summary, the page

**Files:**
- Modify: `src/ggge_ai/engine/session.py:30-48`, `src/ggge_ai/engine/fake.py:73-104`, `scripts/sandbox_ui.py:574-590`, `:636-650`, `:725-739`
- Modify: `tests/test_engine_client.py:17`, `tests/test_sandbox_ui.py` (append)
- Create: `tests/test_engine_turn.py`

**Interfaces:**
- Consumes: `EngineSession.act` (unchanged), the `act` answer `{events, board: {turn, phase, pending, gone}}`, the `load` field `seed`.
- Produces: `EngineSession(engine, state, *, events=None, stage="", seed=0)`; `EngineSession.from_scenario(path, engine, *, seed=0)`; `sandbox_ui.parse_args` with `--seed`.

- [ ] **Step 1: Write the failing tests**

`tests/test_engine_client.py:17`: `IMPLEMENTED = {"hello", "ping", "init", "load", "export", "reach", "actions", "reactions", "act"}`.

Append to `tests/test_sandbox_ui.py`:

```python
def test_the_seed_reaches_the_load_of_the_engine():
    with FakeEngine() as engine:
        EngineSession.from_scenario(str(PLACEHOLDER), engine, seed=21)
        assert engine.loaded_seed == 21


def test_the_act_answer_carries_the_summary_of_the_contract(client):
    pending = client.get("/api/decision")
    unit = pending["units"][0]["unit_id"]

    _, payload = client.post("/api/act", {"candidate": {"unit_id": unit, "kind": "standby"}})

    assert set(payload["board"]) == {"turn", "phase", "pending", "gone"}
    assert unit not in payload["board"]["pending"]
    assert payload["board"]["gone"] == []


def test_the_seed_flag_is_an_integer_with_zero_as_the_default():
    args = parse_args(["--scenario", str(PLACEHOLDER)])
    assert args.seed == 0
    args = parse_args(["--scenario", str(PLACEHOLDER), "--seed", "7"])
    assert args.seed == 7


@pytest.fixture
def live_client(engine_executable):
    with BattleEngine(engine_executable) as engine:
        session = EngineSession.from_scenario(str(PLACEHOLDER), engine, seed=5)
        handler = build_handler(session, engine=engine)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        try:
            yield Client(f"http://{host}:{port}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def test_the_page_plays_the_ally_phase_through_the_engine(live_client):
    pending = live_client.get("/api/decision")
    units = [entry["unit_id"] for entry in pending["units"]]
    assert len(units) == 10, "the placeholder scenario deploys ten ally units"

    for unit in units:
        status, payload = live_client.post(
            "/api/act", {"candidate": {"unit_id": unit, "kind": "standby"}}
        )
        assert status == 200, payload

    assert payload["board"]["phase"] == "enemy"
    assert payload["board"]["turn"] == 1
    assert len(payload["board"]["pending"]) == 18
    assert payload["state"]["phase"] == "enemy", "'export' brings the rotation back"
```

Import `parse_args` and `BattleEngine` at the top of the test (check `REACHED`: the page's import list is asserted by `test_the_page_reaches_the_engine_and_no_rule_module`; the test file's own imports are free). `engine_executable` is the session fixture of `tests/conftest.py`.

`tests/test_engine_turn.py`:

```python
"""The turn cycle through the built binary.

The page cannot drive an attack until issue #78 rebuilds its command
flow, so the engagement here goes through the client directly, with
the decision of a frozen engagement case.
"""

from __future__ import annotations

import json
from pathlib import Path

from ggge_ai.engine.client import BattleEngine

ROOT = Path(__file__).resolve().parents[1]
ENGAGEMENT = ROOT / "tests/fixtures/engine/engagement_board.json"


def _engagement() -> tuple[dict, dict]:
    case = json.loads(ENGAGEMENT.read_text(encoding="utf-8"))
    for check in case["checks"]:
        if check["op"] == "apply" and check["input"]["decision"]["kind"] == "attack":
            return case["setup"]["state"], check["input"]["decision"]
    raise AssertionError("the engagement case holds no attack")


def _play(engine_executable, seed: int) -> tuple[dict, dict]:
    state, decision = _engagement()
    request = {
        "unit_id": decision["unit_id"],
        "action": {**decision, "reaction": None},
        "reaction": decision["reaction"],
        "dice": {"mode": "sampled"},
    }
    with BattleEngine(engine_executable) as engine:
        engine.call("load", {"state": state, "history": [], "seed": seed})
        answer = engine.call("act", request)
        return answer, engine.call("export")


def test_one_seed_gives_one_battle(engine_executable):
    first_answer, first_export = _play(engine_executable, 11)
    second_answer, second_export = _play(engine_executable, 11)

    assert first_answer == second_answer
    assert first_export == second_export
    assert first_export["seed"] == 11
    assert [entry["cmd"] for entry in first_export["history"]] == ["act"]


def test_the_events_hold_a_strike_then_the_summary_names_the_phase(engine_executable):
    answer, _ = _play(engine_executable, 11)

    assert answer["events"][0]["event"] == "strike"
    assert set(answer["board"]) == {"turn", "phase", "pending", "gone"}


def _reaction_none() -> dict:
    return {"stance": "none", "weapon": None, "support_defender": None, "support_attackers": []}


def _attack(decision: dict, actor: dict, target: dict) -> dict:
    action = {**decision, "unit_id": actor["unit_id"], "kind": "attack", "move_to": None,
              "target_id": target["unit_id"], "weapon": actor["weapons"][0]["name"], "reaction": None}
    return {"unit_id": actor["unit_id"], "action": action, "reaction": _reaction_none(),
            "dice": {"mode": "forced", "outcomes": ["hit", "hit", "hit", "hit"]}}


def _standby(decision: dict, actor: dict) -> dict:
    action = {**decision, "unit_id": actor["unit_id"], "kind": "standby", "move_to": None,
              "target_id": None, "weapon": None, "reaction": None}
    return {"unit_id": actor["unit_id"], "action": action, "dice": {"mode": "forced", "outcomes": []}}


def test_a_battle_runs_to_annihilation(engine_executable):
    state, decision = _engagement()
    with BattleEngine(engine_executable) as engine:
        engine.call("load", {"state": state, "history": [], "seed": 2})
        for _ in range(200):
            exported = engine.call("export")["state"]
            living = [unit for unit in exported["units"] if unit["hp"] > 0]
            if not {"ally", "enemy"} <= {unit["faction"] for unit in living}:
                break
            actor = next(u for u in living if u["faction"] == exported["phase"] and not u["acted"])
            target = next(u for u in living if u["faction"] != actor["faction"])
            try:
                answer = engine.call("act", _attack(decision, actor, target))
            except EngineError:
                answer = engine.call("act", _standby(decision, actor))
        else:
            raise AssertionError("no side is gone after 200 activations")
        assert answer["board"]["gone"] in (["ally"], ["enemy"], ["ally", "enemy"])
```

Import `EngineError` from `ggge_ai.engine.client` next to `BattleEngine`. The fallback to `standby` covers an actor out of range or out of EN for its first weapon; the strike of an attacker with a weapon in range lands under four forced hits, so the hit points fall every round and one side is gone within 200 activations. The `reaction` shape follows `protocol.Reaction` (`engine/protocol/state.go:205-210`: `stance`, `weapon`, `support_defender`, `support_attackers`).

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest -q tests/test_sandbox_ui.py tests/test_engine_turn.py tests/test_engine_client.py`
Expected: FAIL on `seed`, `loaded_seed`, `parse_args --seed`, and the summary keys of the fake.

- [ ] **Step 3: Implement**

`src/ggge_ai/engine/session.py`:

```python
    def __init__(
        self,
        engine: Any,
        state: BattleState,
        *,
        events: EventTable | None = None,
        stage: str = "",
        seed: int = 0,
    ) -> None:
        self._engine = engine
        self._state = state
        self._events = events or {}
        self._stage = stage
        self._seed = seed
        self._ask("load", {"state": self.engine_state(), "history": [], "seed": seed})

    @classmethod
    def from_scenario(cls, path: str, engine: Any, *, seed: int = 0) -> EngineSession:
        loaded = scenario_mod.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        state, events = loaded.build()
        return cls(engine, state, events=events, stage=loaded.stage, seed=seed)
```

`src/ggge_ai/engine/fake.py`: `_load` stores `self.loaded_seed = int(payload.get("seed", 0))` (declare `self.loaded_seed = 0` in `__init__`); `_export` answers `{"state": self._loaded(), "history": [], "seed": self.loaded_seed}`; `_summary` answers:

```python
    def _summary(self) -> dict[str, Any]:
        state = self._loaded()
        pending = [
            unit.get("unit_id")
            for unit in state.get("units", [])
            if unit.get("faction") == state.get("phase") and not unit.get("acted") and unit.get("hp", 0) > 0
        ]
        return {"turn": state.get("turn"), "phase": state.get("phase"), "pending": pending, "gone": []}
```

The fake still rotates nothing and judges nothing: the module doc says so.

`scripts/sandbox_ui.py`: `parse_args` gains `parser.add_argument("--seed", type=int, default=0, help="對局亂數源的種子（引擎自抽骰時用）")`; `main` passes `seed=args.seed` to `from_scenario`. In the page script: a global `let gone = [];`; in the `/api/act` handler set `gone = payload.board.gone || [];` before `apply(...)`; in `renderPlay`, after the `error` line and before the phase gate:

```javascript
  if (gone.length) {
    box.appendChild(node("p", "dim", "戰鬥結束：" + gone.map((side) => FACTION_NAME[side] || side).join("、") + "全滅。"));
    return;
  }
```

- [ ] **Step 4: Run the gates**

Run: `uv run pytest -q && uv run ruff check src tests scripts`
Expected: pass. (`test_engine_turn.py` and `live_client` build the binary once through `engine_executable`.)

- [ ] **Step 5: Commit**

```bash
git add src/ggge_ai/engine/session.py src/ggge_ai/engine/fake.py scripts/sandbox_ui.py tests/test_engine_client.py tests/test_sandbox_ui.py tests/test_engine_turn.py
git commit -m "Play the ally phase on the page against the engine

The page loads the scenario with a seed and posts every activation
to 'act'; the engine rotates the phase and 'export' brings the
rotation back, so the page follows the turn without a rule of its
own. The page reads the end of the battle from the summary field
'gone' (user ruling 2026-08-27). The attack path of the page waits
for #78, so the engagement test goes through the client with the
decision of a frozen engagement case.

Issue #65."
```

---

### Task 9: The contract text

**Files:**
- Modify: `docs/spec/battle-engine-protocol.md` sections `init` (66-91), `act` (258-343), `export and load` (397-406), `Differential cases` (658-690), and a new section `## Turn cycle` before `## Board geometry` (408)
- Modify: `docs/reference/terminology-map.md` (append rows)
- Modify: `docs/roadmaps/branch-issue-65.md` (progress log, resume point)

Docs-only: no code gate. Write in the ASD-STE100 style of the file.

- [ ] **Step 1: init**

Replace the paragraph "'init' is not implemented. The section 'Terrain' holds one open requirement ..." with:

```
The field 'board' carries 'width', 'height', 'terrain' (the default
kind of the map) and 'terrain_cells' (the cells of another kind).
The section 'Terrain' holds the kinds.

The field 'events' is stored and not read: the issue that gives a
stage event its shape reads the table (user ruling 2026-08-27). The
field 'rules' is accepted and not read: the engine takes every rule
from a constant. The field 'seed' builds the session random source;
every server draw of the session reads that source.

The board opens at turn 1 in the ally phase with the enemies on it.
'place' is not implemented, so a battle with ally units starts
through 'load' today.
```

- [ ] **Step 2: act**

Replace the two paragraphs from "The field 'dice' holds 'mode'." to "Response: 'events' ... (the new summary)." with:

```
The field 'dice' holds 'mode'. The value 'forced' is the manual
roll: it also holds 'outcomes', a list of the labels 'hit' and
'miss', and the engine reads one label for each chance event, in
the resolution order. The value 'sampled' is the server draw: the
engine draws from the session random source, one draw for each
chance event. One volley of support attackers is one chance event
until issue #47 gives each supporter a draw.

Response: 'events' and 'board'.

'events' is the resolution in order. An entry carries 'event'. The
value 'strike' carries 'strike' (support, strike, defender_support,
or counter), 'shooter_id', 'struck_id', 'weapon', 'landed',
'damage', and 'killed'. The value 'phase' carries 'turn' and
'phase': the engine rotated the phase after the activation, and
the section 'Turn cycle' holds the rule.

'board' is the summary: 'turn', 'phase', 'pending' (the ids of the
units of the phase that can still act), and 'gone' (the sides
'ally' and 'enemy' with no living unit, in that order). The engine
judges no end of the battle: a board with one side gone answers
like any other, and the client stops on 'gone' (user ruling
2026-08-27).

The command runs on a copy of the board and installs the copy when
the whole run succeeds. A refusal changes no board and moves the
session random source nowhere. A success writes one entry to the
operation history.
```

Add to the refusals: "an 'outcomes' label outside 'hit' and 'miss' is a bad_request".

- [ ] **Step 3: export and load**

Replace the section body with:

```
'export' takes no field and gives 'state', 'history', and 'seed'.
'load' takes the same three fields and replaces the session. An
entry of 'history' carries 'cmd' and 'payload', the request of one
command that changed the board. 'seed' is optional on 'load'; an
absent seed is 0. 'load' builds the session random source at the
start of its stream: a loaded history is a record, not a replay.

The state carries 'phase'. A state without that field is a
bad_request.
```

- [ ] **Step 4: Turn cycle**

Insert before `## Board geometry`:

```
## Turn cycle

The phases of one turn run in the order ally, third_party, enemy.
A unit is pending when it lives, is of the faction of the phase,
and did not act in this phase.

After one activation, while the faction of the phase holds no
pending unit, the phase moves to the next entry of the order. The
move from the enemy phase to the ally phase adds one to the turn.
A board with no living unit keeps its phase.

Every move opens the phase of one faction. At that phase start:

- Every living unit of the faction gets its activation back.
- Every living unit of the faction regenerates one tenth of its
  maximum EN, floored, and the EN does not pass the maximum
  (docs/reference/combat-formulas.md line 191). The floor is a
  hypothesis: the reference leaves the rounding open at line 310,
  and the user ruled on 2026-08-27 to floor until a device
  measurement settles it.
- Every living unit of every faction drops the debuffs that one
  full round has passed: a debuff hung in the phase of index p is
  gone when the phase of index p + 3 opens
  (docs/reference/combat-formulas.md line 269). The phase index is
  turn times 3 plus the position of the phase in the order.

The phase start resets no chance step and no support charge, and
fires no stage event. The three wait for the issue that gives them
a shape (user ruling 2026-08-27).
```

- [ ] **Step 5: Differential cases**

After "The files are frozen: the writer retired with the Python rules (issue #73), and no process writes them again.", add:

```
A case can also be written by hand from the reference documents.
Its 'note' says so and names the document lines that give each
expectation. The two turn-cycle cases are of this kind.
```

- [ ] **Step 6: Evolution and hello**

No text change: the section already says a field addition raises the version. Confirm the file states no version number elsewhere (`grep -n '1\.[0-9]' docs/spec/battle-engine-protocol.md`); if it does, set it to 1.3.

- [ ] **Step 7: Terminology**

Append rows to `docs/reference/terminology-map.md`, in the table that holds 'activation' (line 80), in its column format:

```
| turn cycle | 回合循環 | The rotation of the phases ally, third_party, enemy, and the turn counter; docs/spec/battle-engine-protocol.md section 'Turn cycle'; Go: 'Board.Act', 'Board.Advance' in engine/battle/turn.go |
| phase start | 相位開始 | The moment the phase of one faction opens: the activations come back, the EN regenerates, the debuffs of one full round expire; Go: 'beginPhase' |
| pending unit | 待啟動單位 | A living unit of the faction of the phase that did not act in this phase; the summary field 'pending'; Go: 'Board.Pending' |
| session random source | 對局亂數源 | The PCG source that the 'seed' of 'init' or 'load' builds and every server draw reads; Go: 'ServerDraw' |
| manual roll (Go) | — | The Go type of the manual roll is 'ManualRoll'; see the row 'manual roll' |
```

Check the existing Chinese binding for 相位 or 階段 first (`grep -n '階段\|相位' docs/reference/terminology-map.md`): the page uses 階段 for the phase (`scripts/sandbox_ui.py:412`), so bind `phase start` to 階段開始 if the map holds 階段 for phase, and keep one term. Drop the last row if the map's format rejects a row without a Chinese term; put the Go names in the 'manual roll' and 'server draw' rows instead.

- [ ] **Step 8: Roadmap**

In `docs/roadmaps/branch-issue-65.md`, update the resume point and add the progress log entries for the tasks that landed. Add the section "Contention points for the reviewer" with these entries: (1) the field 'rules' of 'init' is unread; (2) 'export' and 'load' carry the seed but not the event table, the victory conditions, or the deploy cells, so a session that 'init' built and 'load' reloads loses the three (they are unread today); (3) the summary field 'gone' as the shape of ruling 6; (4) the necessity rule of the reaction lives in the 'act' handler; (5) the one-draw volley and #47; (6) the page attack path waits for #78; (7) the fixed 'ENRegenPercent' replaces 'ENRegenFraction'.

- [ ] **Step 9: Commit**

```bash
git add docs/spec/battle-engine-protocol.md docs/reference/terminology-map.md docs/roadmaps/branch-issue-65.md
git commit -m "State the turn cycle and the act answer in the spec

The contract described no phase rotation and left the answer
shapes of 'act' to the issue that implements them. The spec now
holds the rotation, the phase start with the floor hypothesis of
the EN regeneration, the debuff expiry, the two event shapes, the
summary with 'pending' and 'gone', and the seed of 'export' and
'load'. The differential section admits a hand-derived case, since
the oracle is retired and the issue forbids a run of it.

Issue #65."
```

---

## Self-review

Spec coverage: init (Tasks 5, 6, 9), act with both dice (2, 6, 9), determinism (2, 6, 8), export/load with seed (1, 6, 9), turn cycle (4, 9), page (8), fixtures (7), gates (every task). Not covered by ruling: events, chance steps, support charges, place, rollback.

Type consistency: `ManualRoll`/`NewManualRoll`/`Short`, `ServerDraw`/`NewServerDraw`/`Clone`, `Board.Act`/`Advance`/`Pending`/`Gone`, `Resolution`/`Rotation`, `DecodeInit`/`EncodeState`/`DecodeOutcomes`/`EncodeResolution`/`EncodeSummary`, `HistoryEntry`, `BoardSummary`, `newSession`, `initBattle`, `ENRegenPercent` are used with one name each across Tasks 2-9.
