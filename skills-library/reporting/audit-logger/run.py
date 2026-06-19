"""audit-logger: record what was done and why as a timestamped audit entry; list entries."""
import argparse
import os
import sys

# --- locate the shared library (_shared/) whether run from its canonical path,
# --- a system's symlinked .claude/skills, or a standalone bundle -------------
_here = os.path.realpath(__file__)
_root = os.environ.get("IM_LIB_ROOT", "")
if not _root:
    _d = os.path.dirname(_here)
    while _d != os.path.dirname(_d):
        if os.path.isdir(os.path.join(_d, "_shared", "data-fetch")):
            _root = _d
            break
        _d = os.path.dirname(_d)
for _p in ("data-fetch", "router", "web-search"):
    _cand = os.path.join(_root, "_shared", _p)
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)

from imdata import skillkit, store


def main(args):
    if args.list:
        rows = store.list_audit(args.limit)
        entries = skillkit.as_dicts(rows)
        summary = (
            f"{len(entries)} recent audit entr{'y' if len(entries) == 1 else 'ies'} "
            f"(limit {args.limit})."
        )
        return {"entries": entries, "count": len(entries), "summary": summary}

    if not args.action:
        raise ValueError("--action is required unless --list is set.")

    entry_id = store.append_audit(args.actor, args.action, args.target, args.detail)
    row = store.get_conn().execute(
        "SELECT * FROM audit_log WHERE id = ?", (entry_id,)
    ).fetchone()
    entry = skillkit.as_dict(row)

    summary = (
        f"Logged #{entry['id']} at {entry['ts']}: {args.actor} {args.action}"
        + (f" on {args.target}" if args.target else "")
        + (f" - {args.detail}" if args.detail else "") + "."
    )
    return {
        "id": entry["id"],
        "ts": entry["ts"],
        "actor": entry["actor"],
        "action": entry["action"],
        "target": entry["target"],
        "detail": entry["detail"],
        "summary": summary,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Record a timestamped audit entry, or list recent entries."
    )
    p.add_argument("--actor", default="analyst")
    p.add_argument("--action", default=None, help="required unless --list")
    p.add_argument("--target", default="")
    p.add_argument("--detail", default="")
    p.add_argument("--list", action="store_true",
                   help="return recent entries instead of writing")
    p.add_argument("--limit", type=int, default=20)
    skillkit.run(main, p)
