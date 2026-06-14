#!/usr/bin/env python3
"""Report cheap update signals for skill-source.json sidecars."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

FORBIDDEN_KEYS = {
    "gitEvidence",
    "recentHistory",
    "evidence",
    "reviewNote",
    "commitSubject",
    "commitSubjects",
    "confidence",
    "confidenceLabel",
    "diagnostics",
    "reviewDiagnostics",
}

SOURCE_TYPES = {"upstream-skill", "upstream-reference", "local-original-content"}
SOURCE_ROLES = {"upstream-source", "supporting-reference", "original-content"}
VERSION_SOURCES = {"frontmatter", "gitCommit", "fetchDate"}


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    stdout: str
    stderr: str


CommandRunner = Callable[[list[str], str | None], CommandResult]
HttpGetter = Callable[[str, dict[str, str]], str]


def run_command(command: list[str], cwd: str | None = None) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        return CommandResult(ok=False, stdout="", stderr=str(error))
    return CommandResult(
        ok=completed.returncode == 0,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def default_http_get(url: str, headers: dict[str, str]) -> str:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def iter_skill_sources(skills_root: Path) -> Iterable[tuple[str, Path, dict]]:
    if not skills_root.is_dir():
        raise ValueError(f"skills root does not exist or is not a directory: {skills_root}")
    skill_dirs = sorted(
        path for path in skills_root.iterdir() if path.is_dir() and (path / "SKILL.md").is_file()
    )
    if not skill_dirs:
        raise ValueError(f"no skill directories found under: {skills_root}")
    for skill_dir in skill_dirs:
        source_file = skill_dir / "skill-source.json"
        if not source_file.is_file():
            yield skill_dir.name, source_file, {"__error__": "skill directory missing skill-source.json"}
            continue
        try:
            payload = json.loads(source_file.read_text())
        except json.JSONDecodeError as error:
            yield skill_dir.name, source_file, {"__error__": f"Invalid JSON: {error}"}
            continue
        yield skill_dir.name, source_file, payload


def parse_utc_datetime(dt_str: str) -> datetime | None:
    dt_str = dt_str.strip()
    if not dt_str:
        return None
    # Replace space with T
    dt_str = dt_str.replace(" ", "T")
    # Replace Z with +00:00 for robust parsing across python versions
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"

    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M%z",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(dt_str, fmt)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            else:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def compare_dates(
    latest_date_str: str,
    fetched_at_str: str,
    is_frontmatter: bool,
) -> tuple[str, str | None] | None:
    latest_parsed = parse_utc_datetime(latest_date_str)
    fetched_parsed = parse_utc_datetime(fetched_at_str)
    
    if not fetched_parsed:
        return "error", f"fetchedAt has an invalid date/time format: {fetched_at_str}"
    if not latest_parsed:
        return "unknown", f"could not parse latest commit date: {latest_date_str}"

    is_date_only = (
        "T" not in fetched_at_str
        and " " not in fetched_at_str
        and len(fetched_at_str.strip()) == 10
    )
    if is_date_only:
        latest_utc_date_str = latest_parsed.strftime("%Y-%m-%d")
        if latest_utc_date_str == fetched_at_str.strip():
            prefix = "Frontmatter unchanged; " if is_frontmatter else ""
            return (
                "unknown",
                f"{prefix}date-only fetchedAt cannot disambiguate same-day source changes",
            )

    if latest_parsed > fetched_parsed:
        note = (
            "Frontmatter unchanged but source path changed after fetchedAt"
            if is_frontmatter
            else None
        )
        return "candidate", note

    return "up-to-date", None


def collect_report(
    skills_root: Path,
    command_runner: CommandRunner = run_command,
    http_get: HttpGetter = default_http_get,
    validate_only: bool = False,
) -> list[dict]:
    rows: list[dict] = []
    for skill, source_file, payload in iter_skill_sources(skills_root):
        if isinstance(payload, dict) and "__error__" in payload:
            rows.append(error_row(skill, source_file, 0, payload["__error__"]))
            continue
        validation_error = validate_sidecar(skill, payload)
        if validation_error:
            rows.append(error_row(skill, source_file, 0, validation_error))
            continue
        if validate_only:
            rows.append(validation_row(skill, source_file))
            continue
        for index, source in enumerate(payload["sources"]):
            try:
                rows.append(
                    check_source(
                        skill=skill,
                        source_file=source_file,
                        index=index,
                        source=source,
                        command_runner=command_runner,
                        http_get=http_get,
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                rows.append(error_row(skill, source_file, index, str(error), source))
    return rows


def validate_sidecar(skill: str, payload: object) -> str | None:
    if not isinstance(payload, dict):
        return "skill-source.json must be a top-level JSON object"
    forbidden_path = find_forbidden_key(payload)
    if forbidden_path:
        return f"skill-source.json contains reconstruction-only key '{forbidden_path}'"
    declared_skill = non_blank_string(payload, "skill")
    if not declared_skill:
        return "missing top-level skill"
    if declared_skill != skill:
        return f"skill-source.json declares skill '{declared_skill}'"
    if payload.get("schemaVersion") != 1:
        return "schemaVersion must be 1"
    sources = payload.get("sources")
    if not isinstance(sources, list):
        return "sources must be a list"
    if not sources:
        return "sources must not be empty"
    has_external_source = False
    for index, source in enumerate(sources):
        error = validate_source(index, source)
        if error:
            return error
        if source["role"] in {"upstream-source", "supporting-reference"}:
            has_external_source = True
    attribution = payload.get("attribution")
    if has_external_source and not (isinstance(attribution, str) and attribution.strip()):
        return "external sources require top-level attribution"
    return None


def validate_source(index: int, source: object) -> str | None:
    if not isinstance(source, dict):
        return f"source[{index}] must be an object"
    missing_fields = [
        field
        for field in ("type", "role", "label", "version", "versionSource", "fetchedAt", "license")
        if not non_blank_string(source, field)
    ]
    if missing_fields:
        return f"source[{index}] missing required field(s): " + ", ".join(missing_fields)

    fetched_at = source["fetchedAt"]
    if not parse_utc_datetime(fetched_at):
        return f"source[{index}] fetchedAt has an invalid date/time format: {fetched_at}"

    source_type = source["type"]
    role = source["role"]
    version_source = source["versionSource"]
    if source_type not in SOURCE_TYPES:
        return f"source[{index}] has unsupported type '{source_type}'"
    if role not in SOURCE_ROLES:
        return f"source[{index}] has unsupported role '{role}'"
    if (role == "original-content") != (source_type == "local-original-content"):
        return f"source[{index}] has inconsistent role '{role}' and type '{source_type}'"
    if version_source not in VERSION_SOURCES:
        return f"source[{index}] has unsupported versionSource '{version_source}'"

    is_external_source = role in {"upstream-source", "supporting-reference"}
    url = non_blank_string(source, "url")
    if is_external_source and not url:
        return f"source[{index}] must define canonical url for external sources"
    check = source.get("check")
    if check is None:
        if is_external_source and is_recoverable_github_source_url(url):
            return f"source[{index}] references GitHub and must define check metadata"
        return None
    if not isinstance(check, dict):
        return f"source[{index}] check must be an object"
    check_type = non_blank_string(check, "type")
    if check_type == "github":
        missing: list[str] = [
            field for field in ("repository", "path", "trackingRef") if not non_blank_string(check, field)
        ]
        if version_source == "frontmatter" and not non_blank_string(check, "frontmatterPath"):
            missing.append("frontmatterPath")
        if missing:
            return f"source[{index}] github check missing required field(s): " + ", ".join(missing)
    elif check_type == "manual":
        if not non_blank_string(check, "reason"):
            return f"source[{index}] manual check missing reason"
        if is_recoverable_github_source_url(url):
            return f"source[{index}] has a recoverable GitHub URL and should use github check metadata"
    else:
        return f"source[{index}] has unsupported check type '{check_type}'"
    return None


def non_blank_string(payload: dict, key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def find_forbidden_key(value: object, path: str = "") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_KEYS:
                return child_path
            found = find_forbidden_key(child, child_path)
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = find_forbidden_key(child, f"{path}[{index}]")
            if found:
                return found
    return None


_GITHUB_TREE_PATH_TYPES = frozenset({"tree", "blob"})


def is_recoverable_github_source_url(url: str) -> bool:
    """Return True only for GitHub tree/blob URLs that have an extractable file-path segment.

    A URL is recoverable only when it encodes all three components needed for a github
    check block: repository (owner/repo), trackingRef (branch/commit), and path
    (at least one path segment after the ref). Issue, PR, release, discussion, bare
    repo, and tag URLs cannot express a check.path, so they require a manual check.
    """
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.lower() != "github.com":
        return False
    parts = [p for p in parsed.path.split("/") if p]
    # Need owner/repo/tree-or-blob/ref/path... (≥5 parts: path must be non-empty)
    return len(parts) >= 5 and parts[2] in _GITHUB_TREE_PATH_TYPES


def validation_row(skill: str, source_file: Path) -> dict:
    row = base_row(skill, source_file, 0, {})
    row["status"] = "valid"
    row["notes"] = "sidecar passed validation"
    return row


def error_row(
    skill: str,
    source_file: Path,
    index: int,
    notes: str,
    source: dict | None = None,
) -> dict:
    row = base_row(skill, source_file, index, source or {})
    row["status"] = "error"
    row["notes"] = notes
    return row


def check_source(
    skill: str,
    source_file: Path,
    index: int,
    source: dict,
    command_runner: CommandRunner,
    http_get: HttpGetter,
) -> dict:
    row = base_row(skill, source_file, index, source)
    if source.get("role") == "original-content":
        row["status"] = "local-original"
        row["notes"] = "Original local content; not an upstream update candidate"
        return row

    check = source.get("check") or {}
    check_type = check.get("type")
    if check_type == "manual" or not check:
        row["status"] = "skipped"
        row["notes"] = check.get("reason") or "No automated check configured"
        return row
    if check_type != "github":
        row["status"] = "skipped"
        row["notes"] = f"Unsupported check type: {check_type}"
        return row

    row["warnings"].extend(local_checkout_warnings(check, command_runner, base_dir=source_file.parent))
    version_source = source.get("versionSource")
    if version_source == "frontmatter":
        latest = latest_frontmatter_version(check, command_runner, http_get, base_dir=source_file.parent)
        if latest is None:
            row["status"] = "unknown"
            row["notes"] = "GitHub and local checkout checks failed"
            return row
        latest_version, upstream_author, checked_by = latest
        row["latestVersion"] = latest_version
        row["checkedBy"] = checked_by
        if upstream_author:
            row["upstreamAuthor"] = upstream_author
        if latest_version != source.get("version"):
            row["status"] = "candidate"
            return row
        latest_commit = latest_github_commit_metadata(check, command_runner, http_get, base_dir=source_file.parent)
        if latest_commit is None:
            row["status"] = "unknown"
            row["notes"] = "Frontmatter unchanged but source path commit freshness could not be established"
            return row
        latest_sha, checked_commit_by, latest_date = latest_commit
        row["latestCommit"] = latest_sha
        fetched_at = str(source.get("fetchedAt") or "")
        if latest_date is None and checked_commit_by == "local-checkout":
            row["status"] = "unknown"
            row["notes"] = "Frontmatter unchanged; local checkout fallback cannot compare commit date"
            return row
        if latest_date and fetched_at:
            comparison = compare_dates(latest_date, fetched_at, is_frontmatter=True)
            if comparison:
                status, notes = comparison
                row["status"] = status
                if notes:
                    row["notes"] = notes
                return row
        row["status"] = "up-to-date"
        return row
    if version_source == "gitCommit":
        latest = latest_github_commit(check, command_runner, http_get, base_dir=source_file.parent)
    elif version_source == "fetchDate":
        latest_commit = latest_github_commit_metadata(check, command_runner, http_get, base_dir=source_file.parent)
        if latest_commit is None:
            row["status"] = "unknown"
            row["notes"] = "Fetch-date source commit freshness could not be established"
            return row
        latest_sha, checked_commit_by, latest_date = latest_commit
        row["latestCommit"] = latest_sha
        row["checkedBy"] = checked_commit_by
        fetched_at = str(source.get("fetchedAt") or source.get("version") or "")
        if latest_date and fetched_at:
            comparison = compare_dates(latest_date, fetched_at, is_frontmatter=False)
            if comparison:
                status, notes = comparison
                row["status"] = status
                if notes:
                    row["notes"] = notes
                return row
        if latest_date is None:
            row["status"] = "unknown"
            row["notes"] = "Fetch-date source has no comparable commit date"
            return row
        row["status"] = "up-to-date"
        return row
    else:
        row["status"] = "skipped"
        row["notes"] = f"Pinned by {version_source} version; no comparable cheap signal"
        return row
    if latest is None:
        row["status"] = "unknown"
        row["notes"] = "GitHub and local checkout checks failed"
        return row

    latest_version, checked_by = latest
    row["latestVersion"] = latest_version
    row["checkedBy"] = checked_by
    row["status"] = "up-to-date" if latest_version == source.get("version") else "candidate"
    return row


def base_row(skill: str, source_file: Path, index: int, source: dict) -> dict:
    return {
        "skill": skill,
        "sourceFile": str(source_file),
        "sourceIndex": index,
        "label": source.get("label", "<unlabelled>"),
        "role": source.get("role"),
        "currentVersion": source.get("version"),
        "versionSource": source.get("versionSource"),
        "status": "unknown",
        "latestVersion": None,
        "latestCommit": None,
        "checkedBy": None,
        "upstreamAuthor": None,
        "warnings": [],
        "notes": "",
    }


def latest_frontmatter_version(
    check: dict,
    command_runner: CommandRunner,
    http_get: HttpGetter,
    base_dir: Path | None = None,
) -> tuple[str, str | None, str] | None:
    """Return (version, author_or_None, checked_by) from the upstream SKILL.md."""
    frontmatter_path = frontmatter_path_for_check(check)
    content = github_file_content(check, frontmatter_path, command_runner, http_get)
    if content is not None:
        raw = content[0]
        version = parse_frontmatter_version(raw)
        if version:
            return version, parse_frontmatter_author(raw), content[1]
    return local_frontmatter_version(check, frontmatter_path, command_runner, base_dir=base_dir)


def frontmatter_path_for_check(check: dict) -> str:
    configured_path = check.get("frontmatterPath")
    if isinstance(configured_path, str) and configured_path.strip():
        return configured_path.strip()
    path = check["path"].rstrip("/")
    return path if path.endswith(".md") else f"{path}/SKILL.md"


def github_file_content(
    check: dict,
    path: str,
    command_runner: CommandRunner,
    http_get: HttpGetter,
) -> tuple[str, str] | None:
    repository = check["repository"]
    tracking_ref = check["trackingRef"]
    api_path = f"repos/{repository}/contents/{urllib.parse.quote(path, safe='/')}"
    api_path_with_query = f"{api_path}?{urllib.parse.urlencode({'ref': tracking_ref})}"

    gh_result = command_runner(["gh", "api", api_path_with_query], None)
    if gh_result.ok:
        content = decode_github_content_response(gh_result.stdout)
        if content is not None:
            return content, "gh-frontmatter"

    try:
        body = http_get(f"https://api.github.com/{api_path_with_query}", github_headers())
    except (OSError, TimeoutError):
        return None
    content = decode_github_content_response(body)
    return (content, "rest-frontmatter") if content is not None else None


def decode_github_content_response(body: str) -> str | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
        return None
    encoded = payload["content"].replace("\n", "")
    try:
        return base64.b64decode(encoded).decode("utf-8")
    except ValueError:
        return None


def parse_frontmatter_metadata(content: str) -> dict[str, str]:
    """Parse the metadata: block from YAML-style frontmatter.

    Per the agentskills.io spec, metadata is a flat map of string scalar values.
    Standard keys are ``version`` and ``author``.
    """
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    in_metadata = False
    child_indent: int | None = None
    result: dict[str, str] = {}

    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if not stripped:
            continue

        indent = len(line) - len(line.lstrip())

        if not in_metadata:
            if indent == 0 and stripped == "metadata:":
                in_metadata = True
        else:
            if child_indent is None:
                child_indent = indent
            if indent < child_indent:
                break
            if indent == child_indent and ":" in stripped:
                key, _, value = stripped.partition(":")
                value = value.strip().strip("\"'")  # strip " and '
                if value:
                    result[key.strip()] = value

    return result


def parse_frontmatter_version(content: str) -> str | None:
    """Read version from SKILL.md frontmatter.

    Checks ``metadata.version`` first (agentskills.io spec), then falls back
    to a top-level ``version:`` key for backward compatibility.
    """
    version = parse_frontmatter_metadata(content).get("version")
    if version:
        return version
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            return None
        if len(line) - len(line.lstrip()) == 0 and stripped.startswith("version:"):
            return stripped.split(":", 1)[1].strip().strip("\"'") or None
    return None


def parse_frontmatter_author(content: str) -> str | None:
    """Read ``metadata.author`` from SKILL.md frontmatter per agentskills.io spec."""
    return parse_frontmatter_metadata(content).get("author") or None

def latest_github_commit_metadata(
    check: dict,
    command_runner: CommandRunner,
    http_get: HttpGetter,
    base_dir: Path | None = None,
) -> tuple[str, str, str | None] | None:
    repository = check["repository"]
    path = check["path"]
    tracking_ref = check["trackingRef"]
    query = urllib.parse.urlencode({"sha": tracking_ref, "path": path, "per_page": "1"})
    api_path = f"repos/{repository}/commits?{query}"

    gh_result = command_runner(["gh", "api", api_path], None)
    if gh_result.ok:
        metadata = first_commit_metadata(gh_result.stdout)
        if metadata:
            return metadata[0], "gh", metadata[1]

    try:
        body = http_get(f"https://api.github.com/{api_path}", github_headers())
    except (OSError, TimeoutError):
        body = ""
    metadata = first_commit_metadata(body)
    if metadata:
        return metadata[0], "rest", metadata[1]
    local_commit = local_commit_version(check, command_runner, base_dir=base_dir)
    return (local_commit[0], local_commit[1], None) if local_commit else None


def latest_github_commit(
    check: dict,
    command_runner: CommandRunner,
    http_get: HttpGetter,
    base_dir: Path | None = None,
) -> tuple[str, str] | None:
    metadata = latest_github_commit_metadata(check, command_runner, http_get, base_dir=base_dir)
    return (metadata[0], metadata[1]) if metadata else None


def github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def first_commit_metadata(body: str) -> tuple[str, str | None] | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    commit = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(commit, dict) or not isinstance(commit.get("sha"), str):
        return None
    commit_body = commit.get("commit")
    commit_date = None
    if isinstance(commit_body, dict):
        committer = commit_body.get("committer")
        author = commit_body.get("author")
        if isinstance(committer, dict) and isinstance(committer.get("date"), str):
            commit_date = committer["date"]
        elif isinstance(author, dict) and isinstance(author.get("date"), str):
            commit_date = author["date"]
    return commit["sha"], commit_date


def local_checkout_context(
    check: dict,
    command_runner: CommandRunner,
    base_dir: Path | None = None,
) -> tuple[Path, str] | None:
    hint = check.get("localCheckoutHint")
    if not hint:
        return None
    
    hint_path = Path(os.path.expanduser(str(hint)))
    if not hint_path.is_absolute() and base_dir is not None:
        checkout = (base_dir / hint_path).resolve()
    else:
        checkout = hint_path

    if not checkout.exists():
        return None
    remote_result = command_runner(["git", "-C", str(checkout), "remote", "-v"], None)
    if not remote_result.ok:
        return None
    matching_remote = remote_name_for_repository(remote_result.stdout, check["repository"])
    if matching_remote is None:
        return None
    root_result = command_runner(["git", "-C", str(checkout), "rev-parse", "--show-toplevel"], None)
    root = Path(root_result.stdout) if root_result.ok and root_result.stdout else checkout
    tracking_ref = check["trackingRef"]
    ref = tracking_ref if tracking_ref.startswith("refs/") else f"refs/remotes/{matching_remote}/{tracking_ref}"
    return root, ref


def remote_name_for_repository(remotes: str, repository: str) -> str | None:
    normalized_repository = repository.lower()
    for line in remotes.splitlines():
        parts = line.split()
        if len(parts) < 2 or (len(parts) >= 3 and parts[2] != "(fetch)"):
            continue
        normalized_remote = parts[1].replace(":", "/").lower()
        remote_url = normalized_remote
        if remote_url.endswith(".git"):
            remote_url = remote_url[:-4]
        if remote_url.endswith("/" + normalized_repository):
            return parts[0]
    return None


def local_commit_version(
    check: dict,
    command_runner: CommandRunner,
    base_dir: Path | None = None,
) -> tuple[str, str] | None:
    context = local_checkout_context(check, command_runner, base_dir=base_dir)
    if context is None:
        return None
    root, ref = context
    result = command_runner(
        ["git", "-C", str(root), "rev-list", "-1", ref, "--", check["path"]],
        None,
    )
    if result.ok and result.stdout:
        return result.stdout.splitlines()[0], "local-checkout"
    return None


def local_frontmatter_version(
    check: dict,
    frontmatter_path: str,
    command_runner: CommandRunner,
    base_dir: Path | None = None,
) -> tuple[str, str | None, str] | None:
    """Return (version, author_or_None, checked_by) from a local checkout."""
    context = local_checkout_context(check, command_runner, base_dir=base_dir)
    if context is None:
        return None
    root, ref = context
    result = command_runner(["git", "-C", str(root), "show", f"{ref}:{frontmatter_path}"], None)
    if not result.ok:
        return None
    version = parse_frontmatter_version(result.stdout)
    if not version:
        return None
    return version, parse_frontmatter_author(result.stdout), "local-checkout-frontmatter"


def local_checkout_warnings(
    check: dict,
    command_runner: CommandRunner,
    base_dir: Path | None = None,
) -> list[str]:
    hint = check.get("localCheckoutHint")
    if not hint:
        return []
    
    hint_path = Path(os.path.expanduser(str(hint)))
    if not hint_path.is_absolute() and base_dir is not None:
        checkout = (base_dir / hint_path).resolve()
    else:
        checkout = hint_path

    if not checkout.exists():
        return []
    warnings: list[str] = []
    remote_result = command_runner(["git", "-C", str(checkout), "remote", "-v"], None)
    if remote_result.ok:
        matching_remote = remote_name_for_repository(remote_result.stdout, check["repository"])
        if matching_remote is None:
            warnings.append(
                f"localCheckoutHint remote does not match declared repository {check['repository']}"
            )
    else:
        warnings.append(f"could not inspect localCheckoutHint remotes: {remote_result.stderr}")
    head_result = command_runner(["git", "-C", str(checkout), "rev-parse", "HEAD"], None)
    if not head_result.ok:
        warnings.append(f"could not inspect localCheckoutHint HEAD: {head_result.stderr}")
    return warnings


def print_human(rows: list[dict]) -> None:
    for row in rows:
        latest = row["latestVersion"] or row["latestCommit"] or "-"
        checked_by = row["checkedBy"] or "-"
        print(
            f"{row['status']:14} {row['skill']:36} "
            f"{row['label']} current={row['currentVersion']} latest={latest} via={checked_by}"
        )
        if row.get("notes"):
            print(f"  note: {row['notes']}")
        if row.get("upstreamAuthor"):
            print(f"  upstream author: {row['upstreamAuthor']}")
        for warning in row.get("warnings", []):
            print(f"  warning: {warning}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", default=".agents/skills", type=Path)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human text")
    parser.add_argument("--validate-only", action="store_true", help="Validate sidecars without remote checks")
    args = parser.parse_args(argv)

    try:
        rows = collect_report(args.skills_root, validate_only=args.validate_only)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        print_human(rows)
    return 1 if any(row["status"] == "error" for row in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
