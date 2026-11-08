"""Set up a demo Home Assistant with synthetic data and take screenshots.

Runs against a fresh Home Assistant on http://localhost:8123 with
``configuration.yaml`` of this folder and the integration installed (see
``.github/workflows/pages.yaml``): onboarding with a throwaway account,
synthetic glucose data of "Alex", the integration with alarms, reminders and
a report, an automation like the one of the automation builder, then
screenshots of the UI. No real health data.

Usage: python scripts/screenshots/demo.py --out site/img
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import secrets
import sys
from typing import Any

import aiohttp
from playwright.async_api import Page, async_playwright

URL = "http://localhost:8123"
CLIENT_ID = f"{URL}/"
DOMAIN = "blood_glucose_monitor"
AUTOMATION_ID = "blood_glucose_notifications_alex"
MG_DL = "mg/dL"


def iso(moment: datetime) -> str:
    """Return a UTC timestamp in ISO 8601."""
    return moment.astimezone(UTC).isoformat()


class HomeAssistant:
    """Minimal REST client of the demo instance."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize."""
        self.session = session
        self.tokens: dict[str, Any] = {}

    async def wait_until_up(self) -> None:
        """Wait until the onboarding API answers (at most 10 minutes)."""
        async with asyncio.timeout(600):
            while True:
                try:
                    async with self.session.get(f"{URL}/api/onboarding") as response:
                        if response.status == 200:
                            return
                except aiohttp.ClientError:
                    pass
                await asyncio.sleep(3)

    async def onboard(self) -> None:
        """Create the throwaway owner account and finish the onboarding."""
        async with self.session.post(
            f"{URL}/api/onboarding/users",
            json={
                "client_id": CLIENT_ID,
                "name": "Alex",
                "username": "alex",
                "password": secrets.token_urlsafe(24),
                "language": "en",
            },
        ) as response:
            response.raise_for_status()
            code = (await response.json())["auth_code"]
        async with self.session.post(
            f"{URL}/auth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": CLIENT_ID,
            },
        ) as response:
            response.raise_for_status()
            self.tokens = await response.json()
        await self.post("/api/onboarding/core_config", {})
        await self.post("/api/onboarding/analytics", {})
        await self.post(
            "/api/onboarding/integration",
            {"client_id": CLIENT_ID, "redirect_uri": f"{URL}/?auth_callback=1"},
        )

    @property
    def headers(self) -> dict[str, str]:
        """Return the authorization header."""
        return {"Authorization": f"Bearer {self.tokens['access_token']}"}

    async def post(self, path: str, data: dict[str, Any]) -> Any:
        """POST JSON and return the decoded answer."""
        async with self.session.post(
            f"{URL}{path}", json=data, headers=self.headers
        ) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"POST {path}: {response.status} {text}")
            try:
                return json.loads(text)
            except ValueError:
                return text

    async def state(self, entity_id: str, state: str, **attributes: Any) -> None:
        """Set a synthetic state."""
        await self.post(
            f"/api/states/{entity_id}", {"state": state, "attributes": attributes}
        )

    async def call(self, domain: str, service: str, **data: Any) -> None:
        """Call an action."""
        await self.post(f"/api/services/{domain}/{service}", data)

    async def template(self, template: str) -> str:
        """Render a template."""
        return str(await self.post("/api/template", {"template": template}))

    async def flow(self, kind: str, handler: str, *steps: dict[str, Any]) -> Any:
        """Run a config flow ("flow") or options flow ("options/flow")."""
        base = f"/api/config/config_entries/{kind}"
        result = await self.post(base, {"handler": handler})
        for data in steps:
            if result["type"] not in ("form", "menu"):
                raise RuntimeError(f"Unexpected flow result: {result}")
            result = await self.post(f"{base}/{result['flow_id']}", data)
            if result.get("errors"):
                raise RuntimeError(f"Flow errors: {result['errors']}")
        if result["type"] != "create_entry":
            raise RuntimeError(f"Flow not finished: {result}")
        return result

    async def options(self, entry_id: str, step: str, data: dict[str, Any]) -> None:
        """Set the options of one menu item."""
        await self.flow("options/flow", entry_id, {"next_step_id": step}, data)


async def reading(ha: HomeAssistant, glucose: float, trend: str, change: float) -> None:
    """Report a synthetic reading now."""
    now = datetime.now(UTC)
    await ha.state(
        "sensor.alex_glucose",
        str(glucose),
        unit_of_measurement=MG_DL,
        state_class="measurement",
        friendly_name="Alex glucose",
        icon="mdi:diabetes",
    )
    await ha.state("sensor.alex_glucose_trend", trend, friendly_name="Alex trend")
    await ha.state(
        "sensor.alex_glucose_change",
        str(change),
        unit_of_measurement=MG_DL,
        friendly_name="Alex change",
    )
    await ha.state(
        "sensor.alex_glucose_reading_time",
        iso(now),
        device_class="timestamp",
        friendly_name="Alex reading time",
    )


