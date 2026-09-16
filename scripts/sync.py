#!/usr/bin/env python3
"""Generate the Grok plugin from the pinned upstream Codex plugin.

The upstream repository at `upstream/` is the single source of truth. This
script performs a deterministic transformation into `plugins/aquarium/`,
which is committed so the plugin installs even when the submodule is absent.

Run `sync.py` to regenerate, or `sync.py --check` to fail on drift.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
UPSTREAM = REPOSITORY / "upstream"
UPSTREAM_PLUGIN = UPSTREAM / "plugins" / "aquarium"
OUTPUT = REPOSITORY / "plugins" / "aquarium"
OVERRIDES = REPOSITORY / "overrides"
OVERRIDE_MANIFEST = OVERRIDES / "manifest.json"
CODEX_EXEMPTIONS = OVERRIDES / "codex-exemptions.json"
ADDITIONS = REPOSITORY / "additions"
SYNC_MANIFEST = "sync-manifest.json"

COPIED_DIRECTORIES = ("skills", "references", "assets", "hooks", "tools")
COPIED_ROOT_FILES = (".mcp.json",)
TEXT_SUFFIXES = (".md",)
SCRIPT_SUFFIXES = (".py",)
DATA_SUFFIXES = (".json", ".yaml")
SCANNED_SUFFIXES = TEXT_SUFFIXES + SCRIPT_SUFFIXES + DATA_SUFFIXES
# tools/ ships a suffix-less launcher and a hash-pinned requirements file.
# Those bytes are not host-rewritten; scanning them would force a global
# suffix expansion that then misses host needles in the rest of the tree.
UNSCANNED_SHIPPED_PREFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tools/", ("", ".txt")),
)

ADDED_PATHS: tuple[str, ...] = (
    "agents/independent-reviewer.md",
    "skills/upgrade/SKILL.md",
    "skills/upgrade/references/rederivation.md",
    "skills/independent-review/scripts/inspect_repository_state.py",
)

ARGUMENT_HINTS: dict[str, str] = {
    "epic-handler": "<roadmap-path> <epic-id>",
    "epic-validator": "<roadmap-path> <epic-id>",
    "task-handler": "<roadmap-path> <task-id>",
    "task-plan": "<roadmap-path> <task-id>",
    "task-implement": "<roadmap-path> <task-id>",
    "task-verify": "<roadmap-path> <task-id>",
    "task-refine": "<roadmap-path> <task-id>",
    "task-document": "<roadmap-path> <task-id>",
    "task-review": "<roadmap-path> <task-id>",
    "task-close": "<roadmap-path> <task-id>",
    "release-handler": "[version]",
    "release-qa": "[version]",
    "dev-setup-bundle": "<manifest-path>",
    "independent-review": "<target> [task-or-epic-id]",
    "orca-review": "<target> [task-or-epic-id]",
    "mulgae-review": "<target> [task-or-epic-id]",
}

ADDITION_ARGUMENT_HINTS: dict[str, str] = {
    "upgrade": "[version]",
}

EXCLUDED_FILES: tuple[tuple[str, str], ...] = (
    (
        "assets/hero.png",
        "a 2.3 MB banner for the upstream repository README",
    ),
    (
        "references/dolgorae-review-contract.md",
        "the Dolgorae capture contract; this edition's independent review dispatches Grok subagents",
    ),
    (
        "skills/dev-setup-global/scripts/verify_dolgorae_release.py",
        "Dolgorae GitHub release verification; this edition does not diagnose Dolgorae",
    ),
)

SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    (
        "`workspace` and `dirty` remain outside this workflow. Report the unsupported "
        "Orca scope and ask for an explicitly selected supported target or review route; "
        "Independent Review is disabled and is not a fallback. Never stage paths or "
        "reinterpret state merely to manufacture an Orca Review target.",
        "`workspace` and `dirty` remain outside this workflow. Report the unsupported "
        "Orca scope and ask for an explicitly selected supported target. Independent "
        "Review on this host also cannot capture `workspace` or `dirty`. Never stage "
        "paths or reinterpret state merely to manufacture an Orca Review target.",
    ),
    (
        "Dolgorae remains unenrolled until its repository creates and validates the approved "
        "producer commit, enrolls that canonical checkout, and publishes the exact committed "
        "generation. Before enrollment, the launcher resolves the required global Dolgorae; "
        "if neither generation exists, it fails closed and requests `$aquarium:dev-setup-global`.",
        "Dolgorae remains an optional development producer until its repository creates and "
        "validates the approved producer commit, enrolls that canonical checkout, and publishes "
        "the exact committed generation. A missing global Dolgorae is not fail-closed readiness "
        "and is not diagnosed or installed by `/aquarium:dev-setup-global`.",
    ),
    ("$aquarium:", "/aquarium:"),
    (
        "Independent Review would require a fresh capture if separately re-enabled.",
        "Independent Review rebinds a fresh reviewer dispatch to the corrected target.",
    ),
    ("$use-", "/use-"),
    ("$create-", "/create-"),
    ("$lore-commits", "/lore-commits"),
    ("$orca-cli", "/orca-cli"),
    ("$interview", "/interview"),
    ("$deslop", "/deslop"),
    ("$seed", "/seed"),
    ("$pm", "/pm"),
    ("$qa", "/qa"),
    (
        "Use structured `request_user_input` when available and ask all three questions together",
        "Use structured `ask_user_question` when available and ask all three questions together",
    ),
    ("`request_user_input`", "`ask_user_question`"),
    ("Codex goal", "Grok todo list"),
    ("fresh Codex audit", "fresh from-scratch audit"),
    ("Codex skill health", "Grok skill health"),
    ("Codex home", "Grok home"),
    ("Codex objective", "Grok todo-list objective"),
    ("Codex tool contract", "Grok todo-list contract"),
    ("Restart Codex", "Restart Grok"),
    (
        "Use the available agent delegation surface to dispatch fresh subagents for independent risk clusters.",
        "Use `spawn_subagent` to dispatch fresh subagents for independent risk clusters.",
    ),
    (
        "Parallelize independent clusters when capacity allows without weakening isolation.",
        "Parallelize independent clusters by launching their workers in a single message with `background: true` when capacity allows, without weakening isolation, and collect each result through `get_command_or_subagent_output`.",
    ),
    (
        "  tools: [dolgorae, mulgae, gaori, sorage, podway, ouroboros, lora, deslop, humanizer, im-not-ai]",
        "  tools: [mulgae, gaori, sorage, podway, ouroboros, lora, deslop, humanizer, im-not-ai]",
    ),
    (
        "Supported tools are `sanho`, `dolgorae`, `mulgae`, `gaori`, `sorage`, `podway`, `ouroboros`, `lora`, `deslop`, `humanizer`, and `im-not-ai`.",
        "Supported tools are `sanho`, `mulgae`, `gaori`, `sorage`, `podway`, `ouroboros`, `lora`, `deslop`, `humanizer`, and `im-not-ai`. This edition does not accept `dolgorae`.",
    ),
    (
        "The `dolgorae` component selects its CLI and same-release `use-dolgorae` skill "
        "for shared global preparation; it does not initialize workspaces or configure Profiles.\n\n",
        "",
    ),
    (
        "The bundled hook is a local guardrail, not complete enforcement: it detects direct shell `git commit` invocations in roadmap repositories, while indirect commits performed by other tools may not pass through that boundary.",
        "The bundled hook is a local guardrail, not complete enforcement: it detects direct shell `git commit` invocations in roadmap repositories, while indirect commits performed by other tools may not pass through that boundary. It is inert until the plugin is trusted.",
    ),
    (
        "Use this contract for one static, read-only review through `/aquarium:orca-review`. "
        "Read [review-intent-contract.md](review-intent-contract.md) for the Review Brief "
        "and change-versus-completion semantics, then read "
        "[finding-disposition.md](finding-disposition.md) for adjudication and remediation. "
        "The Dolgorae-backed `/aquarium:independent-review` route is temporarily disabled "
        "and stops before setup or source transmission; its historical target meanings "
        "remain documented here for compatibility and possible future re-enablement.",
        "Use this contract for one static, read-only review through "
        "`/aquarium:independent-review` or `/aquarium:orca-review`. Read "
        "[review-intent-contract.md](review-intent-contract.md) for the Review Brief and "
        "change-versus-completion semantics, then read "
        "[finding-disposition.md](finding-disposition.md) for adjudication and remediation. "
        "On this edition `/aquarium:independent-review` dispatches fresh reviewer "
        "subagents through `spawn_subagent`; the Dolgorae machinery its Independent "
        "Review half documents is not used here.",
    ),
    (
        "| Dolgorae capture | Unsupported |",
        "| Unsupported | Unsupported |",
    ),
    (
        "reviewed through `git diff --cached`. | Dolgorae capture |",
        "reviewed through `git diff --cached`. On an unborn `HEAD` this is the empty "
        "tree to the index. | Reviewer subagent reads |",
    ),
    (
        "| Dolgorae capture | Current registered worktree Git reads |",
        "| Reviewer subagent Git reads | Current registered worktree Git reads |",
    ),
    (
        "When re-enabled, Independent Review uses Dolgorae's checked immutable capture as target authority. "
        "Its dormant candidate, capture, manifest, path-safety, lifecycle, settlement, and "
        "recovery rules are defined by [dolgorae-review-contract.md](dolgorae-review-contract.md).",
        "Independent Review reads the selected target directly in this host's own checkout through fresh read-only reviewer subagents. "
        "For `staged`, a reviewer inspects `git diff --cached`, the staged files, and their callers. "
        "For `head`, `commit`, and `range`, a reviewer obtains file content and diffs from the resolved revisions through read-only Git commands and never substitutes current index or worktree bytes. "
        "It copies no repository source into a separate store and binds no digest as target authority, so `workspace` and `dirty` remain unsupported.",
    ),
    (
        "When re-enabled, Independent Review also reports ignored state under its "
        "capture contract.",
        "Independent Review also reports ignored state through its target inspector.",
    ),
    (
        "When re-enabled, `independent-review` uses one guarded Dolgorae `specialist.review` v2 operation "
        "to capture the target and run one fresh Codex Reviewer. It creates and accepts no "
        "Orca Run, Task, Dispatch, worker, terminal, context, or worktree. Missing or "
        "invalid Dolgorae state fails closed without Orca fallback.",
        "`independent-review` dispatches one or more fresh read-only reviewer subagents through `spawn_subagent`. "
        "It creates and accepts no Orca Run, Task, Dispatch, worker, terminal, context, or worktree, "
        "and performs no Dolgorae discovery, capture, or launch. An unavailable subagent mechanism, "
        "a failed dispatch, or a reviewer that returns no usable output fails closed without Orca fallback.",
    ),
    (
        "The disabled Independent Review route performs no settlement or recovery. "
        "Orca Review follows its live Orca guides and "
        "[orca-supervision.md](orca-supervision.md), including authoritative "
        "observation on deadline exhaustion.",
        "Independent Review settles from its own dispatch results and its repository-state "
        "comparison, under the liveness budget its skill discloses. "
        "Orca Review follows its live Orca guides and "
        "[orca-supervision.md](orca-supervision.md), including authoritative "
        "observation on deadline exhaustion.",
    ),
    (
        "Independent Review additionally returns its target digest, capture, manifest,\n"
        "source-mutation observation, target-integrity result, and Dolgorae settlement\n"
        "evidence when that route is enabled.",
        "Independent Review additionally returns one row per dispatched reviewer — subagent type, "
        "assigned lens, effective model, its own verdict, and its dispatch status — together with "
        "its repository-state baseline, comparison, any observed drift, and its target-inspector result.",
    ),
    (
        "Use this contract whenever an enabled Aquarium route asks a reviewer to "
        "assess a change or completion, and for the disabled "
        "`/aquarium:independent-review` entrypoint's refusal and routing decision.",
        "Use this contract whenever an enabled Aquarium route asks a reviewer to "
        "assess a change or completion, including the "
        "`/aquarium:independent-review` entrypoint's native reviewer-subagent "
        "route.",
    ),
    (
        "## Route a disabled Independent Review request\n"
        "\n"
        "The disabled `/aquarium:independent-review` entrypoint owns only its refusal "
        "and routing decision. Apply this matrix before any discovery, setup, source "
        "handling, provider contact, or review launch:\n"
        "\n"
        "| Explicitly preselected supported alternative | Result |\n"
        "| --- | --- |\n"
        "| None | Explain the refusal and available alternatives; launch nothing. |\n"
        "| Exactly one Orca route | Preserve the original target and review question, "
        "validate the requested reviewer and supported target, then invoke "
        "`/aquarium:orca-review` under its own contract. |\n"
        "| Exactly one native Codex route | Preserve the original target and review "
        "question. Use a fresh host-native review subagent only when the host exposes "
        "native delegation; otherwise report the unavailable route and stop without "
        "fallback. |\n"
        "| More than one alternative | Ask the user to choose exactly one route; "
        "launch nothing. |\n"
        "\n"
        "The selected route owns execution, source handling, lifecycle, evidence, and "
        "result. The disabled entrypoint adds no fallback, translation, or backend "
        "guarantee.",
        "## Route an Independent Review request\n"
        "\n"
        "The `/aquarium:independent-review` entrypoint owns the native "
        "`spawn_subagent` route below and runs only that route. Apply this matrix "
        "before any discovery, setup, source handling, provider contact, or review "
        "launch:\n"
        "\n"
        "| Explicitly preselected supported alternative | Result |\n"
        "| --- | --- |\n"
        "| None | Dispatch fresh read-only host-native reviewer subagents under the "
        "contract below. |\n"
        "| Exactly one Orca route | Preserve the original target and review question, "
        "validate the requested reviewer and supported target, then invoke "
        "`/aquarium:orca-review` under its own contract. |\n"
        "| More than one alternative | Ask the user to choose exactly one route; "
        "launch nothing. |\n"
        "\n"
        "The selected route owns execution, source handling, lifecycle, evidence, and "
        "result. The entrypoint adds no fallback, translation, or backend guarantee.",
    ),
    (
        "## Use a native Codex review subagent\n"
        "\n"
        "Use a fresh host-native Codex subagent only after the user explicitly selects\n"
        "that review route and the current host exposes native delegation. Give it the\n"
        "same Review Brief, exact target, and approved context that another enabled\n"
        "static route would receive. Do not invent a delegation tool or silently choose\n"
        "Orca, Mulgae, or another backend when native delegation is unavailable.",
        "## Use a native Grok review subagent\n"
        "\n"
        "The host's `spawn_subagent` tool provides the fresh native delegation this route\n"
        "requires, and `/aquarium:independent-review` invokes it on an explicit request.\n"
        "Give a dispatched subagent the same Review Brief, exact target, and approved\n"
        "context that another enabled static route would receive. Do not invent a\n"
        "delegation tool or silently choose Orca, Mulgae, or another backend when that\n"
        "dispatch is unavailable.",
    ),
    (
        "Use only the lifecycle and evidence the host actually provides. Do not describe\n"
        "this route as Independent Review, Dolgorae, Orca, or Mulgae, and do not claim an\n"
        "immutable capture, publication, settlement, or recovery guarantee that was not\n"
        "observed.",
        "Use only the lifecycle and evidence the host actually provides. Do not describe\n"
        "this route as Dolgorae, Orca, or Mulgae, and do not claim an immutable capture,\n"
        "publication, settlement, or recovery guarantee that was not observed. On this\n"
        "host the route is `/aquarium:independent-review`, and its freshness guarantee\n"
        "is only the reviewer's unshared context.",
    ),
    (
        "from Mulgae Review, Orca Review, an explicitly selected native Codex review "
        "subagent, or the dormant Independent Review contract if that route is "
        "re-enabled.",
        "from Mulgae Review, Orca Review, or the fresh reviewer subagents dispatched "
        "by `/aquarium:independent-review`.",
    ),
    (
        "The disabled `/aquarium:independent-review` route itself only reports its "
        "refusal and alternative guidance; that refusal launches nothing. Exactly one "
        "explicitly preselected supported Orca or native Codex alternative may run only "
        "under its own contract, and native Codex additionally requires host fresh "
        "delegation. Multiple preselected alternatives require the user to choose one "
        "before anything launches. A direct `/aquarium:task-review`, standalone "
        "`/aquarium:mulgae-review`, or standalone `/aquarium:orca-review` is report-only.",
        "`/aquarium:independent-review` runs its native reviewer-subagent route under "
        "the intent contract, and a request preselecting another review backend runs "
        "only under that backend's own contract. Multiple preselected backends require "
        "the user to choose one before anything launches. A direct "
        "`/aquarium:task-review`, standalone `/aquarium:independent-review`, "
        "`/aquarium:mulgae-review`, or `/aquarium:orca-review` is report-only.",
    ),
)

SCRIPT_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    (
        "import shutil\n"
        "import stat\n"
        "import subprocess\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n"
        "from typing import Any\n"
        "\n"
        "try:\n"
        "    import yaml\n"
        "except ModuleNotFoundError as error:\n"
        '    if error.name != "yaml":\n'
        "        raise\n"
        "    yaml = None  # type: ignore[assignment]\n"
        "\n"
        "GLOBAL_SCRIPT_DIRECTORY = str(\n"
        '    Path(__file__).resolve().parents[2] / "dev-setup-global/scripts"\n'
        ")\n"
        "if GLOBAL_SCRIPT_DIRECTORY not in sys.path:\n"
        "    sys.path.insert(0, GLOBAL_SCRIPT_DIRECTORY)\n"
        "\n"
        "try:\n"
        "    import verify_dolgorae_release as dolgorae_release\n"
        "except ModuleNotFoundError as error:\n"
        '    if error.name != "verify_dolgorae_release":\n'
        "        raise\n"
        "    dolgorae_release = None\n",
        "import shutil\n"
        "import subprocess\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n"
        "from typing import Any\n"
        "\n"
        "try:\n"
        "    import yaml\n"
        "except ModuleNotFoundError as error:\n"
        '    if error.name != "yaml":\n'
        "        raise\n"
        "    yaml = None  # type: ignore[assignment]\n",
    ),
    ("InvalidCodexHome", "InvalidHostHome"),
    ("per-Codex-home", "per-Grok-home"),
    ("Ouroboros Codex home", "Ouroboros Grok home"),
    ("Codex home", "Grok home"),
    ("configures Codex", "configures Grok"),
    (
        "    environment = os.environ.copy()\n"
        "    for name in tuple(environment):\n"
        '        if name.startswith("GIT_"):\n'
        "            del environment[name]\n"
        '    environment["LANG"] = "C"\n'
        '    environment["LC_ALL"] = "C"\n',
        "    environment = os.environ.copy()\n"
        "    for name in tuple(environment):\n"
        '        if name.startswith("GIT_"):\n'
        "            del environment[name]\n"
        '    environment["GIT_CONFIG_GLOBAL"] = os.devnull\n'
        '    environment["GIT_CONFIG_NOSYSTEM"] = "1"\n'
        '    environment["GIT_OPTIONAL_LOCKS"] = "0"\n'
        '    environment["LANG"] = "C"\n'
        '    environment["LC_ALL"] = "C"\n',
    ),
    (
        'REQUIRED_GLOBAL_COMMANDS = frozenset({"podway", "mulgae", "gaori", "dolgorae"})\n',
        'REQUIRED_GLOBAL_COMMANDS = frozenset({"podway", "mulgae", "gaori"})\n',
    ),
    (
        '            "use-dolgorae": Path.home() / ".agents/skills/use-dolgorae",\n',
        "",
    ),
    (
        '    "sanho",\n'
        '    "dolgorae",\n'
        '    "mulgae",\n',
        '    "sanho",\n'
        '    "mulgae",\n',
    ),
    (
        "DOLGORAE_SKILL_FILES = (\n"
        '    "SKILL.md",\n'
        '    "references/configuration.md",\n'
        '    "references/lifecycle.md",\n'
        '    "references/recovery.md",\n'
        ")\n",
        "",
    ),
    (
        '    codex_home = os.environ.get("CODEX_HOME")\n'
        "    if codex_home:\n"
        "        try:\n"
        '            candidates.append(Path(codex_home).expanduser().joinpath("skills"))\n'
        "        except (OSError, ValueError, RuntimeError):\n"
        "            pass\n"
        "    candidates.extend(\n"
        '        [Path.home().joinpath(".codex/skills"), Path.home().joinpath(".agents/skills")]\n'
        "    )\n",
        "    grok_home = os.environ.get(\"GROK_HOME\")\n"
        "    if grok_home:\n"
        '        candidates.append(Path(grok_home).expanduser().joinpath("skills"))\n'
        "    else:\n"
        '        candidates.append(Path.home().joinpath(".grok/skills"))\n'
        "    candidates.extend(\n"
        '        [Path.home().joinpath(".agents/skills")]\n'
        "    )\n",
    ),
    (
        "DOLGORAE_INVOCATION_ID_RE = re.compile(\n"
        '    r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"\n'
        ")\n",
        "",
    ),
    (
        "OUROBOROS_CODEX_MCP_SUFFIX = (\n"
        '    "--runtime",\n'
        '    "codex",\n'
        '    "--llm-backend",\n'
        '    "codex",\n'
        ")\n"
        "OUROBOROS_CODEX_MCP_ENV = {\n"
        '    "OUROBOROS_AGENT_RUNTIME": "codex",\n'
        '    "OUROBOROS_LLM_BACKEND": "codex",\n'
        "}\n"
        "OUROBOROS_RUNTIME_SELECTOR_KEYS = {\n"
        "    *OUROBOROS_CODEX_MCP_ENV,\n"
        '    "OUROBOROS_RUNTIME",\n'
        "}\n",
        "",
    ),
    (
        '        configuration_entry(repository, ".codex/config.toml", timeout_seconds),\n',
        '        configuration_entry(repository, ".grok/config.toml", timeout_seconds),\n',
    ),
    (
        '    command = payload.get("tool_input", {}).get("command")\n'
        '    if not isinstance(command, str):\n'
        '        return None\n',
        '    tool_input = payload.get("toolInput") or payload.get("tool_input") or {}\n'
        '    command = tool_input.get("command") if isinstance(tool_input, dict) else None\n'
        '    if payload.get("toolInputTruncated") is True:\n'
        '        cwd_value = payload.get("cwd")\n'
        '        truncated_cwd = Path(cwd_value) if isinstance(cwd_value, str) else Path.cwd()\n'
        '        probe = truncated_cwd\n'
        '        roots = [repository_root(probe)]\n'
        '        visible = command if isinstance(command, str) else ""\n'
        '        if visible:\n'
        '            for segment, _separator in shell_segments(visible):\n'
        '                if segment and segment[0] == "cd" and len(segment) == 2:\n'
        '                    candidate = Path(segment[1])\n'
        '                    destination = (\n'
        '                        candidate if candidate.is_absolute() else probe / candidate\n'
        '                    )\n'
        '                    if destination.is_dir():\n'
        '                        probe = destination\n'
        '                        roots.append(repository_root(probe))\n'
        '        if any(\n'
        '            root is not None and is_roadmap_repository(root) for root in roots\n'
        '        ):\n'
        '            return TRUNCATED_PAYLOAD_REASON\n'
        '    if not isinstance(command, str):\n'
        '        return None\n',
    ),
    (
        "MISSING_GATE_REASON = (\n"
        '    "This roadmap repository requires commits through $aquarium:task-commit. "\n'
        '    "Resume the active Aquarium handler or invoke that skill before committing."\n'
        ")\n"
        "MISSING_IDENTITY_REASON = (\n"
        '    "This roadmap repository requires $aquarium:task-commit with non-empty "\n'
        '    "user.name and user.email from Git local or worktree configuration. "\n'
        '    "Configure the repository identity, then resume the active Aquarium handler "\n'
        '    "or invoke that skill before committing."\n'
        ")\n",
        "MISSING_GATE_REASON = (\n"
        '    "This roadmap repository requires commits through the Aquarium task-commit skill. "\n'
        '    "Resume the active Aquarium handler or invoke that skill before committing."\n'
        ")\n"
        "MISSING_IDENTITY_REASON = (\n"
        '    "This roadmap repository requires the Aquarium task-commit skill with non-empty "\n'
        '    "user.name and user.email from Git local or worktree configuration. "\n'
        '    "Configure the repository identity, then resume the active Aquarium handler "\n'
        '    "or invoke that skill before committing."\n'
        ")\n"
        "TRUNCATED_PAYLOAD_REASON = (\n"
        '    "This roadmap repository denied a truncated shell command because the hook payload was cut off. "\n'
        '    "Shorten the command, or route a commit through the Aquarium task-commit skill."\n'
        ")\n",
    ),
    (
        '    manifest = directory.parent.parent / ".codex-plugin/plugin.json"\n',
        '    manifest = directory.parent.parent / "plugin.json"\n',
    ),
    ("$aquarium:", "/aquarium:"),
)

DATA_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("${PLUGIN_ROOT}", "${GROK_PLUGIN_ROOT}"),
    ('"matcher": "^Bash$"', '"matcher": "^(Bash|run_terminal_command|run_terminal_cmd)$"'),
    (
        '            "timeout": 10,\n'
        '            "statusMessage": "Checking the Aquarium roadmap commit boundary"\n',
        '            "timeout": 10\n',
    ),
)

RULE_TABLES: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("SUBSTITUTIONS", SUBSTITUTIONS),
    ("SCRIPT_SUBSTITUTIONS", SCRIPT_SUBSTITUTIONS),
    ("DATA_SUBSTITUTIONS", DATA_SUBSTITUTIONS),
)

REQUIRED_TEXT: tuple[tuple[str, str], ...] = (
    ("skills/dev-setup/scripts/inspect_tools.py", '".grok/skills"'),
    ("skills/dev-setup/scripts/inspect_tools.py", '".agents/skills"'),
    ("skills/dev-setup/scripts/inspect_tools.py", 'Path.home() / ".grok"'),
    ("skills/dev-setup/scripts/inspect_tools.py", "GROK_HOME"),
    ("skills/dev-setup/scripts/inspect_tools.py", '".agents/skills/humanize-korean"'),
    ("skills/dev-setup/scripts/inspect_tools.py", "grok_mcp_entries"),
    ("skills/dev-setup/scripts/inspect_tools.py", "inspect_global_mcp_scope"),
    (
        "references/review-intent-contract.md",
        "Dispatch fresh read-only host-native reviewer subagents",
    ),
    ("tools/aquarium-dev/runtime_entry.py", 'directory.parent.parent / "plugin.json"'),
    ("skills/dev-setup-global/scripts/inspect_global_tools.py", "--grok-home"),
    ("skills/dev-setup-global/scripts/inspect_ouroboros.py", "GROK_HOME"),
    ("skills/dev-setup-global/scripts/inspect_ouroboros.py", 'Path.home() / ".grok"'),
    ("skills/dev-setup/scripts/inspect_tools.py", "disabled_mcp_servers"),
    ("skills/dev-setup/scripts/inspect_tools.py", '"host_integration"'),
    ("skills/dev-setup/scripts/inspect_tools.py", "inspect_ouroboros_host_skills"),
    ("skills/dev-setup/scripts/inspect_tools.py", "GROK_OUROBOROS_RUNTIME_VALUES"),
    ("skills/dev-setup/scripts/inspect_tools.py", "isolated_launcher_contract"),
    ("skills/test-setup/scripts/inspect_testing.py", "aquarium-test-setup-inspection.v1"),
    ("hooks/hooks.json", "${GROK_PLUGIN_ROOT}"),
    ("hooks/hooks.json", "^(Bash|run_terminal_command|run_terminal_cmd)$"),
    ("hooks/task_commit_gate.py", "Aquarium task-commit skill"),
    ("hooks/task_commit_gate.py", "TRUNCATED_PAYLOAD_REASON"),
    ("hooks/task_commit_gate.py", 'payload.get("toolInput")'),
    ("hooks/task_commit_gate.py", "toolInputTruncated"),
    ("skills/independent-review/SKILL.md", "aquarium:independent-reviewer"),
    (
        "skills/independent-review/SKILL.md",
        "aquarium-independent-review-target-error/v1",
    ),
    ("skills/independent-review/SKILL.md", "never reaches dispatch"),
    (
        "skills/independent-review/SKILL.md",
        "untracked nested Git repository is recorded by path and mode only",
    ),
    ("skills/independent-review/SKILL.md", "cwd` set to the exact Git root"),
    ("skills/independent-review/SKILL.md", "spawn_subagent"),
    ("skills/independent-review/SKILL.md", "built-in `explore` type"),
    (
        "skills/independent-review/SKILL.md",
        "on an unborn `HEAD`, only `staged` is available",
    ),
    (
        "references/review-contract.md",
        "reads the selected target directly in this host's own checkout through fresh read-only reviewer subagents",
    ),
    ("skills/task-close/SKILL.md", "ask_user_question` when available"),
    ("skills/dev-setup/scripts/inspect_tools.py", "GIT_CONFIG_GLOBAL"),
    ("skills/independent-review/SKILL.md", "inspection_failed"),
)

FORBIDDEN: tuple[tuple[str, str], ...] = (
    ("$aquarium:", "add a substitution rule"),
    ("$use-", "add a substitution rule"),
    ("$create-", "add a substitution rule"),
    ("$lore-", "add a substitution rule"),
    ("$orca-cli", "add a substitution rule"),
    ("request_user_input", "add a substitution rule or an override"),
    ("--agent codex", "add a substitution rule or an override"),
    ("${PLUGIN_ROOT}", "Grok expands ${GROK_PLUGIN_ROOT}; add a data substitution"),
    (".codex/config", "Grok registers MCP servers in ~/.grok/config.toml; add a substitution rule"),
    (".codex/skills", "Grok loads ~/.grok/skills and ~/.agents/skills; add a substitution rule"),
    ("codex mcp", "Grok has no Codex MCP CLI; add a substitution rule or an override"),
    ("~/.codex", "Grok home is ~/.grok or $GROK_HOME; add a substitution rule"),
    ("Codex", "add a substitution rule, an override, or a reviewed exemption"),
)

SIGIL = re.compile(r"\$[a-z][a-z0-9:_-]*")

SIGIL_LITERALS: tuple[str, ...] = (
    "$aquarium_commit_name",
    "$aquarium_commit_email",
    "$aquarium_dev_branch",
    "$aquarium_dev_branch_status",
)


def apply_script_surgery(relative: str, source: str, plan: dict[str, Any]) -> str:
    lines = source.splitlines(keepends=True)
    spans: dict[str, tuple[int, int, int]] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        starts = [node.lineno] + [decorator.lineno for decorator in node.decorator_list]
        start = min(starts) - 1
        content_end = node.end_lineno
        block_end = content_end
        while block_end < len(lines) and lines[block_end].strip() == "":
            block_end += 1
        spans[node.name] = (start, content_end, block_end)

    replacements = plan.get("replace", {})
    deletions = plan.get("delete", [])
    unknown = sorted((set(replacements) | set(deletions)) - set(spans))
    if unknown:
        raise SyncError(
            f"script surgery on `{relative}` names functions upstream no "
            "longer defines: " + ", ".join(unknown) + "; re-derive the plan"
        )
    for name, text in replacements.items():
        if f"def {name}(" not in text:
            raise SyncError(
                f"script surgery replacement for `{name}` must define `{name}`"
            )

    operations: list[tuple[int, int, list[str] | None]] = []
    for name in deletions:
        start, _, block_end = spans[name]
        operations.append((start, block_end, None))
    for name, text in replacements.items():
        start, content_end, _ = spans[name]
        replacement_lines = text.splitlines(keepends=True)
        if not replacement_lines or not replacement_lines[-1].endswith("\n"):
            replacement_lines.append("\n")
        operations.append((start, content_end, replacement_lines))
    operations.sort(key=lambda operation: operation[0], reverse=True)
    for start, end, replacement in operations:
        lines[start:end] = replacement if replacement is not None else []

    result = "".join(lines)
    try:
        compile(result, relative, "exec")
    except SyntaxError as error:
        raise SyncError(
            f"script surgery on `{relative}` produced invalid syntax: {error}"
        ) from error
    for name in deletions:
        if re.search(rf"\b{re.escape(name)}\b", result):
            raise SyncError(
                f"script surgery deleted `{name}` from `{relative}` but a "
                "reference to it survived; extend the surgery plan"
            )
    return result


SCRIPT_SURGERY: dict[str, dict[str, Any]] = {
    "skills/dev-setup/scripts/inspect_tools.py": {
        "replace": {
            "inspect_mulgae_mcp": r'''def grok_mcp_entries(server: str, repository: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ImportError:
        return {
            "scopes": {"user": None, "project": None},
            "invalid_config": None,
            "invalid_scopes": {},
            "disabled_servers": (),
            "unverifiable": "tomllib_unavailable",
        }

    scopes: dict[str, Any] = {"user": None, "project": None}
    invalid_scopes: dict[str, str] = {}
    disabled_servers: tuple[str, ...] = ()
    grok_home = os.environ.get("GROK_HOME")
    user_config = Path(grok_home).expanduser() / "config.toml" if grok_home else Path.home() / ".grok" / "config.toml"
    for label, source in (
        ("user", user_config),
        ("project", repository.joinpath(".grok/config.toml")),
    ):
        try:
            if source.is_symlink():
                return {
                    "scopes": {"user": None, "project": None},
                    "invalid_config": None,
                    "invalid_scopes": {},
                    "disabled_servers": disabled_servers,
                    "unverifiable": f"{label}_config_symlinked",
                }
            document = tomllib.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            invalid_scopes[label] = f"{label}_config_invalid_toml"
            continue
        if not isinstance(document, dict):
            continue
        if label == "user":
            listed = document.get("disabled_mcp_servers")
            if isinstance(listed, list) and all(isinstance(name, str) for name in listed):
                disabled_servers = tuple(listed)
        servers = document.get("mcp_servers")
        if isinstance(servers, dict) and server in servers:
            scopes[label] = servers[server]
    return {
        "scopes": scopes,
        "invalid_config": next(iter(invalid_scopes), None),
        "invalid_scopes": invalid_scopes,
        "disabled_servers": disabled_servers,
        "unverifiable": None,
    }


def grok_mcp_scope_status(
    entry: Any,
    selected_executable: str | None,
    repository: Path,
    scope: str,
    server: str,
    disabled_servers: tuple[str, ...] = (),
) -> dict[str, Any]:
    if entry is None:
        return {"status": "missing", "reason": "registration_not_found"}
    registration: dict[str, Any] = {
        "status": "degraded",
        "stdio": None,
        "command_resolvable": None,
        "binary_matches_selected": None,
        "arguments_match": None,
        "repository_bound": None,
        "startup_timeout_sec": None,
        "tool_timeout_sec": None,
    }
    if not isinstance(entry, dict):
        registration["reason"] = "registration_mismatch"
        return registration
    if entry.get("enabled") is False or server in disabled_servers:
        registration["reason"] = "registration_disabled"
        return registration
    stdio = not entry.get("url")
    command = entry.get("command")
    resolved_command = resolve_mcp_command(command)
    binary_matches: bool | None = None
    if selected_executable is not None:
        binary_matches = bool(
            resolved_command and resolved_command == Path(selected_executable).resolve()
        )
    args = entry.get("args")
    try:
        canonical = repository.resolve()
    except OSError:
        canonical = repository
    arguments_match = False
    repository_bound = scope == "global"
    if isinstance(args, list) and all(isinstance(argument, str) for argument in args):
        if server == "mulgae":
            if scope == "global":
                arguments_match = args == ["mcp"]
            elif len(args) == 3 and args[:2] == ["mcp", "--project-root"]:
                try:
                    repository_bound = Path(args[2]).expanduser().resolve() == canonical
                except OSError:
                    repository_bound = False
                arguments_match = repository_bound
        elif server == "gaori":
            if scope == "global":
                arguments_match = args == ["mcp"]
            elif len(args) == 3 and args[0] == "--repo" and args[2] == "mcp":
                try:
                    repository_bound = Path(args[1]).expanduser().resolve() == canonical
                except OSError:
                    repository_bound = False
                arguments_match = repository_bound
    startup_timeout = entry.get("startup_timeout_sec")
    tool_timeout = entry.get("tool_timeout_sec")
    min_tool = (
        MULGAE_MCP_TOOL_TIMEOUT_SEC if server == "mulgae" else GAORI_MCP_TOOL_TIMEOUT_SEC
    )
    registration.update(
        {
            "stdio": stdio,
            "command_resolvable": resolved_command is not None,
            "binary_matches_selected": binary_matches,
            "arguments_match": arguments_match,
            "repository_bound": repository_bound,
            "startup_timeout_sec": startup_timeout,
            "tool_timeout_sec": tool_timeout,
        }
    )
    cwd = entry.get("cwd")
    if cwd not in (None, ""):
        if scope == "global":
            cwd_bound = False
        else:
            try:
                cwd_bound = Path(str(cwd)).expanduser().resolve() == canonical
            except OSError:
                cwd_bound = False
    else:
        cwd_bound = True
    if not stdio:
        registration["reason"] = "registration_not_stdio"
    elif resolved_command is None:
        registration["reason"] = "command_unresolvable"
    elif selected_executable is None:
        registration["reason"] = "binary_unselected"
    elif not binary_matches:
        registration["reason"] = "registration_mismatch"
    elif not cwd_bound:
        registration["reason"] = "registration_mismatch"
    elif not arguments_match:
        registration["reason"] = "registration_mismatch"
    elif not (
        finite_number(startup_timeout)
        and startup_timeout >= 30
        and finite_number(tool_timeout)
        and tool_timeout >= min_tool
    ):
        registration["reason"] = "registration_mismatch"
    else:
        registration["status"] = "configured"
    return registration


def grok_mcp_scopes(server: str, repository: Path, selected_executable: str | None) -> dict[str, Any]:
    reading = grok_mcp_entries(server, repository)
    project_config_present, project_config_symlinked = safe_managed_file_state(
        repository / ".grok" / "config.toml", repository
    )
    registration: dict[str, Any] = {
        "status": "missing",
        "preferred_scope": "global",
        "effective_scope": "none",
        "local_confirmation_required": None,
    }
    if reading.get("unverifiable"):
        registration.update(
            {
                "status": "unverifiable",
                "effective_scope": "unverifiable",
                "reason": reading["unverifiable"],
                "global": {"status": "unverifiable", "reason": reading["unverifiable"]},
                "local": {
                    "status": "unverifiable",
                    "reason": reading["unverifiable"],
                    "project_config_present": project_config_present,
                    "project_config_symlinked": project_config_symlinked,
                },
            }
        )
        return registration
    disabled_servers = tuple(reading.get("disabled_servers") or ())
    invalid_scopes = dict(reading.get("invalid_scopes") or {})
    if reading.get("invalid_config") and reading["invalid_config"] not in invalid_scopes:
        invalid_scopes[reading["invalid_config"]] = (
            f"{reading['invalid_config']}_config_invalid_toml"
        )
    if "user" in invalid_scopes:
        global_registration = {
            "status": "degraded",
            "reason": invalid_scopes["user"],
        }
    else:
        global_registration = grok_mcp_scope_status(
            reading["scopes"]["user"],
            selected_executable,
            repository,
            "global",
            server,
            disabled_servers,
        )
    if project_config_symlinked:
        registration.update(
            {
                "status": "unverifiable",
                "effective_scope": "unverifiable",
                "reason": "project_configuration_symlinked",
                "global": global_registration,
                "local": {
                    "status": "unverifiable",
                    "reason": "project_configuration_symlinked",
                    "project_config_present": project_config_present,
                    "project_config_symlinked": project_config_symlinked,
                },
                "recommendation": "resolve_symlinked_local_configuration",
            }
        )
        return registration
    if "project" in invalid_scopes:
        local_registration = {
            "status": "degraded",
            "reason": invalid_scopes["project"],
            "project_config_present": project_config_present,
            "project_config_symlinked": project_config_symlinked,
        }
    else:
        local_registration = grok_mcp_scope_status(
            reading["scopes"]["project"],
            selected_executable,
            repository,
            "local",
            server,
            disabled_servers,
        )
        local_registration.update(
            {
                "project_config_present": project_config_present,
                "project_config_symlinked": project_config_symlinked,
            }
        )
        if local_registration["status"] == "missing" and not project_config_present:
            local_registration["reason"] = "project_configuration_missing"
    if reading["scopes"]["project"] is not None:
        effective_scope = "local"
        effective_registration: dict[str, Any] | None = local_registration
    elif reading["scopes"]["user"] is not None:
        effective_scope = "global"
        effective_registration = global_registration
    else:
        effective_scope = "none"
        effective_registration = None
    local_confirmable = local_registration["status"] != "missing"
    registration.update(
        {
            "status": (
                effective_registration["status"]
                if effective_registration is not None
                else ("degraded" if invalid_scopes else "missing")
            ),
            "effective_scope": effective_scope,
            "local_confirmation_required": local_confirmable,
            "global": global_registration,
            "local": local_registration,
            "recommendation": mcp_recommendation(
                global_registration["status"], bool(local_confirmable)
            ),
        }
    )
    if effective_registration is not None and effective_registration.get("reason"):
        registration["reason"] = effective_registration["reason"]
    elif effective_registration is None and invalid_scopes:
        registration["reason"] = next(iter(invalid_scopes.values()))
    return registration


def inspect_mulgae_mcp(
    repository: Path, mulgae_executable: str | None, timeout_seconds: float
) -> dict[str, Any]:
    return grok_mcp_scopes("mulgae", repository, mulgae_executable)
''',
            "inspect_gaori_mcp": r'''def inspect_gaori_mcp(
    repository: Path, gaori_executable: str | None, timeout_seconds: float
) -> dict[str, Any]:
    return grok_mcp_scopes("gaori", repository, gaori_executable)
''',
            "ouroboros_direct_launcher_matches": r'''def ouroboros_direct_launcher_matches(
    transport: Any, ouroboros_executable: str | None
) -> bool:
    if not isinstance(transport, dict) or not ouroboros_executable:
        return False
    if transport.get("url"):
        return False
    if transport.get("type") not in {None, "stdio"}:
        return False
    resolved_command = resolved_executable(transport.get("command"))
    return bool(
        transport.get("args") == ["mcp", "serve"]
        and resolved_command
        and resolved_command == Path(ouroboros_executable).resolve()
    )
''',
            "ouroboros_isolated_launcher_matches": r'''GROK_OUROBOROS_RUNTIME_VALUES = ("grok",)


def ouroboros_isolated_launcher_matches(transport: Any) -> bool:
    if not isinstance(transport, dict):
        return False
    resolved_command = resolved_executable(transport.get("command"))
    selected_uvx = shutil.which("uvx")
    if not resolved_command or not selected_uvx:
        return False
    if resolved_command != Path(selected_uvx).resolve():
        return False
    args = transport.get("args")
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        return False
    normalized_args = list(args)
    if len(normalized_args) < 5:
        return False
    package_match = OUROBOROS_MCP_PACKAGE.fullmatch(normalized_args[4])
    if not package_match:
        return False
    pinned_version = package_match.group(1)
    if pinned_version and not supported_ouroboros_version(pinned_version):
        return False
    normalized_args[4] = "ouroboros-ai[mcp]"
    env = transport.get("env", {})
    if not isinstance(env, dict):
        env = {}
    env_runtime = env.get("OUROBOROS_AGENT_RUNTIME")
    if env_runtime is not None and env_runtime not in GROK_OUROBOROS_RUNTIME_VALUES:
        return False
    normalized = tuple(normalized_args)
    if normalized == OUROBOROS_UVX_MCP_ARGS:
        return env_runtime in GROK_OUROBOROS_RUNTIME_VALUES
    return normalized == (*OUROBOROS_UVX_MCP_ARGS, "--runtime", "grok")
''',
            "inspect_ouroboros": r'''def ouroboros_mcp_registration(
    repository: Path, ouroboros_executable: str | None
) -> dict[str, Any]:
    probe: dict[str, Any] = {
        "attempted": True,
        "ok": True,
        "exit_code": 0,
        "timed_out": False,
    }
    reading = grok_mcp_entries("ouroboros", repository)
    if reading.get("unverifiable"):
        probe["reason"] = reading["unverifiable"]
        return {"status": "unverifiable", "probe": probe}
    _present, project_symlinked = safe_managed_file_state(
        repository / ".grok" / "config.toml", repository
    )
    if project_symlinked:
        probe["reason"] = "project_configuration_symlinked"
        return {"status": "unverifiable", "probe": probe}
    entry: Any = None
    scope: str | None = None
    if reading["scopes"]["project"] is not None:
        entry = reading["scopes"]["project"]
        scope = "project"
    elif reading["scopes"]["user"] is not None:
        entry = reading["scopes"]["user"]
        scope = "user"
    elif reading.get("invalid_scopes") or reading.get("invalid_config"):
        probe["reason"] = "registration_invalid_toml"
        return {"status": "degraded", "probe": probe}
    if entry is None:
        probe["reason"] = "registration_not_found"
        return {"status": "missing", "probe": probe}
    if not isinstance(entry, dict) or entry.get("url"):
        return {"status": "degraded", "probe": probe, "scope": scope, "reason": "registration_not_stdio"}
    if entry.get("enabled") is False or "ouroboros" in tuple(reading.get("disabled_servers") or ()):
        return {"status": "degraded", "probe": probe, "scope": scope, "reason": "registration_disabled"}
    if ouroboros_direct_launcher_matches(entry, ouroboros_executable):
        return {"status": "configured", "probe": probe, "scope": scope, "launcher": "direct"}
    if ouroboros_isolated_launcher_matches(entry):
        return {"status": "configured", "probe": probe, "scope": scope, "launcher": "isolated"}
    return {"status": "degraded", "probe": probe, "scope": scope, "reason": "registration_mismatch"}


def inspect_ouroboros_host_skills() -> dict[str, Any]:
    skills = {
        name: inspect_agent_skill(name, ("SKILL.md",))
        for name in ("interview", "pm", "seed", "qa")
    }
    statuses = [entry["status"] for entry in skills.values()]
    if all(status == "configured" for status in statuses):
        status = "configured"
    elif all(status == "missing" for status in statuses):
        status = "missing"
    else:
        status = "degraded"
    return {"status": status, "skills": skills}


def inspect_ouroboros(repository: Path, timeout_seconds: float) -> dict[str, Any]:
    tool = base_tool("ooo")
    tool["supported_range"] = ">=0.51.1,<0.54.0"
    tool["mcp_registration"] = ouroboros_mcp_registration(repository, tool["executable"])
    tool["host_integration"] = inspect_ouroboros_host_skills()
    if not tool["installed"]:
        tool["version_supported"] = False
        tool["probes"]["version"] = skipped_probe("executable_missing")
        tool["mcp_runtime"] = {"status": "missing", "probe": skipped_probe("executable_missing")}
        tool["status"] = "degraded"
        return tool
    version_raw = run_command([tool["executable"], "--version"], repository, timeout_seconds)
    tool["version"] = ouroboros_version_from_output(
        f"{version_raw.get('stdout', '')}\n{version_raw.get('stderr', '')}"
    )
    tool["version_supported"] = version_raw["ok"] and supported_ouroboros_version(tool["version"])
    tool["probes"]["version"] = {
        key: version_raw[key] for key in ("attempted", "ok", "exit_code", "timed_out")
    }
    launcher = tool["mcp_registration"].get("launcher")
    if launcher == "isolated":
        tool["mcp_runtime"] = {
            "status": "configured",
            "reason": "isolated_launcher_contract",
            "probe": skipped_probe("isolated_environment_not_probed"),
        }
    elif launcher == "direct":
        mcp_doctor = json_probe(
            [tool["executable"], "mcp", "doctor", "--json"], repository, timeout_seconds
        )
        doctor_checks = mcp_doctor.get("result")
        runtime_probe = normalized_probe(mcp_doctor)
        if isinstance(doctor_checks, list):
            failed = sorted(
                str(check.get("name"))
                for check in doctor_checks
                if isinstance(check, dict)
                and check.get("status") == "fail"
                and check.get("name") != "mcp_import"
            )
            if failed:
                runtime_probe["reason"] = "doctor_checks_failed"
            tool["mcp_runtime"] = {
                "status": "degraded" if failed else "configured",
                "failed_checks": failed,
                "probe": runtime_probe,
            }
        else:
            tool["mcp_runtime"] = {"status": "degraded", "probe": runtime_probe}
    else:
        reason = tool["mcp_registration"].get("reason", "registration_not_found")
        tool["mcp_runtime"] = {
            "status": "missing" if reason == "registration_not_found" else "unverifiable",
            "reason": reason,
            "probe": skipped_probe(reason),
        }
    components_ready = (
        tool["version_supported"]
        and tool["host_integration"]["status"] == "configured"
        and tool["mcp_runtime"]["status"] == "configured"
        and tool["mcp_registration"]["status"] == "configured"
    )
    tool["status"] = "configured" if components_ready else "degraded"
    return tool
''',
            "inspect_global_mcp_scope": r'''def inspect_global_mcp_scope(
    name: str,
    executable: str | None,
    root: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    del timeout_seconds
    reading = grok_mcp_entries(name, Path(root.anchor))
    if reading.get("unverifiable"):
        return {
            "status": "unverifiable",
            "reason": reading["unverifiable"],
        }
    if reading.get("invalid_config"):
        return {
            "status": "degraded",
            "reason": f"{reading['invalid_config']}_config_invalid_toml",
        }
    return grok_mcp_scope_status(
        reading["scopes"]["user"],
        executable,
        Path(root.anchor),
        "global",
        name,
        tuple(reading.get("disabled_servers") or ()),
    )
''',
        },
        "delete": [
            "mcp_registration_probe",
            "classify_mulgae_mcp_scope",
            "classify_gaori_mcp_scope",
            "classify_ouroboros_registration",
            "effective_mcp_registration",
            "missing_mcp_scope",
            "failed_mcp_scope",
            "codex_version_from_output",
            "effective_codex_skill_root",
            "inspect_dolgorae",
            "supported_dolgorae_version",
            "valid_dolgorae_envelope",
            "dolgorae_capabilities_compatible",
            "is_arm64_macho",
        ],
        "upstream": {
            "inspect_mulgae_mcp": "c2548c0144b3399e6da4919d669a73ff6b81d06aca8b7c07945a77867ac6e54f",
            "inspect_gaori_mcp": "2741e3cc194d726601f5c4d5d1d5d2aa834ce4ec5540f1c9fe245d52d735290d",
            "ouroboros_direct_launcher_matches": "cd3da17085733d6f01f0b9f53ff6f9d2c46ed1f298ae9dc93cdc292f4b915fea",
            "ouroboros_isolated_launcher_matches": "ef4368b2f583ba6c88f652e3a59b3f6fa4661dc71f4f77fa1a697c2810913e91",
            "inspect_ouroboros": "d4ab5bb6dc7aac2c7623ac41ccb6c65a9f4fcc551d145508b7bdcc7230599c73",
            "inspect_global_mcp_scope": "970e363c6a258a8b6d12c420f9669273810791812b2169591221f4eacb2c6254",
        },
    },
    "skills/independent-review/scripts/inspect_review_target.py": {
        "replace": {
            "decode_utf8": r'''def decode_utf8(value: bytes, code: str, message: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeError as error:
        if code == "git_path_invalid":
            return value.decode("utf-8", "backslashreplace")
        raise InspectionError(code, message) from error
''',
            "inspect_staged": r'''def inspect_staged(repository: Path) -> dict[str, Any]:
    symbolic = git_command(repository, ["symbolic-ref", "-q", "HEAD"])
    head_probe = git_command(repository, ["rev-parse", "--verify", "--quiet", "HEAD"])
    if symbolic.returncode == 0 and head_probe.returncode != 0:
        head = None
        head_unborn = True
    elif head_probe.returncode == 0:
        head = resolve_commit(repository, "HEAD")
        head_unborn = False
    else:
        raise InspectionError("revision_unresolved", "HEAD could not be resolved")
    diff = binary_diff(
        repository,
        ["diff", "--cached", "--binary", "--no-ext-diff", "--no-textconv"],
    )
    if not diff:
        raise InspectionError("staged_target_empty", "staged target is empty")
    target: dict[str, Any] = {
        "kind": "staged",
        "head_commit": head,
        "head_unborn": head_unborn,
        "diff_sha256": sha256(diff),
    }
    target["target_digest"] = target_digest(target)
    return target
''',
            "main": r'''def main() -> int:
    try:
        arguments = parser().parse_args()
        repository = Path(arguments.repository)
        result = inspect(repository, arguments)
    except (InspectionError, subprocess.TimeoutExpired, OSError) as error:
        if isinstance(error, InspectionError):
            code = error.code
            message = str(error)
        elif isinstance(error, subprocess.TimeoutExpired):
            code = "git_timeout"
            message = "Git inspection timed out"
        else:
            code = "inspection_failed"
            message = "Git inspection failed"
        print(
            json.dumps(
                {
                    "schema_version": ERROR_SCHEMA_VERSION,
                    "error": {"code": code, "message": message},
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0
''',
        },
        "delete": [],
        "upstream": {
            "decode_utf8": "bc781a8e73057b49fd664176e63388d32d5efd0c2dc8878107f7779e733939c7",
            "inspect_staged": "b1b1e30ac1bb575a9188007586ca67102ce388d51ada71154c7d818b8d11f050",
            "main": "9b2a1ef445a0fce8965a75dda1e63654a6e29b8b4812c6f2c8c53d0a831fef1c",
        },
    },
    "skills/dev-setup-global/scripts/inspect_global_tools.py": {
        "replace": {
            "inspect_global": r'''def inspect_global(
    repository: str | None,
    timeout_seconds: float,
    include_sorage_initialization: bool = False,
    components: tuple[str, ...] | None = None,
    grok_homes: tuple[str, ...] = (),
    verify_ouroboros_release: bool = False,
) -> dict[str, Any]:
    inspector = load_inspector()
    root = resolve_working_directory(repository)
    neutral_cwd = Path(root.anchor)
    requested_components = set(components or GLOBAL_COMPONENTS)
    selected_components = tuple(
        name for name in GLOBAL_COMPONENTS if name in requested_components
    )
    raw_tools: dict[str, dict[str, Any]] = {}
    if "sanho" in requested_components:
        raw_tools["sanho"] = inspect_versioned_cli(
            inspector,
            "sanho",
            neutral_cwd,
            timeout_seconds,
            ["version", "--json"],
            inspector.supported_sanho_version,
        )
    if "mulgae" in requested_components:
        raw_tools["mulgae"] = inspect_versioned_cli(
            inspector,
            "mulgae",
            neutral_cwd,
            timeout_seconds,
            ["version", "--json"],
            inspector.supported_mulgae_version,
            platform_required=True,
        )
    if "gaori" in requested_components:
        raw_tools["gaori"] = inspect_versioned_cli(
            inspector,
            "gaori",
            neutral_cwd,
            timeout_seconds,
            ["version", "--json"],
            inspector.supported_gaori_version,
        )
    if "sorage" in requested_components:
        raw_tools["sorage"] = inspect_global_sorage(
            inspector,
            root,
            timeout_seconds,
            include_sorage_initialization,
        )
    if "podway" in requested_components:
        raw_tools["podway"] = inspect_global_podway(inspector, root, timeout_seconds)
    skill_specs = {
        "sanho": ("use-sanho", inspector.SANHO_SKILL_FILES),
        "mulgae": ("use-mulgae", inspector.MULGAE_SKILL_FILES),
        "gaori": ("use-gaori", inspector.GAORI_SKILL_FILES),
        "sorage": ("use-sorage", inspector.SORAGE_SKILL_FILES),
    }
    for name, (skill_name, files) in skill_specs.items():
        if name not in raw_tools:
            continue
        raw_tools[name]["agent_skill"] = inspect_canonical_agent_skill(
            inspector, skill_name, files
        )
    if "gaori" in raw_tools:
        raw_tools["gaori"]["status_skill"] = inspect_canonical_agent_skill(
            inspector, "use-gaori-status", inspector.GAORI_STATUS_SKILL_FILES
        )
    if "mulgae" in raw_tools:
        raw_tools["mulgae"]["installation_prerequisites"] = (
            inspector.inspect_mulgae_installation_prerequisites(
                neutral_cwd,
                timeout_seconds,
                environment_overrides={"GOTOOLCHAIN": "local"},
            )
        )
    for name in ("mulgae", "gaori"):
        if name not in raw_tools:
            continue
        raw_tools[name]["global_mcp"] = inspect_global_mcp(
            inspector,
            name,
            raw_tools[name]["executable"],
            root,
            timeout_seconds,
        )
    tools: dict[str, Any] = {}
    for name, raw in raw_tools.items():
        entry: dict[str, Any] = {"cli": cli_component(raw)}
        if "agent_skill" in raw:
            entry["paired_skill"] = raw["agent_skill"]
        if "status_skill" in raw:
            entry["status_skill"] = raw["status_skill"]
        if "global_mcp" in raw:
            entry["global_mcp"] = raw["global_mcp"]
        if "installation_prerequisites" in raw:
            entry["installation_prerequisites"] = raw["installation_prerequisites"]
        if name == "podway":
            entry["daemon"] = raw["daemon"]
        if name == "sorage":
            entry["initialization_status"] = raw.get("initialization_status")
            entry["initialization_probe"] = raw["probes"]["doctor"]
        tools[name] = entry

    if "ouroboros" in requested_components:
        try:
            tools["ouroboros"] = inspect_ouroboros(
                inspector,
                neutral_cwd,
                timeout_seconds,
                grok_homes,
                verify_ouroboros_release,
            )
        except InvalidHostHome as error:
            raise InspectionError(
                "invalid_grok_home", "Grok home is unavailable or invalid"
            ) from error
    if "lora" in requested_components:
        tools["lora"] = inspector.inspect_lora()
    if "deslop" in requested_components:
        tools["deslop"] = inspector.inspect_deslop()
    if "humanizer" in requested_components:
        tools["humanizer"] = inspector.inspect_humanizer()
    if "im-not-ai" in requested_components:
        tools["im-not-ai"] = inspector.inspect_im_not_ai()
    if "aquarium-dev" in requested_components:
        script = Path(__file__).resolve().parents[3] / "tools/aquarium-dev/install.py"
        try:
            probe = subprocess.run(
                [sys.executable, "-B", str(script), "diagnose"],
                cwd=neutral_cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            if probe.returncode:
                failure = {
                    "status": "unverifiable",
                    "reason": "probe_failed",
                    "exit_code": probe.returncode,
                    "problem": probe.stderr.strip(),
                }
                try:
                    failure["diagnostic"] = json.loads(probe.stderr)
                except ValueError:
                    pass
                tools["aquarium-dev"] = failure
            else:
                tools["aquarium-dev"] = json.loads(probe.stdout)
        except subprocess.TimeoutExpired as error:
            tools["aquarium-dev"] = {
                "status": "unverifiable",
                "reason": "probe_timeout",
                "timeout_seconds": timeout_seconds,
                "problem": str(error),
            }
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            tools["aquarium-dev"] = {
                "status": "unverifiable",
                "reason": "invalid_json"
                if isinstance(error, ValueError)
                else "probe_failed",
                "problem": str(error),
            }
    tools = {name: tools[name] for name in selected_components}
    return {
        "schema_version": SCHEMA_VERSION,
        "inspection_scope": "user_global",
        "tools": tools,
    }
''',
            "parse_arguments": r'''def parse_arguments() -> argparse.Namespace:
    max_command_timeout_seconds = load_inspector().MAX_COMMAND_TIMEOUT_SECONDS
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        help="Existing directory used only as a safe command working directory",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
        help="Timeout for each ordinary read-only command; Podway readiness uses its fixed catalog wait",
    )
    parser.add_argument(
        "--component",
        action="append",
        choices=GLOBAL_COMPONENTS,
        help="Inspect only this user-global component; repeat to select more",
    )
    parser.add_argument(
        "--include-sorage-initialization",
        action="store_true",
        help="Include the selected local Sorage initialization diagnostic",
    )
    parser.add_argument(
        "--grok-home",
        action="append",
        default=[],
        help="Additional Ouroboros Grok home to inspect; repeat for multiple homes",
    )
    parser.add_argument(
        "--verify-ouroboros-release",
        action="store_true",
        help="Compare Ouroboros with official PyPI stable releases",
    )
    arguments = parser.parse_args()
    if (
        not math.isfinite(arguments.timeout_seconds)
        or arguments.timeout_seconds <= 0
        or arguments.timeout_seconds > max_command_timeout_seconds
    ):
        raise InspectionError(
            "invalid_arguments",
            "--timeout-seconds is outside the supported range",
        )
    if any(not value.strip() for value in arguments.grok_home):
        raise InspectionError("invalid_arguments", "--grok-home must not be blank")
    selected_components = set(arguments.component or GLOBAL_COMPONENTS)
    if arguments.include_sorage_initialization and "sorage" not in selected_components:
        raise InspectionError(
            "invalid_arguments",
            "--include-sorage-initialization requires the sorage component",
        )
    if (
        arguments.grok_home or arguments.verify_ouroboros_release
    ) and "ouroboros" not in selected_components:
        raise InspectionError(
            "invalid_arguments", "Ouroboros options require the ouroboros component"
        )
    arguments.component = tuple(
        name for name in GLOBAL_COMPONENTS if name in selected_components
    )
    return arguments
''',
            "main": r'''def main() -> int:
    try:
        arguments = parse_arguments()
        emit(
            inspect_global(
                arguments.repository,
                arguments.timeout_seconds,
                arguments.include_sorage_initialization,
                arguments.component,
                tuple(arguments.grok_home),
                arguments.verify_ouroboros_release,
            )
        )
        return 0
    except InspectionError as error:
        emit(
            {
                "schema_version": SCHEMA_VERSION,
                "error": {"code": error.code, "message": str(error)},
            }
        )
        return error.exit_code
    except Exception as error:  # noqa: BLE001 - keep the CLI error boundary JSON-only
        emit(
            {
                "schema_version": SCHEMA_VERSION,
                "error": {
                    "code": "inspection_failed",
                    "message": "unexpected global inspection failure",
                    "type": type(error).__name__,
                },
            }
        )
        return 1
''',
        },
        "delete": [],
        "upstream": {
            "inspect_global": "98ec89a97f3de0a46505fbfe18115d8729f3c804fde256db7792c918614f5cc6",
            "parse_arguments": "9f5204165840dd7e36e6e5ab601aeab713db5b891bbc6bfbc2e9b8dcc8c5fba3",
            "main": "8ecc2a6e6f7a61000ac7649c5706d3448ac2b3db48c48a664696102d02f42486",
        },
    },
    "skills/dev-setup-global/scripts/inspect_ouroboros.py": {
        "replace": {
            "discover_homes": r'''def discover_homes(
    explicit: tuple[str, ...] = (),
) -> tuple[Path, list[Path], dict[Path, str]]:
    requested = []
    for value in explicit:
        if not value.strip():
            raise InvalidHostHome("Grok home must not be blank")
        try:
            path = Path(value).expanduser().resolve()
            not_directory = path.exists() and not path.is_dir()
        except (OSError, ValueError, RuntimeError) as error:
            raise InvalidHostHome("Grok home is unavailable or invalid") from error
        if not_directory:
            raise InvalidHostHome("Grok home must be a directory")
        requested.append(path)

    failures: dict[Path, str] = {}
    homes: list[Path] = []
    identities: dict[tuple[int, int], Path] = {}

    def include(path: Path) -> Path:
        try:
            path = path.expanduser().resolve()
        except (OSError, ValueError, RuntimeError):
            # Keep the original spelling for diagnosis; never probe an unresolved home.
            failures[path] = "home_resolution_failed"
        if path not in failures:
            try:
                info = path.stat()
                if stat.S_ISDIR(info.st_mode):
                    identity = (info.st_dev, info.st_ino)
                    if identity in identities:
                        return identities[identity]
                    identities[identity] = path
            except FileNotFoundError:
                pass
            except OSError:
                failures[path] = "home_inspection_failed"
        if path not in homes:
            homes.append(path)
        return path

    current = include(Path(os.environ.get("GROK_HOME") or Path.home() / ".grok"))
    default = Path.home() / ".grok"
    try:
        if default.is_dir():
            include(default)
    except OSError:
        failures[include(default)] = "home_inspection_failed"
    for path in requested:
        include(path)
    return current, homes, failures
''',
            "unavailable_home": r'''def unavailable_home(home: Path, current: Path, reason: str) -> dict[str, Any]:
    row = {
        key: {"status": "unverifiable", "reason": reason}
        for key in (
            "rules",
            "skills",
            "host_integration",
            "mcp_registration",
            "mcp_runtime",
        )
    }
    row.update(
        home=str(home), current=home == current, status="degraded", reason=reason
    )
    row["live_runtime"] = {"status": "not_observed", "reason": "configuration_only"}
    return row
''',
            "inspect_home": r'''def inspect_home(
    inspector: Any,
    cwd: Path,
    timeout: float,
    home: Path,
    current: Path,
    cli: dict[str, Any],
    assets: dict[str, str] | None,
    host: dict[str, Any],
) -> dict[str, Any]:
    del inspector
    del cwd
    del timeout
    del cli
    row = {
        "host_integration": host["host_integration"],
        "mcp_registration": host["mcp_registration"],
        "mcp_runtime": host["mcp_runtime"],
    }
    row.update(home=str(home), current=home == current)
    if home.exists() and not home.is_dir():
        row["reason"] = "home_not_a_directory"
    row["rules"] = inspect_artifacts(home, "rules", assets)
    row["skills"] = inspect_artifacts(home, "skills", assets)
    row["live_runtime"] = {"status": "not_observed", "reason": "configuration_only"}
    row["status"] = (
        "configured"
        if (
            host.get("version_supported")
            and all(
                row[key]["status"] == "configured"
                for key in (
                    "host_integration",
                    "mcp_registration",
                    "mcp_runtime",
                )
            )
        )
        else "degraded"
    )
    return row
''',
            "inspect_ouroboros": r'''def inspect_ouroboros(
    inspector: Any,
    cwd: Path,
    timeout: float,
    explicit_homes: tuple[str, ...] = (),
    verify_release: bool = False,
) -> dict[str, Any]:
    current, homes, failures = discover_homes(explicit_homes)
    rows = []
    cli = inspector.inspect_ouroboros_cli(cwd, timeout)
    assets = packaged_assets(inspector, cli, cwd, timeout)
    host = inspector.inspect_ouroboros(cwd, timeout)
    for home in homes:
        if home in failures:
            row = unavailable_home(home, current, failures[home])
        else:
            try:
                row = inspect_home(
                    inspector, cwd, timeout, home, current, cli, assets, host
                )
            except (OSError, ValueError, RuntimeError):
                row = unavailable_home(home, current, "home_inspection_failed")
        rows.append(row)
    freshness = (
        release_freshness(inspector, cli, timeout)
        if verify_release
        else {"status": "not_checked", "source": PYPI_URL}
    )
    return {
        "status": rows[0]["status"],
        "supported_range": SUPPORTED_RANGE,
        "cli": {
            **{
                key: cli[key]
                for key in ("installed", "executable", "version", "version_supported")
            },
            "status": "missing"
            if not cli["installed"]
            else "installed"
            if cli["version_supported"]
            else "degraded",
            "version_probe": cli["probes"]["version"],
        },
        "freshness": freshness,
        "current_home": str(current),
        "current_home_readiness": rows[0]["status"],
        "all_discovered_homes_readiness": "configured"
        if all(row["status"] == "configured" for row in rows)
        else "degraded",
        "homes": rows,
        "legacy_shared_skills": legacy_skills(assets),
    }
''',
        },
        "delete": [],
        "upstream": {
            "discover_homes": "bbb5cd122fd667ac43ad97718052e5a4e3ae18045a5223e49f73cb16f930803a",
            "unavailable_home": "c1ba59f192b967fb5ebb3e06f29b88231a5807eb7a5cb7a2627a05485a1ecde0",
            "inspect_home": "46e99600019f5de387c82f9218d52aed8493a94f5553a88b963a60b84e0c0eb5",
            "inspect_ouroboros": "f71acd6e15dbb4bd0c786f0b025715d705311d8592a154ecdca716b22f1a5aa0",
        },
    },
}


def function_span_digest(source: str, name: str) -> str:
    lines = source.splitlines(keepends=True)
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != name:
            continue
        starts = [node.lineno] + [decorator.lineno for decorator in node.decorator_list]
        start = min(starts) - 1
        return hashlib.sha256("".join(lines[start : node.end_lineno]).encode()).hexdigest()
    raise SyncError(f"script surgery cannot hash missing function `{name}`")


def check_surgery_upstream_pins(relative: str, plan: dict[str, Any]) -> None:
    """Refuse surgery whose upstream function body moved without a re-derivation."""
    replacements = plan.get("replace", {})
    recorded = plan.get("upstream", {})
    missing = sorted(set(replacements) - set(recorded))
    extra = sorted(set(recorded) - set(replacements))
    if missing or extra:
        raise SyncError(
            f"script surgery on `{relative}` has mismatched upstream pins: "
            + ", ".join([*(f"missing {name}" for name in missing), *(f"extra {name}" for name in extra)])
        )
    source = (UPSTREAM_PLUGIN / relative).read_text(encoding="utf-8")
    for name, expected in sorted(recorded.items()):
        current = function_span_digest(source, name)
        if current != expected:
            raise SyncError(
                f"script surgery stale: `{relative}` `{name}` changed upstream\n"
                f"  recorded {expected}\n"
                f"  current  {current}\n"
                "re-derive the replacement from the new upstream function, then "
                "update the surgery upstream pin"
            )


def apply_all_script_surgery(destination: Path) -> None:
    for relative, plan in SCRIPT_SURGERY.items():
        path = destination / relative
        if not path.is_file():
            raise SyncError(f"script surgery target missing: {relative}")
        check_surgery_upstream_pins(relative, plan)
        path.write_text(apply_script_surgery(relative, path.read_text(encoding="utf-8"), plan), encoding="utf-8")


class SyncError(RuntimeError):
    """A condition that must stop generation rather than produce partial output."""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def upstream_commit() -> str:
    result = subprocess.run(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SyncError(
            "cannot resolve the upstream commit; run `git submodule update --init`"
        )
    return result.stdout.strip()


def require_upstream() -> None:
    """Refuse to generate from a missing or partially initialized submodule.

    Grok treats a failed submodule clone as non-fatal, so an empty
    `upstream/` is a realistic state. Generating from it would silently delete
    the committed plugin.
    """
    marker = UPSTREAM_PLUGIN / ".codex-plugin" / "plugin.json"
    if not marker.is_file():
        raise SyncError(
            f"upstream plugin not found at {marker}; "
            "run `git submodule update --init --recursive` before syncing"
        )
    for name in ("skills", "hooks"):
        if not (UPSTREAM_PLUGIN / name).is_dir():
            raise SyncError(f"upstream is missing `{name}/`; refusing to generate")
    status = subprocess.run(
        ["git", "-C", str(UPSTREAM), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0:
        raise SyncError(
            "cannot inspect the upstream worktree; run `git submodule update --init`"
        )
    if status.stdout.strip():
        raise SyncError(
            "upstream worktree is dirty; commit, stash, or reset submodule "
            "changes before generating"
        )
    check_upstream_directories()


def check_upstream_directories() -> None:
    """Refuse to generate when upstream grows a directory nobody decided about.

    `COPIED_DIRECTORIES` is an allowlist with no counterpart check, so `hooks/`
    appeared upstream and was dropped in silence. Whether a new directory belongs
    in a Grok artifact is a decision, and skipping it is not a safe default.
    Root-level files are the same class: a new `.mcp.json` would otherwise vanish.
    """
    known = set(COPIED_DIRECTORIES) | {".codex-plugin"}
    unknown = sorted(
        path.name
        for path in UPSTREAM_PLUGIN.iterdir()
        if path.is_dir() and path.name not in known
    )
    if unknown:
        raise SyncError(
            "upstream has directories this transformation does not handle: "
            + ", ".join(unknown)
            + "; add them to COPIED_DIRECTORIES or exclude them deliberately"
        )
    unknown_files = sorted(
        path.name
        for path in UPSTREAM_PLUGIN.iterdir()
        if path.is_file() and path.name not in COPIED_ROOT_FILES
    )
    if unknown_files:
        raise SyncError(
            "upstream has root-level files this transformation does not handle: "
            + ", ".join(unknown_files)
            + "; copy, exclude, or rewrite them deliberately"
        )
    plugin_meta = UPSTREAM_PLUGIN / ".codex-plugin"
    if plugin_meta.is_dir():
        extra_meta = sorted(
            path.name for path in plugin_meta.iterdir() if path.name != "plugin.json"
        )
        if extra_meta:
            raise SyncError(
                "upstream .codex-plugin/ has files this transformation does not handle: "
                + ", ".join(extra_meta)
            )


def check_excluded_files() -> None:
    """Refuse an exclusion whose target no longer exists upstream.

    An exclusion names a file upstream ships and this artifact does not. Once
    upstream renames or removes that file the entry is dead, and a dead entry
    would hide a differently named replacement behind a decision nobody made.
    """
    for relative, _reason in EXCLUDED_FILES:
        if not (UPSTREAM_PLUGIN / relative).is_file():
            raise SyncError(
                f"exclusion targets `{relative}`, which no longer exists upstream; "
                "remove the exclusion or retarget it"
            )


def check_sigil_literals() -> None:
    """Refuse a sigil exception whose token no longer occurs in any source Markdown.

    The exception exists to stop one shell variable tripping the sigil scan. Once
    nothing writes that token, keeping the entry would blind the scan to a future
    skill sigil that happens to have the same name. Additions and overrides are
    read as well as upstream, because `check_sigils` scans them too and an
    edition-owned file may be the only thing that needs an exception.
    """
    source_markdown = "".join(
        path.read_text(encoding="utf-8")
        for root in (UPSTREAM_PLUGIN, ADDITIONS, OVERRIDES)
        for path in sorted(root.rglob("*.md"))
        if path.is_file()
    )
    dead = [literal for literal in SIGIL_LITERALS if literal not in source_markdown]
    if dead:
        raise SyncError(
            "sigil exceptions no longer occur in upstream, addition, or override Markdown: "
            + ", ".join(dead)
            + "; remove each dead exception so it cannot mask a future sigil"
        )


def apply_substitutions(text: str) -> str:
    for old, new in SUBSTITUTIONS:
        text = text.replace(old, new)
    return text


def read_sidecar_policy(skill: Path) -> bool:
    """Return `allow_implicit_invocation` for one upstream skill.

    The Codex sidecar is the single source of truth for invocation policy, so
    the generated frontmatter flag cannot drift from it. A missing or malformed
    sidecar is an error: guessing a default would risk letting a mutating
    skill fire without the user asking for it.
    """
    sidecar = skill / "agents" / "openai.yaml"
    if not sidecar.is_file():
        raise SyncError(
            f"skill `{skill.name}` has no agents/openai.yaml; "
            "invocation policy cannot be derived and will not be guessed"
        )
    text = sidecar.read_text(encoding="utf-8")
    if not re.search(r"^policy:\s*$", text, re.MULTILINE):
        raise SyncError(f"skill `{skill.name}` sidecar has no policy: mapping")
    match = re.search(
        r"^policy:\s*\n(?:[ \t].*\n)*?[ \t]+allow_implicit_invocation:\s*(true|false)\s*$",
        text,
        re.MULTILINE,
    )
    if not match:
        raise SyncError(
            f"skill `{skill.name}` sidecar has no boolean allow_implicit_invocation under policy:"
        )
    return match.group(1) == "true"


def decorate_frontmatter(
    text: str, skill_name: str, allow_implicit: bool, argument_hint: str | None
) -> str:
    """Add the Grok frontmatter keys the Codex sidecar cannot carry.

    `disable-model-invocation: true` is inserted when implicit invocation is
    off: Grok has no analogue of the Codex sidecar, so the policy has to
    move into the frontmatter, and Codex's own plugin validator rejects the key,
    which is precisely why the generated tree is a separate artifact.
    `argument-hint` is inserted for the skills in `ARGUMENT_HINTS`.
    """
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise SyncError(f"skill `{skill_name}` has no frontmatter block")
    body = match.group(1)
    for key in ("disable-model-invocation", "argument-hint"):
        if key in body:
            raise SyncError(f"skill `{skill_name}` already declares {key}")
    lines = [body]
    if argument_hint is not None:
        # Quoted: a hint such as `[version]` would otherwise parse as a YAML list.
        lines.append(f"argument-hint: {json.dumps(argument_hint)}")
    if not allow_implicit:
        lines.append("disable-model-invocation: true")
    if len(lines) == 1:
        return text
    return text.replace(match.group(0), "---\n" + "\n".join(lines) + "\n---\n", 1)


def reject_symlinks(root: Path) -> None:
    """Refuse a staged tree that contains a symlink.

    `copytree(..., symlinks=True)` preserves upstream links instead of
    dereferencing them; shipping or following either shape is a decision.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        for child in current.iterdir():
            if child.is_symlink():
                relative = child.relative_to(root).as_posix()
                raise SyncError(
                    f"staged tree contains a symlink `{relative}`; "
                    "refuse to dereference or ship it"
                )
            if child.is_dir():
                stack.append(child)


