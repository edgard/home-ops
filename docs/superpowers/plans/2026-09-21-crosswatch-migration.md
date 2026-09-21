# CrossWatch Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken Trakt-dependent PlexTraktSync path with CrossWatch's local tracker, import the user's Trakt watch history and ratings, and record future Plex watches automatically.

**Architecture:** One CrossWatch deployment in `media` stores SQLite data and its encryption key on a single `nfs-fast` claim. A Plex Watcher writes to the built-in tracker; a one-time Trakt ZIP import seeds it. CrossWatch full backups and the existing Restic appdata backup protect the data. Expose the UI only after app authentication is set, and remove PlexTraktSync only after import and event verification.

**Tech Stack:** Kubernetes, Argo CD ApplicationSet, bjw-s app-template 5.2.1, CrossWatch 0.12.3, Plex, NFSv4, Restic, VictoriaMetrics Blackbox VMProbe.

**Spec:** `docs/superpowers/specs/2026-09-21-crosswatch-migration-design.md`

## Global Constraints

- All repository changes go through PRs; never commit to `master`.
- Use `ghcr.io/cenodude/crosswatch:0.12.3`, one `Recreate` replica, UID/GID 1000, `TZ=Europe/Warsaw`, port 8787, and a 5 GiB `nfs-fast` claim mounted at `/config`.
- Do not expose the HTTPRoute before app authentication is configured through a local port-forward.
- Configure one Plex-to-local Watcher for the intended Plex user, autostart, and an 80% watched threshold. Do not enable reverse Plex writes, recurring Trakt sync, or Trakt API authorization.
- Import `~/Downloads/trakt-export-edgard.zip` without editing it. Reconcile 9,978 history and 35 rating rows. Review three history timestamps in 1970.
- CrossWatch backups must use `scope: full` at 02:00 Europe/Warsaw, keep no more than ten local ZIPs, and be included in the existing 03:00 Restic appdata snapshot.
- Keep the PlexTraktSync PVC and original Trakt ZIP for rollback. Add and verify `argocd.argoproj.io/sync-options: Delete=false` on the old chart-generated PVC before deleting its Argo app. Do not remove the old workloads until a new Plex watch reaches CrossWatch and survives a restart.
- SQLite WAL on NFS remains a documented durability risk. Do not scale writers above one; stop writes and move storage if lock, I/O, or corruption errors appear.
- Run `task deps` before `task lint` in this fresh worktree. Merge only a verified exact head after the required PR gates pass, then verify Argo CD and live application behavior.

## Review Focus

These inputs and failure modes have explicit checks in the owning tasks:

1. **Unwritable `/config` or wrong UID:** Task 1 checks pod startup, file ownership, and a writable mount before account setup.
2. **Anonymous access after route exposure:** Task 2 checks unauthenticated API denial, authenticated login, and the Gateway path.
3. **Expired preview or duplicate Trakt events:** Task 3 records row statuses before commit, re-previews if the session expires, and reconciles rather than retrying blindly.
4. **Odd 1970 dates and unmatched IDs:** Task 3 inspects those rows plus representative movies, episodes, rewatches, and ratings before and after import.
5. **Backup ZIP that copies raw SQLite files:** Task 3 inspects `database_snapshots`, validates the archive, and proves a disposable restore before cutover.

---

## File map and review boundaries

- `apps/media/crosswatch/app.yaml`: ApplicationSet chart metadata and sync wave.
- `apps/media/crosswatch/values.yaml`: private deployment, service, probes, security, PVC; Task 2 adds the route.
- `apps/media/plextraktsync/values.yaml`: Task 1 annotates its existing PVC for retention before Task 4 deletes the app.
- `apps/platform-system/prometheus-blackbox-exporter/manifests/prometheus-blackbox-exporter-http.vmprobe.yaml`: Task 2 adds the route target.
- `docs/superpowers/specs/2026-09-21-crosswatch-migration-design.md`: approved behavior and cutover criteria.
- `docs/superpowers/plans/2026-09-21-crosswatch-migration.md`: implementation checklist and verification record.
- `apps/media/plextraktsync/`: Task 4 removes the old app metadata, values, ConfigMap, and ExternalSecret; its PVC is retained in the NFS provisioner.

Task 1 can be reviewed and merged as the initial deployment PR. Task 2 is a separate route/probe PR after private bootstrap. Task 3 changes live CrossWatch state but no Git files. Task 4 is a separate cutover PR. Keep each PR's exact-head validation and live verification evidence in its PR description or a concise comment, without tokens, passwords, archive contents, or private viewing history.

