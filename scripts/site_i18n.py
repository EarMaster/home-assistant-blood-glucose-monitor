"""Copy the names Home Assistant shows into the documentation site.

The builder and the documentation name alarms, menu items and event types
exactly as the integration does. This script takes them from the
integration's translations (``translations/<lang>.json``) and writes
``site/_data/ha/<lang>.json`` for every language of the site
(``site/_data/languages.json``). ``tests/test_site.py`` checks that the files
are up to date.

Usage: python scripts/site_i18n.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS = ROOT / "custom_components" / "blood_glucose_monitor" / "translations"
SITE_DATA = ROOT / "site" / "_data"


def site_languages() -> list[str]:
    """Return the language codes of the site."""
    languages = json.loads((SITE_DATA / "languages.json").read_text("utf-8"))
    return [language["code"] for language in languages]


def ha_texts(language: str) -> dict[str, object]:
    """Return the names of one language as the integration shows them."""
    texts = json.loads((TRANSLATIONS / f"{language}.json").read_text("utf-8"))
    events = texts["entity"]["event"]
    names = {
        key.removesuffix("_alarm"): value["name"]
        for key, value in events.items()
        if key.endswith("_alarm")
    }
    names["report"] = events["report"]["name"]
    event_types: dict[str, str] = {}
    for value in events.values():
        event_types.update(value["state_attributes"]["event_type"]["state"])
    return {
        "names": names,
        "menu": texts["options"]["step"]["init"]["menu_options"],
        "event_types": event_types,
        "pause": texts["entity"]["switch"]["pause"]["name"],
    }


def render(language: str) -> str:
    """Return the file content for one language."""
    return json.dumps(ha_texts(language), ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    """Write the files of all site languages."""
    target = SITE_DATA / "ha"
    target.mkdir(exist_ok=True)
    for language in site_languages():
        (target / f"{language}.json").write_text(
            render(language), encoding="utf-8", newline="\n"
        )
        print(f"Wrote site/_data/ha/{language}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
