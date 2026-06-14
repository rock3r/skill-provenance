import base64
import json
import tempfile
import unittest
from pathlib import Path

import check_skill_updates


class CheckSkillUpdatesTest(unittest.TestCase):
    def write_skill_source(
        self,
        root: Path,
        skill: str,
        sources: list[dict],
        attribution: str | None = None,
    ) -> None:
        skill_dir = root / skill
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: sample\ndescription: Sample\n---\n")
        payload = {"schemaVersion": 1, "skill": skill, "sources": sources}
        if attribution is not None:
            payload["attribution"] = attribution
        (skill_dir / "skill-source.json").write_text(json.dumps(payload))

    def test_missing_skills_root_is_an_input_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "missing"

            with self.assertRaises(ValueError):
                check_skill_updates.collect_report(root, command_runner=self.fail_command)

    def test_non_skill_helper_directory_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_shared").mkdir()
            self.write_skill_source(root, "sample", [self.local_source()])

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual(1, len(report))
            self.assertEqual("sample", report[0]["skill"])

    def test_skill_directory_without_sidecar_is_an_input_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "sample"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: sample\ndescription: Sample\n---\n")

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("missing skill-source.json", report[0]["notes"])

    def test_missing_top_level_skill_is_reported_as_error_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "sample"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: sample\ndescription: Sample\n---\n")
            payload = {"schemaVersion": 1, "sources": []}
            (skill_dir / "skill-source.json").write_text(json.dumps(payload))

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("missing top-level skill", report[0]["notes"])

    def test_invalid_schema_version_is_reported_as_error_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "sample"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: sample\ndescription: Sample\n---\n")
            payload = {"schemaVersion": 2, "skill": "sample", "sources": []}
            (skill_dir / "skill-source.json").write_text(json.dumps(payload))

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("schemaVersion", report[0]["notes"])

    def test_sidecar_skill_name_mismatch_is_reported_as_error_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "sample"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: sample\ndescription: Sample\n---\n")
            payload = {"schemaVersion": 1, "skill": "other", "sources": []}
            (skill_dir / "skill-source.json").write_text(json.dumps(payload))

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("declares skill", report[0]["notes"])

    def test_wrong_top_level_json_shape_is_reported_as_error_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "sample"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: sample\ndescription: Sample\n---\n")
            (skill_dir / "skill-source.json").write_text("[]")

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("top-level JSON object", report[0]["notes"])

    def test_wrong_source_entry_shape_is_reported_as_error_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "sample"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: sample\ndescription: Sample\n---\n")
            payload = {"schemaVersion": 1, "skill": "sample", "sources": ["oops"]}
            (skill_dir / "skill-source.json").write_text(json.dumps(payload))

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("source[0] must be an object", report[0]["notes"])

    def test_invalid_json_sidecar_is_reported_as_error_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "sample"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: sample\ndescription: Sample\n---\n")
            (skill_dir / "skill-source.json").write_text("{")

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("Invalid JSON", report[0]["notes"])

    def test_empty_sources_is_reported_as_error_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "sample"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: sample\ndescription: Sample\n---\n")
            payload = {"schemaVersion": 1, "skill": "sample", "sources": []}
            (skill_dir / "skill-source.json").write_text(json.dumps(payload))

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("must not be empty", report[0]["notes"])

    def test_forbidden_reconstruction_keys_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.local_source()
            source["diagnostics"] = {"confidence": "high"}
            self.write_skill_source(root, "sample", [source])

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("reconstruction-only key", report[0]["notes"])

    def test_incomplete_github_check_is_reported_as_error_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.github_source(version="old")
            del source["check"]["trackingRef"]
            self.write_skill_source(root, "sample", [source], attribution="Adapted from upstream.")

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("trackingRef", report[0]["notes"])

    def test_external_source_requires_attribution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill_source(root, "sample", [self.github_source(version="old")])

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("attribution", report[0]["notes"])

    def test_github_external_source_requires_check_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.github_source(version="old")
            del source["check"]
            self.write_skill_source(root, "sample", [source], attribution="Adapted from upstream.")

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("check metadata", report[0]["notes"])

    def test_manual_github_source_is_reported_as_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.github_source(version="old")
            source["check"] = {"type": "manual", "reason": "Prefer manual review"}
            self.write_skill_source(root, "sample", [source], attribution="Adapted from upstream.")

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("should use github check", report[0]["notes"])

    def test_non_tree_github_urls_are_not_recoverable(self) -> None:
        non_recoverable = [
            "https://github.com/org/repo",
            "https://github.com/org/repo/tree/main",  # no path after ref
            "https://github.com/org/repo/issues/42",
            "https://github.com/org/repo/pull/7",
            "https://github.com/org/repo/releases/tag/v1.0.0",
            "https://github.com/org/repo/releases",
            "https://github.com/org/repo/discussions/99",
            "https://github.com/org/repo/compare/main...feature",
        ]
        for url in non_recoverable:
            with self.subTest(url=url):
                self.assertFalse(
                    check_skill_updates.is_recoverable_github_source_url(url),
                    f"Expected {url} to NOT be recoverable",
                )

        recoverable = [
            "https://github.com/org/repo/tree/main/skills/sample",
            "https://github.com/org/repo/blob/main/SKILL.md",
            "https://github.com/org/repo/tree/main/.",  # path present (single dot)
        ]
        for url in recoverable:
            with self.subTest(url=url):
                self.assertTrue(
                    check_skill_updates.is_recoverable_github_source_url(url),
                    f"Expected {url} to be recoverable",
                )

    def test_github_issue_url_with_manual_check_is_skipped_not_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = {
                "type": "upstream-reference",
                "role": "supporting-reference",
                "label": "Related GitHub issue",
                "url": "https://github.com/org/repo/issues/42",
                "version": "2026-06-01",
                "versionSource": "fetchDate",
                "fetchedAt": "2026-06-01",
                "license": "unknown",
                "check": {"type": "manual", "reason": "Issue URL cannot be path-checked"},
            }
            self.write_skill_source(root, "sample", [source], attribution="Adapted from upstream.")

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("skipped", report[0]["status"])

    def test_malformed_original_content_is_reported_as_error_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.local_source()
            del source["license"]
            self.write_skill_source(root, "sample", [source])

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("license", report[0]["notes"])

    def test_original_content_is_reported_without_remote_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill_source(root, "sample", [self.local_source()])

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("local-original", report[0]["status"])
            self.assertEqual("sample", report[0]["skill"])

    def test_validate_only_reports_valid_without_remote_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill_source(root, "sample", [self.github_source(version="old")], "Adapted from upstream.")

            report = check_skill_updates.collect_report(
                root,
                command_runner=self.fail_command,
                validate_only=True,
            )

            self.assertEqual("valid", report[0]["status"])

    def test_github_check_prefers_gh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill_source(root, "sample", [self.github_source(version="old")], "Adapted from upstream.")
            calls = []

            def run(command, cwd=None):
                calls.append(command)
                if command[:2] == ["gh", "api"]:
                    return check_skill_updates.CommandResult(
                        ok=True,
                        stdout='[{"sha":"new"}]',
                        stderr="",
                    )
                self.fail(f"unexpected command: {command}")

            report = check_skill_updates.collect_report(root, command_runner=run)

            self.assertEqual("candidate", report[0]["status"])
            self.assertEqual("new", report[0]["latestVersion"])
            self.assertEqual("gh", report[0]["checkedBy"])
            self.assertEqual("gh", calls[0][0])

    def test_github_check_falls_back_to_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill_source(root, "sample", [self.github_source(version="new")], "Adapted from upstream.")

            def run(command, cwd=None):
                return check_skill_updates.CommandResult(ok=False, stdout="", stderr="gh missing")

            def fetch(url, headers):
                return '[{"sha":"new"}]'

            report = check_skill_updates.collect_report(
                root,
                command_runner=run,
                http_get=fetch,
            )

            self.assertEqual("up-to-date", report[0]["status"])
            self.assertEqual("rest", report[0]["checkedBy"])

    def test_frontmatter_pinned_github_sources_compare_frontmatter_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.github_source(version="2.1.0")
            source["versionSource"] = "frontmatter"
            source["check"]["frontmatterPath"] = "skills/sample/SKILL.md"
            self.write_skill_source(root, "sample", [source], "Adapted from upstream.")
            content = base64.b64encode(b"---\nname: sample\nversion: 2.2.0\n---\n").decode()

            def run(command, cwd=None):
                if command[:2] == ["gh", "api"]:
                    return check_skill_updates.CommandResult(
                        ok=True,
                        stdout=json.dumps({"content": content}),
                        stderr="",
                    )
                self.fail(f"unexpected command: {command}")

            report = check_skill_updates.collect_report(root, command_runner=run)

            self.assertEqual("candidate", report[0]["status"])
            self.assertEqual("2.2.0", report[0]["latestVersion"])
            self.assertEqual("gh-frontmatter", report[0]["checkedBy"])

    def test_frontmatter_same_version_but_newer_commit_is_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.github_source(version="2.1.0")
            source["versionSource"] = "frontmatter"
            source["fetchedAt"] = "2026-06-11"
            source["check"]["frontmatterPath"] = "skills/sample/SKILL.md"
            self.write_skill_source(root, "sample", [source], "Adapted from upstream.")
            content = base64.b64encode(b"---\nname: sample\nversion: 2.1.0\n---\n").decode()

            def run(command, cwd=None):
                if command[:2] == ["gh", "api"] and "/contents/" in command[2]:
                    return check_skill_updates.CommandResult(
                        ok=True,
                        stdout=json.dumps({"content": content}),
                        stderr="",
                    )
                if command[:2] == ["gh", "api"] and "/commits?" in command[2]:
                    return check_skill_updates.CommandResult(
                        ok=True,
                        stdout=json.dumps(
                            [
                                {
                                    "sha": "new-sha",
                                    "commit": {"committer": {"date": "2026-06-11T12:00:00Z"}},
                                }
                            ]
                        ),
                        stderr="",
                    )
                self.fail(f"unexpected command: {command}")

            report = check_skill_updates.collect_report(root, command_runner=run)

            self.assertEqual("unknown", report[0]["status"])
            self.assertEqual("new-sha", report[0]["latestCommit"])
            self.assertIn("date-only fetchedAt", report[0]["notes"])

    def test_non_object_check_field_is_reported_as_error_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.github_source(version="old")
            source["check"] = "github"
            self.write_skill_source(root, "sample", [source], "Adapted from upstream.")

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("error", report[0]["status"])
            self.assertIn("check must be an object", report[0]["notes"])

    def test_frontmatter_local_checkout_fallback_without_date_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            root.mkdir()
            checkout = Path(tmp) / "checkout"
            checkout.mkdir()
            source = self.github_source(version="2.1.0")
            source["versionSource"] = "frontmatter"
            source["check"]["frontmatterPath"] = "skills/sample/SKILL.md"
            source["check"]["localCheckoutHint"] = str(checkout)
            self.write_skill_source(root, "sample", [source], "Adapted from upstream.")

            def run(command, cwd=None):
                if command[:2] == ["gh", "api"]:
                    return check_skill_updates.CommandResult(ok=False, stdout="", stderr="gh failed")
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == ["remote", "-v"]:
                    return check_skill_updates.CommandResult(
                        ok=True,
                        stdout="origin https://github.com/example/repo.git (fetch)",
                        stderr="",
                    )
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == ["rev-parse", "--show-toplevel"]:
                    return check_skill_updates.CommandResult(ok=True, stdout=str(checkout), stderr="")
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == [
                    "show",
                    "refs/remotes/origin/main:skills/sample/SKILL.md",
                ]:
                    return check_skill_updates.CommandResult(
                        ok=True,
                        stdout="---\nname: sample\nversion: 2.1.0\n---\n",
                        stderr="",
                    )
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == [
                    "rev-list",
                    "-1",
                    "refs/remotes/origin/main",
                    "--",
                    "skills/sample",
                ]:
                    return check_skill_updates.CommandResult(ok=True, stdout="local-sha", stderr="")
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == ["rev-parse", "HEAD"]:
                    return check_skill_updates.CommandResult(ok=True, stdout="local-head", stderr="")
                return check_skill_updates.CommandResult(ok=False, stdout="", stderr="unexpected")

            def fetch(url, headers):
                raise OSError("offline")

            report = check_skill_updates.collect_report(root, command_runner=run, http_get=fetch)

            self.assertEqual("unknown", report[0]["status"])
            self.assertEqual("local-sha", report[0]["latestCommit"])
            self.assertIn("local checkout fallback", report[0]["notes"])

    def test_local_checkout_hint_is_used_when_remote_checks_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            root.mkdir()
            checkout = Path(tmp) / "checkout"
            checkout.mkdir()
            source = self.github_source(version="old")
            source["check"]["localCheckoutHint"] = str(checkout)
            self.write_skill_source(root, "sample", [source], "Adapted from upstream.")

            def run(command, cwd=None):
                if command[:2] == ["gh", "api"]:
                    return check_skill_updates.CommandResult(ok=False, stdout="", stderr="gh failed")
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == ["remote", "-v"]:
                    return check_skill_updates.CommandResult(
                        ok=True,
                        stdout="origin git@github.com:example/repo.git (fetch)",
                        stderr="",
                    )
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == ["rev-parse", "--show-toplevel"]:
                    return check_skill_updates.CommandResult(ok=True, stdout=str(checkout), stderr="")
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == [
                    "rev-list",
                    "-1",
                    "refs/remotes/origin/main",
                    "--",
                    "skills/sample",
                ]:
                    return check_skill_updates.CommandResult(ok=True, stdout="local-sha", stderr="")
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == ["rev-parse", "HEAD"]:
                    return check_skill_updates.CommandResult(ok=True, stdout="local-head", stderr="")
                return check_skill_updates.CommandResult(ok=False, stdout="", stderr="unexpected")

            def fetch(url, headers):
                raise OSError("offline")

            report = check_skill_updates.collect_report(root, command_runner=run, http_get=fetch)

            self.assertEqual("candidate", report[0]["status"])
            self.assertEqual("local-sha", report[0]["latestVersion"])
            self.assertEqual("local-checkout", report[0]["checkedBy"])

    def test_local_checkout_hint_resolves_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # skills root is under tmp/skills
            root = Path(tmp) / "skills"
            root.mkdir()

            # checkout dir is under tmp/checkout (relative as "../checkout")
            checkout = (Path(tmp) / "checkout").resolve()
            checkout.mkdir()

            source = self.github_source(version="old")
            source["check"]["localCheckoutHint"] = "../../checkout"

            self.write_skill_source(root, "sample", [source], "Adapted from upstream.")

            def run(command, cwd=None):
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == ["remote", "-v"]:
                    return check_skill_updates.CommandResult(
                        ok=True,
                        stdout="origin git@github.com:example/repo.git (fetch)",
                        stderr="",
                    )
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == ["rev-parse", "--show-toplevel"]:
                    return check_skill_updates.CommandResult(ok=True, stdout=str(checkout), stderr="")
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == [
                    "rev-list",
                    "-1",
                    "refs/remotes/origin/main",
                    "--",
                    "skills/sample",
                ]:
                    return check_skill_updates.CommandResult(ok=True, stdout="local-sha", stderr="")
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == ["rev-parse", "HEAD"]:
                    return check_skill_updates.CommandResult(ok=True, stdout="local-head", stderr="")
                return check_skill_updates.CommandResult(ok=False, stdout="", stderr="unexpected")

            def fetch(url, headers):
                raise OSError("offline")

            report = check_skill_updates.collect_report(root, command_runner=run, http_get=fetch)

            # It should successfully resolve the relative hint and match status candidate
            self.assertEqual("candidate", report[0]["status"])
            self.assertEqual("local-sha", report[0]["latestVersion"])
            self.assertEqual("local-checkout", report[0]["checkedBy"])
            self.assertEqual([], report[0]["warnings"])

    def test_local_checkout_hint_warns_when_remote_does_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            root.mkdir()
            checkout = Path(tmp) / "checkout"
            checkout.mkdir()
            source = self.github_source(version="old")
            source["check"]["localCheckoutHint"] = str(checkout)
            self.write_skill_source(root, "sample", [source], "Adapted from upstream.")

            def run(command, cwd=None):
                if command[:2] == ["gh", "api"]:
                    return check_skill_updates.CommandResult(ok=True, stdout='[{"sha":"new"}]', stderr="")
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == ["remote", "-v"]:
                    return check_skill_updates.CommandResult(
                        ok=True,
                        stdout="origin https://github.com/someone/else.git (fetch)",
                        stderr="",
                    )
                if command[:3] == ["git", "-C", str(checkout)] and command[3:] == ["rev-parse", "HEAD"]:
                    return check_skill_updates.CommandResult(ok=True, stdout="local", stderr="")
                return check_skill_updates.CommandResult(ok=False, stdout="", stderr="unexpected")

            report = check_skill_updates.collect_report(root, command_runner=run)

            self.assertTrue(any("does not match" in warning for warning in report[0]["warnings"]))

    def test_fetch_date_github_sources_compare_commit_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.github_source(version="2026-06-10")
            source["versionSource"] = "fetchDate"
            source["fetchedAt"] = "2026-06-10"
            self.write_skill_source(root, "sample", [source], "Adapted from upstream.")

            def run(command, cwd=None):
                if command[:2] == ["gh", "api"]:
                    return check_skill_updates.CommandResult(
                        ok=True,
                        stdout=json.dumps(
                            [
                                {
                                    "sha": "new-sha",
                                    "commit": {"committer": {"date": "2026-06-11T00:00:00Z"}},
                                }
                            ]
                        ),
                        stderr="",
                    )
                self.fail(f"unexpected command: {command}")

            report = check_skill_updates.collect_report(root, command_runner=run)

            self.assertEqual("candidate", report[0]["status"])
            self.assertEqual("new-sha", report[0]["latestCommit"])

    def test_manual_non_github_sources_are_skipped_with_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill_source(
                root,
                "sample",
                [
                    {
                        "type": "upstream-reference",
                        "role": "upstream-source",
                        "label": "Pattern",
                        "url": "https://example.com/pattern",
                        "version": "2026-06-11",
                        "versionSource": "fetchDate",
                        "fetchedAt": "2026-06-11",
                        "license": "unknown",
                        "check": {"type": "manual", "reason": "Exact upstream path is unknown"},
                    }
                ],
                attribution="Adapted from upstream.",
            )

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            self.assertEqual("skipped", report[0]["status"])
            self.assertIn("Exact upstream path", report[0]["notes"])

    def test_skill_directory_without_sidecar_is_reported_as_error_when_other_has_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # sample1 has SKILL.md but no sidecar
            skill_dir1 = root / "sample1"
            skill_dir1.mkdir()
            (skill_dir1 / "SKILL.md").write_text("---\nname: sample1\n---\n")

            # sample2 has both SKILL.md and sidecar
            self.write_skill_source(root, "sample2", [self.local_source()])

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)

            # Both should be in the report: sample1 as error, sample2 as valid
            self.assertEqual(2, len(report))
            report_sorted = sorted(report, key=lambda r: r["skill"])
            self.assertEqual("sample1", report_sorted[0]["skill"])
            self.assertEqual("error", report_sorted[0]["status"])
            self.assertIn("missing skill-source.json", report_sorted[0]["notes"])
            self.assertEqual("sample2", report_sorted[1]["skill"])

    def test_parse_frontmatter_metadata_extracts_metadata_block(self) -> None:
        content = "---\nname: my-skill\nmetadata:\n  version: 2.1.0\n  author: example-org\n---\nbody\n"
        meta = check_skill_updates.parse_frontmatter_metadata(content)
        self.assertEqual("2.1.0", meta.get("version"))
        self.assertEqual("example-org", meta.get("author"))

    def test_parse_frontmatter_metadata_ignores_non_metadata_keys(self) -> None:
        content = "---\nname: my-skill\nversion: 9.9.9\nmetadata:\n  version: 1.0\n  author: seb\n---\n"
        meta = check_skill_updates.parse_frontmatter_metadata(content)
        self.assertEqual({"version": "1.0", "author": "seb"}, meta)

    def test_parse_frontmatter_metadata_empty_when_no_block(self) -> None:
        self.assertEqual({}, check_skill_updates.parse_frontmatter_metadata("---\nname: x\n---\n"))
        self.assertEqual({}, check_skill_updates.parse_frontmatter_metadata("no frontmatter"))

    def test_parse_frontmatter_version_prefers_metadata_version(self) -> None:
        content = "---\nname: my-skill\nversion: 9.9.9\nmetadata:\n  version: 2.1.0\n---\n"
        self.assertEqual("2.1.0", check_skill_updates.parse_frontmatter_version(content))

    def test_parse_frontmatter_version_falls_back_to_top_level(self) -> None:
        content = "---\nname: my-skill\nversion: 3.0.0\n---\n"
        self.assertEqual("3.0.0", check_skill_updates.parse_frontmatter_version(content))

    def test_parse_frontmatter_version_returns_none_when_absent(self) -> None:
        self.assertIsNone(check_skill_updates.parse_frontmatter_version("---\nname: x\n---\n"))

    def test_parse_frontmatter_author_extracts_metadata_author(self) -> None:
        content = "---\nname: my-skill\nmetadata:\n  version: 1.0\n  author: acme-org\n---\n"
        self.assertEqual("acme-org", check_skill_updates.parse_frontmatter_author(content))

    def test_parse_frontmatter_author_returns_none_when_absent(self) -> None:
        self.assertIsNone(check_skill_updates.parse_frontmatter_author("---\nname: x\n---\n"))

    def test_frontmatter_source_surfaces_upstream_author_in_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.github_source(version="2.1.0")
            source["versionSource"] = "frontmatter"
            source["fetchedAt"] = "2026-06-12"
            source["check"]["frontmatterPath"] = "skills/sample/SKILL.md"
            self.write_skill_source(root, "sample", [source], "Adapted from upstream.")
            skill_md = "---\nname: sample\nmetadata:\n  version: 2.1.0\n  author: example-org\n---\n"
            contents_response = json.dumps({"content": base64.b64encode(skill_md.encode()).decode()})
            commits_response = json.dumps(
                [{"sha": "abc", "commit": {"committer": {"date": "2026-06-10T00:00:00Z"}}}]
            )

            def run(command, cwd=None):
                if command[:2] == ["gh", "api"] and "/contents/" in command[2]:
                    return check_skill_updates.CommandResult(ok=True, stdout=contents_response, stderr="")
                if command[:2] == ["gh", "api"] and "/commits?" in command[2]:
                    return check_skill_updates.CommandResult(ok=True, stdout=commits_response, stderr="")
                self.fail(f"unexpected command: {command}")

            report = check_skill_updates.collect_report(root, command_runner=run)

            self.assertEqual("up-to-date", report[0]["status"])
            self.assertEqual("example-org", report[0]["upstreamAuthor"])

    def test_parse_utc_datetime(self) -> None:
        from datetime import datetime, timezone
        self.assertEqual(
            datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc),
            check_skill_updates.parse_utc_datetime("2026-06-11T12:00:00Z")
        )
        self.assertEqual(
            datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc),
            check_skill_updates.parse_utc_datetime("2026-06-11 12:00:00")
        )
        self.assertEqual(
            datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc),
            check_skill_updates.parse_utc_datetime("2026-06-11T14:00:00+02:00")
        )
        self.assertEqual(
            datetime(2026, 6, 11, 12, 0, 0, 123000, tzinfo=timezone.utc),
            check_skill_updates.parse_utc_datetime("2026-06-11T12:00:00.123")
        )
        self.assertEqual(
            datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc),
            check_skill_updates.parse_utc_datetime("2026-06-11T12:00Z")
        )
        self.assertEqual(
            datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc),
            check_skill_updates.parse_utc_datetime("2026-06-11T14:00+02:00")
        )
        self.assertEqual(
            datetime(2026, 6, 11, 0, 0, 0, tzinfo=timezone.utc),
            check_skill_updates.parse_utc_datetime("2026-06-11")
        )

    def test_compare_dates_invalid_formats(self) -> None:
        status, notes = check_skill_updates.compare_dates("2026-06-11T12:00:00Z", "yesterday", is_frontmatter=False)
        self.assertEqual("error", status)
        self.assertIn("invalid date/time format", notes)

        status, notes = check_skill_updates.compare_dates("invalid_latest", "2026-06-11", is_frontmatter=False)
        self.assertEqual("unknown", status)
        self.assertIn("could not parse latest", notes)

    def test_malformed_fetched_at_reports_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.local_source()
            source["fetchedAt"] = "yesterday"
            self.write_skill_source(root, "sample", [source])

            report = check_skill_updates.collect_report(root, command_runner=self.fail_command)
            self.assertEqual("error", report[0]["status"])
            self.assertIn("fetchedAt has an invalid date/time format", report[0]["notes"])

    def test_main_cli_help(self) -> None:
        with self.assertRaises(SystemExit) as context:
            check_skill_updates.main(["--help"])
        self.assertEqual(0, context.exception.code)

    def test_main_cli_missing_skills_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_root = Path(tmp) / "missing"
            # Since the directory doesn't exist, main should print error and return 2
            code = check_skill_updates.main(["--skills-root", str(missing_root)])
            self.assertEqual(2, code)

    def test_main_cli_validate_only_and_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill_source(root, "sample", [self.local_source()])
            # Run validate-only, should succeed and return 0
            code = check_skill_updates.main(["--skills-root", str(root), "--validate-only"])
            self.assertEqual(0, code)

    def test_main_cli_json_output(self) -> None:
        import io
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_skill_source(root, "sample", [self.local_source()])

            f = io.StringIO()
            with patch('sys.stdout', new=f):
                code = check_skill_updates.main(["--skills-root", str(root), "--validate-only", "--json"])

            self.assertEqual(0, code)
            data = json.loads(f.getvalue())
            self.assertEqual(1, len(data))
            self.assertEqual("sample", data[0]["skill"])
            self.assertEqual("valid", data[0]["status"])

    def local_source(self) -> dict:
        return {
            "type": "local-original-content",
            "role": "original-content",
            "label": "Local guidance",
            "version": "2026-06-11",
            "versionSource": "fetchDate",
            "fetchedAt": "2026-06-11",
            "license": "Apache-2.0",
        }

    def github_source(self, version: str) -> dict:
        return {
            "type": "upstream-skill",
            "role": "upstream-source",
            "label": "Upstream skill",
            "url": "https://github.com/example/repo/tree/main/skills/sample",
            "version": version,
            "versionSource": "gitCommit",
            "fetchedAt": "2026-06-11",
            "license": "unknown",
            "check": {
                "type": "github",
                "repository": "example/repo",
                "path": "skills/sample",
                "trackingRef": "main",
            },
        }

    def fail_command(self, command, cwd=None):
        self.fail(f"unexpected command: {command}")


if __name__ == "__main__":
    unittest.main()
