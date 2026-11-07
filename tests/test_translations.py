"""Check that all translations are complete and match the flow forms."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import pytest

from custom_components.blood_glucose_monitor import config_flow

TRANSLATIONS = (
    Path(__file__).parent.parent
    / "custom_components"
    / "blood_glucose_monitor"
    / "translations"
)
LANGUAGES = sorted(path.stem for path in TRANSLATIONS.glob("*.json"))

FORMS = {
    ("config", "user"): config_flow.DISCLAIMER_SCHEMA,
    ("config", "person"): config_flow.PERSON_SCHEMA,
    ("config", "already_monitored"): config_flow.ALREADY_MONITORED_SCHEMA,
    ("config", "sources"): config_flow.SOURCES_SCHEMA,
    ("options", "init"): config_flow.OPTIONS_SCHEMA,
    ("options", "already_monitored"): config_flow.ALREADY_MONITORED_SCHEMA,
}
FLOW_ERRORS = {
    "config": {"disclaimer_required", "name_required", "unsupported_unit"},
    "options": {"unsupported_unit"},
}


def load(language: str) -> dict[str, Any]:
    """Load a translation file."""
    return json.loads((TRANSLATIONS / f"{language}.json").read_text("utf-8"))


def flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten nested translations to dotted keys."""
    result: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            result |= flatten(value, f"{path}.")
        else:
            result[path] = value
    return result


def test_english_and_german_exist() -> None:
    """English is the base language, German is provided."""
    assert {"en", "de"} <= set(LANGUAGES)


@pytest.mark.parametrize("language", LANGUAGES)
def test_same_keys_and_placeholders_as_english(language: str) -> None:
    """Every language has exactly the English keys and placeholders."""
    english = flatten(load("en"))
    other = flatten(load(language))
    assert other.keys() == english.keys()
    for key, text in english.items():
        assert set(re.findall(r"\{(\w+)\}", other[key])) == set(
            re.findall(r"\{(\w+)\}", text)
        ), key


@pytest.mark.parametrize(("flow", "step"), list(FORMS))
def test_every_field_is_translated(flow: str, step: str) -> None:
    """Every step has a title and all form fields have a label."""
    translation = load("en")[flow]["step"][step]
    assert translation["title"].strip()
    fields = {str(key) for key in FORMS[flow, step].schema}
    assert set(translation.get("data", {})) == fields


def test_every_step_is_tested() -> None:
    """All translated steps are covered by FORMS."""
    english = load("en")
    steps = {(flow, step) for flow in FLOW_ERRORS for step in english[flow]["step"]}
    assert steps == set(FORMS)


@pytest.mark.parametrize("flow", list(FLOW_ERRORS))
def test_every_error_is_translated(flow: str) -> None:
    """All errors the flows can show have a text."""
    assert set(load("en")[flow]["error"]) == FLOW_ERRORS[flow]


@pytest.mark.parametrize("language", LANGUAGES)
def test_disclaimer_present(language: str) -> None:
    """The setup starts with the notice that this is not a medical device."""
    step = load(language)["config"]["step"]["user"]
    assert step["description"].strip()
    assert step["data"]["disclaimer_accepted"].strip()
