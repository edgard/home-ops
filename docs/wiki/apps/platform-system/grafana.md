# Grafana

Purpose: serve host, workload and uptime dashboards and evaluate alerts against VictoriaMetrics.
Status: current. Reviewed against: `7fad7f2565192a6b198cf345b155063f0c898afd` and this revision.

Use the private Gateway route for Grafana. Git provisions the dashboards, data source and alerting configuration. The appdata volume holds SQLite and UI state across pod replacements. The platform-system Restic backup preserves it for pool recovery. Grafana routes confirmed incidents and recoveries to Telegram. The status hostname redirects to the uptime dashboard after sign-in. Anonymous access and public dashboard sharing are disabled.

## Dashboards and notifications

The [dashboard definitions](../../../../apps/platform-system/grafana/manifests/grafana-dashboards.configmap.yaml)
own the uptime, Talos and workload views. Keep the uptime dashboard UID and
its `target` variable stable so Telegram links open the affected target.
The [alert configuration](../../../../apps/platform-system/grafana/manifests/grafana-alerts.configmap.yaml)
provisions the rules, Telegram contact point and message format. See the
[monitoring runbook](../../architecture/uptime.md) for how to interpret the results.

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
