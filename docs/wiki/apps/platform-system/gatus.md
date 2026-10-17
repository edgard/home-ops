# Gatus

Purpose: Gatus checks explicit app, DNS, and internet targets and sends Telegram and Home Assistant alerts.
Status: current. Reviewed against: `e9e0be76723b83306553122a3f5b0e4e8db832d8`.

## Dependencies

It relies on routes, DNS, and a credential ExternalSecret but does not have persistent status storage.

## Data and recovery

The [values](../../../../apps/platform-system/gatus/values.yaml) select memory
storage and disable persistence. Uptime history is lost when this instance
restarts.

## Networking and monitoring

The status page is routed through the shared Gateway. Gatus targets are
configured in [its values](../../../../apps/platform-system/gatus/values.yaml);
the status page does not monitor itself.

## Home Assistant delivery

The native Home Assistant provider posts `gatus_alert` events over the internal
Service to the [warning-light package](../home-automation/homeassistant.md#gatus-warning-light).
It retains Telegram on every permanent target, sharing the five-failure and
two-success policy and recovery notification setting. Gatus sends nested
`event_data` with the exact `group/name` endpoint identity. Failed triggers are
retried on later failures, but failed recovery delivery is not retried; Home
Assistant therefore also reconciles retained API history.

Create a named long-lived HA access token for Gatus under an administrator
account and store it directly as `homeassistant_gatus_token` in the existing
Bitwarden `home-ops` project. The installed HA event API requires administrator
access; a non-admin token cannot post these events. The token inherits broad
account permissions and is not event-scoped. Prefer a dedicated account for
independent revocation; native-provider delivery cannot use a least-privilege
event-only token. The existing read-only machine account needs no broader access.
The [credential ExternalSecret](../../../../apps/platform-system/gatus/manifests/gatus-credentials.externalsecret.yaml)
delivers `HOMEASSISTANT_GATUS_TOKEN` to the existing Gatus Secret. Never put the
value in Git, chat or diagnostic output.

Provision and verify delivery before enabling the provider. To rotate, create a
replacement token, update the same Bitwarden item, reconcile ESO and verify Gatus
reload and authenticated delivery before revoking the old token in HA. Disable
the provider before revocation during retirement; leave Telegram configured.

Maintenance suppression, different check intervals and per-endpoint threshold
or provider overrides require corresponding reconciliation changes and tests.
Current contracts reject them to avoid disagreement between notifications and
history reconstruction. See the [uptime explanation](../../architecture/uptime.md).

## Operational note

A complete single-node outage cannot be reported by this in-cluster checker.

## Sources

- [HA event API](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/api/__init__.py) — administrator authorization required for event posting.
- [Native HA provider](https://github.com/TwiN/gatus/blob/v5.37.0/alerting/provider/homeassistant/homeassistant.go) — authenticated nested event delivery.
- [Alert delivery lifecycle](https://github.com/TwiN/gatus/blob/v5.37.0/watchdog/alerting.go) — trigger retries and recovery behavior.

- [App metadata](../../../../apps/platform-system/gatus/app.yaml)
- [Helm values](../../../../apps/platform-system/gatus/values.yaml)
- [Raw manifests](../../../../apps/platform-system/gatus/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Networking](../../architecture/networking.md)
- [Gatus transition](../../decisions/gatus-transition.md)
- [Uptime monitoring](../../architecture/uptime.md)
