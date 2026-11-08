#!/usr/bin/env python3
"""Check that the integration version only grows.

Without arguments (pushes to develop): the version in manifest.json must not
be lower than the newest release tag.

With --release (pull requests to main and pushes to main): the version must be
higher than every release tag and, unless it is a pre-release, have its own
section in CHANGELOG.md. --notes writes the release notes to a file and
--github-output writes "version", "tag", "prerelease" and "release" for later
workflow steps.

With --base REVISION, a change that touches nothing of the integration
(custom_components/, hacs.json) and keeps the version of the newest tag is a
docs update (README, documentation site, scripts, tests): it passes without a
new version and "release" is false, so no tag and no release are made.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "custom_components" / "blood_glucose_monitor" / "manifest.json"
CHANGELOG = ROOT / "CHANGELOG.md"
# Paths whose change makes a merge into main a release of the integration.
INTEGRATION_PATHS = ("custom_components/", "hacs.json")
PRERELEASE_NOTES = (
    "Pre-release for testing. Enable pre-releases for this repository in the "
    "Marketplace to install it."
)

_VERSION_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


@dataclass(frozen=True, slots=True)
class Version:
    """A semantic version (build metadata is not supported)."""

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> Version:
        """Parse "X.Y.Z" or "X.Y.Z-pre.1", with an optional leading "v"."""
        match = _VERSION_RE.match(text.removeprefix("v"))
        if match is None:
            raise ValueError(f"not a semantic version: {text!r}")
        major, minor, patch, pre = match.groups()
        return cls(
            int(major), int(minor), int(patch), tuple(pre.split(".")) if pre else ()
        )

    @property
    def is_prerelease(self) -> bool:
        """Return True for versions like 1.0.0-beta.1."""
        return bool(self.prerelease)

    def _key(self) -> tuple:
        # A release ranks above its pre-releases; numeric identifiers rank
        # below alphanumeric ones (semver 2.0, rule 11).
        pre = tuple(
            (0, int(part), "") if part.isdigit() else (1, 0, part)
            for part in self.prerelease
        )
        return (self.major, self.minor, self.patch, not self.prerelease, pre)

    def __lt__(self, other: Version) -> bool:
        return self._key() < other._key()

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{'.'.join(self.prerelease)}" if self.prerelease else base


def parse_tags(tags: list[str]) -> list[Version]:
    """Return the versions of all release tags (vX.Y.Z), ignoring others."""
    versions = []
    for tag in tags:
        if not tag.startswith("v"):
            continue
        try:
            versions.append(Version.parse(tag))
        except ValueError:
            continue
    return versions


def changelog_section(changelog: str, version: Version) -> str:
    """Return the body of the "## [X.Y.Z]" section, or "" if missing."""
    lines = changelog.splitlines()
    header = f"## [{version}]"
    for index, line in enumerate(lines):
        if line.startswith(header):
            body = []
            for following in lines[index + 1 :]:
                if following.startswith("## ["):
                    break
                body.append(following)
            return "\n".join(body).strip()
    return ""


def check_push(current: Version, tags: list[Version]) -> list[str]:
    """Return errors for a normal push."""
    if tags and current < (newest := max(tags)):
        return [f"manifest version {current} is lower than the newest tag v{newest}"]
    return []


def check_release(current: Version, tags: list[Version], changelog: str) -> list[str]:
    """Return errors for a release (pull request to main or push to main)."""
    errors = []
    if tags and not (newest := max(tags)) < current:
        errors.append(
            f"manifest version {current} must be higher than the newest tag "
            f"v{newest}: bump it in manifest.json and CHANGELOG.md"
        )
    if not current.is_prerelease and not changelog_section(changelog, current):
        errors.append(f"CHANGELOG.md has no section for [{current}]")
    return errors


def touches_integration(changed_files: list[str]) -> bool:
    """Return True if any changed file belongs to the integration."""
    return any(
        path == prefix or path.startswith(prefix)
        for path in changed_files
        for prefix in INTEGRATION_PATHS
    )


def is_docs_update(
    current: Version, tags: list[Version], changed_files: list[str]
) -> bool:
    """Return True for a change without integration files and a new version."""
    return (
        bool(tags) and current == max(tags) and not touches_integration(changed_files)
    )


def release_notes(changelog: str, version: Version) -> str:
    """Return the release notes for a version."""
    return changelog_section(changelog, version) or PRERELEASE_NOTES


def _git_tags() -> list[str]:
    result = subprocess.run(
        ["git", "tag", "--list", "v*"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split()


def _changed_files(base: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base, "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split()


def main(argv: list[str] | None = None) -> int:
    """Run the checks and print the result."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--release", action="store_true", help="check a release to main"
    )
    parser.add_argument("--notes", type=Path, help="write the release notes here")
    parser.add_argument(
        "--github-output", type=Path, help="append version and tag to this file"
    )
    parser.add_argument(
        "--base", help="revision to compare with; allows docs updates without release"
    )
    args = parser.parse_args(argv)

    current = Version.parse(json.loads(MANIFEST.read_text("utf-8"))["version"])
    tags = parse_tags(_git_tags())
    changelog = CHANGELOG.read_text("utf-8")

    docs_update = (
        args.release
        and args.base is not None
        and is_docs_update(current, tags, _changed_files(args.base))
    )
    if docs_update:
        errors = []
    elif args.release:
        errors = check_release(current, tags, changelog)
    else:
        errors = check_push(current, tags)
    for error in errors:
        print(f"::error::{error}")
    if errors:
        return 1
    if args.notes:
        args.notes.write_text(release_notes(changelog, current) + "\n", "utf-8")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"version={current}\ntag=v{current}\n")
            output.write(f"prerelease={str(current.is_prerelease).lower()}\n")
            output.write(f"release={str(not docs_update).lower()}\n")
    if docs_update:
        print(f"Docs update: no integration changes, version stays {current}")
        return 0
    print(f"Version {current} OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
