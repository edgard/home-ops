"""Regression tests proving observability contracts reject broken behavior."""

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_observability as observability
from check_observability import behavior_cases, load, load_provisioning_mount, load_runtime_wiring, validate_provisioning_mount, validate_runtime_wiring, validate_structure


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
        extra_rule = copy.deepcopy(self.rules[0])
        extra_rule["uid"] = "additional-rule"
        extra_rule["title"] = "AdditionalRule"
        self.rules.append(extra_rule)
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

    def test_contact_point_credentials_must_be_environment_references(self):
        wiring = list(load_runtime_wiring())
        wiring[4] = copy.deepcopy(wiring[4])
        wiring[4]["settings"]["bottoken"] = "TELEGRAM_BOT_TOKEN"
        with self.assertRaisesRegex(ValueError, "environment variables"):
            validate_runtime_wiring(*wiring)

    def test_logs_read_and_write_use_the_internal_service(self):
        wiring = list(load_runtime_wiring())
        wiring[1] = copy.deepcopy(wiring[1])
        wiring[1]["remoteWrite"][0]["url"] = "http://wrong.example"
        with self.assertRaisesRegex(ValueError, "internal VictoriaLogs service"):
            validate_runtime_wiring(*wiring)

    def test_missing_durable_backup_coverage_is_rejected(self):
        exclusions = (
            ["--exclude", "/data/appdata/platform-system/server-volume-victoria-logs-single-server-0"],
            ["--iexclude", "/data/appdata/platform-system/server-volume-victoria-logs-single-server-0"],
            ["-e", "/data/appdata/platform-system/server-volume-victoria-logs-single-server-0"],
            ["--exclude=/data/appdata/platform-system/vmsingle-victoria-metrics-k8s-stack"],
            ["--exclude", "/data/appdata/platform-system"],
            ["--exclude", "/data/appdata/platform-system/*victoria*"],
            ["--exclude-file", "/etc/restic/excludes"],
        )
        for exclusion in exclusions:
            with self.subTest(exclusion=exclusion):
                architecture = observability.load_architecture()
                architecture["restic_values"] = copy.deepcopy(architecture["restic_values"])
                architecture["restic_values"]["controllers"]["backup"]["containers"]["app"]["args"].extend(exclusion)
                with self.assertRaisesRegex(ValueError, "durable observability state"):
                    observability.validate_architecture(architecture)

    def test_custom_dashboards_keep_discovery_labels(self):
        for index in range(2):
            with self.subTest(index=index):
                architecture = observability.load_architecture()
                architecture["dashboard_configs"] = copy.deepcopy(architecture["dashboard_configs"])
                architecture["dashboard_configs"][index]["metadata"]["labels"].pop("grafana_dashboard")
                with self.assertRaisesRegex(ValueError, "dashboard discovery"):
                    observability.validate_architecture(architecture)

    def test_additional_grafana_plugins_do_not_break_architecture(self):
        architecture = observability.load_architecture()
        architecture["metrics_values"] = copy.deepcopy(architecture["metrics_values"])
        architecture["metrics_values"]["grafana"]["plugins"].append("another-plugin@1.0.0")
        observability.validate_architecture(architecture)

    def test_metrics_chart_source_remains_authoritative(self):
        architecture = observability.load_architecture()
        architecture["metrics_app"] = copy.deepcopy(architecture["metrics_app"])
        architecture["metrics_app"]["chart"]["repo"] = "https://example.invalid/charts"
        with self.assertRaisesRegex(ValueError, "metrics stack"):
            observability.validate_architecture(architecture)

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

if __name__ == "__main__":
    unittest.main()
