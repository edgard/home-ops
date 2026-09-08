#!/usr/bin/env python3
"""Validate Grafana wiring and evaluate repository MetricsQL against synthetic data."""

import json
from pathlib import Path
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "apps/platform-system/victoria-metrics-k8s-stack/manifests"
TEST_EPOCH = 946684800  # vmalert-tool starts tests at 2000-01-01T00:00:00Z.


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load():
    dashboard_config = yaml.safe_load(
        (MANIFESTS / "victoria-metrics-k8s-stack-home-ops-overview.configmap.yaml").read_text()
    )
    alert_config = yaml.safe_load(
        (MANIFESTS / "victoria-metrics-k8s-stack-grafana-alerting.configmap.yaml").read_text()
    )
    dashboard = json.loads(dashboard_config["data"]["home-ops-overview.json"])
    groups = yaml.safe_load(alert_config["data"]["rules.yaml"])["groups"]
    return dashboard, [rule for group in groups for rule in group["rules"]]


def load_provisioning_mount():
    values = yaml.safe_load(
        (ROOT / "apps/platform-system/victoria-metrics-k8s-stack/values.yaml").read_text()
    )
    alert_config = yaml.safe_load(
        (MANIFESTS / "victoria-metrics-k8s-stack-grafana-alerting.configmap.yaml").read_text()
    )
    return values["grafana"].get("extraConfigmapMounts", []), alert_config["metadata"]["name"]


def validate_provisioning_mount(mounts, config_map_name):
    matching = [mount for mount in mounts if mount.get("configMap") == config_map_name]
    require(len(matching) == 1, "Grafana must mount the alerting provisioning ConfigMap")
    require(matching[0].get("mountPath") == "/etc/grafana/provisioning/alerting", "Grafana alerting ConfigMap uses the wrong provisioning path")


def load_runtime_wiring():
    metrics_values = yaml.safe_load(
        (ROOT / "apps/platform-system/victoria-metrics-k8s-stack/values.yaml").read_text()
    )
    collector_values = yaml.safe_load(
        (ROOT / "apps/platform-system/victoria-logs-collector/values.yaml").read_text()
    )
    logs_app = yaml.safe_load(
        (ROOT / "apps/platform-system/victoria-logs-single/app.yaml").read_text()
    )
    credentials = yaml.safe_load(
        (MANIFESTS / "victoria-metrics-k8s-stack-grafana-alerting-credentials.externalsecret.yaml").read_text()
    )
    alert_config = yaml.safe_load(
        (MANIFESTS / "victoria-metrics-k8s-stack-grafana-alerting.configmap.yaml").read_text()
    )
    contact = yaml.safe_load(alert_config["data"]["contactpoints.yaml"])["contactPoints"][0]["receivers"][0]
    return metrics_values, collector_values, logs_app, credentials, contact


def validate_runtime_wiring(metrics_values, collector_values, logs_app, credentials, contact):
    expected_logs_url = f"http://{logs_app['chart']['name']}-server.platform-system.svc.cluster.local:9428"
    read_url = metrics_values["external"]["vl"]["read"]["url"]
    write_urls = [target["url"] for target in collector_values["remoteWrite"]]
    require(read_url == expected_logs_url and write_urls == [expected_logs_url], "Grafana and the collector must use the internal VictoriaLogs service")

    secret_name = credentials["spec"]["target"]["name"]
    require(secret_name == metrics_values["grafana"]["envFromSecret"], "Grafana must consume the alerting credentials Secret")
    expected_keys = {contact["settings"]["bottoken"].removeprefix("$"), contact["settings"]["chatid"].removeprefix("$")}
    data = credentials["spec"]["data"]
    require({item["secretKey"] for item in data} == expected_keys, "Telegram settings must match ExternalSecret output keys")
    remote_keys = [item["remoteRef"].get("key") for item in data]
    require(all(remote_keys) and len(remote_keys) == len(set(remote_keys)), "Telegram credentials require distinct nonempty remote keys")


def value_mapping(panel, value):
    for mapping in panel["fieldConfig"]["defaults"].get("mappings", []):
        if mapping["type"] == "value" and str(value) in mapping["options"]:
            return mapping["options"][str(value)]
    return None


