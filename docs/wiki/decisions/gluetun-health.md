# Restart unhealthy Gluetun

Purpose: retain the reason for qBittorrent's VPN health probe.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

During an incident, Gluetun's HTTP health endpoint returned errors while its
TCP listener remained open. The former TCP liveness probe did not restart it.
[PR #383](https://github.com/edgard/home-ops/pull/383) moved liveness to the
HTTP health endpoint and added a rendered-workload policy guard. Changes to
the qBittorrent pod should preserve VPN failure detection and verify actual
traffic isolation after reconnects.

## Sources

- [Gluetun health fix, PR #383](https://github.com/edgard/home-ops/pull/383)
- [qBittorrent values](../../../apps/media/qbittorrent/values.yaml)
- [Workload security policy](../../../policy/kubernetes/workload_security.rego)

## Related pages

- [qBittorrent](../apps/media/qbittorrent.md)
- [Validation](../architecture/validation.md)
