#!/usr/bin/env python3
"""Remove skill directories created as side effects of eval executor runs.

Eval executors sometimes create real files on disk while acting out a task
(e.g., writing skill-source.json next to SKILL.md). This script removes any
directory under the skills root that is not the canonical skill directory.

Usage:
    python3 cleanup_eval_artifacts.py [--skills-root SKILLS_ROOT] [--dry-run]

Exit codes:
    0: clean (or dry-run complete)
    1: one or more unexpected directories were found (even in dry-run mode)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

CANONICAL_SKILLS = {"skill-provenance"}


def cleanup(skills_root: Path, dry_run: bool) -> int:
    if not skills_root.is_dir():
        print(f"error: skills root does not exist: {skills_root}", file=sys.stderr)
        return 2

    artifacts = [
        d for d in sorted(skills_root.iterdir())
        if d.is_dir() and d.name not in CANONICAL_SKILLS
    ]

    if not artifacts:
        print("clean: no eval artifacts found")
        return 0

    for artifact in artifacts:
        if dry_run:
            print(f"would remove: {artifact}")
        else:
            shutil.rmtree(artifact)
            print(f"removed: {artifact}")

    return 1  # signal that artifacts existed (useful for CI checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", default="skills", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Report but do not delete")
    args = parser.parse_args(argv)
    return cleanup(args.skills_root, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
