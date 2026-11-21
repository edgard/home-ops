# Use Gatus for uptime

Purpose: record the move to explicit, minimal in-cluster uptime checks.
Status: historical. Reviewed against: `f73a66d4d60b9fd7e373eb1cfcbde4e8df270083`.

[PR #397](https://github.com/edgard/home-ops/pull/397) introduced explicit
Gatus targets, Telegram alerting, and route coverage validation.
[PR #398](https://github.com/edgard/home-ops/pull/398) removed the old metrics
and searchable-log stack after Gatus was validated. Later cleanup grouped the
checks and restricted residual metrics listeners in
[PR #399](https://github.com/edgard/home-ops/pull/399) and
[PR #402](https://github.com/edgard/home-ops/pull/402).

Gatus targets were explicit in values, with no route discovery annotation.
The tradeoff is that an in-cluster service cannot alert when the only node is
fully unavailable. Current probe maintenance is documented in [uptime monitoring](../architecture/uptime.md).

## Sources

- [Historical Gatus values](https://github.com/edgard/home-ops/blob/cdb7a398deaa06451737a5a43e895942443e7d3c/apps/platform-system/gatus/values.yaml)
- [Transition PRs #397](https://github.com/edgard/home-ops/pull/397) and [#398](https://github.com/edgard/home-ops/pull/398)

## Related pages

- [Uptime monitoring](../architecture/uptime.md)
- [Networking](../architecture/networking.md)