async def set_up(ha: HomeAssistant) -> dict[str, str]:
    """Create the synthetic data, the entry and the automation."""
    await reading(ha, 104, "steady", -1)
    for key, value, name in (
        ("urgent_low", 55, "Alex urgent low threshold"),
        ("low", 70, "Alex low threshold"),
        ("high", 180, "Alex high threshold"),
        ("urgent_high", 250, "Alex urgent high threshold"),
    ):
        await ha.state(
            f"sensor.alex_{key}_threshold",
            str(value),
            unit_of_measurement=MG_DL,
            friendly_name=name,
        )
    await ha.state(
        "sensor.alex_phone_battery",
        "35",
        unit_of_measurement="%",
        device_class="battery",
        friendly_name="Alex phone battery",
    )
    await ha.state(
        "sensor.alex_phone_battery_state",
        "discharging",
        friendly_name="Alex phone battery state",
    )
    await ha.call("input_boolean", "turn_on", entity_id="input_boolean.alex_night")

    result = await ha.flow(
        "flow",
        DOMAIN,
        {"disclaimer_accepted": True},
        {
            "name": "Alex",
            "glucose_entity": "sensor.alex_glucose",
            "person_entity": "person.alex",
        },
        {
            "trend_entity": "sensor.alex_glucose_trend",
            "change_entity": "sensor.alex_glucose_change",
            "reading_time_entity": "sensor.alex_glucose_reading_time",
        },
    )
    entry_id = result["result"]["entry_id"]

    def alarm(**settings: Any) -> dict[str, Any]:
        return {"only_when_home": False, **settings}

    for key, offset, delay, repeat, snooze in (
        ("urgent_low", 5, 0, 5, 10),
        ("low", 10, 0, 5, 15),
        ("high", 10, 30, 30, 120),
        ("urgent_high", 10, 15, 15, 60),
    ):
        await ha.options(
            entry_id,
            key,
            alarm(
                threshold_entity=f"sensor.alex_{key}_threshold",
                clear_offset=offset,
                delay=delay,
                repeat=repeat,
                snooze=snooze,
            ),
        )
    for key in ("rapid_fall", "rapid_rise"):
        await ha.options(
            entry_id,
            key,
            alarm(
                detection="trend",
                trend_level="quickly",
                delay=0,
                repeat=0,
                snooze=30,
            ),
        )
    await ha.options(
        entry_id,
        "charging",
        alarm(
            battery_entity="sensor.alex_phone_battery",
            charging_entity="sensor.alex_phone_battery_state",
            reminder_time="20:00:00",
            battery_limit=75,
            repeat=0,
            snooze=30,
        ),
    )
    days = {"hours": 0, "minutes": 0, "seconds": 0}
    await ha.options(
        entry_id,
        "cannula_change",
        alarm(
            wear_duration={**days, "days": 3},
            warning={"days": 0, "hours": 12, "minutes": 0, "seconds": 0},
            repeat=0,
            snooze=60,
        ),
    )
    await ha.options(
        entry_id,
        "sensor_change",
        alarm(wear_duration={**days, "days": 10}, repeat=0, snooze=60),
    )
    await ha.options(
        entry_id,
        "report",
        {"report_entity": "input_boolean.alex_night", "only_when_home": False},
    )

    # Like the automation builder: low alarm started/ended, here as
    # persistent notification of Home Assistant.
    await ha.post(
        f"/api/config/automation/config/{AUTOMATION_ID}",
        {
            "alias": "Blood glucose notifications: Alex",
            "description": "Created with the Blood Glucose Monitor automation builder.",
            "mode": "queued",
            "triggers": [
                {
                    "trigger": "event.received",
                    "target": {
                        "entity_id": ["event.alex_low_alarm", "event.alex_report"]
                    },
                    "options": {"event_type": ["low_alert", "report"]},
                }
            ],
            "actions": [
                {
                    "action": "notify.persistent_notification",
                    "data": {
                        "title": "{{ trigger.to_state.attributes.title }}",
                        "message": "{{ trigger.to_state.attributes.message }}",
                    },
                }
            ],
        },
    )
    await asyncio.sleep(3)

    # Changes: the cannula is due (reminder active), the sensor in two days.
    now = datetime.now(UTC)
    await ha.call(
        DOMAIN,
        "record_change",
        config_entry_id=entry_id,
        change="cannula_change",
        time=(now - timedelta(days=3, hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    await ha.call(
        DOMAIN,
        "record_change",
        config_entry_id=entry_id,
        change="sensor_change",
        time=(now - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    # Falling glucose: a low alarm, then the end of the report period.
    for glucose, change in ((92, -6), (81, -6), (64, -9)):
        await asyncio.sleep(2)
        await reading(ha, glucose, "falling", change)
    await asyncio.sleep(2)
    await ha.call("input_boolean", "turn_off", entity_id="input_boolean.alex_night")
    await asyncio.sleep(5)

    triggered = await ha.template(
        "{{ state_attr('automation.blood_glucose_notifications_alex', 'last_triggered') }}"
    )
    print(f"Automation last triggered: {triggered}")
    device_id = await ha.template("{{ device_id('sensor.alex_status') }}")
    return {"entry_id": entry_id, "device_id": device_id.strip()}


async def log_in(page: Page, ha: HomeAssistant) -> None:
    """Store the tokens like the frontend does after a login."""
    tokens = ha.tokens
    await page.goto(f"{URL}/onboarding.html")
    await page.evaluate(
        """([tokens, url, clientId]) => {
            localStorage.setItem("hassTokens", JSON.stringify({
                ...tokens,
                hassUrl: url,
                clientId: clientId,
                expires: Date.now() + tokens.expires_in * 1000,
            }));
            localStorage.setItem("selectedTheme", JSON.stringify({theme: "default", dark: false}));
        }""",
        [tokens, URL, CLIENT_ID],
    )
    # The onboarding page redirects to the start page once it sees the
    # tokens; wait for that, so it does not interrupt the next navigation.
    await page.goto(f"{URL}/")
    await page.get_by_text("Settings").first.wait_for()
    await settle(page, 2)


async def settle(page: Page, seconds: float = 4) -> None:
    """Give the frontend time to render."""
    await page.wait_for_load_state("load")
    await page.wait_for_timeout(seconds * 1000)


async def shoot(page: Page, out: Path, name: str) -> None:
    """Save a screenshot."""
    await page.screenshot(path=out / f"{name}.png")
    print(f"Saved {name}.png")


async def screenshots(
    ha: HomeAssistant, ids: dict[str, str], out: Path, debug: Path
) -> int:
    """Take the screenshots; return the number of failures.

    The page at the time of a failure is saved to ``debug`` (never published).
    """
    failures = 0
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 1280, "height": 860},
            device_scale_factor=1.5,
            locale="en-US",
            timezone_id="Europe/Berlin",
            color_scheme="light",
        )
        page = await context.new_page()
        await log_in(page, ha)

        async def device() -> None:
            # Taller, so the sensors and events of the device are visible.
            await page.set_viewport_size({"width": 1280, "height": 1900})
            await page.goto(f"{URL}/config/devices/device/{ids['device_id']}")
            await page.get_by_text("Low alarm").first.wait_for()
            await settle(page)
            await shoot(page, out, "device")
            await page.set_viewport_size({"width": 1280, "height": 860})

        async def status() -> None:
            await page.goto(f"{URL}/?more-info-entity-id=sensor.alex_status")
            await page.get_by_text("History").first.wait_for()
            await settle(page)
            await shoot(page, out, "status")
            await page.keyboard.press("Escape")

        async def automation() -> None:
            await page.goto(f"{URL}/config/automation/edit/{AUTOMATION_ID}")
            await page.get_by_text("Event received").first.wait_for()
            await settle(page)
            await shoot(page, out, "automation")

        async def options() -> None:
            await page.goto(f"{URL}/config/integrations/integration/{DOMAIN}")
            await settle(page)
            await page.get_by_role("button", name="Configure").first.click()
            await page.get_by_text("Open the automation builder").first.wait_for()
            await settle(page, 2)
            await shoot(page, out, "options")
            await page.keyboard.press("Escape")

        async def setup() -> None:
            await page.goto(f"{URL}/config/integrations/dashboard/add?domain={DOMAIN}")
            # Confirm "Do you want to set up …?", then the notice step opens.
            await page.get_by_role("button", name="OK").first.click()
            await page.get_by_text("not a medical device").first.wait_for()
            await settle(page, 2)
            await shoot(page, out, "setup")
            await page.keyboard.press("Escape")

        async def notifications() -> None:
            await page.goto(f"{URL}/config/dashboard")
            await settle(page)
            await page.get_by_text("Notifications", exact=True).first.click()
            await settle(page, 2)
            await shoot(page, out, "notifications")
            await page.keyboard.press("Escape")

        for take in (device, status, automation, options, setup, notifications):
            try:
                await take()
            except Exception as err:
                failures += 1
                print(f"Screenshot {take.__name__} failed: {err}", file=sys.stderr)
                await page.screenshot(path=debug / f"{take.__name__}.png")
        await browser.close()
    return failures


async def main(out: Path, debug: Path) -> int:
    """Set up the demo and take the screenshots."""
    async with aiohttp.ClientSession() as session:
        ha = HomeAssistant(session)
        await ha.wait_until_up()
        await ha.onboard()
        ids = await set_up(ha)
        print(f"Demo ready: {ids}")
        failures = await screenshots(ha, ids, out, debug)
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("site/img"))
    parser.add_argument("--debug", type=Path, default=Path("screenshots-debug"))
    args = parser.parse_args()
    for folder in (args.out, args.debug):
        folder.mkdir(parents=True, exist_ok=True)
    sys.exit(asyncio.run(main(args.out, args.debug)))
