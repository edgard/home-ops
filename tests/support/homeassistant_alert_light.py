"""Exercise repository HA scripts in the installed HA runtime, never production state.

Run with package.yaml and macro.jinja paths inside the matching Home Assistant image.
Only the Gatus HTTP and physical-light boundaries are replaced. All helpers,
scripts, templates, event dispatch, and restart storage use real HA components.
"""

import asyncio
import copy
import json
import logging
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from aiohttp import web
from homeassistant import bootstrap, config_entries, loader
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import async_load_custom_templates
from homeassistant.setup import async_setup_component

TARGET = "light.office_office_mood_light"
BASE = {"brightness": 77, "color_mode": "color_temp", "color_temp_kelvin": 2202}


class Scenarios:
    def __init__(self, package, macro, folder):
        self.package = package
        self.macro = macro
        self.folder = folder
        self.endpoints = package["script"]["gatus_alert_light_worker"]["variables"][
            "endpoints"
        ]
        self.names = list(self.endpoints)
        self.rows = {}
        self.api_status = 200
        self.physical_state = "on"
        self.physical_attrs = dict(BASE)
        self.hass = None

    def history(self, name, successes):
        now = datetime.now(UTC)
        self.rows[name] = [
            {
                "success": success,
                "timestamp": (
                    now - timedelta(seconds=60 * (len(successes) - i - 1))
                ).isoformat(),
            }
            for i, success in enumerate(successes)
        ]

    async def api(self, request):
        return web.json_response(
            [
                {
                    "name": name.rsplit("/", 1)[-1],
                    "group": name.rsplit("/", 1)[0] if "/" in name else "",
                    "results": results,
                }
                for name, results in self.rows.items()
            ],
            status=self.api_status,
        )

    def set_light(self, state, attrs=None):
        self.physical_state = state
        if attrs is not None:
            self.physical_attrs = dict(attrs)
        if self.hass:
            self.hass.states.async_set(TARGET, state, self.physical_attrs)

    async def light(self, call):
        data = call.data
        target = data.get("entity_id")
        assert target in (TARGET, [TARGET]), target
        assert self.physical_state != "unavailable", (
            "Unsafe command to unavailable bulb"
        )
        if call.service == "turn_off":
            self.set_light("off")
            return
        attrs = dict(self.physical_attrs)
        attrs["brightness"] = data.get(
            "brightness",
            round(
                data.get("brightness_pct", attrs.get("brightness", 77) / 255 * 100)
                * 255
                / 100
            ),
        )
        if "rgb_color" in data:
            assert list(data["rgb_color"]) == [255, 0, 0]
            attrs = {
                "brightness": attrs["brightness"],
                "color_mode": "hs",
                "hs_color": [0, 100],
            }
        for mode, key in [
            ("color_temp", "color_temp_kelvin"),
            ("hs", "hs_color"),
            ("xy", "xy_color"),
        ]:
            if key in data:
                attrs = {
                    "brightness": attrs["brightness"],
                    "color_mode": mode,
                    key: data[key],
                }
        self.set_light("on", attrs)

    async def start(self, url):
        path = Path(self.folder, "custom_templates")
        path.mkdir(exist_ok=True)
        (path / "gatus_alert_light.jinja").write_text(self.macro)
        self.hass = hass = HomeAssistant(self.folder)
        await hass.config.async_set_time_zone("UTC")
        hass.config.skip_pip = True
        loader.async_setup(hass)
        config = copy.deepcopy(self.package)
        config["rest_command"]["gatus_alert_light_status"]["url"] = url
        hass.config_entries = config_entries.ConfigEntries(hass, config)
        assert await bootstrap.async_load_base_functionality(hass)
        assert await async_setup_component(hass, "homeassistant", {})
        await async_load_custom_templates(hass)
        for domain in (
            "network",
            "input_boolean",
            "input_text",
            "rest_command",
            "script",
            "automation",
        ):
            assert await async_setup_component(hass, domain, config), domain
        assert hass.services.has_service("script", "gatus_alert_light_worker"), (
            "Worker disabled by native validation"
        )
        hass.services.async_register("light", "turn_on", self.light)
        hass.services.async_register("light", "turn_off", self.light)
        self.set_light(self.physical_state, self.physical_attrs)
        await hass.async_start()
        await hass.async_block_till_done()
        await hass.services.async_call(
            "automation",
            "turn_off",
            {"entity_id": "automation.gatus_alert_light_dispatch"},
            blocking=True,
        )

    async def worker(self, payload=None):
        await self.hass.services.async_call(
            "script",
            "gatus_alert_light_worker",
            {
                "kind": "event" if payload is not None else "reconcile",
                "payload": payload or {},
            },
            blocking=True,
        )
        await self.hass.async_block_till_done()

    def snapshot(self):
        return self.hass.states.get("input_text.gatus_alert_light_snapshot").state

    def active(self, name):
        return self.hass.states.is_state(self.endpoints[name], "on")

    def assert_red(self):
        assert self.physical_state == "on"
        assert self.physical_attrs == {
            "brightness": 128,
            "color_mode": "hs",
            "hs_color": [0, 100],
        }, self.physical_attrs

    def assert_original(self, state="on", attrs=None):
        assert self.physical_state == state
        if state == "on":
            assert self.physical_attrs == (BASE if attrs is None else attrs), (
                self.physical_attrs
            )
        assert self.snapshot() == ""
        assert not any(self.active(name) for name in self.names)

    async def reset(self, state="on", attrs=None):
        self.api_status = 200
        for name in self.names:
            self.history(name, [True, True])
            await self.hass.services.async_call(
                "input_boolean",
                "turn_off",
                {"entity_id": self.endpoints[name]},
                blocking=True,
            )
        await self.hass.services.async_call(
            "input_text",
            "set_value",
            {"entity_id": "input_text.gatus_alert_light_snapshot", "value": ""},
            blocking=True,
        )
        self.set_light(state, BASE if attrs is None else attrs)

    async def run(self, url):
        for name in self.names:
            self.history(name, [True, True])
        await self.start(url)
        a, b = self.names[:2]
        await self.reset()
        self.history(a, [False] * 4)
        await self.worker()
        self.assert_original()
        self.history(a, [False] * 5)
        await self.worker()
        self.assert_red()
        saved = self.snapshot()
        assert json.loads(saved)["brightness"] == 77
        print("PASS one_alert", flush=True)
        await self.worker({"event_data": {"endpoint": a, "status": "triggered"}})
        assert self.snapshot() == saved
        print("PASS duplicate", flush=True)
        self.history(b, [False] * 5)
        await self.worker()
        self.history(a, [False] * 5 + [True, True])
        await self.worker()
        self.assert_red()
        assert not self.active(a) and self.active(b)
        print("PASS overlap", flush=True)
        await self.worker({"event_data": {"endpoint": b, "status": "resolved"}})
        self.assert_red()
        print("PASS stale_resolution", flush=True)
        self.history(b, [False] * 5 + [True])
        await self.worker()
        self.assert_red()
        self.history(b, [False] * 5 + [True, True])
        await self.worker()
        self.assert_original()
        print("PASS missed_delivery", flush=True)
        await self.reset()
        self.history(a, [False] * 5)
        await self.worker({"event_data": {"endpoint": a}})
        self.assert_original()
        print("PASS invalid_event", flush=True)
        await self.worker()
        self.assert_red()
        self.history(a, [True, True])
        self.api_status = 503
        await self.worker()
        self.assert_red()
        self.api_status = 200
        self.rows[a] = []
        await self.worker()
        self.assert_red()
        print("PASS bad_api", flush=True)
        await self.reset("off")
        self.history(a, [False] * 5)
        await self.worker()
        self.assert_red()
        self.history(a, [True, True])
        await self.worker()
        self.assert_original("off")
        print("PASS initially_off", flush=True)
        for attrs in (
            {"brightness": 99, "color_mode": "hs", "hs_color": [218.27, 50]},
            {"brightness": 99, "color_mode": "xy", "xy_color": [0.21, 0.22]},
        ):
            await self.reset(attrs=attrs)
            self.history(a, [False] * 5)
            await self.worker()
            self.history(a, [True, True])
            await self.worker()
            self.assert_original(attrs=attrs)
        print("PASS colored_snapshot", flush=True)
        await self.reset("unavailable")
        self.history(a, [False] * 5)
        await self.worker()
        assert self.snapshot() == "" and self.active(a)
        self.set_light("on", BASE)
        await self.worker()
        self.assert_red()
        print("PASS deferred_snapshot", flush=True)
        self.set_light("unavailable")
        self.history(a, [True, True])
        await self.worker()
        assert self.snapshot() and self.active(a)
        self.set_light(
            "on", {"brightness": 128, "color_mode": "hs", "hs_color": [0, 100]}
        )
        await self.worker()
        self.assert_original()
        print("PASS deferred_restore", flush=True)
        await self.reset()
        self.history(a, [False] * 5)
        await self.worker()
        saved = self.snapshot()
        await self.hass.async_stop()
        await self.hass.async_block_till_done()
        await self.start(url)
        assert self.snapshot() == saved and self.active(a)
        self.assert_red()
        self.history(a, [True, True])
        await self.worker()
        self.assert_original()
        print("PASS restart", flush=True)
        await self.reset()
        self.history(a, [False] * 5)
        await self.hass.services.async_call(
            "automation",
            "turn_on",
            {"entity_id": "automation.gatus_alert_light_dispatch"},
            blocking=True,
        )
        self.hass.bus.async_fire(
            "gatus_alert",
            {
                "event_type": "gatus_alert",
                "event_data": {"endpoint": a, "status": "triggered"},
            },
        )
        await self.hass.async_block_till_done()
        self.assert_red()
        print("PASS native_event_dispatch", flush=True)


async def main():
    package = yaml.safe_load(Path(sys.argv[1]).read_text())
    assert "gatus_alert_light_worker" in package.get("script", {}), (
        "Missing native worker"
    )
    macro = Path(sys.argv[2]).read_text()
    with tempfile.TemporaryDirectory(prefix="ha-gatus-engine-") as folder:
        scenarios = Scenarios(package, macro, folder)
        app = web.Application()
        app.router.add_get("/api/v1/endpoints/statuses", scenarios.api)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            await scenarios.run(f"http://127.0.0.1:{port}/api/v1/endpoints/statuses")
            print("All native HA alert-light scenarios passed", flush=True)
        finally:
            if scenarios.hass:
                await scenarios.hass.async_stop()
            await runner.cleanup()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