def copy_tree(destination: Path) -> None:
    for name in COPIED_DIRECTORIES:
        source = UPSTREAM_PLUGIN / name
        if source.is_symlink():
            raise SyncError(f"upstream `{name}/` is a symlink; refuse to copy it")
        if not source.is_dir():
            raise SyncError(
                f"upstream is missing `{name}/`; refuse to skip a copied directory"
            )
        shutil.copytree(source, destination / name, symlinks=True)
    for name in COPIED_ROOT_FILES:
        source = UPSTREAM_PLUGIN / name
        if source.is_symlink():
            raise SyncError(f"upstream `{name}` is a symlink; refuse to copy it")
        if not source.is_file():
            raise SyncError(
                f"upstream is missing `{name}`; refuse to skip a copied root file"
            )
        shutil.copy2(source, destination / name)
    reject_symlinks(destination)


def remove_excluded(destination: Path) -> list[str]:
    excluded: list[str] = []
    for relative, _reason in EXCLUDED_FILES:
        target = destination / relative
        try:
            target.unlink()
        except FileNotFoundError as error:
            raise SyncError(
                f"exclusion `{relative}` was not copied into the staging tree"
            ) from error
        excluded.append(relative)
    return excluded


def transform_skills(destination: Path) -> None:
    skills = destination / "skills"
    names = sorted(p.name for p in skills.iterdir() if p.is_dir())
    unknown = sorted(set(ARGUMENT_HINTS) - set(names))
    if unknown:
        raise SyncError(
            "ARGUMENT_HINTS names skills upstream no longer ships: " + ", ".join(unknown)
        )
    for name in names:
        skill = skills / name
        allow_implicit = read_sidecar_policy(UPSTREAM_PLUGIN / "skills" / name)
        skill_md = skill / "SKILL.md"
        if not skill_md.is_file():
            raise SyncError(f"skill `{name}` has no SKILL.md")
        skill_md.write_text(
            decorate_frontmatter(
                skill_md.read_text(encoding="utf-8"),
                name,
                allow_implicit,
                ARGUMENT_HINTS.get(name),
            ),
            encoding="utf-8",
        )
        # The Codex sidecar has no meaning for Grok and its `$` prompts
        # would contradict the generated text, so it is dropped.
        agents = skill / "agents"
        if agents.is_dir():
            extra = sorted(path.name for path in agents.iterdir() if path.name != "openai.yaml")
            if extra:
                raise SyncError(
                    f"skill `{name}` agents/ contains more than openai.yaml: "
                    + ", ".join(extra)
                )
            shutil.rmtree(agents)


