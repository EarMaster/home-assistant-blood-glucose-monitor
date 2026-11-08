"""Check the documentation site: languages, texts and names from the integration."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
from typing import Any

import pytest

from custom_components.blood_glucose_monitor.const import DOCS_LANGUAGES

ROOT = Path(__file__).parent.parent
SITE = ROOT / "site"
TRANSLATIONS = ROOT / "custom_components" / "blood_glucose_monitor" / "translations"
LANGUAGES = [
    language["code"]
    for language in json.loads((SITE / "_data" / "languages.json").read_text("utf-8"))
]
PLACEHOLDER = re.compile(r"\{\w+\}|%\w+%")

spec = importlib.util.spec_from_file_location(
    "site_i18n", ROOT / "scripts" / "site_i18n.py"
)
assert spec is not None
assert spec.loader is not None
site_i18n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site_i18n)


def texts(language: str) -> dict[str, Any]:
    """Return the site texts of a language."""
    return json.loads((SITE / "_data" / "i18n" / f"{language}.json").read_text("utf-8"))


def shape(value: Any, path: str = "") -> dict[str, set[str]]:
    """Return every text path with its placeholders."""
    if isinstance(value, dict):
        return {
            key: found
            for name, item in value.items()
            for key, found in shape(item, f"{path}/{name}").items()
        }
    if isinstance(value, list):
        return {
            key: found
            for index, item in enumerate(value)
            for key, found in shape(item, f"{path}/{index}").items()
        }
    return {path: set(PLACEHOLDER.findall(str(value)))}


def test_languages() -> None:
    """The site has English and the documentation languages of the integration."""
    assert LANGUAGES[0] == "en"
    assert set(LANGUAGES) == {"en", *DOCS_LANGUAGES}
    for language in LANGUAGES:
        assert (TRANSLATIONS / f"{language}.json").exists()
        folder = SITE if language == "en" else SITE / language
        for page in ("index.html", "builder.html", "docs.html"):
            assert (folder / page).exists(), f"{language}/{page}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_same_texts_as_english(language: str) -> None:
    """Every language has the same texts and placeholders as English."""
    assert shape(texts(language)) == shape(texts("en"))


@pytest.mark.parametrize("language", LANGUAGES)
def test_names_from_integration_up_to_date(language: str) -> None:
    """site/_data/ha matches the integration (run scripts/site_i18n.py)."""
    path = SITE / "_data" / "ha" / f"{language}.json"
    assert path.read_text("utf-8") == site_i18n.render(language)
