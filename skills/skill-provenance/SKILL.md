---
name: skill-provenance
description: >
  Use when creating or updating a skill-source.json provenance sidecar for a new, copied, or modified skill, checking
  whether upstream sources have changed, or folding external guidance into a local skill.
license: Apache-2.0
metadata:
  version: "1.0.0"
  author: "Sebastiano Poggi"
---

# Update Skills

## Core rule

Skill source metadata travels with the skill. When you update a skill from upstream material, or fold in new guidance,
examples, scripts, references, or policy from another source, update that skill's `skill-source.json` in the same
change.

Use `skill-source.json` for durable provenance: source material, attribution, licenses, pinned versions, and cheap
update-check hints. Do not use it for reconstruction notes, review opinions, confidence labels, or temporary
diagnostics.

## Workflow

- Inspect the skill and its `skill-source.json` sidecar.
- If you need the sidecar format, read `references/skill-source-json.md`.
- Run the report-only checker from the repository or project that contains the skills:

```bash
python3 SKILL_PATH/scripts/check_skill_updates.py --skills-root SKILLS_ROOT
```

Example when this skill is installed at `.agents/skills/skill-provenance`:

```bash
python3 .agents/skills/skill-provenance/scripts/check_skill_updates.py --skills-root .agents/skills
```

- Treat the report as a triage signal, not as an update decision.
    - `up-to-date` means a commit-pinned, frontmatter-pinned, or fetch-date source matches the latest cheap signal.
    - `candidate` means the source appears to have changed and needs manual upstream diff review.
    - `local-original` means original local material, not an upstream update candidate.
    - `skipped` means the source is intentionally manual, uncheckable, or pinned by a non-comparable signal.
    - `unknown` means the check could not reach a conclusion. Causes include: GitHub and local checkout fallback both
      failed (retry if transient); a date-only `fetchedAt` cannot disambiguate a same-day upstream change (use a full
      ISO timestamp to resolve); or a local checkout fallback found the latest commit but could not determine its date
      (switch to `gitCommit` versionSource or provide network access).
    - `error` means the sidecar violates the required shape and should be fixed before update decisions.
- For each candidate update, inspect the source material directly. Never import upstream guidance wholesale just because
  the cheap checker reported a newer version.
- If you fold in new material, update `skill-source.json`:
    - add a `sources` entry for every new upstream or supporting reference;
    - keep canonical repository or documentation URLs as provenance;
    - use `localCheckoutHint` only as an optional inspection aid, not as provenance;
    - add or revise top-level `attribution` whenever external material exists;
    - keep reconstruction-only evidence out of the JSON.
- Run validation before finalizing:

```bash
python3 -m json.tool SKILL_PATH/skill-source.json
python3 SKILL_PATH/scripts/check_skill_updates.py --skills-root SKILLS_ROOT --validate-only
```

If the checker has changed, run its tests:

```bash
python3 SKILL_PATH/scripts/test_check_skill_updates.py
```

## `skill-source.json` essentials

Read `references/skill-source-json.md` for the full contract and `references/skill-source.schema.json` for a JSON
Schema representation.

Required top-level fields:

- `schemaVersion`: currently `1`.
- `skill`: the directory name of the skill this sidecar describes.
- `sources`: non-empty array of source entries.
- `attribution`: required when any source has role `upstream-source` or `supporting-reference`.

Required source fields:

- `type`: one of `upstream-skill`, `upstream-reference`, `local-original-content`.
- `role`: one of `upstream-source`, `supporting-reference`, `original-content`.
- `label`: short human-readable source name.
- `version`: pinned source version.
- `versionSource`: one of `frontmatter`, `gitCommit`, `fetchDate`.
- `fetchedAt`: ISO date or timestamp for when the source was inspected.
- `license`: source license or `unknown`.

Recommended version choice:

1. use the source skill's `metadata.version` frontmatter field (agentskills.io spec) — the checker reads this directly
   and falls back to a top-level `version:` key;
2. otherwise use the git commit hash that was fetched or inspected;
3. otherwise use the ISO fetch date.

When the upstream skill has `metadata.author` in its frontmatter, the checker includes it as `upstreamAuthor` in the
report row — use it to write the top-level `attribution` field.

## Gotchas

- Do not treat a local checkout path as provenance. Record the canonical upstream URL instead.
- Do not place `attribution` inside a source entry. It is a required **top-level** field alongside `skill` and
  `schemaVersion`, not a per-source field.
- Do not let transitive sources disappear. If a derivative source itself came from another source, and you closely adapt
  that material, record both sources.
- Do not include `gitEvidence`, commit subjects, review notes, diagnostics, or confidence labels in `skill-source.json`.
- Do not let the checker modify files, create branches, commit, push, open pull requests, or publish anything.
- Do not accept source material that conflicts with the target skill's environment or audience; adapt deliberately.
