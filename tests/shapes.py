"""The shape matrix — one fixture per idiom extraction has to handle.

Issue #45, from `docs/designs/extraction-confidence.md`. Extraction correctness used to be tested by
whichever idioms a cloned repository happened to contain, which is how relative-import resolution in
`__init__.py` stayed broken: all six tuning repositories had an effectively empty package initialiser
(0 relative imports, against httpx's 13). The corpus was *uniform*, not small.

**The decisive property is that a matrix is enumerable.** You can read this table and see which cells are
empty. You cannot read "six repositories" and see what is missing.

Each shape asserts the **extracted graph**, not any finding, so the fixtures stay stable as signals come
and go. Expectations are complete rather than partial — a spurious edge fails the cell as surely as a
missing one — and files with no edges are simply absent from the mapping.

Cost, for the record: the whole table runs in well under a second. litellm alone is 132 MiB and a
~90-second git walk.

Adding a cell: append a `Shape`, and add the same row to the matrix table in the design document. A test
asserts the two agree, so neither can quietly drift from the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Shape:
    #: Must match the shape's row in the design document's matrix table, which is the checklist.
    name: str
    #: Repo-relative path -> file content. A few lines each; no git, no network, no clone.
    files: dict[str, str]
    source_paths: tuple[str, ...] = ("src",)
    root_package: str = "pkg"
    #: file -> the internal files it imports **at runtime**. Complete: anything absent must have no edges.
    runtime: dict[str, set[str]] = field(default_factory=dict)
    #: file -> the internal files it imports only under `if TYPE_CHECKING:`.
    type_only: dict[str, set[str]] = field(default_factory=dict)
    #: What `init` should guess for `python.root_package`, where that is the point of the shape.
    guessed_root_package: str | None = None
    #: Which analyser this cell exercises. The JS/TS scanner is a regex rather than an `ast` walk, so it
    #: has more ways to be quietly wrong, not fewer — and had no fixtures at all until #48.
    languages: tuple[str, ...] = ("python",)
    #: Why this cell exists — the defect it pins, or that it was verified and found already sound.
    note: str = ""


#: Two rules produce the `__init__.py` edges that appear throughout this table, and both are real:
#: importing a name *out of* a package executes that package's initialiser first, whether the import is
#: written absolutely or relatively. The relative form did not produce the edge until #46's coverage
#: counter found the asymmetry on archagent's own source.
#:
#: `from pkg import b` edges to **both** `pkg/__init__.py` and `pkg/b.py`, because importing a name out
#: of a package executes that package's initialiser first. Four cells were written without the
#: initialiser edge on the first pass and the matrix caught it — the expectation was wrong, not the code.
#: Noted here because the tempting repair is the other way round, and removing a real edge to satisfy a
#: fixture is how a graph quietly loses dependencies.


SHAPES: list[Shape] = [
    # --- layout ---------------------------------------------------------------------------
    Shape(
        name="package under `src/`",
        files={"src/pkg/__init__.py": "", "src/pkg/a.py": "from pkg import b\n", "src/pkg/b.py": "x = 1\n"},
        runtime={"src/pkg/a.py": {"src/pkg/b.py", "src/pkg/__init__.py"}},
        guessed_root_package="pkg",
        note="archagent's own layout, and the only one exercised before dspy.",
    ),
    Shape(
        name="package at repository root",
        files={"pkg/__init__.py": "", "pkg/a.py": "from pkg import b\n", "pkg/b.py": "x = 1\n"},
        source_paths=(".",),
        runtime={"pkg/a.py": {"pkg/b.py", "pkg/__init__.py"}},
        guessed_root_package="pkg",
        note="dspy, httpx, requests, flask. `_module_of` built its prefix as `sp + '/'`, so '.' became "
             "'./' and matched nothing — the repository resolved no modules at all and `check` reported "
             "that every invariant held (#42).",
    ),
    Shape(
        name="package one level down (`backend/app`)",
        files={"backend/app/__init__.py": "", "backend/app/main.py": "from app import util\n",
               "backend/app/util.py": "x = 1\n"},
        source_paths=("backend",),
        root_package="app",
        runtime={"backend/app/main.py": {"backend/app/util.py", "backend/app/__init__.py"}},
        guessed_root_package="app",
        note="fastapi-template. `_guess_python_root` searched only `src/` and the repository root, so "
             "this layout left `root_package` unset and every BOUNDARY contract unscoped.",
    ),
    Shape(
        name="two source roots (monorepo)",
        files={"services/api/app/__init__.py": "", "services/api/app/main.py": "from shared import util\n",
               "libs/shared/__init__.py": "", "libs/shared/util.py": "x = 1\n"},
        source_paths=("services/api", "libs"),
        root_package="app",
        runtime={"services/api/app/main.py": {"libs/shared/__init__.py", "libs/shared/util.py"}},
        note="Verified during the retrospective; already sound.",
    ),
    Shape(
        name="dot-directories in paths",
        files={"src/pkg/__init__.py": "", "src/pkg/a.py": "from pkg import b\n", "src/pkg/b.py": "x = 1\n",
               ".github/scripts/helper.py": "x = 1\n"},
        runtime={"src/pkg/a.py": {"src/pkg/b.py", "src/pkg/__init__.py"}},
        note="`_resolve_ref` used `lstrip('./')`, which strips characters rather than a prefix, so "
             "`.github/...` became `github/...` and every reference under a dot-directory was reported "
             "dangling (#43).",
    ),

    # --- package initialisers -------------------------------------------------------------
    Shape(
        name="`__init__.py` star re-export",
        files={"src/pkg/__init__.py": "from ._api import *\n", "src/pkg/_api.py": "x = 1\n"},
        runtime={"src/pkg/__init__.py": {"src/pkg/_api.py"}},
        note="httpx. `level` counts from the containing package and for `__init__.py` the file *is* that "
             "package, so one component too many was stripped and the package root produced no edges at "
             "all — an accurate artifact read as stale, and only an inaccurate one turned `drift` green "
             "(#41).",
    ),
    Shape(
        name="`__init__.py` `from . import x` / `from .m import N`",
        files={"src/pkg/__init__.py": "from . import _auth\nfrom ._client import Client\n",
               "src/pkg/_auth.py": "x = 1\n", "src/pkg/_client.py": "class Client: pass\n"},
        runtime={"src/pkg/__init__.py": {"src/pkg/_auth.py", "src/pkg/_client.py"}},
        note="The same defect as the star form. The star is where it was noticed, not the cause (#41).",
    ),
    Shape(
        name="`from . import <name-defined-in-init>`",
        files={"src/pkg/__init__.py": "__version__ = '1.0'\n",
               "src/pkg/a.py": "from . import __version__\n"},
        runtime={"src/pkg/a.py": {"src/pkg/__init__.py"}},
        note="The imported name is not a submodule, so the only candidate was `pkg.__version__` and the "
             "edge to the initialiser was lost — while the absolute form `from pkg import b` produced "
             "it. Found by the #46 coverage counter on archagent's own source, where it was two of two "
             "unresolved relative imports: a missing edge, not a miscount.",
    ),
    Shape(
        name="relative import at level ≥ 3",
        files={"src/pkg/__init__.py": "", "src/pkg/top.py": "x = 1\n",
               "src/pkg/a/__init__.py": "", "src/pkg/a/b/__init__.py": "",
               "src/pkg/a/b/c.py": "from ...top import x\n"},
        runtime={"src/pkg/a/b/c.py": {"src/pkg/top.py"}},
        note="Guards the other half of the #41 off-by-one: a fix that shifted everything would move the "
             "bug rather than remove it.",
    ),
    Shape(
        name="namespace package (PEP 420)",
        files={"src/pkg/sub/a.py": "from pkg.sub import b\n", "src/pkg/sub/b.py": "x = 1\n"},
        runtime={"src/pkg/sub/a.py": {"src/pkg/sub/b.py"}},
        note="No `__init__.py` anywhere — the default since Python 3.3. Verified; already sound.",
    ),

    # --- type-only imports ------------------------------------------------------------------
    Shape(
        name="`if TYPE_CHECKING:` bare and dotted",
        files={"src/pkg/__init__.py": "",
               "src/pkg/a.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from . import b\n",
               "src/pkg/c.py": "import typing\nif typing.TYPE_CHECKING:\n    from . import b\n",
               "src/pkg/b.py": "x = 1\n"},
        type_only={"src/pkg/a.py": {"src/pkg/b.py", "src/pkg/__init__.py"},
                   "src/pkg/c.py": {"src/pkg/b.py", "src/pkg/__init__.py"}},
        note="A type-only back-edge is how a project *breaks* a real import cycle, so counting one made "
             "the graph most wrong where the code was most careful — a high-confidence cycle that does "
             "not exist at runtime (#37).",
    ),
    Shape(
        name="`TYPE_CHECKING` bound under an alias",
        files={"src/pkg/__init__.py": "",
               "src/pkg/a.py": "from typing import TYPE_CHECKING as TC\nif TC:\n    from . import b\n",
               "src/pkg/b.py": "x = 1\n"},
        type_only={"src/pkg/a.py": {"src/pkg/b.py", "src/pkg/__init__.py"}},
        note="#37 surviving in another spelling. Found by enumerating spellings for this table rather "
             "than by waiting for a repository to use one — which is the argument for the table.",
    ),
    Shape(
        name="`if TYPE_CHECKING: … else:`",
        files={"src/pkg/__init__.py": "",
               "src/pkg/a.py": "from typing import TYPE_CHECKING\n"
                               "if TYPE_CHECKING:\n    from . import c\nelse:\n    from . import b\n",
               "src/pkg/b.py": "x = 1\n", "src/pkg/c.py": "x = 1\n"},
        runtime={"src/pkg/a.py": {"src/pkg/b.py", "src/pkg/__init__.py"}},
        type_only={"src/pkg/a.py": {"src/pkg/c.py", "src/pkg/__init__.py"}},
        note="The runtime import lives in the `else`. Treating the whole statement as type-only would "
             "drop a real edge to fix a false one.",
    ),
    Shape(
        name="`if not TYPE_CHECKING:` stays runtime",
        files={"src/pkg/__init__.py": "",
               "src/pkg/a.py": "from typing import TYPE_CHECKING\nif not TYPE_CHECKING:\n    from . import b\n",
               "src/pkg/b.py": "x = 1\n"},
        runtime={"src/pkg/a.py": {"src/pkg/b.py", "src/pkg/__init__.py"}},
        note="The negated guard makes its body runtime code. Not matching it keeps the real edge, which "
             "is the safe direction: a missed exclusion costs a false positive, a wrong one drops a "
             "dependency.",
    ),

    # --- import forms -----------------------------------------------------------------------
    Shape(
        name="conditional `try/except ImportError` import",
        files={"src/pkg/__init__.py": "",
               "src/pkg/a.py": "try:\n    from . import fast\nexcept ImportError:\n    from . import slow\n",
               "src/pkg/fast.py": "x = 1\n", "src/pkg/slow.py": "x = 1\n"},
        runtime={"src/pkg/a.py": {"src/pkg/fast.py", "src/pkg/slow.py", "src/pkg/__init__.py"}},
        note="Both branches are real dependencies — which one runs is an environment fact. Verified; "
             "already sound.",
    ),
    Shape(
        name="import inside a function body",
        files={"src/pkg/__init__.py": "",
               "src/pkg/a.py": "def f():\n    from . import b\n    return b\n",
               "src/pkg/b.py": "x = 1\n"},
        runtime={"src/pkg/a.py": {"src/pkg/b.py", "src/pkg/__init__.py"}},
        note="A deferred import is still a dependency. Verified; already sound.",
    ),
    Shape(
        name="module shadowing a stdlib name",
        files={"src/pkg/__init__.py": "",
               "src/pkg/json.py": "x = 1\n",
               "src/pkg/a.py": "from . import json\nimport json as stdlib\n"},
        runtime={"src/pkg/a.py": {"src/pkg/json.py", "src/pkg/__init__.py"}},
        note="The relative import resolves internally; the absolute one is the standard library and must "
             "not. Verified; already sound.",
    ),

# --- JS/TS (#48) ------------------------------------------------------------------------
#
# Predicted before probing: re-export barrels would be the defect, by analogy with #41. **Wrong** — the
# regex handles `export * from` because `export` is in the alternation. The two real defects were
# `import type` counted as a runtime dependency, and `tsconfig` path aliases resolving to nothing.
#
# That is the argument for a matrix stated as plainly as it can be: enumerating the idioms found what
# reasoning by analogy did not.

    Shape(
        name="TS: `import type` is not a runtime edge",
        files={"src/a.ts": "import type { Thing } from './b';\nexport const x = 1;\n",
               "src/b.ts": "export type Thing = number;\n"},
        languages=("ts",),
        type_only={"src/a.ts": {"src/b.ts"}},
        note="The TypeScript spelling of `if TYPE_CHECKING:` — erased by the compiler, absent at "
             "runtime, and counted as a dependency until #48. Present in 34 obstudio files and 17 "
             "wardrowbe files, so this was inventing edges across the whole corpus.",
    ),
    Shape(
        name="TS: inline `import { type X, val }` keeps its edge",
        files={"src/a.ts": "import { type Thing, val } from './b';\n",
               "src/b.ts": "export const val = 1;\n"},
        languages=("ts",),
        runtime={"src/a.ts": {"src/b.ts"}},
        note="The inline type modifier still leaves a runtime binding, so the edge is real. Drawing the "
             "line at the statement form rather than the word `type` is what keeps this correct.",
    ),
    Shape(
        name="TS: tsconfig path alias",
        files={"src/a.ts": "import { x } from '@/lib/util';\n",
               "src/lib/util.ts": "export const x = 1;\n",
               "tsconfig.json": '{"compilerOptions":{"paths":{"@/*":["src/*"]}}}\n'},
        languages=("ts",),
        runtime={"src/a.ts": {"src/lib/util.ts"}},
        note="An aliased specifier is bare and looked like an npm package. On wardrowbe **383 of 386 "
             "imports were aliased**, so the frontend graph held 3 edges where it should hold 356 — a "
             "repository already used as a calibration target, blind and silent.",
    ),
    Shape(
        name="TS: re-export barrel",
        files={"src/index.ts": "export * from './a';\nexport { B } from './b';\n",
               "src/a.ts": "export const a = 1;\n", "src/b.ts": "export const B = 2;\n"},
        languages=("ts",),
        runtime={"src/index.ts": {"src/a.ts", "src/b.ts"}},
        note="Predicted to be broken by analogy with #41 and found already sound. Recorded because a "
             "verified cell is the answer to 'did anyone check?' and a wrong prediction is worth "
             "keeping visible.",
    ),
    Shape(
        name="TS: `index.ts` directory resolution",
        files={"src/app.ts": "import { x } from './lib';\n", "src/lib/index.ts": "export const x = 1;\n"},
        languages=("ts",),
        runtime={"src/app.ts": {"src/lib/index.ts"}},
        note="Verified; already sound.",
    ),
    Shape(
        name="TS: `.js` specifier resolving to a `.ts` source",
        files={"src/a.ts": "import { x } from './b.js';\n", "src/b.ts": "export const x = 1;\n"},
        languages=("ts",),
        runtime={"src/a.ts": {"src/b.ts"}},
        note="NodeNext writes the emitted extension. Handled in `_resolve_js` and untested until now.",
    ),
    Shape(
        name="TS: dynamic `import()` and `require()`",
        files={"src/a.ts": "const m = await import('./b');\n", "src/b.ts": "export const x = 1;\n",
               "src/c.js": "const b = require('./d');\n", "src/d.js": "module.exports = 1;\n"},
        languages=("ts",),
        runtime={"src/a.ts": {"src/b.ts"}, "src/c.js": {"src/d.js"}},
        note="Both are real dependencies and both were matched; asserted rather than assumed.",
    ),
]
