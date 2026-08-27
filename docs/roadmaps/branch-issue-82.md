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
- The decode in place and the trimmed comment: 29b552f.
- The decode back in the wrapper, with the rule stated: 396631c.
- The absent payload read at the transport: 2944a1e.
- The comments off the two functions: 4b29c24.

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

The prologue carries no comment. The comment it carried stated the
flow that the code states.

The transport takes the rule of the absent payload. The function
'dispatch' of 'engine/server/server.go' parses the envelope, and it
now gives every handler one shape: 'payloadOf' answers an empty
object for a request that carries no 'payload'. The Transport
section of the spec states the rule.

The private wrapper 'decode' is gone. It held the rule, and three
handlers called it; that is a coupling to a function and not a
contract, because a handler written later takes the rule only when
its author copies the call. With the rule at the transport, the
wrapper held 'json.Unmarshal' alone, so the three sites call
'json.Unmarshal'.

## Call chain

    server.act        -> openCommand[protocol.ActRequest]
    server.actions    -> openCommand[protocol.ActionsRequest]
    server.reactions  -> openCommand[protocol.ReactionsRequest]
    server.export     -> openCommand[protocol.ExportRequest]
    server.reach      -> openCommand[protocol.ReachRequest]

    Serve -> dispatch -> payloadOf -> handler

    openCommand -> json.Unmarshal

The commands 'init' and 'load' call 'json.Unmarshal' straight,
because each one builds a session and reads no board.

## Contention points for the reviewer

1. The name. 'openCommand' says the function opens the work of a
   command: the session must hold a board, and the payload must
   decode. The alternative 'boardAndRequest' names the two results
   and not the duties.
2. The rule of the absent payload moved to the transport, and the
   spec gains a sentence in the Transport section. Issue #82 says
   no document change, so this is the one step past its text. The
   reason: the rule held no statement anywhere, and three handlers
   were coupled to one private function in place of a contract.
   The branch reached this in three steps: the decode in place
   (29b552f), the decode back in the wrapper (396631c), and the
   rule at the transport (2944a1e). The test
   'TestABoardCommandTakesALineWithNoPayload' pins the rule: with
   'payloadOf' taken out of 'dispatch', 'export' with no payload
   answers 'bad_request' with the message of an empty input.
3. The command 'export' takes '_' for its request. The type
   'ExportRequest' holds no field that the handler reads today. A
   named request that nothing reads would not compile.
4. The failure path gives 'nil' for the request and for the board.
   Every caller tests 'fail' first, so no caller reads them.
5. One test is new, and it covers the guard of the empty payload.
   The behavior of the five commands is the same, and the tests of
   the server cover the three duties through the commands.

## Evidence

- 'go vet ./...' and 'go test -race ./...' in 'engine': clean, four
  packages.
- 'uv run pytest -q': 1006 passed, 4 skipped.
- 'uv run ruff check src tests scripts': clean.
