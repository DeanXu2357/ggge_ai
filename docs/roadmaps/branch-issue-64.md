# Branch roadmap: issue 64, the engagement resolution

> Type: working—deleted at merge

## Where the branch stands

The branch stands on 'dev' (6134aa3), which holds the reporting
contract of issue #63. It is a rebuild, not a rebase: the branch
'issue-64-engagement' stands on the pre-ruling tip 771916b and stays
on disk for the comparison. Nothing of this branch is on that one.

## Why the rebuild

The user ruled on 2026-08-25 that the engine reports options and the
client composes the action. The old branch was written against the
enumeration that the ruling retired, and three parts of it broke:

1. It added the support attack to the enumeration as two entries of
   the action list, one with the support and one without.
2. It judged a reaction by a lookup in the list that 'Board.Reactions'
   gave back.
3. It picked the support units itself: the first eligible support defender,
   and every eligible support attacker on one boolean.

Everything else of that branch is a consumer of a client-composed
action, which is the side of the ruling the engine keeps. The damage,
the hit rate, the stance multipliers, the debuff rules, the chance
nodes and the resolution order came over as they stood.

## What the user ruled on 2026-08-25

| Question | Ruling |
|---|---|
| Support granularity | The client names each support defender and each support attacker. The engine picks none. |
| The forecast | This branch fills 'hit_rate', 'damage' and 'kill', which issue #63 shipped as null. |
| The shield | A defender that carries a shield defends with it: the shield multiplier applies to the defend stance of that unit. |
| The volley | Not a term of the mechanism. It is one case of a support attack, and the names say support attack. |

## What the user ruled on 2026-08-26

| Question | Ruling |
|---|---|
| The terrain of the damage | The scalar rule 'terrain' goes. The board carries the terrain of each cell, and the engine reads it. |
| The shield reduction | The unit carries no multiplier of its own. The mech says whether the unit carries a shield, and the damage applies the multiplier of the rules. |
| The terrain contract | The shape comes first. Which cell keys the damage factor, and where the values come from, wait for the task that collects the intelligence. |
| The weapon terrain fields | 'TerrainDamage' and 'UnusableIn' leave the domain model and the wire. That table of the datamine is not the shape of the mechanism. |
| The area of a map weapon | The area is a shape of each weapon, and a radius does not hold it. The field 'blast' of a weapon leaves the domain model and the wire. The blast of a skill stays. |
| The map attack | A map attack starts no engagement, so its resolution is not of this issue. 'Board.Apply' refuses the kind 'map_attack' until a contract holds the area. |
| The terrain effects | They are not rules of the board. Each one is an ability of a weapon: the damage ability reads the cell of the target, and the fire restriction reads the cell of the attacker. |
| The ability framework | The engine models a closed set of ability kinds and ignores every kind outside it. A new ability of the game adds a kind, never a field of 'Weapon'. |
| Where the ability lands | Not on this branch. This branch discloses the decision and leaves the gap; issue #80 builds the model. |
| The source of a machine skill | The value 'unit' becomes 'mech'. A unit is a pilot and a mech together, so the source of a machine skill names the mech alone. |
| The source of a driver skill | The value 'character' becomes 'pilot'. The engine names that level 'Pilot' everywhere else, and one concept takes one term. |
| The support defense multiplier | Out of the rules. A unit that takes the strike for another takes it in the defend stance, and its own reduction is an ability of that unit. No rule of the mechanism holds one value for every such case. |
| The shield multiplier | The shield is a second cut on top of the defense, not a stance of its own. The value 0.6 was the two cuts flattened into one, and wrongly: a shielded defender pays 0.8 times 0.8. |
| The rules payload | Out of the contract. Every value of it holds for the whole title, so no stage overrides one. The values are constants of 'engine/battle/rules.go'. |
| The attack shield | The field 'AttackShield' becomes 'SupportDefendWhenAttack', and the wire field 'attack_shield' becomes 'support_defend_when_attack'. The name says what the unit does. |
| The interception reduction | Out of the unit. The user named no such concept. What was described is a weapon that resolves ahead of the order and strikes through the support defense, which is a use of the application order of a weapon and no attribute of a unit. |
| The word 'interception' | Retired. The game labels the unit 支援防禦 and the engine took 'interceptor' from the Python sandbox. The term is 'support defender' 支援防禦者 everywhere. |
| The per-mech reduction | It is a weapon ability, so it joins the kind set of issue #80. The reference record of it stands. |

