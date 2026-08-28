# Branch roadmap: issue 84, contract slots for UR mech and pilot values

> Type: working—deleted at merge

## Where the branch stands

The branch 'issue-84-ur-contract-slots' starts from 'dev' (8d1f598),
after the merge of #74. The datamine reference and the sample store
of #74 are the ground of the mapping table.

## Rulings that shape the branch (2026-08-28)

- The pilot pairing is free: 'gacha.bonus.character' is the bundled
  pilot of a pull, not a link. UR pilots are the pilot rows with
  'rarity' 5 (84 rows); UR units are the unit rows with 'rarity' 5
  (112 rows). No stored selection: one filter each.
- A weapon carries one or more attack tags (射擊, 格鬥, 覺醒). The
  damage reads the pilot value of the tag; with more than one tag,
  the highest. This branch opens the contract shape; the strike
  change is issue #72.
- The site's 'max_hp' is the mech's. The final panel is the mech
  value after the pilot's abilities (issue #77).

## Plan

1. Crawler: add 'character' to 'TABLE_PATHS', a fixture slice of
   three pilot rows (UR, SR with an empty second slot, R), and the
   tests that the row count and the byte stability cover it.
2. Reference: the UR selection rule and the mapping table, mech
   values and pilot values against the engine contract, in
   'docs/reference/datamine-source.md'.
3. Contract: the new engine-only fields on 'protocol.Unit' and on
   'protocol.Weapon', the 'ENGINE_ONLY' entries, the "Types"
   section of the spec, and the codec that carries them into
   'battle.Mech', 'battle.Pilot' and 'battle.Weapon' as data.
4. Gates, review, artifact.

## Resume point

Step 1 is delegated. Step 3 waits for the user's answer on the
field names (see the contention points).

## Progress log

- 2026-08-28: worktree added, roadmap written.

## Contention points

1. Field names for the pilot base data. The panel already uses
   'pilot_attack', 'pilot_defense' and 'reaction', and those names
   are frozen. The base slots need other names. Proposed:
   'pilot_ranged', 'pilot_melee', 'pilot_awaken' (new concepts, no
   collision), 'pilot_base_defense', 'pilot_base_reaction', and for
   the mech 'mech_attack', 'mech_defense', 'mech_mobility'.
2. Whether the final panel also gains three pilot attack slots. The
   game's pilot panel shows 射擊值, 格鬥值 and 覺醒值, and the intel
   store already carries three pilot attack columns. If the panel
   carries one 'pilot_attack' only, #72 has nothing to pick from.
3. The weapon attack tags. A new optional field 'attack_tags' on
   the weapon payload, a list over 'ranged', 'melee', 'awaken'. The
   issue text keeps weapon fields out; the ruling of 2026-08-28
   brings this one in.