def rules_for(path: Path) -> tuple[str, tuple[tuple[str, str], ...]] | None:
    if path.suffix in TEXT_SUFFIXES:
        return RULE_TABLES[0]
    if path.suffix in SCRIPT_SUFFIXES:
        return RULE_TABLES[1]
    if path.suffix in DATA_SUFFIXES:
        return RULE_TABLES[2]
    return None


def transform_text(destination: Path, shadowed: set[str]) -> dict[tuple[str, int], int]:
    """Apply the substitution tables and count how often each rule rewrote shipped text.

    Files an override replaces are transformed too, which is harmless, but a
    match there is not counted: the override discards it, so a rule that only
    ever matched inside an override target rewrites nothing a user sees.
    """
    usage = {
        (table, index): 0
        for table, rules in RULE_TABLES
        for index in range(len(rules))
    }
    for path in sorted(destination.rglob("*")):
        if not path.is_file():
            continue
        selected = rules_for(path)
        if selected is None:
            continue
        table, rules = selected
        counted = str(path.relative_to(destination)) not in shadowed
        original = path.read_text(encoding="utf-8")
        replaced = original
        for index, (old, new) in enumerate(rules):
            matches = replaced.count(old)
            if counted:
                usage[(table, index)] += matches
            if matches:
                replaced = replaced.replace(old, new)
        if replaced != original:
            path.write_text(replaced, encoding="utf-8")
    return usage


