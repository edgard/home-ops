# Uptime monitoring

Purpose: explain routed-app coverage and the limit of in-cluster alerts.
Status: current. Reviewed against: `f73a66d4d60b9fd7e373eb1cfcbde4e8df270083`.

Gatus is the configured uptime checker and Telegram alert engine. Its targets
are explicit in its values; review HTTP targets against routes when changing
apps. Automated route-coverage assertions are retired. Special health paths for Jellyfin and
CrossWatch are deliberate. Gatus stores status in memory, so the single-node
cluster cannot alert through it during a complete node outage.

The [Gatus transition decision](../decisions/gatus-transition.md) records why
the older observability stack was retired. This wiki does not store changing
health results; query the running endpoint and its logs when investigating.

## Sources

- [Gatus values](../../../apps/platform-system/gatus/values.yaml)

## Related pages

- [Networking](networking.md)
- [Gatus decision](../decisions/gatus-transition.md)
- [Validation](validation.md)
