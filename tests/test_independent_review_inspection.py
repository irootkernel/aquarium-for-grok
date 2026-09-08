"""Independent Review inspectors: snapshot/compare and unborn staged HEAD."""

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


def load_module(relative: str, name: str):
    path = Path(__file__).resolve().parents[1] / "plugins" / "aquarium" / Path(relative)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


def init_repository(root: Path) -> None:
    run_git(["git", "init"], root)
    run_git(["git", "config", "user.name", "Test"], root)
    run_git(["git", "config", "user.email", "test@example.com"], root)


class RepositoryStateInspectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module(
            "skills/independent-review/scripts/inspect_repository_state.py",
            "inspect_repository_state",
        )

    def test_snapshot_round_trip_and_compare_without_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            run_git(["git", "add", "tracked.txt"], root)
            run_git(["git", "commit", "-m", "init"], root)
            repository = self.module.canonical_git_root(root.resolve())
            baseline = self.module.snapshot(repository)
            parsed = self.module.parse_baseline(
                json.dumps(baseline).encode(), repository
            )
            self.assertEqual(parsed["fingerprint"], baseline["fingerprint"])
            compared = self.module.compare(repository, parsed)
            self.assertFalse(compared["drift"])
            self.assertEqual(compared["changed"], [])

    def test_compare_reports_tracked_worktree_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            run_git(["git", "add", "tracked.txt"], root)
            run_git(["git", "commit", "-m", "init"], root)
            repository = self.module.canonical_git_root(root.resolve())
            baseline = self.module.snapshot(repository)
            (root / "tracked.txt").write_text("two\n", encoding="utf-8")
            compared = self.module.compare(repository, baseline)
            self.assertTrue(compared["drift"])
            self.assertIn("tracked_worktree_sha256", compared["changed"])

    def test_compare_reports_untracked_content_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            run_git(["git", "add", "tracked.txt"], root)
            run_git(["git", "commit", "-m", "init"], root)
            (root / "loose.txt").write_text("alpha\n", encoding="utf-8")
            repository = self.module.canonical_git_root(root.resolve())
            baseline = self.module.snapshot(repository)
            (root / "loose.txt").write_text("beta\n", encoding="utf-8")
            compared = self.module.compare(repository, baseline)
            self.assertTrue(compared["drift"])
            self.assertIn("status_sha256", compared["changed"])

    def test_snapshot_accepts_untracked_nested_git_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            run_git(["git", "add", "tracked.txt"], root)
            run_git(["git", "commit", "-m", "init"], root)
            nested = root / "vendor"
            nested.mkdir()
            run_git(["git", "init"], nested)
            repository = self.module.canonical_git_root(root.resolve())
            baseline = self.module.snapshot(repository)
            self.assertRegex(baseline["fingerprint"], r"^[0-9a-f]{64}$")
            (nested / "secret.txt").write_text("changed\n", encoding="utf-8")
            compared = self.module.snapshot(repository)
            self.assertEqual(compared["fingerprint"], baseline["fingerprint"])

    def test_snapshot_accepts_uninitialized_gitlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            run_git(["git", "add", "tracked.txt"], root)
            run_git(["git", "commit", "-m", "init"], root)
            (root / "vendor").mkdir()
            run_git(
                [
                    "git",
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    "160000," + ("a" * 40) + ",vendor",
                ],
                root,
            )
            repository = self.module.canonical_git_root(root.resolve())
            baseline = self.module.snapshot(repository)
            self.assertRegex(baseline["fingerprint"], r"^[0-9a-f]{64}$")

    def test_snapshot_accepts_initialized_gitlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            run_git(["git", "add", "tracked.txt"], root)
            run_git(["git", "commit", "-m", "init"], root)
            nested = root / "vendor"
            nested.mkdir()
            init_repository(nested)
            (nested / "lib.txt").write_text("n\n", encoding="utf-8")
            run_git(["git", "add", "lib.txt"], nested)
            run_git(["git", "commit", "-m", "nested"], nested)
            sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=nested, env=GIT_ENV, text=True
            ).strip()
            run_git(
                ["git", "update-index", "--add", "--cacheinfo", f"160000,{sha},vendor"],
                root,
            )
            repository = self.module.canonical_git_root(root.resolve())
            baseline = self.module.snapshot(repository)
            self.assertRegex(baseline["fingerprint"], r"^[0-9a-f]{64}$")
            (nested / "lib.txt").write_text("mutated\n", encoding="utf-8")
            compared = self.module.snapshot(repository)
            self.assertNotEqual(compared["fingerprint"], baseline["fingerprint"])

    def test_snapshot_reports_symlink_retarget_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            (root / "target-a.txt").write_text("a\n", encoding="utf-8")
            (root / "target-b.txt").write_text("b\n", encoding="utf-8")
            (root / "link").symlink_to("target-a.txt")
            run_git(["git", "add", "tracked.txt", "target-a.txt", "target-b.txt", "link"], root)
            run_git(["git", "commit", "-m", "init"], root)
            (root / "loose-link").symlink_to("target-a.txt")
            repository = self.module.canonical_git_root(root.resolve())
            baseline = self.module.snapshot(repository)
            (root / "link").unlink()
            (root / "link").symlink_to("target-b.txt")
            (root / "loose-link").unlink()
            (root / "loose-link").symlink_to("target-b.txt")
            compared = self.module.compare(repository, baseline)
            self.assertTrue(compared["drift"])
            self.assertIn("tracked_worktree_sha256", compared["changed"])
            self.assertIn("status_sha256", compared["changed"])

    def test_parse_baseline_rejects_malformed_oversized_and_foreign(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            run_git(["git", "add", "tracked.txt"], root)
            other = Path(tmp) / "other"
            other.mkdir()
            init_repository(other)
            repository = self.module.canonical_git_root(root.resolve())
            foreign = self.module.canonical_git_root(other.resolve())
            baseline = self.module.snapshot(repository)
            with self.assertRaises(self.module.InspectionError) as malformed:
                self.module.parse_baseline(b"{", repository)
            self.assertEqual(malformed.exception.code, "baseline_invalid")
            oversized = b"{" + (b"x" * (self.module.MAX_BASELINE_BYTES + 1))
            with self.assertRaises(self.module.InspectionError) as huge:
                self.module.parse_baseline(oversized, repository)
            self.assertEqual(huge.exception.code, "baseline_oversized")
            with self.assertRaises(self.module.InspectionError) as other_repo:
                self.module.parse_baseline(json.dumps(baseline).encode(), foreign)
            self.assertEqual(other_repo.exception.code, "baseline_invalid")


class ReviewTargetInspectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module(
            "skills/independent-review/scripts/inspect_review_target.py",
            "inspect_review_target",
        )

    def test_inspect_staged_unborn_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / "staged.txt").write_text("content\n", encoding="utf-8")
            run_git(["git", "add", "staged.txt"], root)
            target = self.module.inspect_staged(root.resolve())
            self.assertEqual(target["kind"], "staged")
            self.assertIsNone(target["head_commit"])
            self.assertTrue(target["head_unborn"])
            self.assertRegex(target["diff_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(target["target_digest"], r"^[0-9a-f]{64}$")

    def test_inspect_staged_born_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            run_git(["git", "add", "tracked.txt"], root)
            run_git(["git", "commit", "-m", "init"], root)
            (root / "tracked.txt").write_text("two\n", encoding="utf-8")
            run_git(["git", "add", "tracked.txt"], root)
            target = self.module.inspect_staged(root.resolve())
            self.assertEqual(target["kind"], "staged")
            self.assertFalse(target["head_unborn"])
            self.assertRegex(target["head_commit"], r"^[0-9a-f]{40,64}$")

    def test_inspect_staged_empty_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            run_git(["git", "add", "tracked.txt"], root)
            run_git(["git", "commit", "-m", "init"], root)
            with self.assertRaises(self.module.InspectionError) as error:
                self.module.inspect_staged(root.resolve())
            self.assertEqual(error.exception.code, "staged_target_empty")

    def test_inspect_staged_revision_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / ".git" / "HEAD").write_text("not-a-commit\n", encoding="utf-8")
            with self.assertRaises(self.module.InspectionError) as error:
                self.module.inspect_staged(root.resolve())
            self.assertEqual(error.exception.code, "revision_unresolved")


class IndependentReviewInspectorEnvelopeTests(unittest.TestCase):
    def test_target_inspector_reports_error_envelope(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "plugins"
            / "aquarium"
            / "skills"
            / "independent-review"
            / "scripts"
            / "inspect_review_target.py"
        )
        result = subprocess.run(
            [sys.executable, str(path), "--repository", "/no/such/repo", "--staged"],
            capture_output=True,
            text=True,
            check=False,
        )
        body = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            body["schema_version"], "aquarium-independent-review-target-error/v1"
        )
        self.assertIn("code", body["error"])

    def test_repository_state_reports_error_envelope_and_compare_round_trip(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "plugins"
            / "aquarium"
            / "skills"
            / "independent-review"
            / "scripts"
            / "inspect_repository_state.py"
        )
        missing = subprocess.run(
            [sys.executable, str(path), "--repository", "/no/such/repo", "--snapshot"],
            capture_output=True,
            text=True,
            check=False,
        )
        body = json.loads(missing.stdout)
        self.assertEqual(missing.returncode, 2)
        self.assertEqual(
            body["schema_version"],
            "aquarium-independent-review-repository-state-error/v1",
        )
        exclusive = subprocess.run(
            [
                sys.executable,
                str(path),
                "--repository",
                "/tmp",
                "--snapshot",
                "--compare",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        exclusive_body = json.loads(exclusive.stdout)
        self.assertEqual(exclusive.returncode, 2)
        self.assertEqual(
            exclusive_body["schema_version"],
            "aquarium-independent-review-repository-state-error/v1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            run_git(["git", "add", "tracked.txt"], root)
            run_git(["git", "commit", "-m", "init"], root)
            repository = str(root.resolve())
            snapshot = subprocess.run(
                [sys.executable, str(path), "--repository", repository, "--snapshot"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(snapshot.returncode, 0)
            compared = subprocess.run(
                [sys.executable, str(path), "--repository", repository, "--compare"],
                input=snapshot.stdout,
                capture_output=True,
                text=True,
                check=False,
            )
            compared_body = json.loads(compared.stdout)
            self.assertEqual(compared.returncode, 0)
            self.assertFalse(compared_body["drift"])

    def test_target_inspector_decodes_non_utf8_paths_and_missing_git(self) -> None:
        target = load_module(
            "skills/independent-review/scripts/inspect_review_target.py",
            "inspect_review_target",
        )
        decoded = target.decode_utf8(b"\xffpath", "git_path_invalid", "bad")
        self.assertEqual(decoded, "\\xffpath")
        json.dumps({"path": decoded}, ensure_ascii=False)
        with self.assertRaises(target.InspectionError) as error:
            target.decode_utf8(b"\xffpath", "git_status_invalid", "bad")
        self.assertEqual(error.exception.code, "git_status_invalid")
        path = (
            Path(__file__).resolve().parents[1]
            / "plugins"
            / "aquarium"
            / "skills"
            / "independent-review"
            / "scripts"
            / "inspect_review_target.py"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            init_repository(root)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            run_git(["git", "add", "tracked.txt"], root)
            empty_path = Path(tmp) / "empty-bin"
            empty_path.mkdir()
            missing = subprocess.run(
                [
                    sys.executable,
                    str(path),
                    "--repository",
                    str(root.resolve()),
                    "--staged",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={
                    **os.environ,
                    "PATH": str(empty_path),
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_NOSYSTEM": "1",
                },
            )
            body = json.loads(missing.stdout)
            self.assertEqual(missing.returncode, 2)
            self.assertEqual(
                body["schema_version"], "aquarium-independent-review-target-error/v1"
            )
            self.assertEqual(body["error"]["code"], "inspection_failed")


if __name__ == "__main__":
    unittest.main()
