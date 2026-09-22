"""Validate embedded application configuration that YAML lint cannot see."""

import copy
from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]


class ConfigLoader(yaml.SafeLoader):
    pass


ConfigLoader.add_constructor("!env_var", lambda loader, node: loader.construct_scalar(node))


def validate_karakeep_browser(values):
    app = values["controllers"]["chrome"]["containers"]["app"]
    image = app["image"]
    args = app.get("args", [])
    if image.get("repository") != "ghcr.io/karakeep-app/karakeep-chrome":
        raise ValueError("Karakeep must use its maintained browser image")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+-r[0-9]+", str(image.get("tag", ""))):
        raise ValueError("Karakeep browser image must use a versioned release")
    if "command" in app:
        raise ValueError("Karakeep browser must preserve the image entrypoint")
    forbidden = {"--no-sandbox", "--disable-software-rasterizer"}
    if forbidden.intersection(args) or any(
        re.match(r"^--remote-debugging-(address|port)(=|$)", arg) for arg in args
    ):
        raise ValueError("Karakeep browser arguments must preserve internal port forwarding")


class MediaConfigContracts(unittest.TestCase):
    def test_karakeep_uses_maintained_browser_entrypoint(self):
        values = yaml.safe_load((ROOT / "apps/selfhosted/karakeep/values.yaml").read_text())
        validate_karakeep_browser(values)

    def test_karakeep_browser_mutations_are_rejected(self):
        values = yaml.safe_load((ROOT / "apps/selfhosted/karakeep/values.yaml").read_text())
        mutations = {
            "repository": lambda app: app["image"].update(repository="example.invalid/browser"),
            "tag": lambda app: app["image"].update(tag="latest"),
            "command": lambda app: app.update(command=["chromium"]),
            "sandbox": lambda app: app["args"].append("--no-sandbox"),
            "debugging": lambda app: app["args"].append("--remote-debugging-port=9222"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                broken = copy.deepcopy(values)
                mutate(broken["controllers"]["chrome"]["containers"]["app"])
                with self.assertRaises(ValueError):
                    validate_karakeep_browser(broken)

    def test_arr_backups_use_writable_temporary_directory(self):
        for service in ("radarr", "sonarr", "prowlarr"):
            with self.subTest(service=service):
                values = yaml.safe_load((ROOT / f"apps/media/{service}/values.yaml").read_text())
                app = values["controllers"]["main"]["containers"]["app"]
                self.assertEqual(app["env"].get("TMPDIR"), "/tmp")
                self.assertNotIn("CHOWN", app["securityContext"]["capabilities"]["add"])

    def test_qbittorrent_vpn_readiness_checks_health_response(self):
        values = yaml.safe_load((ROOT / "apps/media/qbittorrent/values.yaml").read_text())
        probe = values["controllers"]["main"]["containers"]["gluetun"]["probes"]["readiness"]
        self.assertEqual(probe["type"], "HTTP")
        self.assertEqual(probe["port"], 9999)

    def test_recyclarr_custom_format_groups_use_v8_mapping(self):
        manifest = yaml.safe_load(
            (ROOT / "apps/media/recyclarr/manifests/recyclarr-config.configmap.yaml").read_text()
        )
        config = yaml.load(manifest["data"]["recyclarr.yml"], Loader=ConfigLoader)

        for service in ("sonarr", "radarr"):
            for instance in config[service].values():
                with self.subTest(service=service):
                    groups = instance["custom_format_groups"]
                    self.assertIsInstance(groups, dict)
                    self.assertIsInstance(groups.get("add"), list)
                    self.assertTrue(all("trash_id" in group for group in groups["add"]))


if __name__ == "__main__":
    unittest.main()
