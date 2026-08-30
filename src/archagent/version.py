"""The running build's version, as a leaf.

Split out of `__init__.py` because reading it created an upward dependency. `graph.py` stamps the tool
version into a generated map, and `from . import __version__` made the `reporting` subsystem (domain)
import the package root, which the model groups with `cli` (ui) — a layer inversion whose substance was
false, since what `graph` needs is the version and not the command line.

Found by #46's import coverage counter: `from . import __version__` was two of two unresolved relative
imports on archagent's own source, which turned out to be a missing edge rather than a miscount. Adding
the edge made the modelling problem visible, and this module is the fix for it.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    #: Read from the installed distribution rather than hard-coded, so it cannot drift from the wheel
    #: that is actually running. That is the whole point of `--version`: `docs/RELEASING.md` step 7
    #: verifies a release by running the CLI, which proves *a* build starts and cannot say which one.
    __version__ = _pkg_version("archagent")
except PackageNotFoundError:                       # a source tree with nothing installed
    __version__ = "0+unknown"

__all__ = ["__version__"]