def recount_script_substitutions(
    destination: Path,
    usage: dict[tuple[str, int], int],
    shadowed: set[str],
) -> dict[tuple[str, int], int]:
    """Count SCRIPT_SUBSTITUTIONS by remaining shipped text after surgery.

    `transform_text` counts matches before `SCRIPT_SURGERY` rewrites or deletes
    functions. A rule whose only remaining site sat inside a replaced body
    would otherwise report healthy while shipping none of its replacement.
    Override-shadowed paths are skipped, matching `transform_text`.
    """
    recounted = dict(usage)
    remaining: list[str] = []
    for path in sorted(destination.rglob("*")):
        if not path.is_file() or path.suffix not in SCRIPT_SUFFIXES:
            continue
        if str(path.relative_to(destination)) in shadowed:
            continue
        remaining.append(path.read_text(encoding="utf-8"))
    blob = "".join(remaining)
    for index, (old, new) in enumerate(SCRIPT_SUBSTITUTIONS):
        key = ("SCRIPT_SUBSTITUTIONS", index)
        prior = usage.get(key, 0)
        if new:
            recounted[key] = min(prior, blob.count(new))
        elif old in blob:
            recounted[key] = 0
        else:
            recounted[key] = prior
    return recounted


def check_rule_usage(usage: dict[tuple[str, int], int]) -> None:
    """Fail on any substitution rule that rewrote nothing the artifact ships.

    A literal table is brittle to punctuation and to refactoring. v0.1.10
    dropped one Oxford comma and extracted one helper, four Markdown rules and
    three script rules stopped matching, and nothing noticed until a forbidden
    needle happened to trip downstream. A rule that matched nothing is either
    dead and must be deleted, or stale and must be re-derived; neither is a
    decision generation may take by itself.
    """
    tables = dict(RULE_TABLES)
    dead = [
        f"  {table}[{index}]: {tables[table][index][0].splitlines()[0]!r}"
        for (table, index), count in usage.items()
        if count == 0
    ]
    if dead:
        raise SyncError(
            "substitution rules matched nothing that ships:\n"
            + "\n".join(dead)
            + "\ndelete each dead rule or re-derive it against the new upstream text"
        )


