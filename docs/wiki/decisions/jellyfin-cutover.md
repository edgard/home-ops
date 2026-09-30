# Replace Plex with Jellyfin

Purpose: preserve the migration choices relevant to today's media service.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

[PR #411](https://github.com/edgard/home-ops/pull/411) staged Jellyfin with
persistent configuration, temporary cache, read-only media, HTTPS routing,
and health checks. During library scans, HTTP health could stall without the
listener failing, so [PR #412](https://github.com/edgard/home-ops/pull/412)
split TCP liveness from HTTP readiness. Plex was removed after the cutover in
[PR #413](https://github.com/edgard/home-ops/pull/413). Direct LAN discovery
and the HTTPS route coexist after
[PR #414](https://github.com/edgard/home-ops/pull/414).

CrossWatch and Recyclarr are related media integrations. Future media-server
changes should inspect their configuration and checks together with Jellyfin.

## Sources

- [Jellyfin values](../../../apps/media/jellyfin/values.yaml)
- [CrossWatch values](../../../apps/media/crosswatch/values.yaml)
- [Recyclarr configuration](../../../apps/media/recyclarr/manifests/recyclarr-config.configmap.yaml)
- [Migration PRs #411](https://github.com/edgard/home-ops/pull/411), [#412](https://github.com/edgard/home-ops/pull/412), [#413](https://github.com/edgard/home-ops/pull/413), and [#414](https://github.com/edgard/home-ops/pull/414)

## Related pages

- [Jellyfin](../apps/media/jellyfin.md)
- [CrossWatch](../apps/media/crosswatch.md)
- [Networking](../architecture/networking.md)
