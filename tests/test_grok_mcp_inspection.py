"""Grok MCP inspection reads TOML configuration and does not start servers."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def load_inspect_tools():
    path = (
        Path(__file__).resolve().parents[1]
        / "plugins"
        / "aquarium"
        / "skills"
        / "dev-setup"
        / "scripts"
        / "inspect_tools.py"
    )
    spec = importlib.util.spec_from_file_location("inspect_tools", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


class GrokMcpInspectionTests(unittest.TestCase):
    def test_missing_user_config_is_missing_not_degraded(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            repository = Path(tmp) / "repo"
            repository.mkdir()
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                result = inspect_tools.grok_mcp_entries("mulgae", repository)
            self.assertIsNone(result["invalid_config"])
            self.assertIsNone(result["scopes"]["user"])
            self.assertIsNone(result["scopes"]["project"])

    def test_skill_roots_include_grok_agents_and_cursor(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            env = {key: value for key, value in os.environ.items() if key != "GROK_HOME"}
            with patch.object(inspect_tools.Path, "home", return_value=home):
                with patch.dict(os.environ, env, clear=True):
                    roots = [str(path) for path in inspect_tools.skill_roots()]
            self.assertIn(str(home / ".grok/skills"), roots)
            self.assertIn(str(home / ".agents/skills"), roots)
            self.assertNotIn(str(home / ".claude/skills"), roots)
            self.assertIn(str(home / ".cursor/skills"), roots)

    def test_skill_roots_use_grok_home_instead_of_default_home(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            relocated = Path(tmp) / "relocated"
            home.mkdir()
            relocated.mkdir()
            with patch.object(inspect_tools.Path, "home", return_value=home):
                with patch.dict(os.environ, {"GROK_HOME": str(relocated)}, clear=False):
                    roots = [str(path) for path in inspect_tools.skill_roots()]
            self.assertIn(str(relocated / "skills"), roots)
            self.assertNotIn(str(home / ".grok/skills"), roots)
            self.assertIn(str(home / ".agents/skills"), roots)

    def test_project_config_overrides_user_and_classifies_configured(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            repository = Path(tmp) / "repo"
            (repository / ".grok").mkdir(parents=True)
            mulgae = Path(tmp) / "bin" / "mulgae"
            mulgae.parent.mkdir()
            mulgae.write_text("#!/bin/sh\n", encoding="utf-8")
            mulgae.chmod(0o755)
            (home / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                'args = ["mcp"]\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            (repository / ".grok" / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                'command = "/other/binary"\n'
                "enabled = false\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, str(mulgae))
            self.assertEqual(scopes["effective_scope"], "local")
            self.assertEqual(scopes["local"]["status"], "degraded")
            self.assertEqual(scopes["global"]["status"], "configured")

    def test_invalid_toml_is_degraded(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            (home / "config.toml").write_text("this is not toml {", encoding="utf-8")
            repository = Path(tmp) / "repo"
            repository.mkdir()
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, None)
            self.assertEqual(scopes["status"], "degraded")
            self.assertEqual(scopes["reason"], "user_config_invalid_toml")

    def test_enabled_false_is_degraded(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            mulgae = Path(tmp) / "mulgae"
            mulgae.write_text("#!/bin/sh\n", encoding="utf-8")
            mulgae.chmod(0o755)
            (home / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                'args = ["mcp"]\n'
                "enabled = false\n"
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            repository = Path(tmp) / "repo"
            repository.mkdir()
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, str(mulgae))
            self.assertEqual(scopes["global"]["status"], "degraded")
            self.assertEqual(scopes["global"]["reason"], "registration_disabled")

    def test_url_entry_is_not_stdio(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            (home / "config.toml").write_text(
                '[mcp_servers.mulgae]\nurl = "https://example.invalid"\n',
                encoding="utf-8",
            )
            repository = Path(tmp) / "repo"
            repository.mkdir()
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, None)
            self.assertEqual(scopes["global"]["status"], "degraded")
            self.assertEqual(scopes["global"]["reason"], "registration_not_stdio")

    def test_wrong_args_are_not_configured(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            mulgae = Path(tmp) / "mulgae"
            mulgae.write_text("#!/bin/sh\n", encoding="utf-8")
            mulgae.chmod(0o755)
            (home / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                "args = []\n"
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            repository = Path(tmp) / "repo"
            repository.mkdir()
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, str(mulgae))
            self.assertEqual(scopes["global"]["status"], "degraded")
            self.assertEqual(scopes["global"]["reason"], "registration_mismatch")

    def test_global_cwd_is_not_configured(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            mulgae = Path(tmp) / "mulgae"
            mulgae.write_text("#!/bin/sh\n", encoding="utf-8")
            mulgae.chmod(0o755)
            (home / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                'args = ["mcp"]\n'
                'cwd = "/tmp"\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            repository = Path(tmp) / "repo"
            repository.mkdir()
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, str(mulgae))
            self.assertEqual(scopes["global"]["status"], "degraded")
            self.assertEqual(scopes["global"]["reason"], "registration_mismatch")

    def test_unselected_binary_is_not_configured(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            mulgae = Path(tmp) / "mulgae"
            mulgae.write_text("#!/bin/sh\n", encoding="utf-8")
            mulgae.chmod(0o755)
            (home / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                'args = ["mcp"]\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            repository = Path(tmp) / "repo"
            repository.mkdir()
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, None)
            self.assertEqual(scopes["global"]["status"], "degraded")
            self.assertEqual(scopes["global"]["reason"], "binary_unselected")

    def test_wrong_binary_is_not_configured(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            selected = Path(tmp) / "mulgae"
            other = Path(tmp) / "other"
            selected.write_text("#!/bin/sh\n", encoding="utf-8")
            other.write_text("#!/bin/sh\n", encoding="utf-8")
            selected.chmod(0o755)
            other.chmod(0o755)
            (home / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{other}"\n'
                'args = ["mcp"]\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            repository = Path(tmp) / "repo"
            repository.mkdir()
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, str(selected))
            self.assertEqual(scopes["global"]["status"], "degraded")
            self.assertEqual(scopes["global"]["reason"], "registration_mismatch")

    def test_global_project_root_args_are_not_configured(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            mulgae = Path(tmp) / "mulgae"
            mulgae.write_text("#!/bin/sh\n", encoding="utf-8")
            mulgae.chmod(0o755)
            repository = Path(tmp) / "repo"
            repository.mkdir()
            (home / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                f'args = ["mcp", "--project-root", "{repository.resolve()}"]\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, str(mulgae))
            self.assertEqual(scopes["global"]["status"], "degraded")
            self.assertEqual(scopes["global"]["reason"], "registration_mismatch")

    def test_mulgae_local_configured(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            repository = Path(tmp) / "repo"
            (repository / ".grok").mkdir(parents=True)
            mulgae = Path(tmp) / "mulgae"
            mulgae.write_text("#!/bin/sh\n", encoding="utf-8")
            mulgae.chmod(0o755)
            (repository / ".grok" / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                f'args = ["mcp", "--project-root", "{repository.resolve()}"]\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, str(mulgae))
            self.assertEqual(scopes["effective_scope"], "local")
            self.assertEqual(scopes["local"]["status"], "configured")

    def test_gaori_local_configured(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            repository = Path(tmp) / "repo"
            (repository / ".grok").mkdir(parents=True)
            gaori = Path(tmp) / "gaori"
            gaori.write_text("#!/bin/sh\n", encoding="utf-8")
            gaori.chmod(0o755)
            (repository / ".grok" / "config.toml").write_text(
                "[mcp_servers.gaori]\n"
                f'command = "{gaori}"\n'
                f'args = ["--repo", "{repository.resolve()}", "mcp"]\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 3601\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("gaori", repository, str(gaori))
            self.assertEqual(scopes["effective_scope"], "local")
            self.assertEqual(scopes["local"]["status"], "configured")

    def test_timeout_below_minimum_is_mismatch(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            mulgae = Path(tmp) / "mulgae"
            mulgae.write_text("#!/bin/sh\n", encoding="utf-8")
            mulgae.chmod(0o755)
            (home / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                'args = ["mcp"]\n'
                "startup_timeout_sec = 29\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            repository = Path(tmp) / "repo"
            repository.mkdir()
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, str(mulgae))
            self.assertEqual(scopes["global"]["status"], "degraded")
            self.assertEqual(scopes["global"]["reason"], "registration_mismatch")

    def test_disabled_mcp_servers_marks_registration_disabled(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            repository = Path(tmp) / "repo"
            (repository / ".grok").mkdir(parents=True)
            mulgae = Path(tmp) / "mulgae"
            mulgae.write_text("#!/bin/sh\n", encoding="utf-8")
            mulgae.chmod(0o755)
            (home / "config.toml").write_text(
                'disabled_mcp_servers = ["mulgae"]\n'
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                'args = ["mcp"]\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            (repository / ".grok" / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                f'args = ["mcp", "--project-root", "{repository.resolve()}"]\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, str(mulgae))
            self.assertEqual(scopes["local"]["reason"], "registration_disabled")
            self.assertEqual(scopes["global"]["reason"], "registration_disabled")

    def test_symlinked_user_config_is_unverifiable(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            real = Path(tmp) / "real.toml"
            real.write_text("[mcp_servers.mulgae]\ncommand = \"/bin/true\"\n", encoding="utf-8")
            (home / "config.toml").symlink_to(real)
            repository = Path(tmp) / "repo"
            repository.mkdir()
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, None)
            self.assertEqual(scopes["status"], "unverifiable")
            self.assertEqual(scopes["reason"], "user_config_symlinked")

    def test_ouroboros_isolated_launcher_requires_runtime_env(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            uvx = Path(tmp) / "uvx"
            uvx.write_text("#!/bin/sh\n", encoding="utf-8")
            uvx.chmod(0o755)
            args = [
                "--isolated",
                "--python",
                ">=3.12",
                "--from",
                "ouroboros-ai[mcp]",
                "ouroboros",
                "mcp",
                "serve",
            ]
            matching = {
                "command": str(uvx),
                "args": args,
                "env": {"OUROBOROS_AGENT_RUNTIME": "grok"},
            }
            envless = {"command": str(uvx), "args": args}
            with patch.object(inspect_tools.shutil, "which", return_value=str(uvx)):
                self.assertTrue(inspect_tools.ouroboros_isolated_launcher_matches(matching))
                self.assertFalse(inspect_tools.ouroboros_isolated_launcher_matches(envless))

    def test_ouroboros_mcp_registration_isolated_and_direct(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            repository = Path(tmp) / "repo"
            repository.mkdir()
            uvx = Path(tmp) / "uvx"
            uvx.write_text("#!/bin/sh\n", encoding="utf-8")
            uvx.chmod(0o755)
            ooo = Path(tmp) / "ooo"
            ooo.write_text("#!/bin/sh\n", encoding="utf-8")
            ooo.chmod(0o755)
            isolated_args = [
                "--isolated",
                "--python",
                ">=3.12",
                "--from",
                "ouroboros-ai[mcp]",
                "ouroboros",
                "mcp",
                "serve",
            ]
            (home / "config.toml").write_text(
                "[mcp_servers.ouroboros]\n"
                f'command = "{uvx}"\n'
                f"args = {json.dumps(isolated_args)}\n"
                "startup_timeout_sec = 60\n"
                "\n"
                "[mcp_servers.ouroboros.env]\n"
                'OUROBOROS_AGENT_RUNTIME = "grok"\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                with patch.object(inspect_tools.shutil, "which", return_value=str(uvx)):
                    isolated = inspect_tools.ouroboros_mcp_registration(repository, str(ooo))
            self.assertEqual(isolated["status"], "configured")
            self.assertEqual(isolated["launcher"], "isolated")
            (home / "config.toml").write_text(
                "[mcp_servers.ouroboros]\n"
                f'command = "{ooo}"\n'
                'args = ["mcp", "serve"]\n'
                "startup_timeout_sec = 60\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                direct = inspect_tools.ouroboros_mcp_registration(repository, str(ooo))
            self.assertEqual(direct["status"], "configured")
            self.assertEqual(direct["launcher"], "direct")

    def test_ouroboros_isolated_runtime_suffix_and_pinned_package(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            uvx = Path(tmp) / "uvx"
            uvx.write_text("#!/bin/sh\n", encoding="utf-8")
            uvx.chmod(0o755)
            suffix_args = [
                "--isolated",
                "--python",
                ">=3.12",
                "--from",
                "ouroboros-ai[mcp]",
                "ouroboros",
                "mcp",
                "serve",
                "--runtime",
                "grok",
            ]
            pinned_args = [
                "--isolated",
                "--python",
                ">=3.12",
                "--from",
                "ouroboros-ai[mcp]==0.51.14",
                "ouroboros",
                "mcp",
                "serve",
            ]
            with patch.object(inspect_tools.shutil, "which", return_value=str(uvx)):
                self.assertTrue(
                    inspect_tools.ouroboros_isolated_launcher_matches(
                        {"command": str(uvx), "args": suffix_args}
                    )
                )
                self.assertTrue(
                    inspect_tools.ouroboros_isolated_launcher_matches(
                        {
                            "command": str(uvx),
                            "args": pinned_args,
                            "env": {"OUROBOROS_AGENT_RUNTIME": "grok"},
                        }
                    )
                )


    def test_user_config_falls_back_to_home_grok_without_grok_home(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            (home / ".grok").mkdir(parents=True)
            mulgae = Path(tmp) / "mulgae"
            mulgae.write_text("#!/bin/sh\n", encoding="utf-8")
            mulgae.chmod(0o755)
            (home / ".grok" / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                'args = ["mcp"]\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            repository = Path(tmp) / "repo"
            repository.mkdir()
            env = {key: value for key, value in os.environ.items() if key != "GROK_HOME"}
            with patch.object(inspect_tools.Path, "home", return_value=home):
                with patch.dict(os.environ, env, clear=True):
                    result = inspect_tools.grok_mcp_entries("mulgae", repository)
            self.assertIsNotNone(result["scopes"]["user"])

    def test_ouroboros_registration_negatives(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            repository = Path(tmp) / "repo"
            repository.mkdir()
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                missing = inspect_tools.ouroboros_mcp_registration(repository, None)
            self.assertEqual(missing["status"], "missing")
            (home / "config.toml").write_text(
                '[mcp_servers.ouroboros]\nurl = "https://example.invalid"\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                not_stdio = inspect_tools.ouroboros_mcp_registration(repository, None)
            self.assertEqual(not_stdio["status"], "degraded")
            self.assertEqual(not_stdio["reason"], "registration_not_stdio")
            (home / "config.toml").write_text(
                "[mcp_servers.ouroboros]\n"
                'command = "/ooo"\n'
                'args = ["mcp", "serve"]\n'
                "enabled = false\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                disabled = inspect_tools.ouroboros_mcp_registration(repository, None)
            self.assertEqual(disabled["status"], "degraded")
            self.assertEqual(disabled["reason"], "registration_disabled")

    def test_ouroboros_host_skills_missing_without_install(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            env = {key: value for key, value in os.environ.items() if key != "GROK_HOME"}
            with patch.object(inspect_tools.Path, "home", return_value=home):
                with patch.dict(os.environ, env, clear=True):
                    result = inspect_tools.inspect_ouroboros_host_skills()
            self.assertEqual(result["status"], "missing")

    def test_inspect_ouroboros_isolated_skips_doctor(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            repository = Path(tmp) / "repo"
            repository.mkdir()
            ooo = Path(tmp) / "ooo"
            ooo.write_text("#!/bin/sh\necho ouroboros 0.51.14\n", encoding="utf-8")
            ooo.chmod(0o755)
            uvx = Path(tmp) / "uvx"
            uvx.write_text("#!/bin/sh\n", encoding="utf-8")
            uvx.chmod(0o755)
            isolated_args = [
                "--isolated",
                "--python",
                ">=3.12",
                "--from",
                "ouroboros-ai[mcp]",
                "ouroboros",
                "mcp",
                "serve",
            ]
            (home / "config.toml").write_text(
                "[mcp_servers.ouroboros]\n"
                f'command = "{uvx}"\n'
                f"args = {json.dumps(isolated_args)}\n"
                "startup_timeout_sec = 60\n"
                "\n"
                "[mcp_servers.ouroboros.env]\n"
                'OUROBOROS_AGENT_RUNTIME = "grok"\n',
                encoding="utf-8",
            )

            def which(command: str) -> str | None:
                if command == "ooo":
                    return str(ooo)
                if command == "uvx":
                    return str(uvx)
                return None

            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                with patch.object(inspect_tools.shutil, "which", side_effect=which):
                    tool = inspect_tools.inspect_ouroboros(repository, 2.0)
            self.assertEqual(tool["mcp_registration"]["launcher"], "isolated")
            self.assertEqual(tool["mcp_runtime"]["reason"], "isolated_launcher_contract")

    def test_project_invalid_toml_preserves_global_registration(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            repository = Path(tmp) / "repo"
            (repository / ".grok").mkdir(parents=True)
            mulgae = Path(tmp) / "mulgae"
            mulgae.write_text("#!/bin/sh\n", encoding="utf-8")
            mulgae.chmod(0o755)
            (home / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                'args = ["mcp"]\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            (repository / ".grok" / "config.toml").write_text(
                "this is not toml {", encoding="utf-8"
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, str(mulgae))
            self.assertEqual(scopes["global"]["status"], "configured")
            self.assertEqual(scopes["local"]["status"], "degraded")
            self.assertEqual(scopes["local"]["reason"], "project_config_invalid_toml")
            self.assertEqual(scopes["effective_scope"], "global")
            self.assertEqual(scopes["status"], "configured")

    def test_ouroboros_isolated_rejects_codex_runtime_and_unsupported_pin(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            uvx = Path(tmp) / "uvx"
            uvx.write_text("#!/bin/sh\n", encoding="utf-8")
            uvx.chmod(0o755)
            args = [
                "--isolated",
                "--python",
                ">=3.12",
                "--from",
                "ouroboros-ai[mcp]",
                "ouroboros",
                "mcp",
                "serve",
            ]
            with patch.object(inspect_tools.shutil, "which", return_value=str(uvx)):
                self.assertFalse(
                    inspect_tools.ouroboros_isolated_launcher_matches(
                        {
                            "command": str(uvx),
                            "args": args,
                            "env": {"OUROBOROS_AGENT_RUNTIME": "codex"},
                        }
                    )
                )
                self.assertFalse(
                    inspect_tools.ouroboros_isolated_launcher_matches(
                        {
                            "command": str(uvx),
                            "args": [
                                "--isolated",
                                "--python",
                                ">=3.12",
                                "--from",
                                "ouroboros-ai[mcp]==0.50.0",
                                "ouroboros",
                                "mcp",
                                "serve",
                            ],
                            "env": {"OUROBOROS_AGENT_RUNTIME": "grok"},
                        }
                    )
                )

    def test_inspect_omits_dolgorae_when_binaries_missing(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            repository = Path(tmp) / "repo"
            repository.mkdir()
            subprocess.run(
                ["git", "init"],
                cwd=repository,
                check=True,
                capture_output=True,
                env={
                    **os.environ,
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_NOSYSTEM": "1",
                },
            )
            home = Path(tmp) / "home"
            home.mkdir()
            env = {key: value for key, value in os.environ.items() if key != "GROK_HOME"}
            env["HOME"] = str(home)
            env["GIT_CONFIG_GLOBAL"] = os.devnull
            env["GIT_CONFIG_NOSYSTEM"] = "1"
            with patch.object(inspect_tools.Path, "home", return_value=home):
                with patch.dict(os.environ, env, clear=True):
                    with patch.object(inspect_tools.shutil, "which", return_value=None):
                        result = inspect_tools.inspect(
                            str(repository),
                            2.0,
                            include_podway=True,
                        )
            self.assertEqual(result["schema_version"], inspect_tools.SCHEMA_VERSION)
            self.assertNotIn("dolgorae", result["tools"])
            self.assertNotIn("ouroboros", result["tools"])
            self.assertIn("podway", result["tools"])
            self.assertIn("mulgae", result["tools"])
            self.assertIn("gaori", result["tools"])
            self.assertEqual(
                result["trusted_global_skills"]["humanizer"]["canonical_path"],
                str(home / ".agents/skills/humanizer"),
            )
            self.assertEqual(
                result["trusted_global_skills"]["humanize-korean"]["canonical_path"],
                str(home / ".agents/skills/humanize-korean"),
            )

    def test_scope_status_non_dict_unresolvable_and_gaori_global(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            repository = Path(tmp) / "repo"
            repository.mkdir()
            mismatch = inspect_tools.grok_mcp_scope_status(
                "not-a-table", None, repository, "global", "mulgae"
            )
            self.assertEqual(mismatch["reason"], "registration_mismatch")
            unresolvable = inspect_tools.grok_mcp_scope_status(
                {"command": str(Path(tmp) / "missing-binary"), "args": ["mcp"]},
                None,
                repository,
                "global",
                "mulgae",
            )
            self.assertEqual(unresolvable["reason"], "command_unresolvable")
            home = Path(tmp) / "grok-home"
            home.mkdir()
            gaori = Path(tmp) / "gaori"
            gaori.write_text("#!/bin/sh\n", encoding="utf-8")
            gaori.chmod(0o755)
            (home / "config.toml").write_text(
                "[mcp_servers.gaori]\n"
                f'command = "{gaori}"\n'
                'args = ["mcp"]\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 3601\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("gaori", repository, str(gaori))
            self.assertEqual(scopes["global"]["status"], "configured")
            self.assertEqual(scopes["effective_scope"], "global")

    def test_project_config_symlinked_and_empty_scopes(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            repository = Path(tmp) / "repo"
            repository.mkdir()
            real_dir = Path(tmp) / "real-grok"
            real_dir.mkdir()
            (real_dir / "config.toml").write_text(
                "[mcp_servers.mulgae]\ncommand = \"/bin/true\"\n", encoding="utf-8"
            )
            (repository / ".grok").symlink_to(real_dir)
            mulgae = Path(tmp) / "mulgae"
            mulgae.write_text("#!/bin/sh\n", encoding="utf-8")
            mulgae.chmod(0o755)
            (home / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                'args = ["mcp"]\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                linked = inspect_tools.grok_mcp_scopes("mulgae", repository, str(mulgae))
            self.assertEqual(linked["reason"], "project_configuration_symlinked")
            self.assertEqual(linked["global"]["status"], "configured")

    def test_project_config_file_symlink_is_unverifiable(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            repository = Path(tmp) / "repo"
            (repository / ".grok").mkdir(parents=True)
            real = Path(tmp) / "real.toml"
            real.write_text("[mcp_servers.mulgae]\ncommand = \"/bin/true\"\n", encoding="utf-8")
            (repository / ".grok" / "config.toml").symlink_to(real)
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                scopes = inspect_tools.grok_mcp_scopes("mulgae", repository, None)
            self.assertEqual(scopes["status"], "unverifiable")
            self.assertEqual(scopes["reason"], "project_config_symlinked")
            empty_home = Path(tmp) / "empty-home"
            empty_home.mkdir()
            empty_repo = Path(tmp) / "empty-repo"
            empty_repo.mkdir()
            with patch.dict(os.environ, {"GROK_HOME": str(empty_home)}, clear=False):
                empty = inspect_tools.grok_mcp_scopes("mulgae", empty_repo, None)
            self.assertEqual(empty["effective_scope"], "none")
            self.assertEqual(empty["status"], "missing")

    def test_ouroboros_invalid_toml_and_mismatch(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            repository = Path(tmp) / "repo"
            repository.mkdir()
            (home / "config.toml").write_text("this is not toml {", encoding="utf-8")
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                invalid = inspect_tools.ouroboros_mcp_registration(repository, None)
            self.assertEqual(invalid["status"], "degraded")
            self.assertEqual(invalid["probe"]["reason"], "registration_invalid_toml")
            (home / "config.toml").write_text(
                "[mcp_servers.ouroboros]\n"
                'command = "/ooo"\n'
                'args = ["not", "mcp"]\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                mismatch = inspect_tools.ouroboros_mcp_registration(repository, None)
            self.assertEqual(mismatch["status"], "degraded")
            self.assertEqual(mismatch["reason"], "registration_mismatch")

    def test_ouroboros_host_skills_configured_and_mixed(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            skills = home / ".agents" / "skills"
            for name in ("interview", "pm", "seed", "qa"):
                directory = skills / name
                directory.mkdir(parents=True)
                (directory / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: test\n---\n\n# {name}\n",
                    encoding="utf-8",
                )
            env = {key: value for key, value in os.environ.items() if key != "GROK_HOME"}
            with patch.object(inspect_tools.Path, "home", return_value=home):
                with patch.dict(os.environ, env, clear=True):
                    configured = inspect_tools.inspect_ouroboros_host_skills()
            self.assertEqual(configured["status"], "configured")
            (skills / "qa" / "SKILL.md").unlink()
            (skills / "qa").rmdir()
            with patch.object(inspect_tools.Path, "home", return_value=home):
                with patch.dict(os.environ, env, clear=True):
                    mixed = inspect_tools.inspect_ouroboros_host_skills()
            self.assertEqual(mixed["status"], "degraded")

    def test_writing_skill_root_and_im_not_ai(self) -> None:
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            env = {key: value for key, value in os.environ.items() if key != "GROK_HOME"}
            with patch.object(inspect_tools.Path, "home", return_value=home):
                with patch.dict(os.environ, env, clear=True):
                    self.assertEqual(
                        inspect_tools.effective_writing_skill_root(),
                        home / ".agents" / "skills",
                    )
                    result = inspect_tools.inspect_im_not_ai()
                    humanizer = inspect_tools.inspect_humanizer()
            self.assertEqual(result["status"], "missing")
            self.assertEqual(
                result["expected_target"],
                str(home / ".agents" / "skills" / "humanize-korean"),
            )
            self.assertEqual(
                humanizer["expected_target"],
                str(home / ".agents" / "skills" / "humanizer"),
            )
            self.assertNotIn(".codex/skills/humanize-korean", result["expected_target"])

    def test_main_rejects_nonpositive_timeout(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "plugins"
            / "aquarium"
            / "skills"
            / "dev-setup"
            / "scripts"
            / "inspect_tools.py"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(path), "--repository", tmp, "--timeout-seconds", "-1"],
                capture_output=True,
                text=True,
                check=False,
            )
        body = json.loads(result.stdout)
        self.assertEqual(body["error"]["code"], "invalid_arguments")
        self.assertNotEqual(result.returncode, 0)


def load_inspect_global_tools():
    directory = (
        Path(__file__).resolve().parents[1]
        / "plugins"
        / "aquarium"
        / "skills"
        / "dev-setup-global"
        / "scripts"
    )
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    path = directory / "inspect_global_tools.py"
    spec = importlib.util.spec_from_file_location("inspect_global_tools", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


def load_inspect_ouroboros():
    directory = (
        Path(__file__).resolve().parents[1]
        / "plugins"
        / "aquarium"
        / "skills"
        / "dev-setup-global"
        / "scripts"
    )
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    path = directory / "inspect_ouroboros.py"
    spec = importlib.util.spec_from_file_location("inspect_ouroboros", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


class GlobalInspectorHostTests(unittest.TestCase):
    def test_global_mcp_reads_user_grok_config(self) -> None:
        inspect_global_tools = load_inspect_global_tools()
        inspect_tools = load_inspect_tools()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok-home"
            home.mkdir()
            repository = Path(tmp) / "repo"
            repository.mkdir()
            mulgae = Path(tmp) / "mulgae"
            mulgae.write_text("#!/bin/sh\n", encoding="utf-8")
            mulgae.chmod(0o755)
            (home / "config.toml").write_text(
                "[mcp_servers.mulgae]\n"
                f'command = "{mulgae}"\n'
                'args = ["mcp"]\n'
                "startup_timeout_sec = 30\n"
                "tool_timeout_sec = 7501\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GROK_HOME": str(home)}, clear=False):
                result = inspect_global_tools.inspect_global_mcp(
                    inspect_tools,
                    "mulgae",
                    str(mulgae),
                    repository,
                    3.0,
                )
            self.assertEqual(result["status"], "configured")
            self.assertTrue(result["arguments_match"])

    def test_discover_homes_uses_grok_home(self) -> None:
        inspect_ouroboros = load_inspect_ouroboros()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            grok_home = Path(tmp) / "relocated-grok"
            home.mkdir()
            grok_home.mkdir()
            env = {key: value for key, value in os.environ.items() if key != "GROK_HOME"}
            env["GROK_HOME"] = str(grok_home)
            with patch.object(inspect_ouroboros.Path, "home", return_value=home):
                with patch.dict(os.environ, env, clear=True):
                    current, homes, failures = inspect_ouroboros.discover_homes()
            self.assertEqual(current, grok_home.resolve())
            self.assertIn(grok_home.resolve(), homes)
            self.assertNotIn(home / ".codex", homes)
            extra = home / ".grok-other"
            extra.mkdir()
            (extra / "config.toml").write_text("", encoding="utf-8")
            with patch.object(inspect_ouroboros.Path, "home", return_value=home):
                with patch.dict(os.environ, env, clear=True):
                    _, homes_without_extra, _ = inspect_ouroboros.discover_homes()
            self.assertNotIn(extra.resolve(), homes_without_extra)
            self.assertEqual(failures, {})


if __name__ == "__main__":
    unittest.main()
