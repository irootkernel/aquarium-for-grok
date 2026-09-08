---
name: upgrade
description: "Upgrade this edition to a newly released upstream Aquarium version: pin the submodule, resolve every sync abort, re-derive overrides and exemptions, validate, and publish the reviewed tag and GitHub Release. Use when the user explicitly invokes /aquarium:upgrade with one released upstream version; do not use for unreleased upstream commits or unrelated repository work."
argument-hint: "[version]"
disable-model-invocation: true
---

# Upgrade

Bring this generated edition from its pinned upstream Aquarium release to a newly released one through the repository's deterministic transformation, then publish and install it behind explicit user review. The upstream submodule at `upstream/` is read-only evidence: nothing beyond the tag checkout ever touches it, and every mutation stays in this repository.

## Authorization

Explicit invocation authorizes read-only inspection of this repository, the upstream submodule, and the configured Git remote. It does not authorize credential inspection, authentication changes, destructive state repairs, or publication mutations. Obtain separate approval at each mutating boundary — the pin, the first edit, each commit, the push, the tag, the release, and the local installation refresh — and put every material decision through `ask_user_question`.

## Orchestration Contract

The invoking conversation is the orchestrator: it plans, decides, reviews every subagent product, tracks goal achievement, and confirms every material decision with the user through `ask_user_question`; subagents gather evidence and apply approved edits, and nothing else.

- Mirror the phase plan into the Grok todo list through `todo_write` when the upgrade begins and keep it current as phases complete.
- Gather evidence through read-only `spawn_subagent` calls, preferring `explore` for mechanical collection.
- Synthesize the gathered evidence into one adaptation plan yourself; subagents inform the plan and never own a decision.
- Review each subagent product against the plan before the next gate.

## Establish the Request

1. Verify the working directory is this marketplace repository: `scripts/sync.py` exists, `.grok-plugin/marketplace.json` names `aquarium-for-grok`, and `upstream/` is the pinned submodule. Refuse to run anywhere else.
2. Take the intended upstream release in tag form (`vX.Y.Z`) from the argument, or discover the newest released upstream tag and confirm it with the user. Refuse an unreleased branch or commit.
3. Record the starting state before touching anything: the checked-out branch and its cleanliness — a dirty tree stops the run — the pinned upstream commit, the generated version in `plugins/aquarium/plugin.json`, and the intended version.
4. Confirm the intended version is newer than the generated one. A downgrade or a re-pin of the already adopted version needs an explicit user decision before continuing.

## Pin Upstream

1. Run `git submodule update --init --recursive`, then `git -C upstream fetch --tags origin`, then `git -C upstream checkout vX.Y.Z`, then `git add upstream`, and record the resolved commit. The tag, never a branch, is the pin.
2. Read the absorbed range whole — the upstream changelog, the release notes, and the commit log since the previous pin.

## Resolve the Sync Loop

Run `python3 scripts/sync.py` repeatedly. Every abort names its own fix and stops generation rather than producing partial output. Read `references/rederivation.md` before resolving the first abort. Work the classes in this order:

1. Stale override — re-derive from the new upstream text with counted swaps and rotate `overrides/manifest.json`.
2. Stale exemption — re-read remaining third-party CLI mentions and rotate `overrides/codex-exemptions.json`.
3. Dead substitution rule — delete or re-derive.
4. Surviving host-specific text — substitution, override, or reviewed exemption.
5. New skill sigil family — add the slash form and matching forbidden needles in both `scripts/sync.py` and `tests/validate.rb`.
6. Script surgery abort — re-derive the named-function plan.
7. Unknown upstream directory — decide copy or exclude.

This edition does not use Dolgorae as a review backend; do not reintroduce it when absorbing an upstream Independent Review rewrite. Hook payloads on this host are camelCase (`toolInput`). MCP registrations live in `~/.grok/config.toml`. MCP tools are called through `search_tool` then `use_tool`. Ouroboros is runtime-only (`ooo setup --runtime grok`).

## Validate and Document

1. Run `python3 scripts/sync.py --check`, `ruby tests/validate.rb`, `python3 -m unittest discover -s tests -p 'test_*.py'`, `git diff --check --cached`, and `grok plugin validate plugins/aquarium`.
2. Update `README.md` and `README.ko.md` together and record shipped outcomes under the open `Unreleased` section of `CHANGELOG.md`.

## Commit Behind Review

Create bisectable commits in this repository's style with Lore trailers on non-trivial commits. Then stop: no push, tag, release, or installation without the user's explicit approval.

## Release After Approval

1. Push `main`.
2. Create the annotated tag `vX.Y.Z` titled `Aquarium for Grok vX.Y.Z` and push it.
3. Publish the GitHub release.
4. Write `.grok-plugin/plugin-index.json` with this release commit as the plugin `sha` so installs under `[marketplace] require_sha = true` can pin it. The first commit of this edition cannot carry its own sha; emit the file after that commit exists.
5. When the user asks, refresh the local installation with `grok plugin marketplace update` and `grok plugin update aquarium`, then tell the user a new session is required.

## Boundaries

- Never edit `plugins/aquarium/` by hand; every change flows through `scripts/sync.py`, `overrides/`, or `additions/`.
- Never push to, tag, or mutate the upstream repository.
- Never pin upstream `main` or an unreleased commit.
- Never bypass a sync abort.