## Change summary

- 'engine/battle/model.go': the fields one engagement reads and
  writes (weapon power, debuff, the rule multipliers, the charges,
  the shield, the interception reduction, the debuff list).
  'Activatable' comes back for the resolution alone.
- 'engine/protocol/state.go', 'src/ggge_ai/engine/state.py' and
  'codec.py': the action carries 'support_attackers' and
  'support_defender', and the reaction carries the same two fields
  for the defending side. The boolean 'support', 'support_defend' and
  'support_attack' are out.
- 'engine/battle/strike.go' and 'dice.go': the damage of one shot,
  the hit rate of one shot, the stance and interception multipliers,
  the counter weapon, and the four chance nodes.
- 'engine/battle/resolve.go': 'Board.Apply' runs one action and gives
  the trace. It judges the whole pick before it changes one field.
- 'engine/battle/forecast.go' and 'reactions.go': every entry of the
  engagement answer carries the forecast of its own shot.
- 'engine/differential/resolve_test.go' and two golden boards: the
  resolution against the Python oracle, unit by unit and field by
  field.
- The terrain contract: 'src/ggge_ai/engine/contract.py' gives the
  five kinds, 'state.py' mirrors the two state fields, and
  'stage/scenario.py' reads them from the stage file into the board.
  The board carries the terrain of each cell. No rule reads it: the
  scalar 'Rules.terrain' and the weapon fields 'TerrainDamage' and
  'UnusableIn' are all out, and 'StrikeDamage' passes 1 for the
  terrain correction until the intelligence task settles the rule.
- The map attack: 'Board.mapAttack', the strike kind 'map' and the
  weapon field 'Blast' are out of the model, the wire, the Python
  mirror and 'stage/intel.py'. 'Board.Apply' refuses the kind and
  changes no field. Issue #79 holds the area of a map weapon.
- The rules: 'protocol.Rules', 'battle.Rules', 'DefaultRules',
  'DecodeRules', 'Board.Rules', the Python 'Rules' and 'DEFAULT_RULES',
  'encode_rules', 'decode_rules', the 'rules' field of a scenario file
  and the rules override of 'stage/scenario.py' are all out. The new
  file 'engine/battle/rules.go' holds every value as a constant, with
  'StanceMultiplier' and 'InterceptionMultiplier' beside them.
  'engine/differential' holds the whole retired block so the frozen
  files still load, as it holds 'terrain'.
- The shield: 'ShieldMultiplier' is 0.8, its own cut, and
  'StanceMultiplier' multiplies it by 'DefendMultiplier' for a shielded
  defender. The two reference documents carry the correction.
- The attack shield: 'AttackShield' and 'attack_shield' become
  'SupportDefendWhenAttack' and 'support_defend_when_attack' through the
  model, the wire, the Python mirror, the panel reader, the ability
  vocabulary of the panel prompt, the frozen files and the scenario
  file.
- The interception reduction: 'Unit.InterceptionReduction', the wire
  field, the Python mirror, the intelligence record, the panel ability
  code and the frozen values are all out.
  'InterceptionMultiplier' goes with them, because a unit that takes
  the strike for another now reads 'StanceMultiplier' for the defend
  stance and nothing else.
- The support defender: the Go names 'namedInterceptor',
  'interceptedReceiver', 'interceptionForecast' and the two
  'interceptor' fields become 'namedSupportDefender',
  'coveredReceiver', 'supportDefenderForecast' and 'supportDefender'.
  The prose of 'docs/spec/battle-engine-protocol.md',
  'docs/reference/combat-formulas.md' and
  'docs/reference/battle-prep-ui.md' drops 'interceptor' and 攔截者.
  'docs/reference/terminology-map.md' folds the retired entry into
  'support defender' and records where the word came from.
- The skill source: the wire value 'unit' becomes 'mech' and
  'character' becomes 'pilot', in 'engine/protocol/state.go',
  'engine/battle/model.go', the two codecs and
  'src/ggge_ai/engine/contract.py'. The three frozen files that hold a
  skill take the new name of 'unit'; no file holds 'character'.
- The weapon ability: 'docs/spec/battle-engine-protocol.md' gains the
  section 'Weapon abilities', which holds the three known abilities,
  the closed-kind rule and the gap. 'docs/reference/terminology-map.md'
  binds the term and retires 'terrain restriction', which the ability
  absorbs. 'StrikeDamage' says why it passes 1 and why it takes no
  board. Issue #80 builds the model.

