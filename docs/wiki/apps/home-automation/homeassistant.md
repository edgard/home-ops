# Home Assistant

Purpose: Home Assistant hosts home automation state and integrations, with a local Matter controller.
Status: current. Reviewed against: `e9e0be76723b83306553122a3f5b0e4e8db832d8`.

## Dependencies

Uses the shared Gateway, NFS appdata, a repository ConfigMap, and an app-owned
Multus attachment. Home Assistant and Matter.js Server share one pod and its
LAN interface. Their rollouts, pod recreation, and readiness are coupled:
a failing Matter readiness probe can withdraw Home Assistant's service endpoint.

## Data and recovery

Home Assistant configuration and Matter controller state use separate app-owned
PVCs, mounted only into their respective containers. The Matter volume contains
fabric credentials and pairing identity; preserve it across container and pod
replacement. The existing filesystem group supplies volume access to the
non-root Matter process. Never publish the volume contents or commissioning codes.

Both claims use appdata storage covered by Restic. Preview
`task restic:restore app=homeassistant` and confirm both claims appear before a
restore. Restore matching Home Assistant and Matter state from one snapshot;
before a server downgrade that changes storage format, restore a compatible
state backup. See the [restore runbook](../../operations/restic-backup-restore.md).

The configuration claim's name is explicitly pinned to the original
`homeassistant` claim. App-template otherwise appends persistence identifiers
when another PVC is added, which would select a fresh configuration volume.
Both claims disable Argo pruning and deletion; retire them explicitly only after
verifying the retained data and its backup.

## Networking and monitoring

The Home Assistant route remains on the shared Gateway. The app-owned
[network attachment](../../../../apps/home-automation/homeassistant/manifests/homeassistant-matter-lan.networkattachmentdefinition.yaml)
chains the bridge/static-IP setup with CNI tuning. It preserves the LAN address,
gateway, MAC and interface while enabling IPv6 autoconfiguration and advertised
Thread route learning inside the pod. It changes neither the shared attachment
nor the Talos host's IPv6 forwarding or router-advertisement settings.

Matter's WebSocket and dashboard listen only on pod loopback. No Matter ingress
or Service port is exposed. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml)
for Home Assistant's explicit uptime target; the warning-light package consumes confirmed alerts.

## Gatus warning light

The [alert-light package](../../../../apps/home-automation/homeassistant/manifests/homeassistant-gatus-alert-light.configmap.yaml)
owns `light.office_office_mood_light` while a confirmed Gatus warning is open.
It applies steady red at 50% brightness after five consecutive failed checks.
Two successful checks clear an endpoint; the original on/off state, brightness,
and active color mode return only after every open warning clears.
Manual light changes during a warning are replaced by red on the next worker
run. The saved original state is preserved across duplicates and overlapping alerts.

Repository configuration enables packages and mounts this package and its Jinja
macros read-only into Home Assistant alone. UI-managed automations, scripts and
scenes remain on the configuration claim. A queued worker serializes Gatus events
and reconciliation at startup, every 30 seconds and after bulb availability.
It checks fresh ordered Gatus history to repair missed deliveries and reject
stale recovery events. API failures, missing rows and insufficient history retain
open warnings; an unavailable bulb defers snapshotting or restoration.

Persistent `input_boolean.gatus_alert_*` helpers hold endpoint flags and
`input_text.gatus_alert_light_snapshot` holds compact restoration JSON. No helper
has an `initial` value. Ordinary restarts restore them from the existing HA claim;
this is not crash-atomic incident storage. Gatus's memory history can be lost,
so extended simultaneous downtime can require operator recovery.

When retiring an endpoint, first confirm recovery and an empty snapshot, then
remove its Gatus entry and mapped helper together. Do not treat a missing API
row as recovery. If a snapshot is missing while an open warning is already red,
the worker stops snapshot capture: restore the intended light state explicitly
before clearing the known incident after verifying Gatus health.

