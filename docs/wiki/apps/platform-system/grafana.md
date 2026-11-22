# Grafana

Purpose: serve host, workload and uptime dashboards and evaluate alerts against VictoriaMetrics.
Status: current. Reviewed against: `cdb7a398deaa06451737a5a43e895942443e7d3c` and this revision.

Use the private Gateway route for Grafana. Git provisions the dashboards, data source and alerting configuration. The appdata volume holds SQLite and UI state across pod replacements. The platform-system Restic backup preserves it for pool recovery. Grafana routes confirmed incidents and recoveries to Telegram. The status hostname redirects to the uptime dashboard after sign-in. Anonymous access and public dashboard sharing are disabled.

## Credentials and access

The ExternalSecret requires the Bitwarden items `grafana_admin_user`,
`grafana_admin_password`, `telegram_bot_token` and `telegram_chat_id`.
Grafana reads the admin settings when it initializes SQLite. For rotation,
change the persisted admin account in Grafana and update its matching Bitwarden
items in the same maintenance window. Wait for the ExternalSecret to refresh
and verify the rotated login. Create named operator accounts in Grafana.
Their roles and credentials are stored in the Grafana database and included
in its Restic backup.

## Sources

- [Application](../../../../apps/platform-system/grafana/app.yaml)
- [Helm values](../../../../apps/platform-system/grafana/values.yaml)

## Related pages

- [Monitoring and cutover](../../architecture/uptime.md)
