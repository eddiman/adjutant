"""Tests for adjutant.core.version — semver parsing, bumping, and conventional commits."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from adjutant.core.version import (
    bump_version,
    infer_bump,
    main_commit_msg,
    parse_semver,
    read_version,
    validate_conventional_commit,
    write_version,
)

# ---------------------------------------------------------------------------
# parse_semver
# ---------------------------------------------------------------------------


class TestParseSemver:
    def test_basic(self) -> None:
        assert parse_semver("1.2.3") == (1, 2, 3, "")

    def test_with_v_prefix(self) -> None:
        assert parse_semver("v0.2.0") == (0, 2, 0, "")

    def test_with_prerelease(self) -> None:
        assert parse_semver("1.0.0-beta.1") == (1, 0, 0, "beta.1")

    def test_invalid(self) -> None:
        with pytest.raises(ValueError, match="Invalid semver"):
            parse_semver("not-a-version")

    def test_incomplete(self) -> None:
        with pytest.raises(ValueError, match="Invalid semver"):
            parse_semver("1.2")


# ---------------------------------------------------------------------------
# bump_version
# ---------------------------------------------------------------------------


class TestBumpVersion:
    def test_patch(self) -> None:
        assert bump_version("0.2.0", "patch") == "0.2.1"

    def test_minor(self) -> None:
        assert bump_version("0.2.3", "minor") == "0.3.0"

    def test_major(self) -> None:
        assert bump_version("0.2.3", "major") == "1.0.0"

    def test_major_resets_minor_and_patch(self) -> None:
        assert bump_version("1.5.9", "major") == "2.0.0"

    def test_minor_resets_patch(self) -> None:
        assert bump_version("1.5.9", "minor") == "1.6.0"

    def test_invalid_bump_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid bump type"):
            bump_version("1.0.0", "prerelease")


# ---------------------------------------------------------------------------
# validate_conventional_commit
# ---------------------------------------------------------------------------


class TestValidateConventionalCommit:
    def test_feat(self) -> None:
        typ, scope, breaking, desc = validate_conventional_commit("feat: add login")
        assert typ == "feat"
        assert scope is None
        assert breaking is False
        assert desc == "add login"

    def test_fix_with_scope(self) -> None:
        typ, scope, breaking, desc = validate_conventional_commit(
            "fix(auth): handle expired tokens"
        )
        assert typ == "fix"
        assert scope == "auth"
        assert breaking is False

    def test_breaking_bang(self) -> None:
        _, _, breaking, _ = validate_conventional_commit("chore!: drop Python 3.10")
        assert breaking is True

    def test_breaking_footer(self) -> None:
        msg = "feat: new API\n\nBREAKING CHANGE: removed old endpoints"
        _, _, breaking, _ = validate_conventional_commit(msg)
        assert breaking is True

    def test_all_valid_types(self) -> None:
        for typ in [
            "feat", "fix", "docs", "style", "refactor",
            "perf", "test", "build", "ci", "chore", "revert",
        ]:
            result = validate_conventional_commit(f"{typ}: description")
            assert result[0] == typ

    def test_invalid_type(self) -> None:
        with pytest.raises(ValueError, match="Conventional Commits"):
            validate_conventional_commit("yolo: did some stuff")

    def test_missing_colon_space(self) -> None:
        with pytest.raises(ValueError, match="Conventional Commits"):
            validate_conventional_commit("feat:no space")

    def test_empty_message(self) -> None:
        with pytest.raises(ValueError, match="Empty commit message"):
            validate_conventional_commit("")

    def test_comments_stripped(self) -> None:
        msg = "feat: add login\n# This is a git comment\n# Another comment"
        typ, _, _, desc = validate_conventional_commit(msg)
        assert typ == "feat"
        assert desc == "add login"

    def test_only_comments(self) -> None:
        with pytest.raises(ValueError, match="Empty commit message"):
            validate_conventional_commit("# all comments\n# nothing here")


# ---------------------------------------------------------------------------
# infer_bump
# ---------------------------------------------------------------------------


class TestInferBump:
    def test_feat_is_minor(self) -> None:
        assert infer_bump("feat", False) == "minor"

    def test_fix_is_patch(self) -> None:
        assert infer_bump("fix", False) == "patch"

    def test_breaking_is_major(self) -> None:
        assert infer_bump("feat", True) == "major"
        assert infer_bump("fix", True) == "major"

    def test_docs_defaults_to_patch(self) -> None:
        assert infer_bump("docs", False) == "patch"


# ---------------------------------------------------------------------------
# read_version / write_version
# ---------------------------------------------------------------------------


class TestReadWriteVersion:
    def test_round_trip(self, tmp_path: Path) -> None:
        (tmp_path / "VERSION").write_text("1.2.3\n")
        assert read_version(tmp_path) == "1.2.3"

        write_version("2.0.0", tmp_path)
        assert read_version(tmp_path) == "2.0.0"

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_version(tmp_path)


# ---------------------------------------------------------------------------
# main_commit_msg (hook entry point)
# ---------------------------------------------------------------------------


class TestMainCommitMsg:
    def test_valid_message(self, tmp_path: Path) -> None:
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("feat: add login\n")
        assert main_commit_msg([str(msg_file)]) == 0

    def test_invalid_message(self, tmp_path: Path) -> None:
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("did some stuff\n")
        assert main_commit_msg([str(msg_file)]) == 1

    def test_no_args(self) -> None:
        assert main_commit_msg([]) == 1
