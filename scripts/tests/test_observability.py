"""Regression tests proving observability contracts reject broken behavior."""

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_observability import ROOT, behavior_cases, load, load_provisioning_mount, load_runtime_wiring, run_cases, validate_provisioning_mount, validate_runtime_wiring, validate_structure


class ObservabilityContracts(unittest.TestCase):
    def setUp(self):
        self.dashboard, self.rules = load()

    def test_cosmetic_dashboard_edits_and_query_references_are_allowed(self):
        self.dashboard["panels"].reverse()
        for panel in self.dashboard["panels"]:
            panel["title"] = "Changed display wording"
            panel["gridPos"]["y"] += 10
        for rule in self.rules:
            rule["data"].reverse()
        validate_structure(self.dashboard, self.rules)

    def test_overlapping_panels_fail(self):
        self.dashboard["panels"][1]["gridPos"] = copy.deepcopy(self.dashboard["panels"][0]["gridPos"])
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_structure(self.dashboard, self.rules)

    def test_paused_alert_fails(self):
        self.rules[0]["isPaused"] = True
        with self.assertRaisesRegex(ValueError, "paused"):
            validate_structure(self.dashboard, self.rules)

    def test_disconnected_alert_condition_fails(self):
        self.rules[0]["data"][-1]["model"]["expression"] = "missing"
        with self.assertRaises(KeyError):
            validate_structure(self.dashboard, self.rules)

    def test_alerting_configmap_must_be_mounted_for_provisioning(self):
        mounts, config_map_name = load_provisioning_mount()
        validate_provisioning_mount(mounts, config_map_name)
        broken = [dict(mount) for mount in mounts]
        next(mount for mount in broken if mount.get("configMap") == config_map_name)["mountPath"] = "/tmp/inert"
        with self.assertRaisesRegex(ValueError, "wrong provisioning path"):
            validate_provisioning_mount(broken, config_map_name)

    def test_credentials_must_feed_the_contact_point(self):
        wiring = list(load_runtime_wiring())
        validate_runtime_wiring(*wiring)
        wiring[3] = copy.deepcopy(wiring[3])
        wiring[3]["spec"]["data"][0]["secretKey"] = "UNUSED_TOKEN"
        with self.assertRaisesRegex(ValueError, "output keys"):
            validate_runtime_wiring(*wiring)

    def test_logs_read_and_write_use_the_internal_service(self):
        wiring = list(load_runtime_wiring())
        wiring[1] = copy.deepcopy(wiring[1])
        wiring[1]["remoteWrite"][0]["url"] = "http://wrong.example"
        with self.assertRaisesRegex(ValueError, "internal VictoriaLogs service"):
            validate_runtime_wiring(*wiring)

    def test_missing_metrics_cannot_be_colored_healthy(self):
        panel = next(item for item in self.dashboard["panels"] if item["id"] == 2)
        panel["fieldConfig"]["defaults"]["mappings"][0]["options"]["-1"]["color"] = "green"
        with self.assertRaisesRegex(ValueError, "misleading"):
            behavior_cases(self.dashboard, self.rules)

    def test_failed_service_cannot_be_colored_healthy(self):
        panel = next(item for item in self.dashboard["panels"] if item["id"] == 22)
        panel["fieldConfig"]["defaults"]["mappings"][0]["options"]["0"]["color"] = "green"
        with self.assertRaisesRegex(ValueError, "misleading"):
            behavior_cases(self.dashboard, self.rules)

    def evaluate(self, case_name):
        cases = [case for case in behavior_cases(self.dashboard, self.rules) if case["name"] == case_name]
        self.assertEqual(len(cases), 1)
        return run_cases(cases, ROOT / ".venv/bin/vmalert-tool")

    def test_equivalent_query_is_allowed(self):
        panel = next(item for item in self.dashboard["panels"] if item["id"] == 5)
        panel["targets"][0]["expr"] = panel["targets"][0]["expr"].replace("/ 3600", "/ 60 / 60")
        result = self.evaluate("backup age from kube_cronjob_created")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_metrics_as_healthy_is_rejected(self):
        panel = next(item for item in self.dashboard["panels"] if item["id"] == 2)
        panel["targets"][0]["expr"] = panel["targets"][0]["expr"].replace("vector(-1)", "vector(0)")
        result = self.evaluate("panel 2/A: missing metrics")
        self.assertNotEqual(result.returncode, 0)

    def test_inverted_alert_threshold_is_rejected(self):
        rule = next(item for item in self.rules if item["title"] == "NodeMemoryAvailableLow")
        rule["data"][0]["model"]["expr"] = rule["data"][0]["model"]["expr"].replace("< 0.10", "> 0.10")
        result = self.evaluate("memory alert at 5% available")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
