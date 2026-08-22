"""archagent — keep code adherent to a described architecture."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

from .cli import main

try:
    #: Read from the installed distribution rather than hard-coded here, so it cannot drift from the
    #: wheel that is actually running. That is the whole point of `--version`: `docs/RELEASING.md` step 7
    #: verifies a release by running the CLI, which proves *a* build starts and cannot say which one.
    __version__ = _pkg_version("archagent")
except PackageNotFoundError:                       # running from a source tree with nothing installed
    __version__ = "0+unknown"

__all__ = ["main", "__version__"]
