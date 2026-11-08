"""GMI and estimated HbA1c from long-term statistics (synthetic data)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.blood_glucose_monitor.const import DOMAIN

from .conftest import GLUCOSE_ENTITY
from .test_alarms import Scenario, options

GMI_SENSOR = "sensor.alex_gmi"
A1C_SENSOR = "sensor.alex_estimated_hba1c"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: Any, enable_custom_integrations: None
) -> None:
    """Start the recorder before Home Assistant in this module."""


async def import_hourly_means(
    hass: HomeAssistant, hours: int, mean: float, unit: str = "mg/dL"
) -> None:
    """Import hourly means of the glucose sensor for the last ``hours``."""
    end = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    async_import_statistics(
        hass,
        {
            "mean_type": StatisticMeanType.ARITHMETIC,
            "has_sum": False,
            "name": None,
            "source": "recorder",
            "statistic_id": GLUCOSE_ENTITY,
            "unit_class": "blood_glucose_concentration",
            "unit_of_measurement": unit,
        },
        [
            {
                "start": end - timedelta(hours=hour),
                "mean": mean,
                "min": mean,
                "max": mean,
            }
            for hour in range(1, hours + 1)
        ],
    )
    await async_wait_recording_done(hass)


async def setup(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, **overrides: Any
) -> Scenario:
    """Set up an entry and wait for the estimates."""
    scenario = Scenario(hass, freezer)
    await scenario.reading(110)
    await scenario.setup(options(**overrides))
    await hass.async_block_till_done(wait_background_tasks=True)
    return scenario


async def test_estimates_from_statistics(
    recorder_mock: Any, hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """80 of 90 days with a mean of 154 mg/dL: GMI and eHbA1c about 7 %."""
    freezer.move_to("2026-11-08 12:30:00+00:00")
    await import_hourly_means(hass, 80 * 24, 154)
    await setup(hass, freezer)

    gmi = hass.states.get(GMI_SENSOR)
    assert float(gmi.state) == pytest.approx(6.99, abs=0.01)
    assert gmi.attributes["mmol_mol"] == 53
    assert gmi.attributes["glucose_mean"] == 154
    assert gmi.attributes["unit"] == "mg/dL"
    assert gmi.attributes["coverage"] == pytest.approx(88.9, abs=0.1)
    assert gmi.attributes["period_days"] == 90
    assert gmi.attributes["end"] == "2026-11-08T12:00:00+00:00"
    assert float(hass.states.get(A1C_SENSOR).state) == pytest.approx(6.99, abs=0.01)


async def test_estimates_in_mmol(
    recorder_mock: Any, hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Statistics in mmol/L are converted; the period can be shorter."""
    freezer.move_to("2026-11-08 12:30:00+00:00")
    await import_hourly_means(hass, 14 * 24, 8.0, "mmol/L")
    await setup(hass, freezer, estimate={"period": 14})
    gmi = hass.states.get(GMI_SENSOR)
    # 8.0 mmol/L = 144.1 mg/dL
    assert float(gmi.state) == pytest.approx(3.31 + 0.02392 * 144.1, abs=0.01)
    assert gmi.attributes["coverage"] == 100


async def test_too_little_data_is_unknown(
    recorder_mock: Any, hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """15 of 90 days: unknown, the coverage says why."""
    freezer.move_to("2026-11-08 12:30:00+00:00")
    await import_hourly_means(hass, 15 * 24, 154)
    await setup(hass, freezer)
    gmi = hass.states.get(GMI_SENSOR)
    assert gmi.state == STATE_UNKNOWN
    assert gmi.attributes["coverage"] == pytest.approx(16.7, abs=0.1)
    assert gmi.attributes["mmol_mol"] is None


async def test_period_entity_wins(
    recorder_mock: Any, hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The period entity takes precedence and is followed."""
    freezer.move_to("2026-11-08 12:30:00+00:00")
    await import_hourly_means(hass, 15 * 24, 154)
    hass.states.async_set("input_number.period", "14")
    await setup(
        hass, freezer, estimate={"period": 90, "period_entity": "input_number.period"}
    )
    assert hass.states.get(GMI_SENSOR).attributes["period_days"] == 14
    assert hass.states.get(GMI_SENSOR).state != STATE_UNKNOWN

    hass.states.async_set("input_number.period", "60")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(GMI_SENSOR).attributes["period_days"] == 60
    assert hass.states.get(GMI_SENSOR).state == STATE_UNKNOWN


async def test_no_statistics_issue(
    recorder_mock: Any, hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A glucose sensor without long-term statistics gets a repair issue."""
    freezer.move_to("2026-11-08 12:30:00+00:00")
    scenario = await setup(hass, freezer)
    assert hass.states.get(GMI_SENSOR).state == STATE_UNKNOWN
    issue_id = f"no_statistics_{scenario.entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    # Statistics appear: the issue goes at the next hourly update.
    await import_hourly_means(hass, 90 * 24, 154)
    freezer.move_to("2026-11-08 13:15:00+00:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert hass.states.get(GMI_SENSOR).state != STATE_UNKNOWN


async def test_estimates_switched_off(
    recorder_mock: Any, hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Without a period there are no estimate sensors."""
    await setup(hass, freezer, estimate={})
    assert hass.states.get(GMI_SENSOR) is None
