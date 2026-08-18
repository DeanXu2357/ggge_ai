# Branch roadmap: issue 69, the battle engine shell

> Type: working—deleted at merge

## Change summary

The branch lands the process that serves the contract of
'docs/spec/battle-engine-protocol.md'. It lands the transport and
two commands. It lands no board and no rule.

New, Go:

- 'engine/go.mod', module github.com/DeanXu2357/ggge_ai/engine.
- 'engine/protocol/envelope.go': the request, the response, the
  error, and the seven error codes.
- 'engine/protocol/commands.go': the sixteen declared names and
  'IsDeclared'.
- 'engine/protocol/types.go': the decide contract and the request
  and response struct of every declared command.
- 'engine/server/server.go': the stdio loop and the handler
  registry.
- 'engine/main.go'.

New, Python:

- 'src/ggge_ai/engine/contract.py': the same types.
- 'src/ggge_ai/engine/client.py': 'BattleEngine'.

Changed:

- 'tests/test_package_boundary.py' puts the new package under the
  import gate.
- 'docs/how-to/development-flow.md' records the two Go gates.

## Call chain

A client starts the executable. 'BattleEngine.call' writes one
line and reads one line.

'Server.Serve' reads a line and calls 'dispatch'. 'dispatch' finds
a handler, or answers 'not_implemented' for a declared name, or
answers 'unknown_command'. A port issue calls 'Handle' to add a
command; it changes no line of the loop.

## Contention points

1. A cell is a pair on the wire, not an object with x and y. The
   contract does not fix the shape. The pair matches
   'sandbox/model.py', where a cell is a tuple, so the codec of #60
   needs no conversion.
2. The forced dice input takes named outcomes, not draws. A draw
   does not show which path a test forces, and #67 forces the
   worst outcome by name. The port issues own the names.
3. A stage holds a list of victory conditions, in 'init' and in
   the goal of 'advice'. One entry holds one condition.
4. An answer with the wrong id raises 'EngineDead'. The stream is
   out of step at that moment, so the process is not usable.
5. The new modules carry English docstrings. The older modules
   carry Traditional Chinese. The project rule asks for English in
   new documents; the code rule names no language.

## Verification

- cd engine && go vet ./... : no finding.
- cd engine && go test ./... : ok.
- uv run ruff check src tests scripts : all checks passed.
- uv run pytest -q : 1078 passed, 4 skipped.

The seven behavior rules of the contract are pinned two times: as
Go tests against 'Server.Serve', and as Python tests through the
built executable. The Go set holds a line of 1 MiB, above the
default scanner limit. The Python set holds a killed process and a
mute process.
