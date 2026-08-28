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

## The shape (user ruling 2026-08-28)

The unit is the current state of the pairing on the board. It
records state and the maxima of state, and it takes no part in a
computation. The pilot and the mech are data on the unit; a formula
reads them at computation time.

    Pilot  { ranged, melee, awaken, defense, reaction, sp }
    Mech   { hp, en, attack, defense, mobility, move_range, weapons }
    Weapon { ...existing..., attack_tags: [ranged | melee | awaken] }
    Unit   { unit_id, faction, pos, size, hp, max_hp, en, en_max,
             sp, sp_max, pilot, mech, skills, acted, charges, ammo,
             debuffs }

'max_hp' and 'en_max' come from the mech at 'init' (the pilot's
abilities join in issue #77). 'sp_max' comes from the pilot. The
pilot attack of a strike is 'Pilot.AttackFor(weapon)': the highest
pilot value among the attack tags of the weapon; a weapon with no
tag reads the highest of the three.

## Plan

1. Crawler: add 'character' to 'TABLE_PATHS', a fixture slice of
   three pilot rows (UR, SR with an empty second slot, R), and the
   tests that the row count and the byte stability cover it.
2. Reference: the UR selection rule and the mapping table, mech
   values and pilot values against the engine contract, in
   'docs/reference/datamine-source.md'.
3. Contract: the shape above in 'engine/protocol', 'engine/battle'
   (domain, codec, the readers in 'hit.go' and the damage path),
   the Python mirror and codec, the protocol version, the golden
   files converted so the recorded numbers stay, the parity test.
4. Spec "Types" section, the terminology entries 'final panel' and
   'base data' rewritten, the mapping table in the reference.
5. Gates, review, artifact.

## Resume point

Step 1 landed (e5186d8, 5df1516). Step 3 is delegated to the code
editor; step 4 runs in the main session in parallel.

## Progress log

- 2026-08-28: worktree added, roadmap written.
- The pilot table crawled: e5186d8. The two measured sentences:
  5df1516.
- The shape ruled by the user; the reshape delegated.

## Contention points

1. The golden files record the flat unit payloads of the retired
   oracle. The conversion sets 'ranged', 'melee' and 'awaken' of
   each pilot to the recorded 'pilot_attack', so the tag pick gives
   the recorded number and the expectations stay a true record.
2. 'sp' and 'sp_max' have no source in the datamine. They land as
   state fields with 0 until the device reader fills them.