def check_required(destination: Path) -> None:
    missing: list[str] = []
    for relative, needle in REQUIRED_TEXT:
        path = destination / relative
        if not path.is_file():
            missing.append(f"  {relative}: file not generated")
        elif needle not in path.read_text(encoding="utf-8"):
            missing.append(f"  {relative}: missing `{needle}` — a substitution stopped matching")
    if missing:
        raise SyncError("required text is absent from the generated tree:\n" + "\n".join(missing))


def upstream_manifest() -> dict[str, Any]:
    return json.loads(
        (UPSTREAM_PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )


def load_override_manifest() -> dict[str, str]:
    if not OVERRIDE_MANIFEST.is_file():
        return {}
    return json.loads(OVERRIDE_MANIFEST.read_text(encoding="utf-8"))


def check_codex_exemptions() -> set[str]:
    """Return the paths whose remaining `Codex` mentions were reviewed and kept.

    Some upstream text names the Codex CLI as a third-party tool rather than as
    the host running the skill — a Mulgae provider, a required CLI version, one
    of several selectable review providers. That text is correct in a Grok
    artifact and cannot be renamed without making it false, but it still trips
    the `Codex` needle, because neither overrides nor copies exempt their own
    content.

    An exemption records that a human read every remaining mention in one file
    and confirmed each is third-party. That judgement holds only for the bytes it
    was made against, so an upstream edit stops the run instead of widening the
    exemption in silence.
    """
    if not CODEX_EXEMPTIONS.is_file():
        return set()
    recorded_all: dict[str, Any] = json.loads(CODEX_EXEMPTIONS.read_text(encoding="utf-8"))
    override_manifest = load_override_manifest()
    for relative, recorded in sorted(recorded_all.items()):
        if isinstance(recorded, str):
            raise SyncError(
                f"`Codex` exemption `{relative}` must record source and shipped "
                "digests as an object; re-read remaining mentions and update "
                "overrides/codex-exemptions.json"
            )
        try:
            source_digest = recorded["source"]
        except (KeyError, TypeError) as error:
            raise SyncError(
                f"`Codex` exemption `{relative}` is missing `source`; "
                "re-read remaining mentions and update overrides/codex-exemptions.json"
            ) from error
        override = OVERRIDES / relative
        if relative in override_manifest:
            source = override
            origin = "override"
        else:
            source = UPSTREAM_PLUGIN / relative
            origin = "upstream"
        if not source.is_file():
            raise SyncError(
                f"`Codex` exemption targets `{relative}`, which no longer exists "
                f"as {origin} bytes; remove the exemption or retarget it"
            )
        current = digest(source)
        if current != source_digest:
            raise SyncError(
                f"`Codex` exemption stale: `{relative}` {origin} bytes changed\n"
                f"  recorded {source_digest}\n"
                f"  current  {current}\n"
                "re-read every remaining `Codex` mention, confirm each still names "
                "the third-party CLI, then update overrides/codex-exemptions.json"
            )
        if "Codex" not in source.read_text(encoding="utf-8"):
            raise SyncError(
                f"`Codex` exemption `{relative}` no longer contains `Codex`; "
                "remove the exemption"
            )
    return set(recorded_all)


def apply_overrides(destination: Path) -> list[str]:
    """Replace files whose Grok form diverges semantically from upstream.

    Every override records the SHA-256 of the upstream file it was derived
    from. When upstream changes that file the override is stale, and merging
    it silently would ship guidance that no longer matches the source. That is
    the one failure mode that quietly breaks a fork, so it stops the run.
    """
    manifest = load_override_manifest()
    applied: list[str] = []
    for relative, recorded in sorted(manifest.items()):
        source = UPSTREAM_PLUGIN / relative
        override = OVERRIDES / relative
        if not override.is_file():
            raise SyncError(f"override file missing: {override}")
        if not source.is_file():
            raise SyncError(
                f"override targets `{relative}`, which no longer exists upstream; "
                "remove the override or retarget it"
            )
        current = digest(source)
        if current != recorded:
            raise SyncError(
                f"override stale: `{relative}` changed upstream\n"
                f"  recorded {recorded}\n"
                f"  current  {current}\n"
                "re-derive the override from the new upstream content, then update "
                "overrides/manifest.json"
            )
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(override, target)
        applied.append(relative)
    return applied


def listed_source_files(root: Path) -> set[str]:
    ignored = {"__pycache__"}
    files: set[str] = set()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in ignored for part in relative.parts):
            continue
        if path.name == ".DS_Store":
            continue
        if path.is_file():
            files.add(relative.as_posix())
    return files


