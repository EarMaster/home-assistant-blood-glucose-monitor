"""Report statistics from the recorder history (synthetic data)."""

from __future__ import annotations

from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import async_capture_events
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from .test_alarms import ALARM_EVENT, Scenario, alarm, options
from .test_charging_and_reports import LAST_REPORT, REPORT_ENTITY, local


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: Any, enable_custom_integrations: None
) -> None:
    """Start the recorder before Home Assistant in this module."""


async def test_report_statistics(
    recorder_mock: Any, hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """With the recorder, the report has the statistics of the period."""

    events = async_capture_events(hass, ALARM_EVENT)
    freezer.move_to(local(22))
    hass.states.async_set(
        "input_number.low_threshold", "70", {"unit_of_measurement": "mg/dL"}
    )
    hass.states.async_set(
        "input_number.high_threshold", "180", {"unit_of_measurement": "mg/dL"}
    )
    hass.states.async_set(REPORT_ENTITY, "off")
    scenario = Scenario(hass, freezer)
    await scenario.reading(100)
    await scenario.setup(
        options(
            report={"report_entity": REPORT_ENTITY},
            high=alarm(threshold_entity="input_number.high_threshold", snooze=60),
        )
    )
    hass.states.async_set(REPORT_ENTITY, "on")
    await hass.async_block_till_done()
    await scenario.wait(30, 100)
    await scenario.wait(30, 200)
    await async_wait_recording_done(hass)
    hass.states.async_set(REPORT_ENTITY, "off")
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    await hass.async_block_till_done()

    report = next(e.data for e in events if e.data["type"] == "report")
    assert report["glucose_min"] == 100
    assert report["glucose_max"] == 200
    assert report["above"] is not None
    assert report["in_range"] is not None
    assert report["message"].startswith("22:00–23:00: ")
    assert hass.states.get(LAST_REPORT).state == str(report["in_range"])
