"""Tests for the release version check script."""

from __future__ import annotations

import importlib.util
import itertools
from pathlib import Path
import sys

import pytest

_PATH = Path(__file__).parent.parent / "scripts" / "check_version.py"
_SPEC = importlib.util.spec_from_file_location("check_version", _PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
check_version = importlib.util.module_from_spec(_SPEC)
sys.modules["check_version"] = check_version
_SPEC.loader.exec_module(check_version)

Version = check_version.Version

CHANGELOG = """# Changelog

## [Unreleased]

## [1.2.0] - 2026-11-07

### Added
- Something new

## [1.1.0] - 2026-10-01

### Fixed
- Something old
"""


def v(text: str) -> Version:
    """Parse a version."""
    return Version.parse(text)


@pytest.mark.parametrize(
    "ordered",
    [
        # Example order from the semver 2.0 specification.
        [
            "1.0.0-alpha",
            "1.0.0-alpha.1",
            "1.0.0-alpha.beta",
            "1.0.0-beta",
            "1.0.0-beta.2",
            "1.0.0-beta.11",
            "1.0.0-rc.1",
            "1.0.0",
        ],
        ["0.9.9", "0.10.0", "1.0.0", "1.0.1", "1.1.0", "2.0.0"],
    ],
)
def test_version_order(ordered: list[str]) -> None:
    """Versions sort like semver 2.0 says."""
    versions = [v(text) for text in ordered]
    for lower, higher in itertools.pairwise(versions):
        assert lower < higher
        assert not higher < lower
    assert sorted([*versions[1:], versions[0]]) == versions


@pytest.mark.parametrize("text", ["1.0", "01.0.0", "1.0.0+build", "x1.0.0", ""])
def test_invalid_versions(text: str) -> None:
    """Invalid versions are rejected."""
    with pytest.raises(ValueError, match="not a semantic version"):
        v(text)


def test_parse_and_format() -> None:
    """Parsing accepts a leading v and round-trips."""
    assert v("v1.2.3") == Version(1, 2, 3)
    assert str(v("1.2.3-beta.1")) == "1.2.3-beta.1"
    assert v("1.2.3-beta.1").is_prerelease
    assert not v("1.2.3").is_prerelease


def test_parse_tags_ignores_other_tags() -> None:
    """Only vX.Y.Z tags count."""
    assert check_version.parse_tags(["v1.0.0", "1.1.0", "vnext", "v1.2.0-rc.1"]) == [
        v("1.0.0"),
        v("1.2.0-rc.1"),
    ]


def test_changelog_section() -> None:
    """The section body of a version is returned without the header."""
    assert check_version.changelog_section(CHANGELOG, v("1.2.0")) == (
        "### Added\n- Something new"
    )
    assert check_version.changelog_section(CHANGELOG, v("1.1.0")) == (
        "### Fixed\n- Something old"
    )
    assert check_version.changelog_section(CHANGELOG, v("1.3.0")) == ""
    assert check_version.changelog_section(CHANGELOG, v("1.2.0-beta.1")) == ""


@pytest.mark.parametrize(
    ("current", "tags", "ok"),
    [
        ("0.1.0", [], True),
        ("1.2.0", ["1.1.0", "1.2.0"], True),
        ("1.3.0", ["1.2.0"], True),
        ("1.1.0", ["1.2.0"], False),
    ],
)
def test_check_push(current: str, tags: list[str], ok: bool) -> None:
    """Pushes only fail when the version went backwards."""
    errors = check_version.check_push(v(current), [v(tag) for tag in tags])
    assert (not errors) is ok


@pytest.mark.parametrize(
    ("current", "tags", "expected"),
    [
        ("1.2.0", [], []),
        ("1.2.0", ["1.1.0"], []),
        ("1.2.0", ["1.1.0", "1.2.0"], ["higher than the newest tag v1.2.0"]),
        ("1.2.0", ["1.3.0"], ["higher than the newest tag v1.3.0"]),
        ("1.3.0", ["1.2.0"], ["no section for [1.3.0]"]),
        ("1.3.0-beta.1", ["1.2.0"], []),
        ("1.2.0", ["1.2.0-rc.1"], []),
    ],
)
def test_check_release(current: str, tags: list[str], expected: list[str]) -> None:
    """Releases need a higher version and a CHANGELOG section."""
    errors = check_version.check_release(
        v(current), [v(tag) for tag in tags], CHANGELOG
    )
    assert len(errors) == len(expected)
    for error, part in zip(errors, expected, strict=True):
        assert part in error


def test_release_notes() -> None:
    """Pre-releases without a section get a generic note."""
    assert check_version.release_notes(CHANGELOG, v("1.2.0")).startswith("### Added")
    assert "Pre-release" in check_version.release_notes(CHANGELOG, v("1.3.0-rc.1"))


def test_main(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """main() checks the repository files and writes notes and outputs."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"version": "1.2.0"}', "utf-8")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, "utf-8")
    monkeypatch.setattr(check_version, "MANIFEST", manifest)
    monkeypatch.setattr(check_version, "CHANGELOG", changelog)
    monkeypatch.setattr(check_version, "_git_tags", lambda: ["v1.1.0"])

    notes = tmp_path / "notes.md"
    output = tmp_path / "output"
    assert (
        check_version.main(
            ["--release", "--notes", str(notes), "--github-output", str(output)]
        )
        == 0
    )
    assert notes.read_text("utf-8") == "### Added\n- Something new\n"
    assert output.read_text("utf-8") == (
        "version=1.2.0\ntag=v1.2.0\nprerelease=false\nrelease=true\n"
    )

    monkeypatch.setattr(check_version, "_git_tags", lambda: ["v1.2.0"])
    assert check_version.main([]) == 0
    assert check_version.main(["--release"]) == 1
    assert "::error::" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        (["README.md", "site/index.html", "tests/test_site.py"], False),
        (["custom_components/blood_glucose_monitor/monitor.py"], True),
        (["hacs.json"], True),
        ([], False),
    ],
)
def test_touches_integration(files: list[str], expected: bool) -> None:
    """Only files of the integration make a merge a release."""
    assert check_version.touches_integration(files) is expected


def test_docs_update(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Without integration changes the version may stay: no release."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"version": "1.2.0"}', "utf-8")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, "utf-8")
    monkeypatch.setattr(check_version, "MANIFEST", manifest)
    monkeypatch.setattr(check_version, "CHANGELOG", changelog)
    monkeypatch.setattr(check_version, "_git_tags", lambda: ["v1.2.0"])
    monkeypatch.setattr(check_version, "_changed_files", lambda base: ["site/x.html"])

    output = tmp_path / "output"
    args = ["--release", "--base", "main", "--github-output", str(output)]
    assert check_version.main(args) == 0
    assert output.read_text("utf-8").endswith("release=false\n")
    assert "Docs update" in capsys.readouterr().out

    # Integration changed without a new version: a release is required.
    monkeypatch.setattr(
        check_version,
        "_changed_files",
        lambda base: ["custom_components/blood_glucose_monitor/const.py"],
    )
    assert check_version.main(["--release", "--base", "main"]) == 1
    # Without --base every merge into main is a release.
    assert check_version.main(["--release"]) == 1
