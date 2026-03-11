"""Tests for src/adjutant/setup/install.py"""

from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from adjutant.setup.install import (
    check_prerequisites,
    download_and_extract,
    print_banner,
    prompt_install_dir,
    resolve_version,
)


class TestPrintBanner:
    def test_prints_to_stderr(self, capsys) -> None:
        print_banner()
        out = capsys.readouterr().err
        assert "Adjutant" in out


class TestCheckPrerequisites:
    def test_passes_when_all_present(self, capsys) -> None:
        with patch("shutil.which", return_value="/usr/bin/cmd"):
            # Should not raise or exit
            check_prerequisites()

    def test_dies_when_opencode_missing(self) -> None:
        def which_side(cmd):
            if cmd == "opencode":
                return None
            return "/usr/bin/cmd"

        with patch("shutil.which", side_effect=which_side):
            with pytest.raises(SystemExit):
                check_prerequisites()

    def test_dies_when_python_too_old(self) -> None:
        # sys.version_info is a named tuple — create a compatible tuple subclass
        VerInfo = collections.namedtuple(
            "version_info", ["major", "minor", "micro", "releaselevel", "serial"]
        )
        old_ver = VerInfo(3, 7, 0, "final", 0)
        with patch("sys.version_info", new=old_ver):
            with patch("shutil.which", return_value="/usr/bin/cmd"):
                with pytest.raises(SystemExit):
                    check_prerequisites()


class TestPromptInstallDir:
    def test_uses_env_var_when_set(self, tmp_path: Path) -> None:
        target = str(tmp_path / "myinstall")
        with patch.dict(os.environ, {"ADJUTANT_INSTALL_DIR": target}):
            result = prompt_install_dir()
        assert result == Path(target).expanduser()

    def test_prompts_user_when_no_env_var(self, tmp_path: Path) -> None:
        target = str(tmp_path / "myinstall")
        with patch.dict(os.environ, {}, clear=True):
            # Ensure no ADJUTANT_INSTALL_DIR
            env = {k: v for k, v in os.environ.items() if k != "ADJUTANT_INSTALL_DIR"}
            with patch.dict(os.environ, env, clear=True):
                with patch("builtins.input", return_value=target):
                    result = prompt_install_dir()
        assert result == Path(target)

    def test_exits_when_already_installed(self, tmp_path: Path) -> None:
        (tmp_path / ".adjutant-root").touch()
        with patch.dict(os.environ, {"ADJUTANT_INSTALL_DIR": str(tmp_path)}):
            with pytest.raises(SystemExit):
                prompt_install_dir()

    def test_dies_when_path_is_file(self, tmp_path: Path) -> None:
        f = tmp_path / "afile"
        f.write_text("x")
        with patch.dict(os.environ, {"ADJUTANT_INSTALL_DIR": str(f)}):
            with pytest.raises(SystemExit):
                prompt_install_dir()


class TestResolveVersion:
    def test_returns_env_var_version(self) -> None:
        with patch.dict(os.environ, {"ADJUTANT_VERSION": "v1.2.3"}):
            assert resolve_version() == "v1.2.3"

    def test_fetches_from_github(self) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"tag_name": "v2.0.0"}).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        env = {
            k: v for k, v in os.environ.items() if k not in ("ADJUTANT_VERSION", "ADJUTANT_REPO")
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("adjutant.setup.install.urlopen", return_value=mock_response):
                version = resolve_version()
        assert version == "v2.0.0"

    def test_dies_on_empty_tag(self) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"tag_name": ""}).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        env = {
            k: v for k, v in os.environ.items() if k not in ("ADJUTANT_VERSION", "ADJUTANT_REPO")
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("adjutant.setup.install.urlopen", return_value=mock_response):
                with pytest.raises(SystemExit):
                    resolve_version()


class TestDownloadAndExtract:
    def test_creates_install_dir(self, tmp_path: Path) -> None:
        import tarfile, io

        install_dir = tmp_path / "adj_install"
        # Create a minimal tarball in memory
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            content = b"hello"
            info = tarfile.TarInfo(name="adjutant-v1/file.txt")
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
        buf.seek(0)
        tarball_bytes = buf.getvalue()

        # Patch urlopen to return tarball bytes
        mock_resp = MagicMock()
        chunks = [tarball_bytes, b""]
        mock_resp.read.side_effect = chunks
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("adjutant.setup.install.urlopen", return_value=mock_resp):
            download_and_extract("v1", install_dir)

        assert install_dir.is_dir()
        assert (install_dir / "file.txt").is_file()