### Task 1: Deploy private CrossWatch

**Files:** Create `apps/media/crosswatch/app.yaml` and `apps/media/crosswatch/values.yaml`; modify `apps/media/plextraktsync/values.yaml` to protect its existing PVC; update draft PR #386 with these files.

**Interfaces:** Produces `deployment/crosswatch`, `service/crosswatch` on port 8787, and PVC `crosswatch-config` in namespace `media`. No external route exists yet. Task 2 consumes these resources.

- [ ] **Step 1: Add the ApplicationSet metadata.** Create `apps/media/crosswatch/app.yaml`:

```yaml
---
chart:
  repo: oci://ghcr.io/bjw-s-labs/helm/app-template
  path: "."
  version: 5.2.1
sync:
  wave: "0"
```

- [ ] **Step 2: Add the private workload.** Create `apps/media/crosswatch/values.yaml` with the repository's app-template field order:

```yaml
---
defaultPodOptions:
  securityContext:
    fsGroup: 1000
    fsGroupChangePolicy: OnRootMismatch
    runAsGroup: 1000
    runAsNonRoot: true
    runAsUser: 1000
controllers:
  main:
    annotations:
      reloader.stakater.com/auto: "true"
    type: deployment
    replicas: 1
    strategy: Recreate
    containers:
      app:
        image:
          repository: ghcr.io/cenodude/crosswatch
          tag: 0.12.3
        env:
          TZ: Europe/Warsaw
        ports:
          - name: http
            containerPort: 8787
        probes:
          startup:
            enabled: true
            custom: true
            spec:
              httpGet:
                path: /healthz
                port: http
              periodSeconds: 10
              failureThreshold: 30
          liveness:
            enabled: true
            custom: true
            spec:
              httpGet:
                path: /healthz
                port: http
              periodSeconds: 30
          readiness:
            enabled: true
            custom: true
            spec:
              httpGet:
                path: /healthz
                port: http
              periodSeconds: 10
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop:
              - ALL
service:
  main:
    controller: main
    type: ClusterIP
    ports:
      http:
        enabled: true
        port: 8787
        targetPort: http
persistence:
  config:
    type: persistentVolumeClaim
    forceRename: crosswatch-config
    accessMode: ReadWriteOnce
    size: 5Gi
    annotations:
      argocd.argoproj.io/sync-options: Delete=false
    globalMounts:
      - path: /config
```

- [ ] **Step 3: Protect the old PVC.** In `apps/media/plextraktsync/values.yaml`, under `persistence.config`, add:

```yaml
    annotations:
      argocd.argoproj.io/sync-options: Delete=false
```

  This must render onto the PVC object, not the pod or Deployment. Argo CD documents `Delete=false` as preventing deletion of a resource when its Application is deleted. The NFS storage class's `Retain` reclaim policy alone preserves the PV data, not the PVC object.
- [ ] **Step 4: Check rendered behavior.** Run `task deps`, `task fmt`, and `task lint` in that order. Confirm rendered output has one deployment, one `crosswatch-config` PVC, one ClusterIP service, three `/healthz` probes, and **no HTTPRoute**. Confirm both the new and old PVCs render with `Delete=false`. If policy or schema validation rejects a field, fix the manifest and rerun the focused check plus `task lint`.
- [ ] **Step 5: Commit and submit.** Commit the three files on `codex-crosswatch-migration`, push, and let draft PR #386 run Format, Static Analysis, Ansible, Kubernetes, Terraform, and Quality Gate for that exact head. Review the diff for secrets and unrelated files. Merge through the protected PR workflow only after gates pass.
- [ ] **Step 6: Verify the private deployment.** Refresh Argo (`task argo:sync app=crosswatch` if ApplicationSet discovery is delayed), wait for `crosswatch` to be `Synced` and `Healthy`, and run:

```sh
kubectl -n media rollout status deployment/crosswatch --timeout=5m
kubectl -n media get deployment,service,pvc,pod -l app.kubernetes.io/name=crosswatch
kubectl -n media exec deployment/crosswatch -- sh -c 'id && test -w /config && ls -ld /config'
kubectl -n media logs deployment/crosswatch --since=15m
```

  Expected: one ready pod, bound PVC, UID 1000, writable `/config`, no database/permission errors. Query the service's `/healthz` via a temporary port-forward. Check both PVCs have the live `Delete=false` annotation before any old-app removal. The `.cw_master_key` is created when CrossWatch first encrypts a secret, so check for it after Plex authorization in Task 2.

### Task 2: Secure bootstrap, Plex Watcher, and external route

