# Node Exporter

Purpose: collect Talos host resource and kernel metrics.
Status: current. Reviewed against: `cdb7a398deaa06451737a5a43e895942443e7d3c` and this revision.

The DaemonSet reads the host filesystems and network namespace on the single node. Client-authenticated TLS protects the metrics listener. Verify CPU count, physical disk counters, bridge traffic and ZFS collector results against the host after a Talos upgrade. The exporter has no persistent data.

## Sources

- [Application](../../../../apps/platform-system/node-exporter/app.yaml)
- [Helm values](../../../../apps/platform-system/node-exporter/values.yaml)

## Related pages

- [Monitoring and cutover](../../architecture/uptime.md)
