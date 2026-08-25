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

## Change summary

- 'engine/battle/model.go': the fields one engagement reads and
  writes (weapon power, blast, debuff, the rule multipliers, the
  charges, the shield, the interception reduction, the debuff list).
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
- 'engine/differential/resolve_test.go' and three golden boards: the
  resolution against the Python oracle, unit by unit and field by
  field.

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
6. **The command 'act' is not here.** It lives in issue #65 with the
   turn cycle. This branch gives 'Board.Apply' and the judgment; #65
   binds them to the wire.

## What issue #65 must change

- Rebase or rebuild on this branch: 'StrikeReactions' and
  'reactionFits' of that branch read the retired reaction list.
- Its Python and page commits belong to issue #78.
