# Architecture log

## 2026-08-01 — artifact created

First description of archagent by archagent. Eight subsystems identified from the real import graph
(an `ast` walk over every module in the package), not from memory.

Two observations recorded at creation, both confirmed against the code rather than assumed:

- `drift.py` is a hub: seven modules import it, but most of them want `_git`, `_source_files` or
  `_import_graph` — shared plumbing — rather than the drift check itself. Recorded as ADR 0003.
- `evaluate.py` at 1095 lines is the largest module and imports twelve siblings. It is the composition
  root for the signal families rather than a god object, but it is the first place to watch.
