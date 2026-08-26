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
3. It picked the support units itself: the first eligible interceptor,
   and every eligible support attacker on one boolean.

Everything else of that branch is a consumer of a client-composed
action, which is the side of the ruling the engine keeps. The damage,
the hit rate, the stance multipliers, the debuff rules, the chance
nodes and the resolution order came over as they stood.

## What the user ruled on 2026-08-25

| Question | Ruling |
|---|---|
| Support granularity | The client names each interceptor and each support attacker. The engine picks none. |
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
        namedAttackShield
        answerOf
          CounterWeapon
          namedInterceptor
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
2. **An interceptor of the defending side carries no hit rate.** The
   stance settles that hit roll. An interceptor of the attacking side
   carries no forecast at all, because the defender picks which weapon
   counters.
3. **The stand with an interceptor stays legal.**
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
   'TestTheAttackShieldTakesTheCounterForTheAttacker' of
   'engine/battle/resolve_test.go' covers the attack shield.
7. **The frozen files still carry 'terrain' inside 'rules'.**
   'engine/differential' holds the field, so the nine remaining files
   still load. 'protocol.Rules' holds it no more.
8. **Which cell keys the damage factor is open.** The code reads the
   cell of the target, which docs/reference/combat-formulas.md records
   from the first-hand confirmation of 2026-08-21. The same datamine
   table gives the cell of the attacker as the fire gate
   ('unusable_in', issue #75). The contract carries both cells, so the
   answer moves one lookup.
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
11. **Issue #75 reads three names that are gone.**
    'Weapon.UnusableIn', 'Weapon.UsableIn' and the function 'mapAttacks'
    of 'candidates.go' are all retired. That issue needs a rewrite
    against issue #79.

## What issue #65 must change

- Rebase or rebuild on this branch: 'StrikeReactions' and
  'reactionFits' of that branch read the retired reaction list.
- Its Python and page commits belong to issue #78.
