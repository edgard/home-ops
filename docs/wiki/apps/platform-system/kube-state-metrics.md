# kube-state-metrics

Purpose: publish Kubernetes workload status for Grafana through VictoriaMetrics.
Status: current. Reviewed against: `cdb7a398deaa06451737a5a43e895942443e7d3c` and this revision.

A read-only service account watches the workload resources selected in the values. This private exporter is stateless. Availability and restart counts come from the API. CPU and memory usage come from the kubelet resource endpoint.

## Sources

- [Application](../../../../apps/platform-system/kube-state-metrics/app.yaml)
- [Helm values](../../../../apps/platform-system/kube-state-metrics/values.yaml)

## Related pages

- [Monitoring and cutover](../../architecture/uptime.md)
