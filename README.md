# Aquarium for Grok

Aquarium development skills packaged as a Grok plugin marketplace. This repository is a **generated artifact**: the source of truth is the Codex plugin at [irootkernel/aquarium](https://github.com/irootkernel/aquarium), pinned here as a submodule and transformed by `scripts/sync.py`.

English · [한국어](README.ko.md)

By [Root Kernel](https://home.rootkernel.xyz) · Support: [cs@rootkernel.xyz](mailto:cs@rootkernel.xyz)

## Aquarium Editions

- [Aquarium](https://github.com/irootkernel/aquarium) — Codex
- [Aquarium for Claude](https://github.com/irootkernel/aquarium-for-claude)
- [Aquarium for GLM](https://github.com/irootkernel/aquarium-for-glm)

## Install

```bash
grok plugin marketplace add irootkernel/aquarium-for-grok
grok plugin install aquarium --trust
```

If `[marketplace] require_sha = true`, the documented pin is a `plugin-index.json` `sha` after the first commit exists. The combined `owner/repo@<sha>#subdir` install form is unverified against Grok's published SOURCE grammar.

Enable the plugin in `/plugins` if it is not already on, then start a new session so the skill snapshot reloads.

The generated plugin is committed, so installation never depends on the submodule being fetched.

Both this edition and Aquarium for Claude use the plugin name `aquarium`. Grok still discovers `~/.claude/plugins` when `[compat.claude] skills = false`, and the Claude copy hides this edition so `grok inspect` never lists the Grok install. Leave Claude Code's install in place for that host.

On Grok, link the hashed install — the `path` field from `grok plugin list --json` on the object whose `marketplace` is `aquarium-for-grok`, not `source` — to `~/.grok/plugins/aquarium` so the native user plugin wins. Use `ln -sfn`; `ln -sf` does not retarget an existing directory symlink on macOS. Confirm `readlink ~/.grok/plugins/aquarium` equals that `path` and `grok inspect` reports `aquarium` from `~/.grok/plugins/aquarium`. Retarget after every `grok plugin update` because the hashed install directory changes.

```bash
mkdir -p ~/.grok/plugins
ln -sfn "$(grok plugin list --json | python3 -c 'import json,sys; print(next(p["path"] for p in json.load(sys.stdin) if p.get("marketplace") == "aquarium-for-grok"))')" ~/.grok/plugins/aquarium
readlink ~/.grok/plugins/aquarium
```

Written skill names use the plugin-qualified form `/aquarium:<skill>`. The table below lists that qualified name, not the keystrokes to type. After install, type the form `grok inspect --json` reports for that skill: the bare `/<skill>` when `invocableAs` is absent, or `/aquarium:<skill>` when Grok sets `invocableAs` because the name collides. Grok documents the qualified form for name collisions. The plugin `name` is `aquarium`.

## Skills

| Skill | Purpose | Invocation |
|---|---|---|
| `new-project` | Shape a greenfield project into an approved PRD and initial roadmap with Ouroboros, without implementing it. | `/aquarium:new-project` |
| `new-feature` | Shape one feature epic for an existing project without implementing it. | `/aquarium:new-feature` |
| `refactor` | Shape one refactor epic with compatibility, migration, and rollback impact. | `/aquarium:refactor` |
| `war-room` | Diagnose one difficult bug and propose a task, epic, or incomplete investigation without a fix. | `/aquarium:war-room` |
| `epic-handler` | Orchestrate an epic through sequential task goals and a convergent epic-wide audit. | `/aquarium:epic-handler` with a roadmap path and one epic ID |
| `epic-validator` | Cold-validate a completed epic and converge confirmed gaps through remediation goals. | `/aquarium:epic-validator` with a roadmap path and one epic ID |
| `task-handler` | Strengthen the procedure around one task goal through focused phase skills and verified transitions. | `/aquarium:task-handler` with a roadmap path and one task ID |
| `task-commit` | Reconcile roadmap task lifecycle state and create one authorized commit that preserves unrelated work. | Automatic for commit requests, or `/aquarium:task-commit` |
| `release-handler` | Own one stable release lifecycle: settle the cumulative changelog, gate release QA, and publish one version behind separate approvals. | `/aquarium:release-handler` with an intended or planned version |
| `release-qa` | Exercise the current release candidate through read-only user scenarios covering every change since the previous stable release. | `/aquarium:release-qa` with an intended or confirmed version |
| `dev-setup` | Diagnose and configure selected repository-local development tools, and propose reference-based instruction-file guidance behind separate approvals. | `/aquarium:dev-setup` |
| `dev-setup-global` | Diagnose and install user-global CLIs, paired skills, Grok MCP registrations, and Ouroboros without changing repository configuration. Aquarium plugin install or update stays in `grok plugin` marketplace flow. | `/aquarium:dev-setup-global` |
| `dev-setup-bundle` | Apply development-tool setup to explicit Git repositories from one external YAML manifest. | `/aquarium:dev-setup-bundle` with a manifest path |
| `test-setup` | Audit, propose, and configure the common Make or Bun testing contract for one repository, including evidence-backed legacy waivers. | `/aquarium:test-setup` |
| `docs-setup` | Audit, establish, adopt, or migrate the repository's canonical documentation structure and roadmap IDs. | `/aquarium:docs-setup` |
| `independent-review` | Run the canonical static review contract with fresh read-only Grok reviewer subagents, assessing a change or named Task/Epic completion, then adjudicate their findings. | `/aquarium:independent-review` with a staged, `HEAD`, commit, range, task, epic, or special-request target |
| `mulgae-review` | Run one report-only standalone Mulgae review of an exact change target or named Task or Epic completion candidate, outside an active Task or Epic handler. | `/aquarium:mulgae-review` with a review target |
| `orca-review` | Run the same review contract through a requested native reviewer that Orca owns and supervises, then adjudicate locally. | Automatic when you name both a target and a reviewer, or `/aquarium:orca-review` |
| `upgrade` | Adopt a newly released upstream Aquarium version in this generator repository, then publish the reviewed tag and GitHub Release. | `/aquarium:upgrade` with an optional released upstream version |

The four design skills drive Ouroboros as a bounded leaf capability and need it installed and pinned to `>=0.51.1,<0.54.0`. They shape documents only and never implement.

The development channel ships as plugin MCP: `.mcp.json` launches `tools/aquarium-dev/`. It is not a skill. Humanizer and `humanize-korean` install and diagnose at `~/.agents/skills/humanizer` and `~/.agents/skills/humanize-korean`.

`task-handler` loads seven phase skills in order — `task-plan`, `task-implement`, `task-refine`, `task-verify`, `task-document`, `task-review`, `task-close`. Invoke one directly only to resume that exact phase with its required task context.

Independent Review on this host is the native Grok review route. It dispatches `spawn_subagent` reviewers, carries a Review Brief, and can assess `change` or `completion`. It does not use Dolgorae. `workspace` and `dirty` scopes are unsupported because this backend holds no immutable capture. Prefer the bundled `aquarium:independent-reviewer` agent; fall back to `explore`.

Every skill except `task-commit` and `orca-review` carries `disable-model-invocation: true`.

## How generation works

```
upstream/                        git submodule, pinned to one upstream commit
  plugins/aquarium/              the Codex plugin — never edited here
overrides/
  manifest.json                  path → SHA-256 of the upstream file each override was derived from
  codex-exemptions.json          path → source digest of reviewed bytes, plus digest of the `Codex` lines that actually ship
  skills/... references/...      full-file replacements for host-specific divergence
additions/
  agents/...                     host-only plugin subagents with no upstream counterpart
  skills/...                     edition-owned skill files
scripts/sync.py                  the transformation
plugins/aquarium/                generated output, committed
```

Five files diverge semantically and are kept as overrides rather than substitutions. The shared review and intent contracts are restated by counted substitutions so new Orca and completion-review prose is byte-carried.

| Override | Why |
|---|---|
| `references/tool-catalog.md` | Registers Mulgae, Gaori, and Ouroboros in `~/.grok/config.toml`. Humanizer and `humanize-korean` live at `~/.agents/skills`. This edition does not diagnose Dolgorae. |
| `skills/independent-review/SKILL.md` | Dispatches `spawn_subagent` reviewers, preferring `aquarium:independent-reviewer`, otherwise `explore`, with intent-aware change and completion reviews. |
| `skills/dev-setup/SKILL.md` | Repository-local setup: Grok MCP, skill roots, `ask_user_question`, Ouroboros `grok` runtime. Does not offer Dolgorae. Plugin install stays in the host plugin-management flow. |
| `skills/dev-setup/references/agents-guidance.md` | AGENTS.md is Grok's native instruction file. |
| `skills/dev-setup-global/SKILL.md` | User-global setup for this host: no Dolgorae, Grok MCP, writing skills at `~/.agents/skills`. Plugin install stays in `grok plugin` marketplace flow. |

## Upgrade

```bash
git submodule update --init --recursive
git -C upstream fetch --tags origin
git -C upstream checkout <new-tag>
python3 scripts/sync.py
ruby tests/validate.rb
git add -A && git commit
```

## Validate

```bash
python3 scripts/sync.py --check
ruby tests/validate.rb
python3 -m unittest discover -s tests -p 'test_*.py'
git diff --check --cached
grok plugin validate plugins/aquarium
grok plugin details aquarium
```

Inspection scripts require Python 3.11 or newer (`tomllib`). CI uses 3.12. Local `git diff --check --cached` inspects the staged index; CI uses `git diff --check` from the empty tree to `HEAD` after the files are committed. `grok plugin validate plugins/aquarium` is a local install-time check; CI omits it because the runner has no `grok` binary. `grok plugin details aquarium` and `grok plugin validate plugins/aquarium` list the PreToolUse commit-gate hook and the `independent-reviewer` agent; Grok discovers `hooks/` and `agents/` by convention when `plugin.json` declares `skills`.

## Documentation style

Do not hard-wrap prose. Keep each prose paragraph on one source line; use line breaks only for structural Markdown, code, tables, lists, or other syntax where the break is meaningful.

## License

MIT, inherited from upstream.