def validate_structure(dashboard, rules):
    panels = dashboard["panels"]
    require(len({panel["id"] for panel in panels}) == len(panels), "duplicate panel ID")
    for index, panel in enumerate(panels):
        grid = panel["gridPos"]
        require(grid["x"] >= 0 and grid["y"] >= 0 and grid["w"] > 0 and grid["h"] > 0 and grid["x"] + grid["w"] <= 24, "panel outside dashboard grid")
        for other in panels[index + 1 :]:
            box = other["gridPos"]
            require(
                grid["x"] + grid["w"] <= box["x"]
                or box["x"] + box["w"] <= grid["x"]
                or grid["y"] + grid["h"] <= box["y"]
                or box["y"] + box["h"] <= grid["y"],
                "dashboard panels overlap",
            )
        targets = panel.get("targets", [])
        require(len({target["refId"] for target in targets}) == len(targets), "duplicate query reference")
        if panel["type"] != "row":
            require(targets and panel["datasource"]["uid"] == "prometheus", "metrics panel lacks a query or datasource")
            require(all(target["datasource"]["uid"] == "prometheus" for target in targets), "query uses the wrong datasource")

    for rule in rules:
        require(not rule.get("isPaused", False), "provisioned alert is paused")
        data = {item["refId"]: item for item in rule["data"]}
        require(len(data) == len(rule["data"]), "duplicate alert query reference")
        threshold = data[rule["condition"]]["model"]
        require(threshold["type"] == "threshold" and threshold["conditions"][0]["evaluator"] == {"type": "gt", "params": [0]}, "alert must threshold a positive firing indicator")
        reduce = data[threshold["expression"]]["model"]
        require(reduce["type"] == "reduce" and reduce["reducer"] == "last", "alert must reduce the latest query value")
        query = data[reduce["expression"]]
        require(query["datasourceUid"] == "prometheus" and query["model"]["instant"] is True, "alert must use an instant metrics query")


def series(name, values):
    return {"series": name, "values": values if isinstance(values, str) else f"{values}x60"}


def behavior_cases(dashboard, rules):
    panels = {panel["id"]: panel for panel in dashboard["panels"]}
    alerts = {rule["title"]: rule for rule in rules}
    cases = []

    def panel_case(name, panel_id, expected, inputs=(), ref="A", unit=None, color=None):
        panel = panels[panel_id]
        target = next(item for item in panel["targets"] if item["refId"] == ref)
        if unit:
            require(panel["fieldConfig"]["defaults"]["unit"] == unit, f"{name}: query and display units disagree")
        if color:
            mapping = value_mapping(panel, expected)
            require(mapping and mapping.get("color") == color and mapping.get("text"), f"{name}: status mapping is misleading")
        cases.append({"name": name, "expr": target["expr"], "inputs": list(inputs), "expected": expected, "key": (panel_id, ref)})

    def alert_case(name, title, expected, inputs=()):
        rule = alerts[title]
        expression = next(item["model"]["expr"] for item in rule["data"] if item["datasourceUid"] == "prometheus")
        cases.append({"name": name, "expr": f"sum({expression}) or vector(0)", "inputs": list(inputs), "expected": expected})

    stat_queries = [(panel["id"], target["refId"]) for panel in panels.values() if panel["type"] == "stat" for target in panel["targets"]]
    for panel_id, ref in stat_queries:
        panel_case(f"panel {panel_id}/{ref}: missing metrics", panel_id, -1, ref=ref, color="red")

    for value in (0, 3):
        panel_case(f"active alerts: {value}", 2, value, [series('grafana_alerting_active_alerts{job="victoria-metrics-k8s-stack-grafana"}', value)], color="green" if value == 0 else None)
    for value in (0, 1):
        panel_case(f"reachability: {value}", 3, 1 - value, [series('probe_success{instance="one"}', value), series('probe_success{instance="two"}', 1)], color="green" if value == 1 else None)
        panel_case(f"node ready: {value}", 4, value, [series('kube_node_status_condition{job="kube-state-metrics",condition="Ready",status="true"}', value)], color="green" if value else "red")
        panel_case(f"PVC pending: {value}", 15, value, [series('kube_persistentvolume_status_phase{phase="Pending",job="kube-state-metrics"}', value), series('kube_persistentvolume_status_phase{phase="Failed",job="kube-state-metrics"}', 0)], color="green" if value == 0 else None)

    for metric in ("kube_cronjob_status_last_successful_time", "kube_cronjob_created"):
        panel_case(f"backup age from {metric}", 5, 1, [series(f'{metric}{{namespace="selfhosted",cronjob="restic-backup"}}', TEST_EPOCH)], unit="h")
    panel_case("backup success takes precedence", 5, 0.5, [series('kube_cronjob_created{namespace="selfhosted",cronjob="restic-backup"}', TEST_EPOCH - 7200), series('kube_cronjob_status_last_successful_time{namespace="selfhosted",cronjob="restic-backup"}', TEST_EPOCH + 1800)], unit="h")

    for health, sync, expected in (("Healthy", "Synced", 0), ("Progressing", "Synced", 0), ("Degraded", "Synced", 1), ("Healthy", "OutOfSync", 1)):
        panel_case(f"Argo {health}/{sync}", 7, expected, [series(f'argocd_app_info{{health_status="{health}",sync_status="{sync}"}}', 1)], color="green" if expected == 0 else None)
    panel_case("certificate expiry is days", 8, 2, [series("certmanager_certificate_expiration_timestamp_seconds", TEST_EPOCH + 176400)], unit="suffix: days")
    for panel_id, metric in ((9, "kube_pod_container_status_restarts_total"), (10, 'container_oom_events_total{job="kubelet",metrics_path="/metrics/cadvisor",container="app",pod="demo"}')):
        panel_case(f"panel {panel_id}: no events", panel_id, 0, [series(metric, 0)], color="green")
        panel_case(f"panel {panel_id}: one event", panel_id, 1, [series(metric, "0x55 1x4")])
    panel_case("CPU used is percent", 12, 50, [series('node_cpu_seconds_total{job="node-exporter",mode="idle"}', "0+30x60")], unit="percent")
    panel_case("memory used is percent", 13, 75, [series('node_memory_MemAvailable_bytes{job="node-exporter"}', 25), series('node_memory_MemTotal_bytes{job="node-exporter"}', 100)], unit="percent")
    panel_case("filesystem excludes virtual mounts", 14, 25, [series('node_filesystem_avail_bytes{job="node-exporter",fstype="ext4"}', 25), series('node_filesystem_size_bytes{job="node-exporter",fstype="ext4"}', 100), series('node_filesystem_avail_bytes{job="node-exporter",fstype="tmpfs"}', 0), series('node_filesystem_size_bytes{job="node-exporter",fstype="tmpfs"}', 100)], unit="percent")

    jobs = {
        20: ("probe_success", ["prometheus-blackbox-exporter-http", "prometheus-blackbox-exporter-dns", "prometheus-blackbox-exporter-icmp"]),
        22: ("up", ["node-exporter", "kubelet", "kube-state-metrics", "prometheus-blackbox-exporter"]),
        23: ("up", ["vmsingle-victoria-metrics-k8s-stack", "vmagent-victoria-metrics-k8s-stack", "victoria-metrics-k8s-stack-victoria-metrics-operator", "victoria-logs-single-server", "platform-system/victoria-logs-collector", "victoria-metrics-k8s-stack-grafana"]),
    }
    for panel_id, (metric, names) in jobs.items():
        for index, job in enumerate(names):
            for value in (0, 1):
                panel_case(f"{job}: {value}", panel_id, value, [series(f'{metric}{{job="{job}"}}', value)], ref=chr(65 + index), color="green" if value else "red")

    for value in (5, 10, 50):
        alert_case(f"memory alert at {value}% available", "NodeMemoryAvailableLow", int(value < 10), [series('node_memory_MemAvailable_bytes{job="node-exporter"}', value), series('node_memory_MemTotal_bytes{job="node-exporter"}', 100)])
    for value in (0, 1):
        alert_case(f"node alert readiness {value}", "NodeNotReady", 1 - value, [series('kube_node_status_condition{job="kube-state-metrics",condition="Ready",status="true"}', value)])
        alert_case(f"OOM alert event {value}", "PodContainerOOMKilled", value, [series('container_oom_events_total{container="app",pod="demo",namespace="selfhosted"}', f"0x55 {value}x4")])
    for metric in ("kube_cronjob_status_last_successful_time", "kube_cronjob_created"):
        for age in (35, 37):
            alert_case(f"backup alert {metric}: {age}h", "ResticBackupStale", int(age > 36), [series(f'{metric}{{namespace="selfhosted",cronjob="restic-backup"}}', TEST_EPOCH + 3600 - age * 3600)])
    for down_job in jobs[22][1]:
        inputs = [series(f'up{{job="{job}"}}', int(job != down_job)) for job in jobs[22][1]]
        alert_case(f"core scrape alert: {down_job} down", "CoreScrapeTargetDown", 1, inputs)
        inputs = [series(f'up{{job="{job}"}}', 1) for job in jobs[22][1] if job != down_job]
        alert_case(f"core scrape alert: {down_job} missing", "CoreScrapeTargetDown", 1, inputs)

    covered = {case["key"] for case in cases if "key" in case}
    require(set(stat_queries) <= covered, f"health queries lack behavior fixtures: {set(stat_queries) - covered}")
    return cases


