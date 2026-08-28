# Branch roadmap: issue 87, the command handlers in their own package

> Type: working—deleted at merge

## Where the branch stands

The branch 'issue-87-server-handler' starts from 'dev' (1b63a85),
after the merge of #86. It runs in parallel with #85: the two
branches touch different packages, and their one shared line is
the "Process model" bullet of the spec.

## What the code is today

'engine/server' holds nine command handlers, each a method on
'*Server' because it reads and writes 's.session', each registered
by an 'init()' in its own file through 'Register(name, Binding)'.
'server.go' holds the transport ('New', 'Serve', 'dispatch',
'payloadOf', 'Handle') and 'registry.go' the binding table. Only
'engine/main.go' imports the package: 'server.New().Serve(...)'.

## Plan

1. 'engine/server/handler' takes every handler body and what the
   handlers touch: the session type, 'newSession', 'openCommand',
   'activationOf', 'openDice', 'refusalCode'. 'engine/server' keeps
   the transport and the registry. The import runs 'server' ->
   'handler' -> 'battle', 'board', 'protocol'; nothing the other
   way.
2. The shape of the binding is the branch's to settle under the
   rules of 0828: the handler package exports what 'server' binds
   and nothing else; identifiers name their owner; no comment
   beyond the two kinds.
3. The spec names the package. Gates, review, artifact.

## Resume point

Step 1 is delegated to the code editor.

## Progress log

- 2026-08-28: worktree added, roadmap written.
