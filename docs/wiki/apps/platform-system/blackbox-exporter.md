# Blackbox Exporter

Purpose: probe application routes, public DNS resolvers and IPv4 internet targets from inside the cluster.
Status: current. Reviewed against: `cdb7a398deaa06451737a5a43e895942443e7d3c` and this revision.

VictoriaMetrics sends the target and probe module to the private service. The storage probe uses the readiness Service so Kubernetes withdraws its endpoint when pool, SMART or maintenance checks fail. The exporter is stateless.

## Sources

- [Application](../../../../apps/platform-system/blackbox-exporter/app.yaml)
- [Helm values](../../../../apps/platform-system/blackbox-exporter/values.yaml)

## Related pages

- [Monitoring and cutover](../../architecture/uptime.md)