For rollback, disable the dispatch automation, finish or manually verify the
saved restoration, then revert package/provider wiring through GitOps. Preserve
helpers until recovery is verified; retain both PVCs and the Apple Home fabric.
Revoke the dedicated provider token only after disabling its consumer. See
[Gatus credentials](../platform-system/gatus.md#home-assistant-delivery).

## Matter setup and acceptance

The [HAOS add-on build](https://github.com/home-assistant/addons/blob/master/matter_server/build.yaml)
identifies the upstream base image. The
[add-on startup implementation](https://github.com/home-assistant/addons/blob/master/matter_server/rootfs/etc/s6-overlay/s6-rc.d/matter-server/run)
is the reference for storage, fabric/vendor IDs, logging and time synchronization.
This deployment uses that upstream server directly, without Supervisor wrappers,
beta installs, host Bluetooth or D-Bus. Multus and CNI tuning replace host
networking and NetworkManager route handling. Kubernetes remains a self-managed
installation, outside Home Assistant's supported HAOS Matter installation path.

Before rollout or enabling device time synchronization, check
`talosctl -n <node> get timestatus` reports synchronized time. The container flag
assumes Talos maintains NTP; it does not dynamically query Supervisor's
`time_sync: auto` status. If the node is unsynchronized, resolve it before rollout
or disable device time synchronization. Image updates require manual comparison
with the HAOS baseline and the installed Home Assistant Matter client.

1. After rollout, verify the pod's LAN interface has usable IPv6 addresses,
   discovers the Thread border router, and learns a route to the Thread network.
   Healthy HTTP probes alone do not prove device connectivity.
2. In Home Assistant, add the Matter integration under Settings > Devices &
   services. Choose an existing server and enter `ws://127.0.0.1:5580/ws`.
3. In Apple Home, open a fresh pairing window for the existing Matter bulb.
   In the Home Assistant iPhone app, add an already-used Matter device and follow
   the Apple Home sharing flow. Keep the existing Apple fabric; do not factory reset.
   See [Home Assistant's sharing procedure](https://www.home-assistant.io/integrations/matter/#sharing-a-device-from-another-platform-with-home-assistant).
4. Verify on/off, brightness, white temperature and color controls from both
   ecosystems, including state feedback. Restore the original light state after testing.
5. Restart Matter Server and recreate the whole pod. Confirm the same device
   returns without pairing again, routes are relearned, and Home Assistant's
   existing route and integrations recover.
6. Verify a fresh Restic snapshot contains both claim paths and the restore
   preview selects them. Keep pairing codes and credentials out of reports.

For temporary dashboard diagnostics, run:

```sh
kubectl -n home-automation port-forward deployment/homeassistant 5580:5580
```

Open `http://127.0.0.1:5580` locally and stop the forward afterward. Do not bind
it to all interfaces. The dashboard is an upstream diagnostic tool, not an
additional publicly routed app.

For rollback, revert the container and network changes through GitOps while
retaining the Matter PVC and its backup. Do not delete controller identity to
repair connectivity. Apple Home pairing remains independent; delete only the
Home Assistant fabric if deliberately retiring this controller.

## Sources

- [App metadata](../../../../apps/home-automation/homeassistant/app.yaml)
- [Helm values](../../../../apps/home-automation/homeassistant/values.yaml)
- [Network attachment](../../../../apps/home-automation/homeassistant/manifests/homeassistant-matter-lan.networkattachmentdefinition.yaml)
- [Raw manifests](../../../../apps/home-automation/homeassistant/manifests)
- [Matter.js Server](https://github.com/matter-js/matterjs-server) — upstream controller and diagnostic dashboard.
- [CNI tuning](https://www.cni.dev/plugins/current/meta/tuning/) — network-namespace sysctls and interface substitution.
- [Matter networking requirements](https://github.com/matter-js/matterjs-server/blob/main/docs/os_requirements.md) — IPv6 and Thread route acceptance.
- [Renovate configuration](../../../../.renovaterc.json5) — manual server-update review.

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
- [Backup and recovery](../../architecture/backup-recovery.md)
