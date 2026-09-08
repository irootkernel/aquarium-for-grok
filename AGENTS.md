# AGENTS.md

Aquarium for Grok is a generated Grok plugin marketplace, and this file is its local agent guidance.

## Core Behavior

### 1. Inspect Before Acting

- Resolve repository facts and named authorities before implementation.
- State material assumptions, surface trade-offs, and ask when unresolved ambiguity would materially change the result.
- Push back when a request conflicts with repository authority, safety, or the user's stated goal.

### 2. Prefer the Smallest Complete Solution

- Implement only the verified requirement and reuse established patterns.
- Avoid speculative features, abstractions, configurability, and compatibility layers.
- Simplify an implementation whose size or complexity is not justified by its behavior.

### 3. Prefer Durable Root-Cause Solutions

- Address the verified root cause with the smallest complete approach, weighing correctness, maintainability, and structural fit rather than diff size.
- Prefer a durable design over a symptomatic patch; when the ideal design exceeds the current scope, ship a bounded step that fully satisfies the current success criteria and leaves a clear path forward.
- Record only remaining independent actionable work in the repository's canonical owner, and never defer work that current correctness or acceptance requires.

### 4. Make Surgical Changes

- Touch only what the requested outcome and its verification require.
- Preserve unrelated work and match local style.
- Remove only artifacts made obsolete by the current change.

### 5. Work Toward Verifiable Goals

- Define success checks before implementation.
- Match verification strength to the claimed behavior and relevant failure paths.
- Continue until the result is verified or a concrete blocker is established; report skipped checks and remaining uncertainty.

## Master Preferences

- Respond to Master in Korean using polite speech. When directly addressing the user, use exactly `Master`.
- Write plans, proposals, reviews, and other text shown to Master in Korean. Treat them as conversation, not repository artifacts, even when they live in a session file.
- Keep repository artifacts in the repository's established language and style. When no convention exists, use English unless Master requests otherwise.
- Report concise conclusions and useful evidence without exposing private chain-of-thought.

## Aquarium Development Guide

- Use `/lore-commits` for non-trivial commit messages and `/lore-query` to inspect recorded decision context.
- This repository is the generator of the Aquarium plugin, not a roadmap project: do not drive changes to it through the Aquarium workflow skills.
- Repository-specific rules in `Project Configuration` override these defaults.

## Project Configuration

### Repository Index and Authorities

- Purpose: a Grok plugin marketplace generated from the Codex plugin pinned as the `upstream/` submodule; the generated tree under `plugins/aquarium/` is committed so installation never depends on the submodule.
- `scripts/sync.py` is the transformation and the authority on every difference between upstream and the artifact.
- `overrides/manifest.json` and `overrides/codex-exemptions.json` pin the upstream digests each override and exemption was judged against.
- Canonical commands: `python3 scripts/sync.py`, `python3 scripts/sync.py --check`, `ruby tests/validate.rb`, `python3 -m unittest discover -s tests -p 'test_*.py'`, `git diff --check --cached`, and `grok plugin validate plugins/aquarium`. Local `git diff --check --cached` inspects the staged index; CI uses the empty-tree-to-`HEAD` form after commit.
- `overrides/codex-exemptions.json` pins the SHA-256 of the source bytes a human reviewed (upstream when the path is not overridden, override bytes when it is) and the digest of the `Codex` lines that actually ship.
- Inspection scripts require Python 3.11 or newer. CI uses 3.12 and does not run `grok plugin validate` because the runner has no `grok` binary.

### Commit Messages

- Start every commit title with exactly one uppercase header and one imperative summary. Use `[INT]` for upstream adoption, `[FIX]` for defect corrections, `[FEAT]` for new user-facing capabilities, `[DEV]` for development-tool changes, `[DOC]` for documentation, `[REL]` for releases, and `[TEST]` for tests.
- Write Lore trailers — `Constraint:`, `Rejected:`, `Directive:`, `Tested:`, `Not-tested:`, `Confidence:`, `Scope-risk:`, `Reversibility:` — on every non-trivial commit.

### Project-Specific Operating Rules

- Never edit `plugins/aquarium/` by hand. Change `scripts/sync.py`, `overrides/`, or `additions/`, run `python3 scripts/sync.py`, and commit the regenerated tree together with its source change.
- Independent Review on this host uses Grok subagents only. Do not reintroduce Dolgorae as a review backend.
- Keep every prose paragraph in Markdown on one source line.
- Do not push or create tags without explicit direction.
