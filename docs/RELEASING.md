# Releasing archagent

How to cut a new release to [PyPI](https://pypi.org/project/archagent/). Keep it boring and repeatable.

## Prerequisites (one-time)

- A PyPI API token scoped to the `archagent` project (pypi.org → Account settings → API tokens). Keep it
  out of the repo and out of any shared session — pass it only in your own terminal.
- A clean `main` with everything you want in the release already committed and pushed.

## Steps

1. **Bump the version.** Edit `version` in `pyproject.toml` (semver: patch for fixes, minor for features).
   Update `docs/ROADMAP.md` / any changelog notes if relevant.

2. **Test.**
   ```bash
   uv run pytest -q
   ```

3. **Build a clean set of artifacts.**
   ```bash
   rm -rf dist && uv build          # writes dist/archagent-<version>-py3-none-any.whl + .tar.gz
   ```

4. **Validate the artifacts.**
   ```bash
   uvx twine check dist/*           # README/metadata render on PyPI
   ```
   Sanity-check that the agent templates shipped (they must, or `archagent init` breaks after install):
   ```bash
   python3 -c "import zipfile,glob; z=zipfile.ZipFile(glob.glob('dist/*.whl')[0]); print(sum('templates/' in n for n in z.namelist()), 'template files')"
   ```

5. **Smoke-test the built wheel in a clean environment** — this catches packaging bugs a source-tree run
   won't:
   ```bash
   python3 -m venv /tmp/agx && /tmp/agx/bin/pip -q install dist/*.whl
   /tmp/agx/bin/archagent --help >/dev/null && echo CLI-OK
   mkdir -p /tmp/agxproj/.claude && (cd /tmp/agxproj && /tmp/agx/bin/archagent init . --agents claude)
   ls /tmp/agxproj/.claude/skills /tmp/agxproj/architecture   # skills + scaffold present?
   rm -rf /tmp/agx /tmp/agxproj
   ```

6. **Publish.** (Optional dry run first: `uv publish --publish-url https://test.pypi.org/legacy/ --token <testpypi-token>`.)
   ```bash
   uv publish --token pypi-XXXXXXXX   # or: export UV_PUBLISH_TOKEN=pypi-XXXX && uv publish
   ```
   PyPI versions are **immutable** — you cannot re-upload a version. If something's wrong, bump the version
   and release again.

7. **Verify it's live.**
   ```bash
   uvx archagent@<version> --help
   ```

8. **Commit the bump, tag, and push.**
   ```bash
   git commit -am "release: v<version>"
   git tag -a v<version> -m "archagent <version>"
   git push origin main && git push origin v<version>
   ```

## After a release

Users pick up the new version — and the updated agent prompts, which ship inside the package — with:
```bash
uv tool upgrade archagent     # then, inside each repo:
archagent upgrade             # refresh the installed skills + architecture/AGENTS.md
```
(See the README **Upgrading** section for why it's two steps.)
