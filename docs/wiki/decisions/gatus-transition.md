# Use Gatus for uptime

Purpose: record the move to explicit, minimal in-cluster uptime checks.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

[PR #397](https://github.com/edgard/home-ops/pull/397) introduced explicit
Gatus targets, Telegram alerting, and route coverage validation.
[PR #398](https://github.com/edgard/home-ops/pull/398) removed the old metrics
and searchable-log stack after Gatus was validated. Later cleanup grouped the
checks and restricted residual metrics listeners in
[PR #399](https://github.com/edgard/home-ops/pull/399) and
[PR #402](https://github.com/edgard/home-ops/pull/402).

Gatus targets stay explicit in values, with no route discovery annotation.
The tradeoff is that an in-cluster service cannot alert when the only node is
fully unavailable. Add a routed app to Gatus and the route coverage contract
rather than reinstating the retired discovery or observability stack.

## Sources

- [Gatus values](../../../apps/platform-system/gatus/values.yaml)
- [Route coverage check](../../../ansible/roles/kubernetes_validation/tasks/check-uptime.yml)
- [Transition PRs #397](https://github.com/edgard/home-ops/pull/397) and [#398](https://github.com/edgard/home-ops/pull/398)

## Related pages

- [Uptime monitoring](../architecture/uptime.md)
- [Networking](../architecture/networking.md)
