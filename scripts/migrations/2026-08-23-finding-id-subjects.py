#!/usr/bin/env python3
"""Re-key labels whose finding id changed when #36 put every subject into the digest.

Only multi-subject findings move: the encoding leaves single-subject ids byte-identical, so 151 of the
176 recorded ids are untouched. This rewrites the remainder in place, and only where the old key can be
*proved* — recomputing it from the record's own `evidence` subjects must reproduce the stored key
exactly. Anything that does not reproduce is left alone and reported, because a label attached to the
wrong finding is worse than a label that no longer resolves.

`prior_key` is kept on each migrated record so the rename stays auditable: these are human review
verdicts and this is the only copy.

Run once, from the archagent repo, against the evaluations data repo. Idempotent.
"""
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from archagent.evaluate import finding_id  # noqa: E402


def old_id(sign: str, subjects: list[str]) -> str:
    """The pre-#36 scheme: the digest hashed the value set only, which for these signs was empty."""
    owner = subjects[0] if subjects else ""
    return f"{sign}:{owner}:{hashlib.sha1(b'').hexdigest()[:8]}"


def main(data_repo: pathlib.Path, apply: bool = False) -> int:
    moved = skipped = 0
    for f in sorted(data_repo.glob("labels/*.jsonl")):
        out, changed = [], False
        for line in f.open():
            s = line.strip()
            if not s:
                out.append(line)
                continue
            d = json.loads(s)
            subs = [x for x in d.get("evidence", "").split("|") if x]
            key, sign = d.get("key", ""), d.get("sign", "")
            if len(subs) > 1 and key and old_id(sign, subs) == key:
                new = finding_id(sign, subs)
                if new != key:
                    d["prior_key"] = key
                    d["key"] = new
                    changed = True
                    moved += 1
                    print(f"  {f.name}: {key} -> {new}  {subs}")
            elif len(subs) > 1 and key and key.endswith("da39a3ee"):
                skipped += 1
                print(f"  ! {f.name}: {key} could not be reproduced from its own evidence — left alone")
            out.append(json.dumps(d, sort_keys=True) + "\n")
        if changed and apply:
            f.write_text("".join(out))
    print(f"\n{moved} label(s) re-keyed, {skipped} left alone{'' if apply else '  (dry run)'}")
    return 0


if __name__ == "__main__":
    repo = pathlib.Path(sys.argv[1]).expanduser()
    main(repo, apply="--apply" in sys.argv)
