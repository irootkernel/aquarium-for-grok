# Override Re-derivation

How this edition re-derives overrides, exemptions, and script rules when the upstream pin moves, and the traps that are invisible in the code. Read this before resolving the first sync abort.

## The Counted-Swap Method

- Re-derive every stale override from the new upstream text, porting this edition's divergence onto it; never patch the previous override, because unnoticed drift compounds across releases.
- Extract old text blocks from the checked-out submodule with `sed -n` line ranges verified by head, tail, and uniqueness, or scan the release archive in memory with `gh api repos/irootkernel/aquarium/tarball/vX.Y.Z`.
- Replay the differences hunk by hunk in document order, and verify each replacement target occurs exactly once before swapping; a swap whose target count is not one is the wrong swap.
- For script rules, reconstruct the in-file literal from the imported table with per-line `json.dumps(..., ensure_ascii=False)` — em-dashes make ASCII escaping diverge — and require a count of exactly one before replacing.
- Rotate a digest in `overrides/manifest.json` only after the override is re-derived, and rotate both the source and shipped-line digests in `overrides/codex-exemptions.json` only after re-reading every surviving third-party CLI mention in the shipped file.

## Known Traps

- `references/orca-supervision.md` was the only shipped match of the orca-cli sigil rule until v0.1.14 gave that rule a second match in `orca-review/SKILL.md`. Recount before assuming an override there is safe; a rule whose last shipped match moves inside an override target dies silently at the next adoption.
- The create-prefixed sigil rule counts exactly one shipped match because its occurrence in `agents-guidance.md` is override-shadowed; overriding `references/podway-integration.md` would drive it to zero, the same class of trap.
- The task-close closeout rule stays ordered before the generic input-tool substitution because its anchor contains the generic needle, and the generic rule survives on a single `docs-setup` match.
- The isolated and direct Ouroboros launcher matchers are called from `inspect_ouroboros`; `tests/validate.rb` does not pin them as unused. Recheck those call sites on every adoption.
- The `independent-review` override reached across skill directories for the repository-state inspector until upstream deleted it in v0.1.14. The edition now owns that inspector as an addition under `independent-review` itself, and `tests/validate.rb` asserts both that it ships and that the skill no longer names the old cross-skill path.
- `check_rule_usage` counts SCRIPT_SUBSTITUTIONS after script surgery. A rule whose only match sits inside a function that `SCRIPT_SURGERY` later replaces or deletes reports healthy if counted before surgery and ships nothing; recount remaining `new` text after the rewrite, take `min(usage, remaining)`, skip override-shadowed paths, and never raise a zero usage to one.
- The `todo_write` naming rule is this edition's to retire if the harness renames the tool; its upstream anchor keeps matching either way, so no abort will surface it. The same holds for any host tool this edition names in replacement text: the release-qa substitution names `spawn_subagent`.
- The sigil scan assumes every lowercase dollar-prefixed name in Markdown is a skill invocation, which v0.1.14 broke with the shell variables in `task-commit`'s `git -c` snippet. Name each new false positive in `SIGIL_LITERALS` rather than narrowing the pattern, and mirror it into `tests/validate.rb`, which compares the two lists as sets. The scan covers additions too, so an unlisted sigil-shaped token written into this file or any other addition stops generation just as an upstream one would. v0.1.15 added `$aquarium_dev_branch` and `$aquarium_dev_branch_status` in `tools/aquarium-dev/dev_manager.py`; keep those literals listed.
- Invocation gating is upstream's decision, not a fixed set: v0.1.14 opened `orca-review` to implicit invocation. Read the model-invocable set from the sidecars on every adoption instead of asserting a remembered one.
- The generated-script gate parses, checks call arity including keyword calls, and rejects unresolved module globals, so block rules must still swallow every downstream reader of the locals they delete; the MCP-inspection unit tests remain the executable coverage.
- The bundled reviewer subagent has no digest gate against the review contract it serves; re-read them together when upstream changes that contract.
- `SCRIPT_SURGERY` replacement bodies are pinned to the SHA-256 of the upstream function they overwrite. A pin abort means re-derive the replacement from the new body, then rotate the `upstream` digest in the surgery plan. Re-read every replaced function on each adoption even when the pin is unchanged. v0.1.16 moved the global MCP view to `inspect_global_mcp_scope` in `inspect_tools.py`; the global script's `inspect_global_mcp` wrapper is host-neutral and must not be replaced. Keep surgery on `inspect_global`, `parse_arguments`, and `main` in `inspect_global_tools.py` because those still name Dolgorae and `--codex-home`.
- Writing-skill live targets stay `~/.agents/skills/humanizer` and `~/.agents/skills/humanize-korean`. Upstream v0.1.16 adopted that root; do not reintroduce `inspect_im_not_ai` surgery, and do not patch an installed plugin cache to compensate.
- v0.1.16 deleted `named_mcp_server_missing`. Leaving it in a surgery delete list aborts generation. Drop it when the pin moves.
- v0.1.16 disabled Dolgorae-backed Independent Review. This edition keeps the native `spawn_subagent` route; restate `review-intent-contract.md`, `review-contract.md`, and `finding-disposition.md` with counted substitutions rather than a full review-contract override. Do not name the excluded Dolgorae capture-contract file in generated text.
- v0.1.16 added `mulgae-review`. Give it an argument hint and keep it model-non-invocable from the sidecar.
- `README.ko.md` has no automated agreement check with `README.md`; mirror every change by hand and re-read both.
- `.yaml` files are in the data-substitution table with `.json`. A Podway procedure that grows a host sigil is rewritten by that table, not by a Markdown substitution; do not add a Markdown-only rule and expect it to apply.

## Verifying a Re-derivation

- Generation is the first gate: every substitution rule must match text that ships, and a rule whose only matches are override-shadowed is dead.
- A new sigil family needs its forbidden needle added to both the Python table and the Ruby list, which the validator compares as sets; a needle added to one side alone reports healthy.
- After the five validation commands pass, prove presence with `grok plugin details aquarium` or `grok inspect --json`. Model-invocability is the generated frontmatter (`disable-model-invocation`), which `tests/validate.rb` already asserts against the upstream sidecars: only `task-commit` and `orca-review` stay model-invocable.
