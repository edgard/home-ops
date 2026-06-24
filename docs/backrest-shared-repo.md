---
# Backrest Shared Restic Repo

Backrest is the backup scheduler, restore UI, and shared-repo coordinator. The
existing `restic` app remains the restic REST backend and keeps serving the
shared repository at `restic.edgard.org`.

## Initial Server Setup

1. Sync the new `backrest` app and open `https://backrest.edgard.org`.
2. Create the initial admin user. Store the credentials outside Git.
3. Set the instance ID to `homelab`.
4. Add the existing repository:
   - Repository URI: `rest:http://restic.selfhosted.svc.cluster.local:8000/`
   - Environment variables are already present in the pod:
     `RESTIC_PASSWORD`, `RESTIC_REST_USERNAME`, and `RESTIC_REST_PASSWORD`.
5. Enable the repo's Shared toggle.
6. Index snapshots and confirm the expected legacy host families are visible:
   `homelab`, `edgards-mini`, and `edgard-desktop`.

## Kubernetes Plan

Create a plan for cluster appdata:

- Path: `/data/appdata`
- Schedule: `0 3 * * *`
- Retention: daily 14, weekly 8, monthly 12, yearly 3

Backrest adds its own plan tags to new snapshots. Do not assume this retention
policy expires older raw-restic snapshots created by the previous CronJobs.

## Shared Repo Clients

Generate short-lived pairing tokens from the server for each workstation. Grant
clients:

- `Receive Shared Repos`
- `Read Operations`

The shared repo is read-only in client configuration. Clients run backup plans
against it, while server-side forget, prune, and check remain owned by the
`homelab` Backrest instance.

## Kubernetes Restore Procedure

Backrest mounts `/mnt/spool/appdata` read-write through the `restic-appdata`
claim so direct restores are possible from the UI.

Before restoring application data:

1. Stop or suspend the target app.
2. Optionally create a fresh Backrest backup or TrueNAS snapshot.
3. Restore the selected path in Backrest.
4. Restart or resync the app.
5. Verify the app starts cleanly and contains the expected data.

Backrest should stay trusted-network-only and strongly authenticated because it
can write to all appdata.

## CLI Fallback

For NFS-backed appdata restores outside Backrest, keep excluding xattrs:

```sh
restic restore <snapshot> --exclude-xattr '*' --target <restore-root>
```

Restoring xattrs to this NFS appdata path has previously failed on
`system.nfs4_acl`.

## Cutover

Keep the existing `restic` app backup and maintenance CronJobs until all of the
following pass:

1. Backrest indexes the existing repo.
2. A manual Kubernetes appdata backup succeeds.
3. A harmless direct restore to a test path under `/data/appdata` succeeds.
4. macOS and Windows clients pair and complete one successful backup each.
5. Server-side maintenance has been verified.

After cutover, remove only the old backup and maintenance CronJobs from the
`restic` app. Keep rest-server, its PVCs, DNS, and LAN IP.
