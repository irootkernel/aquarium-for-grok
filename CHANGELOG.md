# Changelog

This file records concise shipped outcomes of the Aquarium for Grok edition. Upstream outcomes live in the [Aquarium changelog](https://github.com/irootkernel/aquarium/blob/main/CHANGELOG.md).

## Unreleased

### Changed

- Adopt upstream Aquarium v0.1.17 and generate the Grok marketplace from that pin.
- Keep completion-review route token `native-codex` byte-stable and run that route as fresh read-only Grok reviewer subagents: `spawn_subagent` with `background: true`, `isolation: none`, and the Git root as `cwd`, preferring `aquarium:independent-reviewer` on `grok-4.7` and falling back to `explore`. Independent Review stays the standalone entrypoint for the same dispatch.
- Raise tool floors with the catalog: Mulgae v0.1.23 with Grok pinned to `grok-4.7`, Podway v0.2.11, Humanizer `>=v2.11.1`, im-not-ai `>=v2.3.2`, and Ouroboros `>=0.51.1` without an upper bound.
- Stop shipping `tools/`, `aquarium-status`, and the development-channel contract. Those runtimes stay with the upstream Aquarium edition.

### Fixed

- Keep the Grok `aquarium` install in front of a same-named Claude-compat plugin by `ln -sfn` of the `grok plugin list --json` `path` (not `source`) onto `~/.grok/plugins/aquarium` after marketplace update, and refuse Claude-path Aquarium skills in this generator's agent guidance.

## v0.1.16 - 2026-09-16

### Added

- Adopt upstream Aquarium v0.1.16 and generate the Grok marketplace from that pin.
- Ship `/aquarium:mulgae-review` for one report-only standalone Mulgae review of an exact change target or named Task or Epic completion candidate.
- Carry intent-aware Task, Goal, and Epic completion reviews that classify every requirement `met`, `unmet`, `unverified`, or `not-applicable`.

### Changed

- Keep Independent Review as the native Grok `spawn_subagent` route. Upstream disabled its Dolgorae-backed entrypoint; this edition does not adopt that stub. Review Briefs, change-versus-completion purpose, and criterion aggregation land on the bundled `aquarium:independent-reviewer` path.
- Restate the shared review and intent contracts with counted substitutions instead of a full `review-contract.md` override, so new Orca proportional-review prose is byte-carried.
- Raise tool floors with the catalog: Mulgae v0.1.21 (`mulgae-command-result.v8`), Gaori v0.1.17 (seven-file `use-gaori` tree), Sanho v0.2.8 (five-file `use-sanho` tree), and Sorage v0.1.1 with the root `.sorage/` ignore rule.
- Move plugin install and update requests out of setup skills into the host `grok plugin` marketplace flow.
- Drop the deleted Aquarium for Kimi edition link.

### Fixed

- Retire `inspect_im_not_ai` surgery: upstream now diagnoses `humanize-korean` at `~/.agents/skills`.
- Route the user-global MCP view through `inspect_global_mcp_scope` reading `~/.grok/config.toml`, and stop replacing the now host-neutral global wrapper.
- Read aquarium-dev bundled identity from `plugin.json` instead of missing `.codex-plugin/plugin.json`.
- Drop Dolgorae from global-setup freshness authorization, agents-guidance review routing, and the bundle-manifest component paragraph.

## v0.1.15 - 2026-09-08

### Added

- Adopt upstream Aquarium v0.1.15 and generate the Grok marketplace from that pin.
- Ship `dev-setup-global` for user-global CLI, skill, MCP, and Ouroboros diagnosis. The development channel moves from an `aquarium-dev` skill to plugin `.mcp.json` plus `tools/aquarium-dev/`.
- Treat optional Sorage as a diagnosed global component. Production-binary readiness remains Podway, Mulgae, and Gaori.

### Changed

- Keep Independent Review on Grok `spawn_subagent` with four scopes. This edition still does not diagnose or install Dolgorae.
- Install and diagnose Humanizer and `humanize-korean` at `~/.agents/skills/humanizer` and `~/.agents/skills/humanize-korean`. Do not treat `$CODEX_HOME/skills/humanize-korean` as a live target.
- Read Mulgae, Gaori, and Ouroboros MCP from `~/.grok/config.toml` in both repository and global inspectors. Discover Ouroboros homes from `$GROK_HOME` / `~/.grok`.

## v0.1.14 - 2026-09-07

### Added

- Generate a Grok plugin marketplace from upstream Aquarium v0.1.14.
- Dispatch Independent Review through Grok `spawn_subagent`, with a bundled `aquarium:independent-reviewer` and `explore` fallback. This edition does not install or diagnose Dolgorae.
- Register Mulgae, Gaori, and Ouroboros MCP servers in `~/.grok/config.toml` without starting them during setup.
- Gate roadmap commits with a PreToolUse hook that matches `run_terminal_command` and reads camelCase `toolInput`. Truncated Grok hook payloads fail closed in a roadmap repository, with a distinct deny reason that names truncation rather than `task-commit`.
- Treat an unborn `HEAD` `staged` target as the empty tree to the index.
- Ship `/aquarium:upgrade` for this generator repository.

### Changed

- Stop Independent Review before dispatch when the target inspector fails, and return its result in the review envelope.
- Count script substitutions after surgery without masking dead rules; pin shipped `Codex` lines in exemptions; isolate Git fixtures from the developer global config.
- Pin `SCRIPT_SURGERY` replacements to upstream function digests; disclose MCP `${VAR}` pre-expansion and live skill/MCP refresh; declare `mcpInheritance: none` and Claude-compatible `permissionMode: plan` on the bundled reviewer (read-only rests on the tools allowlist, not plan mode), with both shell tool spellings in the allowlist and the commit-gate matcher.
- Refuse generation from a dirty upstream worktree; degrade only the unreadable MCP config scope; name the Aquarium `task-commit` skill without a slash form in hook deny strings.
- Restore `ask_user_question` availability fallback; isolate inspect_tools Git from the developer config; decode non-UTF-8 Git paths in the target inspector.
