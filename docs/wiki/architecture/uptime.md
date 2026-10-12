# Uptime monitoring

Purpose: explain routed-app coverage and the limit of in-cluster alerts.
Status: current. Reviewed against: `6aeb7489ec815222523c414983c8678bb5fd93bc`.

Gatus is the configured uptime checker and Telegram alert engine. Its targets
are explicit in its values; route coverage validation compares HTTP targets
with rendered and raw HTTPRoutes. Special health paths for Jellyfin and
CrossWatch are deliberate. Gatus stores status in memory, so the single-node
cluster cannot alert through it during a complete node outage.

The [Gatus transition decision](../decisions/gatus-transition.md) records why
the older observability stack was retired. This wiki does not store changing
health results; query the running endpoint and its logs when investigating.

## Sources

- [Gatus values](../../../apps/platform-system/gatus/values.yaml)
- [Route inventory collection](../../../ansible/roles/kubernetes_validation/tasks/check-uptime.yml)
- [Route coverage policy](../../../policy/kubernetes/route_coverage.rego)
- [Uptime contract](../../../ansible/tests/uptime.yml)

## Related pages

- [Networking](networking.md)
- [Gatus decision](../decisions/gatus-transition.md)
- [Validation](validation.md)