**Files:** Modify `apps/media/crosswatch/values.yaml` and `apps/platform-system/prometheus-blackbox-exporter/manifests/prometheus-blackbox-exporter-http.vmprobe.yaml` in a new PR. App account and provider settings are saved through CrossWatch UI on `/config`, not in Git.

**Interfaces:** Consumes Task 1 service/PVC. Produces authenticated `https://crosswatch.edgard.org` and a Plex-to-local Watcher with autostart. Task 3 consumes the connected local tracker and Plex source.

- [ ] **Step 1: Set app authentication privately.** Start `kubectl -n media port-forward service/crosswatch 8787:8787` on the operator machine. Open `http://127.0.0.1:8787`, let the user set a strong admin password in CrossWatch's first-run flow, then log out and log in again. Do not place the password in shell history or repository files.
- [ ] **Step 2: Test the auth boundary.** From the port-forward, confirm `/healthz` returns 200 and an unauthenticated request to a protected API such as `/api/import/options` is denied or redirected. Confirm the same API works in an authenticated browser session. Stop if anonymous access reaches private data.
- [ ] **Step 3: Connect providers and Watcher.** In the UI, connect the built-in CrossWatch tracker, complete the Plex PIN sign-in with the user, set the Plex server to `http://plex.media.svc.cluster.local:32400`, and select the intended Plex account. Configure a single Plex-to-CrossWatch Watcher with autostart, that user's filter, and 80% threshold; leave reverse writes and recurring Trakt sync disabled. Confirm `.cw_master_key` exists with mode 0600 on `/config` without printing it; confirm the Watcher is running and no auth errors appear in watcher logs. Restart `deployment/crosswatch` once and confirm the settings and running Watcher persist.
- [ ] **Step 4: Add route and probe.** Add this `route` block between `service` and `persistence` in `apps/media/crosswatch/values.yaml`:

```yaml
route:
  main:
    parentRefs:
      - name: gateway
        namespace: platform-system
        sectionName: https
    hostnames:
      - crosswatch.edgard.org
    rules:
      - backendRefs:
          - identifier: main
            port: 8787
```

  Add `https://crosswatch.edgard.org/healthz` to the `targets.staticConfig.targets` list in the Blackbox HTTP VMProbe. Use the existing DNS and Gateway conventions; do not add a direct internet ingress.
- [ ] **Step 5: Validate and merge the route PR.** Run `task fmt`, `task lint`, inspect the rendered HTTPRoute and VMProbe, then require all exact-head PR gates. Merge through the protected PR workflow. Verify Argo `Synced`/`Healthy`, authoritative DNS, Gateway route acceptance, browser login, unauthenticated API denial, and `probe_success=1` for the new target. `/healthz` alone does not prove the tracker works.

### Task 3: Import Trakt data and prove recovery

**Files:** No Git changes. Source archive: `/Users/edgard/Downloads/trakt-export-edgard.zip`. Store only aggregate counts and pass/fail evidence in the PR; do not commit the ZIP, its records, or credentials.

**Interfaces:** Consumes the authenticated UI and connected local tracker from Task 2. Produces imported watched history and ratings, a running Watcher, and validated recoverable backup state. Task 4 requires its acceptance evidence.

- [ ] **Step 1: Recheck the source and target.** Run a local ZIP integrity check (`python3 -m zipfile -t /Users/edgard/Downloads/trakt-export-edgard.zip`), verify the importer lists the connected default tracker, and confirm the archive is still within its upload/row limits. Verify no new Plex history event after the ZIP's latest 2026-06-02 event needs separate reconciliation.
- [ ] **Step 2: Capture a pre-import recovery point.** In CrossWatch Backups, create `scope: full`; validate the resulting archive and record its path. Configure the scheduled backup for 02:00 Europe/Warsaw, `scope: full`, active every day, at most ten local backups. Check the scheduler's displayed next run is before the 03:00 Restic backup, including the daylight-saving transition.
- [ ] **Step 3: Preview the Trakt ZIP.** In CrossWatch Import, select `Trakt export ZIP`, target the connected local tracker, and upload the original ZIP. Record preview status counts for all 9,978 history rows and 35 rating rows; inspect the three 1970 events, missing identities, unsupported rows, and any existing/duplicate events. Preview IDs are transient: if it expires, upload the same ZIP again and recheck counts before commit.
- [ ] **Step 4: Commit once and reconcile.** Import history and ratings, then record the commit report's imported, existing, duplicate, skipped, and failed counts. Account for every history and rating row by event ID or documented status. Inspect representative movie, episode, rewatch, rating, and 1970 entries in the tracker. If expected events are missing, stop cutover and resolve the precise report reason; do not blindly re-import.
- [ ] **Step 5: Verify backup integrity.** Create a post-import `scope: full` backup. Download or inspect its `manifest.json`: require `.cw_provider` contents, `config.json`, `.cw_master_key`, and database snapshot entries with `database_snapshots` matching the included SQLite DBs. Treat logged fallback raw DB copies as failure. Validate the ZIP through CrossWatch's backup validation feature.
- [ ] **Step 6: Prove restore and Restic coverage.** Start Docker Desktop on the operator Mac and run the same pinned CrossWatch image locally with a disposable Docker volume and loopback-only port 18787:

