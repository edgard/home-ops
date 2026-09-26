"""Validate embedded application configuration that YAML lint cannot see."""

from pathlib import Path
import unittest
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[2]


class ConfigLoader(yaml.SafeLoader):
    pass


ConfigLoader.add_constructor("!env_var", lambda loader, node: loader.construct_scalar(node))


class MediaConfigContracts(unittest.TestCase):
    def test_karakeep_browser_uses_image_entrypoint_and_service_port(self):
        values = yaml.safe_load((ROOT / "apps/selfhosted/karakeep/values.yaml").read_text())
        chrome = values["controllers"]["chrome"]["containers"]["app"]
        self.assertEqual(chrome["image"]["repository"], "ghcr.io/karakeep-app/karakeep-chrome")
        self.assertNotIn("command", chrome)
        self.assertFalse(
            {"--no-sandbox", "--disable-software-rasterizer"}.intersection(chrome.get("args", []))
        )
        self.assertFalse(any(arg.startswith("--remote-debugging-") for arg in chrome.get("args", [])))
        browser_url = values["controllers"]["main"]["containers"]["app"]["env"]["BROWSER_WEB_URL"]
        self.assertEqual(urlsplit(browser_url).port, values["service"]["chrome"]["ports"]["http"]["port"])

    def test_arr_backups_use_writable_temporary_directory(self):
        for service in ("radarr", "sonarr", "prowlarr"):
            with self.subTest(service=service):
                values = yaml.safe_load((ROOT / f"apps/media/{service}/values.yaml").read_text())
                app = values["controllers"]["main"]["containers"]["app"]
                self.assertEqual(app["env"].get("TMPDIR"), "/tmp")
                self.assertNotIn("CHOWN", app["securityContext"]["capabilities"]["add"])

    def test_qbittorrent_vpn_readiness_checks_health_response(self):
        values = yaml.safe_load((ROOT / "apps/media/qbittorrent/values.yaml").read_text())
        gluetun = values["controllers"]["main"]["containers"]["gluetun"]
        probe = gluetun["probes"]["readiness"]
        health_port = int(gluetun["env"]["HEALTH_SERVER_ADDRESS"].rsplit(":", 1)[1])
        self.assertEqual(probe["type"], "HTTP")
        self.assertEqual(probe["port"], health_port)
        self.assertIn(str(health_port), gluetun["env"]["FIREWALL_INPUT_PORTS"].split(","))

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