def run_cases(cases, tool):
    tests = []
    for case in cases:
        tests.append({"name": case["name"], "interval": "1m", "input_series": case["inputs"], "metricsql_expr_test": [{"expr": case["expr"], "eval_time": "60m", "exp_samples": [{"labels": "{}", "value": case["expected"]}]}]})
    with tempfile.TemporaryDirectory(prefix="observability-tests-") as directory:
        temp = Path(directory)
        rules = temp / "rules.yaml"
        rules.write_text("groups:\n- name: query-clock\n  rules:\n  - record: test_clock\n    expr: vector(time())\n")
        suite = temp / "queries.yaml"
        suite.write_text(yaml.safe_dump({"rule_files": [str(rules)], "evaluation_interval": "1m", "tests": tests}, sort_keys=False))
        return subprocess.run([str(tool), "unittest", "-files", str(suite)], cwd=temp, text=True, capture_output=True)


def main():
    dashboard, rules = load()
    validate_structure(dashboard, rules)
    validate_provisioning_mount(*load_provisioning_mount())
    validate_runtime_wiring(*load_runtime_wiring())
    cases = behavior_cases(dashboard, rules)
    tool = ROOT / ".venv/bin/vmalert-tool"
    require(tool.is_file(), "run task deps to install vmalert-tool")
    result = run_cases(cases, tool)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    print(f"Observability wiring and {len(cases)} query scenarios passed")


if __name__ == "__main__":
    main()