```sh
docker volume create crosswatch-restore-check
docker run --rm --name crosswatch-restore-check -p 127.0.0.1:18787:8787 -v crosswatch-restore-check:/config ghcr.io/cenodude/crosswatch:0.12.3
```

  The restored internal Plex hostname should not resolve from local Docker; verify that and stop the test if it can reach the production Plex server. Upload and restore the downloaded full ZIP at `http://127.0.0.1:18787`; check login, sample imported history/rating, and tracker configuration. Stop the container and run `docker volume rm crosswatch-restore-check`. Do not point the test instance at the production PVC. Run a fresh Restic backup from `cronjob/restic-backup` or wait for the 03:00 run; verify job success and that the newest `homelab`/`appdata` snapshot includes the CrossWatch PVC path and full ZIP. Use `task restic:restore app=crosswatch` in plan-only mode to confirm the restore mapping without changing production.
- [ ] **Step 7: Verify ongoing writes.** Observe a new real Plex watch or a disposable library item. Confirm exactly one new event in CrossWatch, restart the pod, and confirm the event remains and the Watcher autostarts. Inspect recent CrossWatch and Plex logs for auth, lock, I/O, and corruption errors. Keep PlexTraktSync resources until this check passes.

### Task 4: Retire PlexTraktSync after successful cutover

**Files:** Delete `apps/media/plextraktsync/app.yaml`, `apps/media/plextraktsync/values.yaml`, `apps/media/plextraktsync/manifests/plextraktsync-config.configmap.yaml`, and `apps/media/plextraktsync/manifests/plextraktsync-credentials.externalsecret.yaml` in a separate PR. Preserve the provisioned PVC and original Trakt ZIP.

**Interfaces:** Consumes Task 3's import, backup, and new-event evidence. Produces no active PlexTraktSync deployment or CronJob. CrossWatch is then the watched-status source.

- [ ] **Step 1: Check the cutover gate.** Confirm the import report reconciles the source, the real new watch survived a pod restart, a full backup and disposable restore passed, Restic captured the PVC, the old `plextraktsync` PVC has live `Delete=false`, and the CrossWatch route/probe and Argo app are healthy. If any check fails, stop here.
- [ ] **Step 2: Remove only Git-owned old resources.** Delete the four PlexTraktSync files listed above, leaving unrelated media apps and the PVC's NFS data untouched. Review the diff for accidental changes to Plex, Restic, or CrossWatch.
- [ ] **Step 3: Validate and merge.** Run `task fmt`, `task lint`, require all exact-head PR gates, and merge through the protected PR workflow. Wait for ApplicationSet pruning and verify the old deployment, CronJob, ConfigMap, and ExternalSecret are gone while the old `plextraktsync` PVC remains `Bound` for rollback.
- [ ] **Step 4: Verify alerts and app behavior.** Confirm old `invalid_grant`/failed-job alerts clear without silencing unrelated alerts. Recheck CrossWatch login, sample imported history, a new Watcher event, `probe_success=1`, recent logs, Argo `Synced`/`Healthy`, and the next full backup. Record any remaining issue distinctly from the retired Trakt integration.

## Recovery stop conditions

- If CrossWatch cannot write `/config` or shows SQLite lock/I/O/corruption errors, stop import and Watcher writes; inspect NFS and move the PVC to supported local/block storage before continuing.
- If auth or route checks expose private API data anonymously, remove/disable the HTTPRoute in Git and re-verify the app's auth state before re-exposure.
- If import counts do not reconcile, preserve the source ZIP and pre-import full backup; investigate mapping and row statuses before any second commit.
- If a full backup contains raw SQLite fallback copies or fails disposable restore, keep PlexTraktSync resources and correct backup/recovery before cutover.
- If a new Plex watch is missing or duplicated, inspect Watcher user selection and routes; do not retire PlexTraktSync until a clean event survives restart.
