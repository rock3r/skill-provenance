# `skill-source.json` format

`skill-source.json` is a provenance sidecar for a reusable skill. It records the sources that informed the skill,
license and attribution information, and optional cheap update-check hints. The sidecar should live in the same
directory as `SKILL.md`.

## Goals

- Make provenance travel with the skill folder.
- Preserve attribution when a skill is copied, forked, bundled, or republished.
- Give maintainers enough pinned source information to review upstream changes later.
- Keep temporary reconstruction evidence out of published metadata.

## Top-level object

| Field           |    Required | Type    | Description                                                            |
|-----------------|------------:|---------|------------------------------------------------------------------------|
| `schemaVersion` |         yes | integer | Current value is `1`.                                                  |
| `skill`         |         yes | string  | Must match the containing skill directory name.                        |
| `sources`       |         yes | array   | Non-empty array of source entries.                                     |
| `attribution`   | conditional | string  | Required when any source is external. Human-readable attribution text. |

External sources are entries whose `role` is `upstream-source` or `supporting-reference`.

## Source entry

| Field           |      Required | Type   | Description                                                          |
|-----------------|--------------:|--------|----------------------------------------------------------------------|
| `type`          |           yes | string | `upstream-skill`, `upstream-reference`, or `local-original-content`. |
| `role`          |           yes | string | `upstream-source`, `supporting-reference`, or `original-content`.    |
| `label`         |           yes | string | Human-readable source label.                                         |
| `url`           | external only | string | Canonical URL for external sources.                                  |
| `version`       |           yes | string | Pinned source version.                                               |
| `versionSource` |           yes | string | `frontmatter`, `gitCommit`, or `fetchDate`.                          |
| `fetchedAt`     |           yes | string | ISO date or timestamp for when the source was inspected.             |
| `license`       |           yes | string | Source license identifier or `unknown`.                              |
| `check`         |   conditional | object | Required for GitHub external URLs unless no cheap check is possible. |

`role` and `type` must agree:

- `original-content` must use `local-original-content`.
- `local-original-content` must use `original-content`.
- external roles must use `upstream-skill` or `upstream-reference`.

## Version selection

Choose `version` and `versionSource` with this precedence:

1. Use `frontmatter` when the source skill has a stable frontmatter version. The checker reads `metadata.version` per the agentskills.io spec, falling back to a top-level `version:` key for older skills.
2. Use `gitCommit` when the source is in a git repository and no frontmatter version exists.
3. Use `fetchDate` when no more precise comparable version is available.

When using `frontmatter`, the checker also reads `metadata.author` from the upstream SKILL.md and includes it as `upstreamAuthor` in the report row. Use that value to write the top-level `attribution` field in the sidecar.

Use an ISO date or timestamp in `fetchedAt`. Date-only values are allowed, but same-day upstream changes may be reported
as `unknown` because the checker cannot disambiguate ordering.

## `check` object

The checker supports two check types.

### GitHub check

Use this when the external source lives in a public or accessible GitHub repository.

| Field               |    Required | Type   | Description                                                          |
|---------------------|------------:|--------|----------------------------------------------------------------------|
| `type`              |         yes | string | `github`.                                                            |
| `repository`        |         yes | string | `owner/repo`.                                                        |
| `path`              |         yes | string | Source path within the repository.                                   |
| `trackingRef`       |         yes | string | Branch, tag, or ref to inspect.                                      |
| `frontmatterPath`   | conditional | string | Required when `versionSource` is `frontmatter`.                      |
| `localCheckoutHint` |          no | string | Optional local checkout path used only as a fallback inspection aid. |

`localCheckoutHint` is never provenance. It may be stripped by bundlers or ignored by other maintainers.

### Manual check

Use this when no cheap automated check is reliable.

| Field    | Required | Type   | Description                                     |
|----------|---------:|--------|-------------------------------------------------|
| `type`   |      yes | string | `manual`.                                       |
| `reason` |      yes | string | Why the source cannot be checked automatically. |

Do not use `manual` for a normal GitHub URL when the repository and path are recoverable.

## Forbidden keys

Do not include reconstruction-only keys anywhere in the sidecar, including nested objects:

- `gitEvidence`
- `recentHistory`
- `evidence`
- `reviewNote`
- `commitSubject`
- `commitSubjects`
- `confidence`
- `confidenceLabel`
- `diagnostics`
- `reviewDiagnostics`

## Examples

### Original local skill

```json
{
  "schemaVersion": 1,
  "skill": "example-skill",
  "sources": [
    {
      "type": "local-original-content",
      "role": "original-content",
      "label": "Original workflow for example tasks",
      "version": "2026-06-14",
      "versionSource": "fetchDate",
      "fetchedAt": "2026-06-14",
      "license": "Apache-2.0"
    }
  ]
}
```

### Adapted external skill

```json
{
  "schemaVersion": 1,
  "skill": "example-skill",
  "attribution": "Adapted from Example Org's example-skill (https://github.com/example/skills), Apache-2.0.",
  "sources": [
    {
      "type": "upstream-skill",
      "role": "upstream-source",
      "label": "Example Org example-skill",
      "url": "https://github.com/example/skills/tree/main/skills/example-skill",
      "version": "2.1.0",
      "versionSource": "frontmatter",
      "fetchedAt": "2026-06-14",
      "license": "Apache-2.0",
      "check": {
        "type": "github",
        "repository": "example/skills",
        "path": "skills/example-skill",
        "trackingRef": "main",
        "frontmatterPath": "skills/example-skill/SKILL.md"
      }
    }
  ]
}
```
