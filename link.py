#!/usr/bin/env python3
"""link.py — materialize each system's manifest into symlinks.

The repo commits only the *recipe*: a system's manifest.yaml lists exactly which
skills and agents (by name + semver) it uses. This script reads the manifest,
finds each piece's one canonical copy (skills in skills-library/, agents in the
top-level agents-library/), and creates a symlink under the system's .claude/skills
(and .claude/agents). Those symlinks are the
regenerable *cake* — git-ignored, rebuilt on demand after a clone.

Relative link targets are always computed with os.path.relpath — never hand-written
— so the tree relocates cleanly.

Usage:
    python link.py                 # link every system under systems/
    python link.py idea-sourcing   # link one system
    python link.py --check         # validate manifests vs library, link nothing
"""
from __future__ import annotations

import argparse
import os
import sys

REPO = os.path.dirname(os.path.realpath(__file__))
LIB = os.path.join(REPO, "skills-library")
# Agents live in their own top-level library (sibling of skills-library), not inside it.
AGENTS_LIB = os.path.join(REPO, "agents-library")
SYSTEMS = os.path.join(REPO, "systems")


def _load_yaml(path):
    import yaml
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def _frontmatter(md_path) -> dict:
    """Parse the YAML frontmatter block of a SKILL.md / agent .md."""
    import yaml
    text = open(md_path).read()
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    return yaml.safe_load(text[3:end]) or {}


def index_library() -> tuple[dict, dict]:
    """Map skill-name -> {dir, version} (from skills-library/) and
    agent-name -> {file, version} (from the top-level agents-library/)."""
    skills, agents = {}, {}
    for root, _dirs, files in os.walk(LIB):
        if "SKILL.md" in files:
            fm = _frontmatter(os.path.join(root, "SKILL.md"))
            name = fm.get("name") or os.path.basename(root)
            skills[name] = {"dir": root, "version": str(fm.get("version", "0.0.0"))}
    agents_dir = AGENTS_LIB
    if os.path.isdir(agents_dir):
        for f in os.listdir(agents_dir):
            if f.endswith(".md") and f != "README.md":
                fm = _frontmatter(os.path.join(agents_dir, f))
                name = fm.get("name") or f[:-3]
                agents[name] = {"file": os.path.join(agents_dir, f),
                                "version": str(fm.get("version", "0.0.0"))}
    return skills, agents


def _symlink(target: str, link_path: str) -> None:
    os.makedirs(os.path.dirname(link_path), exist_ok=True)
    if os.path.islink(link_path) or os.path.exists(link_path):
        if os.path.islink(link_path):
            os.unlink(link_path)
        else:
            raise SystemExit(f"refusing to overwrite non-symlink {link_path}")
    rel = os.path.relpath(target, os.path.dirname(link_path))  # never hand-written
    os.symlink(rel, link_path)


def link_system(name: str, skills_idx: dict, agents_idx: dict, check: bool) -> list:
    sys_dir = os.path.join(SYSTEMS, name)
    manifest_path = os.path.join(sys_dir, "manifest.yaml")
    if not os.path.exists(manifest_path):
        return [f"  ! {name}: no manifest.yaml"]
    man = _load_yaml(manifest_path)
    notes = []
    skills_link_root = os.path.join(sys_dir, ".claude", "skills")
    agents_link_root = os.path.join(sys_dir, ".claude", "agents")

    for entry in man.get("skills", []) or []:
        sname = entry["name"] if isinstance(entry, dict) else entry
        want = str(entry.get("version")) if isinstance(entry, dict) else None
        hit = skills_idx.get(sname)
        if not hit:
            notes.append(f"  ✗ skill '{sname}' NOT in library")
            continue
        if want and want != hit["version"]:
            notes.append(f"  ! skill '{sname}' manifest {want} != library {hit['version']}")
        if not check:
            _symlink(hit["dir"], os.path.join(skills_link_root, sname))
        notes.append(f"  ✓ skill {sname}@{hit['version']}")

    for entry in man.get("agents", []) or []:
        aname = entry["name"] if isinstance(entry, dict) else entry
        want = str(entry.get("version")) if isinstance(entry, dict) else None
        hit = agents_idx.get(aname)
        if not hit:
            notes.append(f"  ✗ agent '{aname}' NOT in library")
            continue
        if want and want != hit["version"]:
            notes.append(f"  ! agent '{aname}' manifest {want} != library {hit['version']}")
        if not check:
            _symlink(hit["file"], os.path.join(agents_link_root, aname + ".md"))
        notes.append(f"  ✓ agent {aname}@{hit['version']}")
    return notes


def main():
    ap = argparse.ArgumentParser(description="Materialize system symlinks from manifests.")
    ap.add_argument("system", nargs="?", help="one system name (default: all)")
    ap.add_argument("--check", action="store_true", help="validate only, link nothing")
    args = ap.parse_args()

    skills_idx, agents_idx = index_library()
    targets = ([args.system] if args.system
               else sorted(d for d in os.listdir(SYSTEMS)
                           if os.path.isdir(os.path.join(SYSTEMS, d))))
    bad = 0
    for name in targets:
        print(f"{name}:")
        for line in link_system(name, skills_idx, agents_idx, args.check):
            print(line)
            if "✗" in line:
                bad += 1
    print(f"\nlibrary: {len(skills_idx)} skills, {len(agents_idx)} agents indexed.")
    if bad:
        print(f"{bad} missing reference(s).")
        sys.exit(1)


if __name__ == "__main__":
    main()
