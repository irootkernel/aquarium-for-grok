"""Commit-gate payload compatibility for Grok camelCase envelopes."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, env=GIT_ENV)


def load_gate():
    path = Path(__file__).resolve().parents[1] / "plugins" / "aquarium" / "hooks" / "task_commit_gate.py"
    spec = importlib.util.spec_from_file_location("task_commit_gate", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


def init_roadmap_repository(root: Path) -> None:
    run_git(["git", "init"], root)
    roadmap = root / "docs" / "roadmap.md"
    roadmap.parent.mkdir()
    roadmap.write_text("# Task\n\nIn Progress\n", encoding="utf-8")
    run_git(["git", "add", "docs/roadmap.md"], root)


class TaskCommitGatePayloadTests(unittest.TestCase):
    def test_missing_command_fails_open(self) -> None:
        gate = load_gate()
        self.assertIsNone(gate.denial_reason({"cwd": "/tmp"}))

    def test_denies_camelcase_git_commit_in_roadmap_repo(self) -> None:
        gate = load_gate()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_roadmap_repository(root)
            payload = {
                "toolInput": {"command": "git commit -m test"},
                "cwd": str(root),
            }
            self.assertEqual(gate.denial_reason(payload), gate.MISSING_GATE_REASON)

    def test_denies_snake_case_git_commit_in_roadmap_repo(self) -> None:
        gate = load_gate()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_roadmap_repository(root)
            payload = {
                "tool_input": {"command": "git commit -m test"},
                "cwd": str(root),
            }
            self.assertEqual(gate.denial_reason(payload), gate.MISSING_GATE_REASON)

    def test_non_commit_command_in_roadmap_repository_is_allowed(self) -> None:
        gate = load_gate()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_roadmap_repository(root)
            payload = {
                "toolInput": {"command": "git status"},
                "cwd": str(root),
            }
            self.assertIsNone(gate.denial_reason(payload))

    def test_commit_outside_roadmap_repository_is_not_denied(self) -> None:
        gate = load_gate()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_git(["git", "init"], root)
            payload = {
                "toolInput": {"command": "git commit -m test"},
                "cwd": str(root),
            }
            self.assertIsNone(gate.denial_reason(payload))

    def test_gated_commit_requires_local_identity(self) -> None:
        gate = load_gate()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_roadmap_repository(root)
            payload = {
                "toolInput": {
                    "command": "AQUARIUM_COMMIT_GATE=task-commit-v1 git commit -m test"
                },
                "cwd": str(root),
            }
            self.assertEqual(gate.denial_reason(payload), gate.MISSING_IDENTITY_REASON)
            run_git(["git", "config", "user.name", "Test"], root)
            run_git(["git", "config", "user.email", "test@example.com"], root)
            self.assertIsNone(gate.denial_reason(payload))

    def test_main_emits_deny_wire_format(self) -> None:
        gate = load_gate()
        gate_path = (
            Path(__file__).resolve().parents[1]
            / "plugins"
            / "aquarium"
            / "hooks"
            / "task_commit_gate.py"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_roadmap_repository(root)
            payload = {
                "toolInput": {"command": "git commit -m test"},
                "cwd": str(root),
            }
            result = subprocess.run(
                [sys.executable, str(gate_path)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            body = json.loads(result.stdout)
            output = body["hookSpecificOutput"]
            self.assertEqual(output["hookEventName"], "PreToolUse")
            self.assertEqual(output["permissionDecision"], "deny")
            self.assertEqual(output["permissionDecisionReason"], gate.MISSING_GATE_REASON)

    def test_truncated_payload_denies_in_roadmap_repository(self) -> None:
        gate = load_gate()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_roadmap_repository(root)
            payload = {
                "toolInput": {"command": "npm test && echo done"},
                "toolInputTruncated": True,
                "cwd": str(root),
            }
            self.assertEqual(gate.denial_reason(payload), gate.TRUNCATED_PAYLOAD_REASON)

    def test_truncated_payload_without_command_denies_in_roadmap_repository(self) -> None:
        gate = load_gate()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_roadmap_repository(root)
            payload = {
                "toolInputTruncated": True,
                "cwd": str(root),
            }
            self.assertEqual(gate.denial_reason(payload), gate.TRUNCATED_PAYLOAD_REASON)

    def test_truncated_payload_outside_roadmap_repository_is_not_denied(self) -> None:
        gate = load_gate()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_git(["git", "init"], root)
            payload = {
                "toolInput": {"command": "npm test && echo done"},
                "toolInputTruncated": True,
                "cwd": str(root),
            }
            self.assertIsNone(gate.denial_reason(payload))

    def test_truncated_payload_denies_cd_into_roadmap_repository(self) -> None:
        gate = load_gate()
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "outside"
            roadmap = Path(tmp) / "roadmap"
            outside.mkdir()
            roadmap.mkdir()
            init_roadmap_repository(roadmap)
            run_git(["git", "init"], outside)
            payload = {
                "toolInput": {"command": f"cd {roadmap} && git commit -m test"},
                "toolInputTruncated": True,
                "cwd": str(outside),
            }
            self.assertEqual(gate.denial_reason(payload), gate.TRUNCATED_PAYLOAD_REASON)

    def test_main_invalid_json_and_non_dict_fail_open(self) -> None:
        gate_path = (
            Path(__file__).resolve().parents[1]
            / "plugins"
            / "aquarium"
            / "hooks"
            / "task_commit_gate.py"
        )
        for stdin in ("not json", "[]"):
            result = subprocess.run(
                [sys.executable, str(gate_path)],
                input=stdin,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
