#!/usr/bin/env python3
"""Extract a skill-source.json from a Markdown output file and validate it.

Usage:
    python3 validate_eval_json.py <output_md_path> <skill_name>

The script finds the first fenced JSON block in the Markdown, writes it to a
temporary skills directory, then runs check_skill_updates.py --validate-only.

Exit codes:
    0: valid
    1: validation error (the checker reported 'error' status)
    2: could not extract JSON from the file
    3: JSON is not valid JSON
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def extract_first_json_block(text: str) -> str | None:
    """Return the contents of the first ```json ... ``` code block."""
    pattern = re.compile(r"```json\s*([\s\S]*?)```", re.MULTILINE)
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def validate(output_md: Path, skill_name: str) -> int:
    if not output_md.is_file():
        print(f"error: output file does not exist: {output_md}", file=sys.stderr)
        return 2

    text = output_md.read_text()
    raw_json = extract_first_json_block(text)
    if raw_json is None:
        # Fall back: try the whole output if it looks like a JSON object or array.
        stripped = text.strip()
        if stripped.startswith(("{", "[")):
            raw_json = stripped
        else:
            print("error: no JSON code block or raw JSON object found in output", file=sys.stderr)
            return 2

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        print(f"error: extracted JSON is not valid: {exc}", file=sys.stderr)
        return 3

    # Write to a temporary skills root: <tmp>/skills/<skill_name>/SKILL.md + skill-source.json
    with tempfile.TemporaryDirectory() as tmp:
        skill_dir = Path(tmp) / skill_name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(f"---\nname: {skill_name}\ndescription: eval temp\n---\n")
        (skill_dir / "skill-source.json").write_text(json.dumps(payload, indent=2))

        checker = Path(__file__).parent.parent.parent / "scripts" / "check_skill_updates.py"
        result = subprocess.run(
            [sys.executable, str(checker), "--skills-root", tmp, "--validate-only"],
            capture_output=True,
            text=True,
        )
        print(result.stdout, end="")
        if result.returncode != 0 or "error" in result.stdout.lower():
            print(result.stderr, end="", file=sys.stderr)
            return 1
        return 0


def main(cli_args: list[str] | None = None) -> int:
    args: list[str] = cli_args if cli_args is not None else sys.argv[1:]
    if len(args) != 2:
        print(f"usage: {Path(sys.argv[0]).name} <output_md_path> <skill_name>", file=sys.stderr)
        return 2
    return validate(Path(args[0]), args[1])


if __name__ == "__main__":
    sys.exit(main())