def check_source_tables() -> None:
    """Refuse an additions or overrides file that no table names.

    Both apply loops walk tables, not trees. An unlisted file is silent
    partial output, the class this generator is built to refuse.
    """
    excluded = {path for path, _reason in EXCLUDED_FILES}
    resurrected = sorted(excluded & (set(ADDED_PATHS) | set(load_override_manifest())))
    if resurrected:
        raise SyncError(
            "excluded path also listed as an addition or override: "
            + ", ".join(resurrected)
        )

    added = listed_source_files(ADDITIONS)
    expected_added = set(ADDED_PATHS)
    extra_added = sorted(added - expected_added)
    missing_added = sorted(expected_added - added)
    if extra_added or missing_added:
        details: list[str] = []
        if extra_added:
            details.append("unlisted additions: " + ", ".join(extra_added))
        if missing_added:
            details.append("missing additions: " + ", ".join(missing_added))
        raise SyncError("; ".join(details))

    tables = {"manifest.json", "codex-exemptions.json"}
    override_files = listed_source_files(OVERRIDES) - tables
    expected_overrides = set(load_override_manifest())
    extra_overrides = sorted(override_files - expected_overrides)
    missing_overrides = sorted(expected_overrides - override_files)
    if extra_overrides or missing_overrides:
        details = []
        if extra_overrides:
            details.append("unlisted overrides: " + ", ".join(extra_overrides))
        if missing_overrides:
            details.append("missing overrides: " + ", ".join(missing_overrides))
        raise SyncError("; ".join(details))