## Call chain

    server 'reactions' (issue #63)
      Board.Reactions(action, defenderID)
        stanceOption      -> Rules.StanceMultiplier, forecastOf
        defendOptions     -> SupportDefenders, interceptionForecast
        attackOptions     -> SupportAttackers, forecastOf
      EncodeEngagement    -> EncodeForecast

    Board.Apply(decision, dice)          <- the command 'act' of #65
      Activatable
      run -> attack
        foe, destination
        namedSupportAttackers            <- the pick of the client
        namedSupportDefendWhenAttack
        answerOf
          CounterWeapon
          namedSupportDefender
        receiverOf -> plainReceiver | interceptedReceiver
        fire  (NodeAttackerSupport)
        receiver.hit (NodeStrike) -> StrikeDamage, wound, applyDebuff
        defenderReply
          fire (NodeDefenderSupport)
          counterStrike (NodeCounter)
      endActivation

## Contention points

1. **The forecast of a support attack entry reads no stance.** The
   foe picks its stance after this answer, so the entry gives the
   damage with no defense. The client cannot add the stance itself
   without a rule of the battle.
2. **A support defender of the defending side carries no hit rate.**
   The stance settles that hit roll. One of the attacking side carries
   no forecast at all, because the defender picks which weapon
   counters.
3. **The stand with a support defender stays legal.**
   docs/reference/battle-prep-ui.md:279 states that defend never pairs
   with support defense and marks 'none' as unconfirmed. The engine
   refuses the defend pair and permits the stand pair.
4. **One golden case left the comparison.** The oracle reads the
   defend multiplier for a shielded unit that defends, and the ruling
   reads the shield. The shield case of the same board stayed and now
   names the stance 'defend'.
5. **The cap reads the named list.** The rules cap the support
   attackers, and the engine counts the units the client named, before
   the strike. The oracle counted after the strike. No golden case
   parts the two.
6. **One more golden case left the comparison.**
   'attack_shield_board.json' ran on a board that carried a terrain of
   its own: every damage number of it divides by the scalar rule
   'terrain' 1.25. That rule is gone and no process writes the file
   again (issue #73), so the case is deleted.
   'TestTheSupportDefendWhenAttackTakesTheCounterForTheAttacker' of
   'engine/battle/resolve_test.go' covers the attack shield.
7. **The frozen files still carry two retired fields inside 'rules'.**
   'engine/differential' holds 'terrain' and
   'support_defend_multiplier', so the nine remaining files still
   load. 'protocol.Rules' holds neither.
8. **Which cell keys the damage factor is settled.** The user ruled on
   2026-08-26: the damage ability reads the cell of the target
   ('對水中目標'), and the fire restriction reads the cell of the
   attacker ('攻方自身在水中'). They are two abilities and two
   lookups, not one factor with an open key.
9. **The command 'act' is not here.** It lives in issue #65 with the
   turn cycle. This branch gives 'Board.Apply' and the judgment; #65
   binds them to the wire.
10. **The frozen files lost the weapon field 'blast'.** The terrain
    answer of point 7 does not work here: 'blast' sits inside the unit
    payload of the state, and 'engine/differential' cannot hold it in a
    local struct. The nine files lost the field of each weapon, and
    nothing else of them changed. The two map strike checks of
    'kill_skill_board.json' are deleted, and its note no longer names
    the map strike; the checks after them read the state that the map
    strike wrote.
11. **Issue #75 is superseded by issue #80.** It frames the fire
    restriction as a rule of the board, and it reads three names that
    are gone: 'Weapon.UnusableIn', 'Weapon.UsableIn' and the function
    'mapAttacks' of 'candidates.go'. The user closes it.
12. **The frozen files took a rename, not a rewrite.** The 30 skill
    entries of three golden files now read 'mech' where they read
    'unit'. The value means what it meant when the oracle wrote it;
    only its name changed. Adding a field the oracle never wrote is
    the case that stays refused, and point 13 holds it.
13. **The wire carries no ability field yet.**
    'engine/differential/compare.go' refuses a field the frozen
    expectation does not carry, so a new weapon field fails every
    golden file. Writing the field into those files would make them a
    false record of the retired oracle. Issue #80 settles the harness
    before it changes the wire.

## What issue #65 must change

- Rebase or rebuild on this branch: 'StrikeReactions' and
  'reactionFits' of that branch read the retired reaction list.
- Its Python and page commits belong to issue #78.
