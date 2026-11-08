"""List the texts that the other languages have to follow.

Compares the English source files with a git revision (default: HEAD) and the
other languages with the current English files:

- integration: custom_components/blood_glucose_monitor/translations/<lang>.json
- site: site/_data/i18n/<lang>.json

Prints, per file set, the English keys that were added, changed or removed
since the revision, and per language the keys that are missing or no longer
exist in English. Exit code 1 if any language needs work.

Usage: python scripts/i18n_diff.py [revision]
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SETS = {
    "integration": ROOT
    / "custom_components"
    / "blood_glucose_monitor"
    / "translations",
    "site": ROOT / "site" / "_data" / "i18n",
}


def flatten(value: Any, path: str = "") -> dict[str, Any]:
    """Return {key path: text} of a nested JSON value."""
    if isinstance(value, dict):
        items = value.items()
    elif isinstance(value, list):
        items = ((str(index), item) for index, item in enumerate(value))
    else:
        return {path: value}
    result: dict[str, Any] = {}
    for key, item in items:
        result.update(flatten(item, f"{path}/{key}" if path else str(key)))
    return result


def at_revision(path: Path, revision: str) -> dict[str, Any]:
    """Return the flattened English file at a git revision (empty if new)."""
    relative = path.relative_to(ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return flatten(json.loads(result.stdout)) if result.returncode == 0 else {}


def main() -> int:
    """Print what the translations have to follow."""
    revision = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    work = False
    for name, folder in SETS.items():
        english = flatten(json.loads((folder / "en.json").read_text("utf-8")))
        before = at_revision(folder / "en.json", revision)
        added = sorted(english.keys() - before.keys())
        changed = sorted(
            k for k in english.keys() & before.keys() if english[k] != before[k]
        )
        removed = sorted(before.keys() - english.keys())
        print(f"== {name} ({folder.relative_to(ROOT).as_posix()}) since {revision}")
        for label, keys in (
            ("added", added),
            ("changed", changed),
            ("removed", removed),
        ):
            for key in keys:
                print(f"  {label}: {key}")
        if added or changed or removed:
            work = True
        for path in sorted(folder.glob("*.json")):
            if path.stem == "en":
                continue
            other = flatten(json.loads(path.read_text("utf-8")))
            missing = sorted(english.keys() - other.keys())
            extra = sorted(other.keys() - english.keys())
            for key in missing:
                print(f"  {path.stem}: missing {key}")
            for key in extra:
                print(f"  {path.stem}: not in English {key}")
            work |= bool(missing or extra)
    return 1 if work else 0


if __name__ == "__main__":
    sys.exit(main())
