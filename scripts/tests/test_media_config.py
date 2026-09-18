"""Validate embedded application configuration that YAML lint cannot see."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]


class ConfigLoader(yaml.SafeLoader):
    pass


ConfigLoader.add_constructor("!env_var", lambda loader, node: loader.construct_scalar(node))


class MediaConfigContracts(unittest.TestCase):
    def test_plextraktsync_job_fails_when_sync_logs_an_error(self):
        values = yaml.safe_load((ROOT / "apps/media/plextraktsync/values.yaml").read_text())
        app = values["controllers"]["sync"]["containers"]["app"]

        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "plextraktsync"
            executable.write_text(
                "#!/bin/sh\n"
                'printf "%s\\n" "$1" >> "$CALLS"\n'
                'if [ "$1" = "sync" ]; then exit "$SYNC_STATUS"; fi\n'
                'exit "$HEALTH_STATUS"\n'
            )
            executable.chmod(0o755)
            calls = Path(directory) / "calls"
            environment = os.environ | {
                "PATH": f"{directory}:{os.environ['PATH']}",
                "CALLS": str(calls),
                "SYNC_STATUS": "0",
                "HEALTH_STATUS": "1",
            }

            command = app["command"] + app["args"]
            result = subprocess.run(command, env=environment, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(calls.read_text().splitlines(), ["sync", "healthcheck"])

            calls.unlink()
            environment["HEALTH_STATUS"] = "0"
            result = subprocess.run(command, env=environment, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(calls.read_text().splitlines(), ["sync", "healthcheck"])

            calls.unlink()
            environment["SYNC_STATUS"] = "2"
            result = subprocess.run(command, env=environment, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(calls.read_text().splitlines(), ["sync"])

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
