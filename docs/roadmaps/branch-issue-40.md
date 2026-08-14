# Branch roadmap — issue 40: sandbox query contract

> Type: working—deleted at merge

## Goal

Implement the 'Sandbox' facade and the query contract from issue
#40. After initialization, consumers outside the sandbox package
touch only the facade. 'scripts/sandbox_ui.py' becomes an HTTP and
HTML shell.

## Plan

1. New module 'src/ggge_ai/sandbox/facade.py': class 'Sandbox',
   decision payload types, aggregate action enumeration, reaction
   enumeration, read methods, act method, optional advisor slot.
2. Move serialization from 'scripts/sandbox_ui.py' into the package.
3. Reduce the script to routing and HTML.
4. Tests: aggregate output versus the piecewise enumerators; facade
   reads; the script imports only the facade.

## Resume point

Step 1 is done: the facade and its tests are in place. Next: step 2
and step 3, the script becomes a shell.

## Progress log

- 2026-08-14: branch created, roadmap written.
- 2026-08-14: 'sandbox/facade.py' added. The class 'Sandbox' holds
  the scenario products, serializes the board, aggregates the
  activation candidates and the reaction options, and applies one
  decision through 'step'. The candidate order is the concatenation
  of the piecewise enumerators, so 'advice.pricing' aligns with it.
  New test file 'tests/test_sandbox_facade.py'. Terminology map: new
  entries for 'sandbox facade', 'decision payload', 'activation'.
