# Uptime and cluster monitoring

Purpose: operate the in-cluster Grafana dashboards, probes and production alerts.
Status: current. Reviewed against: `7fad7f2565192a6b198cf345b155063f0c898afd` and this revision.

Grafana owns Telegram notifications. `status.edgard.org` redirects to the
uptime dashboard on the Grafana hostname. All three dashboards require sign-in. Monitoring and notification delivery depend on the single
node and working internet access.

## Inspect monitoring

VictoriaMetrics asks Blackbox Exporter to probe configured targets every
minute. Keep the routed applications, storage readiness Service, DNS A
queries and IPv4 ICMP targets current in the scrape configuration.
Inspect `probe_success{job="uptime"}` by instance for target health and
`up` for scrape health. The rules count consecutive probe results and
separately detect a loss of samples.

Each monitored application's web Service declares its probe URL. Its standard
`app.kubernetes.io/instance` label supplies the stable name used by Grafana. Use the routed HTTPS hostname and health path
so Blackbox exercises DNS, TLS and the Gateway from inside the cluster.
The `monitoring.edgard.org/uptime` label opts the Service in. VictoriaMetrics
has read-only Service discovery access in the four application namespaces.

The uptime dashboard lists affected targets first. Select a target name to
open its probe history. Failed HTTP checks show the response code or
“No response” when the probe received none. Filter by group to compare latency. A failed probe means the check ran and
failed. Unknown means the result is missing or stale. Telegram waits for
confirmation before reporting a service failure or recovery, so its state
can briefly differ from the latest probe.

For a storage readiness alert, open the target history and check the
[storage maintenance workload](../apps/kube-system/storage-maintenance.md).
Its readiness depends on pool checks, SMART health and scheduled maintenance.
Use the Talos dashboard to check pool state and free space alongside CPU and
available RAM. The bridge and its physical interfaces can carry the same
traffic, so compare their rates separately.

Use the workloads dashboard to find deployments short of available replicas
and pods with recent restarts. Filter by namespace to compare CPU and memory
with `kubectl top pods -n <namespace>` over a similar sampling interval.
The kubelet supplies resource usage and kube-state-metrics supplies workload
state. The Kubernetes resource metrics API still depends on metrics-server.

After seven days including a backup cycle, record the monitoring pods' CPU
and working sets, active series, ingestion rate, and actual bytes used on the
metrics filesystem. Use the observed daily growth to project 13 months,
allowing for VictoriaMetrics' monthly partitions and compaction. If the
projection exceeds 80% of the PVC capacity, expand the claim in Git. Disk allocation and initial resource requests are sizing inputs,
not measurements. [VictoriaMetrics retention](https://docs.victoriametrics.com/victoriametrics/single-server-victoriametrics/#retention)

A failing static scrape continues to generate `up=0`. When a target is removed
from the configuration its old label set ages out of missing-scrape detection
after an hour. Review the target list in every route-changing PR.
Grafana groups notifications by instance and repeats an ongoing incident after
five days.

## Verify changes and recover

Verify a controlled target fires after five failed checks, stays firing through
an isolated success and resolves after two consecutive successes. Test missing
scrapes separately. Open the status hostname in a signed-out session and verify that Grafana asks
for a login. Sign in and check that the uptime dashboard loads.

To restore Gatus following a cutover failure, revert the cutover PR. Check
Argo restores its status route and Telegram delivery, and that Grafana's
comparison mute returns. Reverting the entire cutover also re-enables public
sharing and restores the sharing Job. To keep dashboards private during
rollback, retain the disabled public dashboard setting and omit the Job.
Both monitoring appdata volumes persist across this rollback.

## Sources

- [VictoriaMetrics collection](../../../apps/platform-system/victoria-metrics)
- [Blackbox modules](../../../apps/platform-system/blackbox-exporter)
- [Grafana dashboards and alerting](../../../apps/platform-system/grafana)
- [Storage readiness](../../../apps/kube-system/storage-maintenance/values.yaml)

## Related pages

- [Local telemetry storage](storage.md#local-telemetry)
- [Networking](networking.md)
- [Gatus transition history](../decisions/gatus-transition.md)