def apply_additions(destination: Path) -> list[str]:
    """Copy the host-only files that have no upstream counterpart.

    `transform_skills` deletes each skill's own `agents/` sidecar directory; the
    plugin-root `agents/` directory created here is unrelated to those and is
    where Grok discovers plugin subagents.
    """
    added: list[str] = []
    addition_skills = {
        relative.split("/")[1]
        for relative in ADDED_PATHS
        if relative.startswith("skills/") and relative.endswith("/SKILL.md")
    }
    unknown_hints = sorted(set(ADDITION_ARGUMENT_HINTS) - addition_skills)
    if unknown_hints:
        raise SyncError(
            "ADDITION_ARGUMENT_HINTS names skills this edition does not add: "
            + ", ".join(unknown_hints)
        )
    for relative in ADDED_PATHS:
        source = ADDITIONS / relative
        target = destination / relative
        if not source.is_file():
            raise SyncError(f"addition file missing: {source}")
        if target.exists():
            raise SyncError(
                f"addition `{relative}` collides with an upstream-derived file; "
                "use an override for a file upstream ships"
            )
        segments = relative.split("/")
        if len(segments) == 3 and segments[0] == "skills" and segments[2] == "SKILL.md":
            text = source.read_text(encoding="utf-8")
            if "disable-model-invocation: true" not in text:
                # An addition skill bypasses the sidecar-derived gating, so a
                # missing flag would ship a model-invocable mutating skill.
                raise SyncError(
                    f"addition skill `{relative}` must declare "
                    "disable-model-invocation: true in its own frontmatter"
                )
            hint = ADDITION_ARGUMENT_HINTS.get(segments[1])
            if hint is not None and f"argument-hint: {json.dumps(hint)}" not in text:
                raise SyncError(
                    f"addition skill `{relative}` must declare "
                    f"argument-hint: {json.dumps(hint)}"
                )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        added.append(relative)
    return added


