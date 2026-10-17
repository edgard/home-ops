# Gatus alert light with automatic restoration

## Intent and scope

Use the existing IKEA KAJPLATS Matter light as a steady red indicator while any
configured Gatus endpoint has a confirmed alert. Automatically restore its saved
on/off state, brightness, and color after the final alert resolves. Preserve
Apple Home control and existing Telegram notifications. No additional service,
Home Assistant custom integration, or change to Matter networking is required.

The target is `light.office_office_mood_light`. Proposed warning brightness
is 50%, with RGB `[255, 0, 0]`; this is a default implementation choice.

## Existing behavior and source findings

- Gatus evaluates explicit targets and sends Telegram alerts after five failed
  checks, resolving after two successful checks. Its state is currently in memory.
- The installed Home Assistant includes the native Gatus integration. Its binary
  sensors expose the latest check, rather than the confirmed alert state.
- Gatus also supports a Home Assistant alert provider. It posts to
  `/api/events/gatus_alert` with a Bearer token. The request contains nested
  `event_data`; its endpoint identifier is `group/name`, not simply the name.
- Failed trigger deliveries are retried on subsequent failed checks. Failed
  resolved deliveries are not retried. Events alone therefore cannot reliably
  restore the bulb after Home Assistant downtime.
- Dynamically created Home Assistant scenes disappear on scene reload or restart.
  The original light state must instead be stored in persistent helpers.

## Approach selection

1. Native Home Assistant Gatus sensors: fewest credentials and useful dashboard
   visibility, but their latest-check status is not the confirmed alert state.
   Reproducing Gatus thresholds would require separate logic anyway.
2. Gatus alert events alone: exact notification thresholds and little wiring,
   but a missed resolved message can leave the bulb red indefinitely.
3. Recommended: Gatus alert events plus periodic recovery reconciliation, using
   native Home Assistant configuration and persistent helpers. This retains
   confirmed-alert semantics and repairs delivery gaps without another service.

## Configuration ownership

Add a repository-owned Home Assistant package, mounted read-only alongside the
existing configuration. Load it through `homeassistant.packages`. Preserve the
existing UI-managed automations, scripts, and scenes on the configuration PVC.

The package owns persistent per-endpoint active-alert boolean helpers, a compact
JSON light-state snapshot helper, serialized alert-processing scripts, and the
startup/periodic reconciliation automation. Helper IDs map explicitly to the
configured Gatus endpoint identifiers; tests enforce complete coverage and no
collisions. Existing helpers are restored, rather than reset with `initial`.

Add the Home Assistant provider alongside Telegram in Gatus. Both providers use
the same five-failure/two-success policy, including recovery notifications. Use
`http://homeassistant.home-automation.svc:8123` for event delivery.

A dedicated named Home Assistant access token is stored once in the existing
Bitwarden project and delivered to Gatus through its existing ExternalSecret.
Never commit its value or include it in diagnostics. Provision the credential
before enabling the new provider; do not deploy a missing-secret configuration.
Credential creation/storage is an operator step if the available account cannot
write Bitwarden secrets.

## State transitions

All event handling and reconciliation must pass through one queued worker so
simultaneous endpoints cannot overwrite the saved state or prematurely restore.

1. Validate a known endpoint identifier and `triggered`/`resolved` status.
2. On the first alert, capture the light's current available state before issuing
   any light command. Save only the fields needed to restore its current color
   mode, brightness, and on/off state. Bound the snapshot to helper capacity.
3. Set that endpoint's active flag. Duplicate trigger events must not overwrite
   the original snapshot.
4. While any endpoint remains active, apply steady red at the warning brightness.
   A resolved event for one endpoint must not restore while another is active.
5. Before the final restoration, require a fresh Gatus response confirming
   recovery of the affected endpoints. This prevents a delayed resolved event
   from clearing a newer failure. If confirmation is unavailable, retain the
   warning and retry. Restore the saved state; if it was off, return it to off.
   Preserve the snapshot until restoration succeeds; retry if the bulb is
   temporarily unavailable. Clear the snapshot only after confirmed recovery.
