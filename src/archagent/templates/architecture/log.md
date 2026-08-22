# Architecture Log

Append-only, chronological. One line per change, newest at the bottom. Grep/tail friendly:
each entry starts `## [YYYY-MM-DD] <kind> | <summary>`.

**A `describe` entry records what produced it** — the target revision and the archagent version
(`archagent --version`). Every claim in this artifact is relative to both, and a reader hitting a command
this artifact cites but their build does not have needs to be able to tell version skew from a stale
document.

## [DATE] init | archagent scaffolding created
