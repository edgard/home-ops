# Uptime monitoring

Purpose: explain routed-app coverage and the limit of in-cluster alerts.
Status: current. Reviewed against: `e9e0be76723b83306553122a3f5b0e4e8db832d8`.

Gatus is the configured uptime checker and Telegram alert engine. Its native
Home Assistant provider also drives the [office warning light](../apps/home-automation/homeassistant.md#gatus-warning-light). Its targets
are explicit in its values; route coverage validation compares HTTP targets
with rendered and raw HTTPRoutes. Special health paths for Jellyfin and
CrossWatch are deliberate. Gatus stores status in memory, so the single-node
cluster cannot alert through it during a complete node outage.

The [Gatus transition decision](../decisions/gatus-transition.md) records why
the older observability stack was retired. This wiki does not store changing
health results; query the running endpoint and its logs when investigating.

The light represents confirmed five-failure/two-success incidents, including
overlapping endpoint failures. A fresh-history reconciliation repairs missed
events; missing, stale or insufficient data retains the previous warning.
An open warning's saved light state survives ordinary HA restarts. Both Gatus
and HA must be running for live changes; neither provides independent node-outage
notification. Maintenance windows or threshold overrides need matching changes
in the history reducer before use.

## Sources

- [Gatus values](../../../apps/platform-system/gatus/values.yaml)
- [Route inventory collection](../../../tests/config/kubernetes/test_rendered.py)
- [Route coverage assertions](../../../tests/config/kubernetes/test_rendered.py)
- [Uptime contract](../../../tests/config/kubernetes/test_resources.py)

## Related pages

- [Networking](networking.md)
- [Gatus decision](../decisions/gatus-transition.md)
- [Validation](validation.md)
