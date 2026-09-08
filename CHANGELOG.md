# Changelog

This file records concise shipped outcomes of the Aquarium for Grok edition. Upstream outcomes live in the [Aquarium changelog](https://github.com/irootkernel/aquarium/blob/main/CHANGELOG.md).

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