6. If a light cannot be safely snapshotted, defer changing it and retry when it
   becomes available. Do not invent an original state or capture an unavailable
   state. Malformed events must not change helpers or the light.

## Reconciliation and restart behavior

On Home Assistant startup and every 30 seconds, read
`http://gatus.platform-system.svc/api/v1/endpoints/statuses` through a native
Home Assistant REST command. Serialize this with event processing.

Use only fresh successful API responses with known endpoint identities and
chronologically ordered valid check results. For each endpoint:

- Two consecutive recent successful checks clear a previously active flag,
  repairing a missed resolved event.
- A confirmed run of five failed checks in retained history activates the flag,
  repairing a missed triggered event. Evaluate subsequent results in order so
  two successful checks after that run correctly resolve it.
- Without enough valid history to establish a transition, retain the last known
  flag. Missing endpoints, API failures, empty history, or unknown states must
  not be treated as recovery.

After flag reconciliation, retry any pending warning or restoration. A restart
must not replace the original saved state with the red warning state. Ordinary
Home Assistant and pod restarts retain helper state on the existing backed-up
configuration PVC.

The existing in-memory Gatus history limits reconstruction after extended
simultaneous downtime. This is an in-cluster indicator, not an independent
outage alarm: it cannot operate while Home Assistant or the single node is down.
No claim of durable Gatus incident history or crash-atomic storage is added.
The current configuration has no maintenance windows. Adding suppression or
per-endpoint threshold overrides later must update reconciliation and its tests;
otherwise polling could disagree with Gatus notification policy. Retiring an
endpoint must explicitly migrate/clear its known helper after confirming it is
removed, rather than interpreting a transient API omission as recovery.

## Verification

Focused tests must exercise configuration/template behavior for one alert,
concurrent alerts, duplicates, out-of-order or malformed payloads, correct nested
event data and group/name identity, both recovery thresholds, missed recovery,
missed trigger reconstruction, stale or unavailable API data, initially-off and
colored bulbs, unavailable light retries, and restart-safe snapshot handling.

Verify rendered package mounts remain isolated to Home Assistant, existing PVC
identities stay unchanged, all configured endpoints participate, Telegram remains
configured, and secret values remain external. Run Home Assistant's own
configuration validation in addition to repository tests.

After protected PR delivery, test the real Gatus provider with a temporary
controlled failing endpoint rather than taking down a production service. Prove
red-on-failure, overlapping alerts, restore-after-final-recovery, an initially-off
light, and restart recovery. Remove temporary targets and diagnostic resources.
Verify a fresh backup and restore preview still cover both application claims.

Update the Home Assistant, Gatus, uptime, and applicable recovery wiki pages,
source catalog, and log in the same implementation PR. October's semantic wiki
review is already recorded.

## Rollback

Disable only the new light automation/provider, restore the saved light state
when available, and preserve the helpers until recovery is verified. Revert the
package and Gatus changes through GitOps. Keep the Matter controller data and
Apple Home pairing intact. Revoke the dedicated token only after disabling its
consumer; leave Telegram unchanged.

## Sources

- [Gatus values](../../../apps/platform-system/gatus/values.yaml)
- [Gatus credential delivery](../../../apps/platform-system/gatus/manifests/gatus-credentials.externalsecret.yaml)
- [Home Assistant configuration](../../../apps/home-automation/homeassistant/manifests/homeassistant-config.configmap.yaml)
- [Home Assistant deployment](../../../apps/home-automation/homeassistant/values.yaml)
- [Gatus Home Assistant alert provider](https://github.com/TwiN/gatus/blob/v5.37.0/alerting/provider/homeassistant/homeassistant.go)
- [Gatus alert delivery/recovery](https://github.com/TwiN/gatus/blob/v5.37.0/watchdog/alerting.go)
- [Gatus endpoint identity](https://github.com/TwiN/gatus/blob/v5.37.0/config/endpoint/endpoint.go)
- [Home Assistant Gatus integration](https://www.home-assistant.io/integrations/gatus/)
- [Home Assistant scenes](https://www.home-assistant.io/integrations/scene/)
- [Persistent input text helpers](https://www.home-assistant.io/integrations/input_text/)
