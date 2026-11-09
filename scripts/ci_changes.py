"""Tell the workflows which parts of the repository a push or pull request changed.

Usage: ci_changes.py [--base REF] [--head REF] [--github-output FILE]

Writes one line ``<group>=true|false`` per group. Without a usable base (a new
branch, a scheduled or manual run) every group is ``true``: when in doubt,
everything runs.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

GROUPS = {
    # Hassfest and the Marketplace validation look at the integration only.
    "integration": (
        r"custom_components/",
        r"hacs\.json$",
        r"\.github/workflows/validate\.yaml$",
    ),
    # Lint and tests cover the integration, the scripts and the site data.
    "tests": (
        r"custom_components/",
        r"tests/",
        r"scripts/",
        r"site/",
        r"hacs\.json$",
        r"pyproject\.toml$",
        r"requirements_test\.txt$",
        r"\.github/workflows/tests\.yaml$",
    ),
    # The screenshots show the integration in the demo Home Assistant.
    "screenshots": (
        r"custom_components/",
        r"scripts/screenshots/",
        r"\.github/workflows/pages\.yaml$",
    ),
}


def changed_files(base: str, head: str) -> list[str] | None:
    """Return the files changed between base and head, None if unknown."""
    if not base or set(base) == {"0"}:
        return None
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return None
    return result.stdout.split()


def main() -> None:
    """Print and write the groups."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--github-output")
    args = parser.parse_args()

    files = changed_files(args.base, args.head)
    lines = []
    for group, patterns in GROUPS.items():
        hit = files is None or any(
            re.match(pattern, path) for path in files for pattern in patterns
        )
        lines.append(f"{group}={'true' if hit else 'false'}")
    print("\n".join(lines))
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as output:
            output.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