def write_plugin_manifest(destination: Path) -> None:
    """Derive the Grok plugin.json from the Codex one so versions cannot diverge."""
    codex = upstream_manifest()
    copied = {
        "name",
        "version",
        "description",
        "author",
        "homepage",
        "license",
        "keywords",
    }
    dropped = {"interface", "repository", "skills", "mcpServers"}
    unknown = sorted(set(codex) - copied - dropped)
    if unknown:
        raise SyncError(
            "upstream plugin.json has keys this transformation does not handle: "
            + ", ".join(unknown)
            + "; copy, drop, or rewrite them deliberately"
        )
    manifest: dict[str, Any] = {
        "name": codex["name"],
        "version": codex["version"],
        "description": apply_substitutions(codex["description"]),
        "author": codex.get("author", "Root Kernel"),
        "homepage": codex.get("homepage"),
        "license": codex["license"],
        "keywords": codex.get("keywords", []),
        "skills": "./skills/",
    }
    manifest = {k: v for k, v in manifest.items() if v is not None}
    (destination / "plugin.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def check_forbidden(destination: Path, codex_exemptions: set[str]) -> None:
    """Scan every generated text file for host-specific text.

    Scripts and YAML are included. `CODEX_HOME` survives in im-not-ai installer
    prose and the aquarium-dev launcher pass-through on purpose — a Grok user
    may also have Codex skills installed — and it is not a match, because the
    needle is `Codex` rather than `CODEX`.

    Only the `Codex` needle is skipped, and only for reviewed exemptions; every
    other needle applies to every file.
    """
    failures: list[str] = []
    for path in sorted(destination.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        relative = path.relative_to(destination)
        text = path.read_text(encoding="utf-8")
        for needle, remedy in FORBIDDEN:
            if needle == "Codex" and str(relative) in codex_exemptions:
                continue
            if needle in text:
                failures.append(f"  {relative}: contains `{needle}` — {remedy}")
    if failures:
        raise SyncError("host-specific text survived transformation:\n" + "\n".join(failures))
    check_shipped_codex_lines(destination)


def shipped_codex_digest(text: str) -> str:
    payload = "\n".join(line for line in text.splitlines() if "Codex" in line)
    if payload:
        payload += "\n"
    return hashlib.sha256(payload.encode()).hexdigest()


def check_shipped_codex_lines(destination: Path) -> None:
    """Pin the `Codex` lines that actually ship, not only the source bytes."""
    if not CODEX_EXEMPTIONS.is_file():
        return
    recorded_all: dict[str, Any] = json.loads(CODEX_EXEMPTIONS.read_text(encoding="utf-8"))
    failures: list[str] = []
    for relative, recorded in sorted(recorded_all.items()):
        path = destination / relative
        if not path.is_file():
            failures.append(f"  {relative}: exempted file was not generated")
            continue
        current = shipped_codex_digest(path.read_text(encoding="utf-8"))
        try:
            expected = recorded["shipped"]
        except (KeyError, TypeError) as error:
            raise SyncError(
                f"`Codex` exemption `{relative}` is missing `shipped`; "
                "re-read remaining mentions and update overrides/codex-exemptions.json"
            ) from error
        if current != expected:
            failures.append(
                f"  {relative}: shipped `Codex` lines changed\n"
                f"    recorded {expected}\n"
                f"    current  {current}\n"
                "    re-read every remaining mention in the generated file"
            )
        elif "Codex" not in path.read_text(encoding="utf-8"):
            failures.append(f"  {relative}: exemption no longer contains `Codex`")
    if failures:
        raise SyncError(
            "shipped `Codex` exemption lines drifted:\n" + "\n".join(failures)
        )


def check_sigils(destination: Path) -> None:
    """Fail on any Codex skill sigil that no substitution rule rewrote.

    This closes the class rather than the known instances: an unmapped sigil is
    a silent failure, because it is valid Markdown that simply names a command
    the reader's host does not have. `SIGIL_LITERALS` carries the named
    exceptions, each one a shell variable the pattern cannot tell apart.
    """
    failures: list[str] = []
    for path in sorted(destination.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        found = sorted(
            token
            for token in set(SIGIL.findall(path.read_text(encoding="utf-8")))
            if token not in SIGIL_LITERALS
        )
        if found:
            failures.append(f"  {path.relative_to(destination)}: {', '.join(found)}")
    if failures:
        raise SyncError(
            "Codex skill sigils survived transformation:\n"
            + "\n".join(failures)
            + "\nadd a substitution rule naming each sigil's Grok form"
        )


def generated_function_nodes(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

    def walk(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nodes.append(node)
            elif isinstance(node, ast.ClassDef):
                walk(node.body)

    walk(tree.body)
    return nodes


def positional_arity_errors(tree: ast.Module) -> list[tuple[int, str]]:
    """Report direct calls that a same-module signature rejects.

    A block substitution that drifts can produce code that parses but cannot
    run: v0.1.10 gave `classify_ouroboros_registration` a second parameter, and
    a replacement block that kept calling it with one would have raised
    `TypeError` on every inspection. Only simple shapes are checked — functions
    without `*args`, `**kwargs`, or keyword-only parameters, called by bare name.
    """
    signatures: dict[str, tuple[int, int, tuple[str, ...]]] = {}
    for node in generated_function_nodes(tree):
        arguments = node.args
        if arguments.vararg or arguments.kwarg or arguments.kwonlyargs:
            continue
        positional = arguments.posonlyargs + arguments.args
        names = tuple(argument.arg for argument in positional)
        signatures[node.name] = (
            len(positional) - len(arguments.defaults),
            len(positional),
            names,
        )
    errors: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        signature = signatures.get(node.func.id)
        if signature is None:
            continue
        if any(isinstance(argument, ast.Starred) for argument in node.args):
            continue
        if any(keyword.arg is None for keyword in node.keywords):
            continue
        required, total, names = signature
        if not node.keywords:
            if not required <= len(node.args) <= total:
                expected = str(total) if required == total else f"{required}-{total}"
                errors.append(
                    (
                        node.lineno,
                        f"{node.func.id}: {len(node.args)} positional argument(s), expected {expected}",
                    )
                )
            continue
        if len(node.args) > total:
            errors.append(
                (
                    node.lineno,
                    f"{node.func.id}: {len(node.args)} positional argument(s), expected at most {total}",
                )
            )
            continue
        bound = set(names[: len(node.args)])
        incompatible: list[str] = []
        for keyword in node.keywords:
            name = keyword.arg
            if name is None or name in bound or name not in names:
                incompatible.append(name or "*")
            else:
                bound.add(name)
        if incompatible:
            errors.append(
                (
                    node.lineno,
                    f"{node.func.id}: incompatible keyword argument(s): {', '.join(incompatible)}",
                )
            )
        elif not set(names[:required]) <= bound:
            errors.append(
                (node.lineno, f"{node.func.id}: missing required argument(s)")
            )
    return errors


def _bind_assign_target(target: ast.AST, bound: set[str]) -> None:
    if isinstance(target, ast.Name):
        bound.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            _bind_assign_target(element, bound)
    elif isinstance(target, ast.Starred):
        _bind_assign_target(target.value, bound)


def _scope_bindings(function: ast.FunctionDef) -> set[str]:
    bound = {argument.arg for argument in function.args.posonlyargs + function.args.args}
    if function.args.vararg:
        bound.add(function.args.vararg.arg)
    if function.args.kwarg:
        bound.add(function.args.kwarg.arg)
    bound.update(argument.arg for argument in function.args.kwonlyargs)
    for node in ast.walk(function):
        if node is function:
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                _bind_assign_target(target, bound)
        elif isinstance(node, ast.AnnAssign):
            _bind_assign_target(node.target, bound)
    return bound


def unresolved_module_global_errors(tree: ast.Module) -> list[tuple[int, str]]:
    """Report Name loads in module functions that no module binding can satisfy.

    `compile` accepts `supported_dolgorae_version` after its `dolgorae_release`
    import is stripped; the NameError waits until the dead helper is called.
    """
    builtins_names = set(dir(__builtins__)) if not isinstance(__builtins__, dict) else set(__builtins__)
    bindings = set(builtins_names) | {
        "__file__",
        "__name__",
        "__package__",
        "__doc__",
        "__spec__",
        "__cached__",
        "__builtins__",
        "__loader__",
        "__annotations__",
    }

    def collect(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bindings.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                _bind_assign_target(target, bindings)
        elif isinstance(node, ast.AnnAssign):
            _bind_assign_target(node.target, bindings)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bindings.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bindings.add(alias.asname or alias.name)
        elif isinstance(node, ast.Try):
            for statement in (*node.body, *node.orelse, *node.finalbody):
                collect(statement)
            for handler in node.handlers:
                if handler.name:
                    bindings.add(handler.name)
                for statement in handler.body:
                    collect(statement)
        elif isinstance(node, ast.If):
            for statement in (*node.body, *node.orelse):
                collect(statement)
        elif isinstance(node, ast.With):
            for statement in node.body:
                collect(statement)

    for statement in tree.body:
        collect(statement)
    errors: list[tuple[int, str]] = []
    for node in generated_function_nodes(tree):
        local = _scope_bindings(node)
        for child in ast.walk(node):
            if not isinstance(child, ast.Name) or not isinstance(child.ctx, ast.Load):
                continue
            if child.id in local or child.id in bindings:
                continue
            errors.append((child.lineno, f"unresolved name `{child.id}`"))

    def module_level_loads(node: ast.AST, extra: set[str]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.Lambda):
            local = extra | {arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
            if node.args.vararg:
                local.add(node.args.vararg.arg)
            if node.args.kwarg:
                local.add(node.args.kwarg.arg)
            module_level_loads(node.body, local)
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            local = set(extra)
            for generator in node.generators:
                _bind_assign_target(generator.target, local)
                module_level_loads(generator.iter, extra)
                for if_clause in generator.ifs:
                    module_level_loads(if_clause, local)
            if isinstance(node, ast.DictComp):
                module_level_loads(node.key, local)
                module_level_loads(node.value, local)
            else:
                module_level_loads(node.elt, local)
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in bindings and node.id not in extra:
                errors.append((node.lineno, f"unresolved name `{node.id}`"))
            return
        for child in ast.iter_child_nodes(node):
            module_level_loads(child, extra)

    for statement in tree.body:
        module_level_loads(statement, set())
    return errors


def check_generated_python(destination: Path) -> None:
    """Refuse generated scripts that cannot parse or call their own functions.

    `ast.parse` rather than `py_compile`: the latter writes `__pycache__` into
    the staged tree, which `--check` would then report as drift.
    """
    failures: list[str] = []
    for path in sorted(destination.rglob("*.py")):
        relative = path.relative_to(destination)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
        except SyntaxError as error:
            failures.append(f"  {relative}:{error.lineno}: {error.msg}")
            continue
        failures.extend(
            f"  {relative}:{line}: {message}" for line, message in positional_arity_errors(tree)
        )
        failures.extend(
            f"  {relative}:{line}: {message}"
            for line, message in unresolved_module_global_errors(tree)
        )
    if failures:
        raise SyncError(
            "generated Python cannot run — a script substitution drifted:\n" + "\n".join(failures)
        )


def unscanned_shipped(relative: str, suffix: str) -> bool:
    return any(
        relative.startswith(prefix) and suffix in suffixes
        for prefix, suffixes in UNSCANNED_SHIPPED_PREFIXES
    )


def check_generated_suffixes(destination: Path) -> None:
    """Refuse generated files whose suffix the transformation does not scan."""
    allowed = set(SCANNED_SUFFIXES)
    unexpected = [
        str(path.relative_to(destination))
        for path in sorted(destination.rglob("*"))
        if path.is_file()
        and path.suffix not in allowed
        and not unscanned_shipped(path.relative_to(destination).as_posix(), path.suffix)
    ]
    if unexpected:
        raise SyncError(
            "generated files use suffixes this transformation does not scan:\n  "
            + "\n  ".join(unexpected)
            + "\nadd the suffix to SCANNED_SUFFIXES or exclude the file"
        )


def check_excluded_references(destination: Path) -> None:
    """Fail when generated text still names a file the exclusion removed."""
    failures: list[str] = []
    for relative, _reason in EXCLUDED_FILES:
        basename = Path(relative).name
        for path in sorted(destination.rglob("*")):
            if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
                continue
            if basename in path.read_text(encoding="utf-8"):
                failures.append(f"  {path.relative_to(destination)}: references excluded `{relative}`")
    if failures:
        raise SyncError(
            "generated text references an excluded file:\n"
            + "\n".join(failures)
            + "\nstop excluding it or rewrite the reference"
        )


def write_sync_manifest(
    destination: Path,
    repository: str,
    commit: str,
    overrides: list[str],
    excluded: list[str],
    additions: list[str],
) -> None:
    files = {
        path.relative_to(destination).as_posix(): digest(path)
        for path in sorted(
            destination.rglob("*"),
            key=lambda path: path.relative_to(destination).parts,
        )
        if path.is_file() and path.name != SYNC_MANIFEST
    }
    payload = {
        "upstream": {
            "repository": repository,
            "commit": commit,
        },
        "overrides": overrides,
        "excluded": excluded,
        "additions": additions,
        "argument_hints": dict(
            sorted({**ARGUMENT_HINTS, **ADDITION_ARGUMENT_HINTS}.items())
        ),
        "files": files,
    }
    (destination / SYNC_MANIFEST).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def generate(destination: Path) -> tuple[str, list[str]]:
    commit = upstream_commit()
    codex_exemptions = check_codex_exemptions()
    check_excluded_files()
    check_sigil_literals()
    check_source_tables()
    copy_tree(destination)
    excluded = remove_excluded(destination)
    shadowed = set(load_override_manifest())
    usage = transform_text(destination, shadowed)
    apply_all_script_surgery(destination)
    check_rule_usage(recount_script_substitutions(destination, usage, shadowed))
    # Overrides replace whole files, so they run before gating. Otherwise an
    # override would overwrite the frontmatter key and quietly reintroduce the
    # policy drift the sidecar is meant to prevent.
    overrides = apply_overrides(destination)
    transform_skills(destination)
    additions = apply_additions(destination)
    write_plugin_manifest(destination)
    check_forbidden(destination, codex_exemptions)
    check_sigils(destination)
    check_generated_python(destination)
    check_generated_suffixes(destination)
    check_excluded_references(destination)
    check_required(destination)
    try:
        repository_url = upstream_manifest()["repository"]
    except KeyError as error:
        raise SyncError(
            "upstream plugin.json is missing `repository`; the Grok manifest "
            "cannot record provenance without it"
        ) from error
    write_sync_manifest(
        destination, repository_url, commit, overrides, excluded, additions
    )
    return commit, overrides


def artifact_file_map(root: Path) -> dict[str, str]:
    """Map artifact-relative POSIX paths to a type-aware identity, skipping ignored names."""
    ignored = {"__pycache__"}
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if any(part in ignored for part in path.relative_to(root).parts):
            continue
        if path.name == ".DS_Store":
            continue
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            files[relative] = "symlink:" + str(path.readlink())
        elif path.is_dir():
            continue
        elif path.is_file():
            executable = int(bool(path.stat().st_mode & 0o111))
            files[relative] = f"{executable}:{digest(path)}"
    return files


def differences(left: Path, right: Path, prefix: Path = Path()) -> list[str]:
    del prefix
    left_files = artifact_file_map(left)
    right_files = artifact_file_map(right)
    found = [
        f"only in committed output: {name}"
        for name in sorted(set(left_files) - set(right_files))
    ]
    found += [
        f"only in regenerated output: {name}"
        for name in sorted(set(right_files) - set(left_files))
    ]
    found += [
        f"differs: {name}"
        for name in sorted(set(left_files) & set(right_files))
        if left_files[name] != right_files[name]
    ]
    ignored = {"__pycache__"}
    left_dirs = {
        path.relative_to(left).as_posix()
        for path in left.rglob("*")
        if path.is_dir()
        and not path.is_symlink()
        and not any(part in ignored for part in path.relative_to(left).parts)
    }
    right_dirs = {
        path.relative_to(right).as_posix()
        for path in right.rglob("*")
        if path.is_dir()
        and not path.is_symlink()
        and not any(part in ignored for part in path.relative_to(right).parts)
    }
    found += [
        f"type mismatch: {name}"
        for name in sorted((set(left_files) & right_dirs) | (set(right_files) & left_dirs))
    ]
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed output matches a fresh regeneration",
    )
    arguments = parser.parse_args()

    try:
        require_upstream()
        with tempfile.TemporaryDirectory() as temporary:
            staged = Path(temporary) / "aquarium"
            staged.mkdir()
            commit, overrides = generate(staged)

            if arguments.check:
                if not OUTPUT.is_dir():
                    print("error: plugins/aquarium/ has not been generated", file=sys.stderr)
                    return 1
                drift = differences(OUTPUT, staged)
                if drift:
                    print("error: committed output is stale:", file=sys.stderr)
                    for entry in drift:
                        print(f"  {entry}", file=sys.stderr)
                    print("\nrun `python3 scripts/sync.py` and commit the result", file=sys.stderr)
                    return 1
                print(f"in sync with upstream {commit[:9]} ({len(overrides)} overrides)")
                return 0

            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            replacement = OUTPUT.with_name(".aquarium.new")
            previous = OUTPUT.with_name(".aquarium.old")
            if replacement.exists():
                shutil.rmtree(replacement)
            if previous.exists():
                shutil.rmtree(previous)
            shutil.copytree(staged, replacement, symlinks=True)
            if OUTPUT.exists():
                OUTPUT.rename(previous)
            replacement.rename(OUTPUT)
            if previous.exists():
                shutil.rmtree(previous)
    except SyncError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    skills = sorted(p.name for p in (OUTPUT / "skills").iterdir() if p.is_dir())
    gated = sum(
        1
        for name in skills
        if "disable-model-invocation: true" in (OUTPUT / "skills" / name / "SKILL.md").read_text(
            encoding="utf-8"
        )
    )
    print(f"generated {len(skills)} skills from upstream {commit[:9]}")
    print(f"  {gated} gated against model invocation, {len(skills) - gated} model-invocable")
    print(
        f"  {len(overrides)} overrides applied, {len(EXCLUDED_FILES)} upstream files excluded, "
        f"{len(ADDED_PATHS)} host-only files added"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
