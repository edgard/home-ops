# Restart unhealthy Gluetun

Purpose: retain the reason for qBittorrent's VPN health probe.
Status: current. Reviewed against: `f73a66d4d60b9fd7e373eb1cfcbde4e8df270083`.

During an incident, Gluetun's HTTP health endpoint returned errors while its
TCP listener remained open. The former TCP liveness probe did not restart it.
[PR #383](https://github.com/edgard/home-ops/pull/383) moved liveness to the
HTTP health endpoint and added a rendered-workload policy guard. Changes to
the qBittorrent pod should preserve VPN failure detection and verify actual
traffic isolation after reconnects. The rendered probe regression guard is
retired; native schema validation does not prove VPN failure detection.

## Sources

- [Gluetun health fix, PR #383](https://github.com/edgard/home-ops/pull/383)
- [qBittorrent values](../../../apps/media/qbittorrent/values.yaml)

## Related pages

- [qBittorrent](../apps/media/qbittorrent.md)
- [Validation](../architecture/validation.md)
