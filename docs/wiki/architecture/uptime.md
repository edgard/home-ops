# Uptime and cluster monitoring

Purpose: operate the in-cluster Grafana dashboards, probes and production alerts.
Status: current. Reviewed against: `cdb7a398deaa06451737a5a43e895942443e7d3c` and this revision.

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

On the host dashboard, check physical NIC and disk counters against Talos,
including bridge br0, and compare the number of CPU cores with the node
inventory. On the workloads dashboard compare CPU rates and working-set
memory with `kubectl top pods -A` over a similar sampling interval. Check
controller readiness and restarts against Kubernetes. Keep metrics-server
for the Kubernetes resource metrics API.

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
