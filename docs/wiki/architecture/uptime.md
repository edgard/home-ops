# Uptime and cluster monitoring

Purpose: operate the in-cluster Grafana comparison and verify a safe transfer of production alerts.
Status: current. Reviewed against: `cdb7a398deaa06451737a5a43e895942443e7d3c` and this revision.

Gatus owns `status.edgard.org` and production Telegram notifications during
the comparison. VictoriaMetrics asks Blackbox Exporter to check the same
targets once a minute. Preserve the final HTTPS 2xx checks, the exact 200
storage Service check, the DNS A queries with NOERROR, and IPv4-only ICMP.
Jellyfin uses `/health` and CrossWatch uses `/healthz`. Keep both target lists
in sync when routes change. Neither in-cluster evaluator can report a total
node outage, and Telegram delivery depends on working internet access.

## Inspect the parallel deployment

Open `grafana.edgard.org` from the LAN or Tailscale. In Explore, check
`count by (group) (probe_success{job="uptime"})` against the Gatus groups.
Compare individual `instance` results and timestamps with the Gatus status
history over at least 24 hours. Probe success means the target passed;
`up` measures whether the scraper obtained a response from the exporter.
Keep absent or stale results visible during diagnosis.

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
projection exceeds 80% of the PVC capacity, expand the claim in Git before
cutover. Disk allocation and initial resource requests are sizing inputs,
not measurements. [VictoriaMetrics retention](https://docs.victoriametrics.com/victoriametrics/single-server-victoriametrics/#retention)

A failing static scrape continues to generate `up=0`. When a target is removed
from the configuration its old label set ages out of missing-scrape detection
after an hour. Review the target list in every route-changing PR.
Grafana groups notifications by instance and repeats an ongoing incident after
five days once production delivery is enabled.

## Transfer production alerting

1. Exercise a temporary, independently controlled target through the same
   probe and Grafana evaluation path. Route only the canary to Telegram.
   Verify four consecutive failures stay quiet, the fifth fires once, one
   success followed by a failure leaves the incident open, and two consecutive
   successes send one recovery. Interrupt its scrape separately and verify
   missing data is reported. Remove the temporary target, policy and fixtures.
2. Verify both PVCs survive pod replacement, historical queries still work,
   and the uptime dashboard's shared URL works logged out. Check a host dashboard
   and data-source query require authentication from the same browser.
3. Make a separate cutover PR after acceptance. Move the status HTTPRoute
   from Gatus to a Gateway redirect to the verified shared dashboard URL on
   the private Grafana hostname, activate the Grafana Telegram policy, and
   retire the Gatus app. Keep the shared Bitwarden Telegram items, which also
   supply Changedetection. Confirm exactly one production notifier and route
   owner after Argo sync. Record the verification evidence in the PR.
4. To roll back, revert that cutover PR and verify Gatus owns the hostname and
   Telegram while Grafana returns to comparison mode. This preserves collected
   telemetry. Deleting the telemetry claims deletes their datasets.

## Sources

- [Gatus probes and alert thresholds](../../../apps/platform-system/gatus/values.yaml)
- [VictoriaMetrics collection](../../../apps/platform-system/victoria-metrics)
- [Blackbox modules](../../../apps/platform-system/blackbox-exporter)
- [Grafana dashboards and alerting](../../../apps/platform-system/grafana)
- [Storage readiness](../../../apps/kube-system/storage-maintenance/values.yaml)

## Related pages

- [Local telemetry storage](storage.md#local-telemetry)
- [Networking](networking.md)
- [Gatus transition history](../decisions/gatus-transition.md)
