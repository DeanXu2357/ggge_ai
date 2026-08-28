# Branch roadmap: issue 87, the command handlers in their own package

> Type: working—deleted at merge

Issue: #87. Branch: issue-87-server-handler. Status: awaiting-review.

## Change summary

| Commit | What |
|---|---|
| 27834ca | This file |
| 9980cea | The seven command bodies and the session move to 'engine/server/handler'; 'server' binds them |
| c82d893 | The registry and its two types private to 'server'; two comments deleted |
| f052ec9 | The last narrating comments deleted; the local that shadowed the 'handler' package renamed |

    engine/server           server.go (New, Serve, dispatch, payloadOf,
                            hello), registry.go (register, binding,
                            command, the 'hello' and 'ping' bindings),
                            commands.go (the seven bindings), the four
                            test files
    engine/server/handler   commands.go (Commands, NewCommands), act.go,
                            candidates.go, initbattle.go, session.go

'server' exports 'New', 'Serve' and 'Server'; 'engine/main.go' calls
the first two. 'handler' exports 'Commands', 'NewCommands' and the
seven commands 'Act', 'Actions', 'Export', 'InitBattle', 'Load',
'Reach', 'ResponseAttacks'; 'server' binds them and nothing else
does. 'server' imports 'protocol' and 'handler'; 'handler' imports
'battle', 'board' (for 'DecodeInit' and 'DecodeState' alone) and
'protocol'. No cycle.

## Call chain

    main.go: server.New().Serve(stdin, stdout)
      New: commands = handler.NewCommands(); for each binding, bind(server)
        register("act", func(s *Server) command { return s.commands.Act })
      Serve -> dispatch(line) -> handlers[cmd](id, payload)
        handler.Commands.Act(id, payload)
          openCommand[ActRequest] -> session, board battle.Board
          board.Act(&request.Action, dice) -> events
          protocol.Ok(id, ActResponse{Events, Board: board.Summary()})

## Verification

- Gates green at 9980cea and c82d893 (the editor's runs); a
  separate run at the last commit is recorded when it lands.
- Wire behaviour unchanged: every server test keeps its assertions;
  the goldens are untouched.
- The main session read 'handler/commands.go', 'server/commands.go',
  'registry.go' and the 'server.go' diff, listed every comment of
  both packages, and the exported surface of both.

## Contention points

1. **The tests stayed in 'server'.** All three command test files
   drive the loop through 'Serve' and assert on the wire reply, so
   they test the transport and the command together. Moving them
   would need a second harness or an external test package that
   imports 'server' back. 'handler' has no test file of its own and
   is covered through the loop.
2. **'Commands' as the state holder.** One value per server holds
   the optional session; each command is a method on it, so a nil
   session still answers 'no_session' as before. The registry stays
   in the transport that dispatches it; the alternative, 'handler'
   registering itself, would make 'handler' import 'server'.
3. **The function type is 'command'.** The registry maps a contract
   command name to it; 'handler' as a name collides with the
   package.

## Deferred

- Nothing. The order was: after #85 merges, to keep 'act.go' from a
  second rebase; the two branches touched different packages, and
  only the "Process model" bullet of the spec is shared.
