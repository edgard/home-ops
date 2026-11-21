# Grafana

Purpose: serve host, workload and uptime dashboards and evaluate alerts against VictoriaMetrics.
Status: current. Reviewed against: `cdb7a398deaa06451737a5a43e895942443e7d3c` and this revision.

Use the private Gateway route for Grafana. Git provisions the dashboards, data source and alerting configuration. A local telemetry volume holds SQLite and UI state across pod replacements. Pool loss requires reprovisioning and resets that state. Gatus owns production notifications during comparison.

## Credentials and status sharing

The ExternalSecret requires the Bitwarden items `grafana_admin_user`,
`grafana_admin_password`, `telegram_bot_token` and `telegram_chat_id`.
Grafana reads the admin settings when it initializes SQLite. For rotation,
change the persisted admin account in Grafana and update its matching Bitwarden
items in the same maintenance window. Wait for the ExternalSecret to refresh
and run a full Grafana application sync. Verify the sharing Job succeeds and
the shared uptime dashboard opens logged out. Replacing only the Bitwarden
item can leave the sharing Job unable to authenticate.

## Sources

- [Application](../../../../apps/platform-system/grafana/app.yaml)
- [Helm values](../../../../apps/platform-system/grafana/values.yaml)

## Related pages

- [Monitoring and cutover](../../architecture/uptime.md)
