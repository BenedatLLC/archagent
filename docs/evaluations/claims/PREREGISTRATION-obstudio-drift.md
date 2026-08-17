# obstudio drift test — pre-registration

Tests the **narrowed** justification that survived the wardrowbe drift experiment: *a claims file earns its
place where it covers a closed collection archagent's static analysis cannot see.*

## Why obstudio is the right target

obstudio's `archagent.toml` declares `python` and `typescript`. **The whole Go codebase — 57 files,
including every route, every MCP tool, the CLI, and the install machinery — is invisible to `drift`,
`check` and `evaluate`.** The artifact says so itself, in a section headed *"What this artifact can and
cannot check"*. If a claims file has value anywhere, it is here.

wardrowbe had one blind spot (pydantic-settings config keys) discovered post-hoc. obstudio is nothing but
blind spot.

## The change

`88aebe8` → `17797b9`: two commits, three files, 32 insertions — *"feat: add Windsurf install target"*,
plus a changelog line. Small, and precisely on the hypothesis: it adds a fifth member to a closed
collection that lives in Go.

**This is a weak test statistically and a clean one mechanically.** One change, one collection touched.
It can demonstrate that the mechanism works on the class; it cannot estimate a rate, and this document
says so before the result rather than after.

## Disclosure

The wardrowbe experiment used a claims file written before its diff was seen. **That is not true here.** I
sized the diff first and know it adds `windsurf`. To keep the test from being a single cherry-picked
claim, the instrument is:

- **`claims/obstudio-predicates.md`, 15 claims, unchanged** — written days ago for step 1's second attempt,
  before this diff existed. This is the pre-existing half.
- **plus one new `set` claim over the install targets**, written now, knowing the diff. Disclosed as such
  and reported separately from the 15.

The question the combination answers is not "does one claim fire" but **"of the artifact's checkable Go
closed collections, how many does this change touch, and does either instrument catch it?"**

## Procedure

1. Baseline at `88aebe8`: run `drift` and `claims check`, record both.
2. Advance the code to `17797b9`, leaving the artifact and the claims file alone.
3. Run both again; record the delta.
4. Enumerate ground truth from the diff independently.
5. Also record the **coverage** number, which does not depend on the change at all: of the closed
   collections the artifact asserts about Go, how many can `drift` check? The answer is expected to be
   zero, and it is the substantive result whatever the drift delta does.

## Predictions

1. **`drift` reports no change.** The modified files are Go; `drift` does not read them. Its output should
   be byte-identical before and after.
2. **The install-target `set` claim fires**, naming `windsurf` as present in the code and absent from the
   artifact — which is stale in three places (`constitution.md:15`, `observer-cli.md:36-39`,
   `deployment.md:76`).
3. **The other 15 claims do not fire**, because the change touches nothing else they cover.
4. **Coverage: `drift` can check 0 of the artifact's Go closed collections.**

**What would argue against the narrowed justification**: `drift` catching the change anyway, or the claim
firing on something a reader would not act on. **What would argue for it**: a real documentation staleness,
in three places, caught mechanically, that archagent's existing checks structurally cannot reach.
