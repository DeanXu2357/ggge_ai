# Branch roadmap: issue 82, the prologue of a board command

> Type: working—deleted at merge

## Where the branch stands

The branch 'issue-82-open-command' starts from 'dev' (b16a103),
after the merge of #65 (3f04d86). Issue #82 waited for that merge,
because #65 gave the helper its fourth and fifth caller.

## Resume point

The rename landed. The branch waits for the merge review of the
user.

## Progress log

- 2026-08-27: worktree added, roadmap written (4eaeb27).
- The rename: fe98040.

## Change summary

The helper 'boardOf' of 'engine/server/session.go' becomes
'openCommand' and gives the decoded request back as a value.

Before:

    func boardOf[T any](s *Server, id string, payload json.RawMessage,
        into *T) (*battle.Board, *protocol.Response)

After:

    func openCommand[T any](s *Server, id string, payload json.RawMessage) (
        *T, *battle.Board, *protocol.Response)

The helper keeps its three duties in the same order: it refuses a
call that holds no session with 'no_session', it decodes the
payload and refuses a bad one with 'bad_request', and it gives the
board of the session. The request now travels as a return value,
so a caller reads the three results from one line.

Each of the five callers drops its 'var request' line:

    request, board, fail := openCommand[protocol.ActRequest](s, id, payload)

The command 'export' reads no field of its request, so it takes the
request as '_'. The payload still decodes, and a bad payload still
answers 'bad_request'.

The handler 'act' calls 'decodeActivation(request)' in place of
'decodeActivation(&request)', because the request is a pointer now.

## Call chain

    server.act        -> openCommand[protocol.ActRequest]
    server.actions    -> openCommand[protocol.ActionsRequest]
    server.reactions  -> openCommand[protocol.ReactionsRequest]
    server.export     -> openCommand[protocol.ExportRequest]
    server.reach      -> openCommand[protocol.ReachRequest]

    openCommand -> decode -> json.Unmarshal

The commands 'init' and 'load' call 'decode' straight, because each
one builds a session and reads no board.

## Contention points for the reviewer

1. The name. 'openCommand' says the function opens the work of a
   command: the session must hold a board, and the payload must
   decode. The alternative 'boardAndRequest' names the two results
   and not the duties.
2. The out-parameter of 'decode' (session.go:41) stays. That helper
   is the wrapper of 'json.Unmarshal', and 'init' and 'load' call
   it straight. Issue #82 covers the prologue of a board command,
   so the change stops there.
3. The command 'export' takes '_' for its request. The type
   'ExportRequest' holds no field that the handler reads today. A
   named request that nothing reads would not compile.
4. The failure path gives 'nil' for the request and for the board.
   Every caller tests 'fail' first, so no caller reads them.
5. No test changes. The behavior is the same, and the tests of the
   server cover the three duties through the commands.

## Evidence

- 'go vet ./...' and 'go test -race ./...' in 'engine': clean, four
  packages.
- 'uv run pytest -q': 1006 passed, 4 skipped.
- 'uv run ruff check src tests scripts': clean.
