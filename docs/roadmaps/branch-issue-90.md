# Branch roadmap: issue 90, the two shapes exchange contents

> Type: working—deleted at merge

Issue #90. Branch off 'dev' at 'eb3d2f4'.

## The ruling

The user ruled on 2026-09-01 that the two fields of 'AffectArea'
exchange their contents. The two names stay.

- 'apply_shape' holds the cells where the center of the area can sit.
  Column: 'map_weapon_shooting_range' on a map weapon; a skill has no
  such column.
- 'effect_shape' holds the cells that the owner acts on. Column:
  'map_weapon_effect_range' on a map weapon, 'effect_range' on a skill.

The crossover of version 1.9 and version 1.10 ends. After the swap
'effect_shape' carries the two columns whose name holds "effect", so
the name matches the column. The warning "Read the column, not the
name" leaves the code and the two tables of the spec.

The caster rule follows its content. An empty 'apply_shape.cells' is no
choice of center: the owner opens its 'effect_shape' at the cell of the
caster.

## Change summary

Eight files. Protocol 1.10 to 1.11.

| File | Change |
|---|---|
| engine/battle/snapshot.go | The comment of 'AffectArea' and of each field. The crossover warning is deleted. |
| engine/protocol/envelope.go | 'Version' to "1.11". |
| src/ggge_ai/engine/contract.py | 'PROTOCOL_VERSION' to "1.11". |
| src/ggge_ai/engine/state.py | The docstring of 'MapWeapon' and of 'Skill'. |
| src/ggge_ai/stage/intel.py | Both comments name 'apply_shape' as the caster rule. |
| docs/spec/battle-engine-protocol.md | Both tables swapped, the caster rule and the integer sentence moved to 'apply_shape', and the eighth exception for version 1.11. |
| docs/reference/terminology-map.md | The two entries. The Chinese bindings did not move. |
| docs/record/decisions.md | The dated entry of the ruling, appended. |

## Call chain

None. No rule reads either field, so the change starts and ends at the
declaration and at the documents. The two conversions that touch the
fields are 'engine/battle/state/contract.go' ('fromContractAffectArea'
and 'ToContractAffectArea') and 'engine/battle/board/projection.go'
('mapWeaponEntriesOf' and 'skillEntriesOf'). Each copies a name to the
same name on the other form, and both ends of every copy swapped
together, so neither file needed an edit.

## Contention points

1. The version history keeps the crossover sentence in the entries for
   version 1.9 and version 1.10. Those entries state what those two
   versions did, and they stay true. The acceptance criterion of the
   issue asks for no hit of "cross over" outside decisions.md; the
   version history is the one exception, and it is deliberate.
2. The Chinese terms 施放形狀 and 效果形狀 already described the new
   contents, so this branch changed no binding of the terminology map.
   A reader who expects a Chinese change will not find one.
3. Issue #89 is open on the same wire. Its branch held no code at
   'eb3d2f4', so this branch takes 1.11 and #89 takes the next number.
   Whichever merges second resolves the version constant.
4. No fixture moved. Every shape under tests/fixtures/engine/ is empty,
   so the swap is invisible to every golden.

## Gates

- 'uv run pytest -q': 1034 passed, 4 skipped.
- 'uv run ruff check src tests scripts': passed.
- From 'engine': 'gofmt -l' reported no file, 'go vet ./...' passed,
  'go test ./...' passed.
