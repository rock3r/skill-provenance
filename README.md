# skill-provenance

A portable agent skill for maintaining `skill-source.json` sidecars next to reusable skills.

The skill helps agents:

- record source material, attribution, licenses, and update-check hints for each skill;
- detect cheap upstream update candidates without automatically importing changes;
- keep provenance in a portable JSON format that travels with the skill folder;
- validate sidecars against a documented schema before publishing or sharing skills.

You can install the skill in many modes, including:

* Clone the repo and copy the `skills/skill-provenance/` directory into your agent skills directory, for example
  `.agents/skills/skill-provenance/`.
* Use `npx skills add rock3r/skill-provenance` and similar mechanisms

### Claude Code

The repo root contains a Claude Code plugin manifest (`.claude-plugin/plugin.json`). Add it as a plugin
directly from the GitHub repo:

```bash
codex plugin marketplace add rock3r/skill-provenance
```

### OpenAI Codex

The repo root contains a Codex plugin manifest (`.codex-plugin/plugin.json`). Add it from the GitHub repo:

```bash
codex plugin marketplace add rock3r/skill-provenance
```

Both manifests point `skills` at `./skills/`, so each platform discovers `skills/skill-provenance/SKILL.md`
as the bundled skill.

## Quick validation

From this repository root:

```bash
python3 skills/skill-provenance/scripts/test_check_skill_updates.py
python3 skills/skill-provenance/scripts/check_skill_updates.py --skills-root skills
python3 -m json.tool skills/skill-provenance/skill-source.json
```

From a project that stores skills under `.agents/skills`:

```bash
python3 .agents/skills/skill-provenance/scripts/check_skill_updates.py --skills-root .agents/skills
```

## License

Apache License 2.0. See [`LICENSE`](LICENSE).

> Copyright 2026 Sebastiano Poggi
>
> Licensed under the Apache License, Version 2.0 (the "License");
> you may not use this file except in compliance with the License.
> You may obtain a copy of the License at
> 
>   http://www.apache.org/licenses/LICENSE-2.0
> 
> Unless required by applicable law or agreed to in writing, software
> distributed under the License is distributed on an "AS IS" BASIS,
> WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
> See the License for the specific language governing permissions and
> limitations under the License.
