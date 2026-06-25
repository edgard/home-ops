---
# Shared Restic Backup And Restore Runbook

The `restic` app backs up Kubernetes appdata and serves the same repository used
by the macOS and Windows workstation backups. Kubernetes owns repository
maintenance; workstations only create backup snapshots.

Use this runbook when restoring Kubernetes appdata from the shared restic repo.

## Facts

| Item | Value |
| --- | --- |
| In-cluster repo | `rest:http://restic.selfhosted.svc.cluster.local:8000/` |
| Workstation repo | `rest:http://restic.edgard.org:8000/` |
| Repo storage | `/mnt/dpool/restic` |
| Appdata storage | `/mnt/spool/appdata` |
| Snapshot root | `/data/appdata` |
| PVC path | `/data/appdata/<namespace>/<pvc-name>` |
| Restore mount | `/restore/data/appdata` |

Auth uses `RESTIC_REST_USERNAME`, `RESTIC_REST_PASSWORD`, and `RESTIC_PASSWORD`.

Schedules:

- Backup: daily `0 3 * * *`
- Maintenance: weekly `0 4 * * 1`
- Retention: daily 14, weekly 8, monthly 12, yearly 3
- Maintenance scope: `forget --group-by host,paths,tags --prune`, then
  `check`, then `check --read-data-subset=10%`

Expected snapshot families:

```text
homelab         /data/appdata                    appdata
edgards-mini    /Users/edgard/Documents          documents
edgard-desktop  C:\Users\Edgard\Documents        documents
```

## Restore Rules

- Normal restore order: create restore job, choose snapshot, pause GitOps, stop
  app, delete current PVC contents, restore snapshot, restart app, resume
  GitOps, delete restore job.
- Stop the app before deleting or restoring its files.
- Delete the existing PVC contents before restoring when you want a full, fresh
  restore.
- Delete files under `/restore/data/appdata/...`, not the PVC object.
- Keep `--exclude-xattr '*'` for NFS-backed appdata restores.
- Pause the `apps` ApplicationSet before restoring so self-heal does not race
  the restore.

## Create Restore Job

Create this temporary job before running restore commands. It mounts
`restic-appdata` read-write at `/restore/data/appdata`.

```sh
kubectl -n selfhosted apply -f - <<'EOF'
---
apiVersion: batch/v1
kind: Job
metadata:
  name: restic-restore
  namespace: selfhosted
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: restic
          image: restic/restic:0.19.0
          command: ["/bin/sh", "-c", "sleep 3600"]
          env:
            - name: RESTIC_REPOSITORY
              value: rest:http://restic.selfhosted.svc.cluster.local:8000/
            - name: RESTIC_REST_USERNAME
              value: restic
            - name: RESTIC_REST_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: restic-credentials
                  key: RESTIC_PASSWORD
            - name: RESTIC_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: restic-credentials
                  key: RESTIC_PASSWORD
          volumeMounts:
            - name: appdata
              mountPath: /restore/data/appdata
      volumes:
        - name: appdata
          persistentVolumeClaim:
            claimName: restic-appdata
EOF
```

Check available snapshots:

```sh
kubectl -n selfhosted exec job/restic-restore -- \
  restic --retry-lock 30m snapshots --group-by host,paths,tags
```

Delete the job after all restores are finished:

```sh
kubectl -n selfhosted delete job restic-restore
```

## Restore One PVC

Home Assistant is the example:

| Field | Value |
| --- | --- |
| Argo CD app | `homeassistant` |
| Namespace | `home-automation` |
| Workload | `deployment/homeassistant` |
| PVC | `homeassistant` |
| Restic path | `/data/appdata/home-automation/homeassistant` |

Set restore variables:

```sh
APP=homeassistant
NAMESPACE=home-automation
WORKLOAD=deployment/homeassistant
PVC=homeassistant
SNAPSHOT=<snapshot-id>

RESTIC_PATH="/data/appdata/${NAMESPACE}/${PVC}"
RESTORE_PATH="/restore${RESTIC_PATH}"

case "$RESTORE_PATH" in
  /restore/data/appdata/*) ;;
  *) echo "Refusing unsafe restore path: $RESTORE_PATH" >&2; exit 1 ;;
esac
```

Pause GitOps and stop the app:

```sh
kubectl -n argocd patch applicationset apps --type merge \
  -p '{"spec":{"syncPolicy":{"applicationsSync":"create-only"}}}'
argocd app set "$APP" --sync-policy none
kubectl -n "$NAMESPACE" scale "$WORKLOAD" --replicas=0
```

Optional: take one last backup before deleting files:

```sh
kubectl -n selfhosted create job --from=cronjob/restic-backup restic-before-restore
```

Delete the current PVC contents:

```sh
kubectl -n selfhosted exec job/restic-restore -- \
  sh -ceu "find '$RESTORE_PATH' -mindepth 1 -exec rm -rf -- {} +"
```

Restore the selected snapshot:

```sh
kubectl -n selfhosted exec job/restic-restore -- \
  restic --retry-lock 30m restore "$SNAPSHOT" \
    --include "$RESTIC_PATH" \
    --exclude-xattr '*' \
    --target /restore
```

Restart and verify:

```sh
kubectl -n "$NAMESPACE" scale "$WORKLOAD" --replicas=1
kubectl -n "$NAMESPACE" rollout status "$WORKLOAD"
```

Resume GitOps:

```sh
argocd app set "$APP" --sync-policy automated --auto-prune --self-heal
kubectl -n argocd patch applicationset apps --type merge \
  -p '{"spec":{"syncPolicy":null}}'
task argo:sync app="$APP"
```

## Restore Multiple PVCs

Use the same app pause and resume flow. Stop the app once, delete each PVC path,
then restore all paths in one command.

```sh
SNAPSHOT=<snapshot-id>

kubectl -n selfhosted exec job/restic-restore -- \
  sh -ceu "find '/restore/data/appdata/selfhosted/example-data' -mindepth 1 -exec rm -rf -- {} +"
kubectl -n selfhosted exec job/restic-restore -- \
  sh -ceu "find '/restore/data/appdata/selfhosted/example-cache' -mindepth 1 -exec rm -rf -- {} +"

kubectl -n selfhosted exec job/restic-restore -- \
  restic --retry-lock 30m restore "$SNAPSHOT" \
    --include /data/appdata/selfhosted/example-data \
    --include /data/appdata/selfhosted/example-cache \
    --exclude-xattr '*' \
    --target /restore
```

## Cluster DR

1. Rebuild Talos and Kubernetes from Git.
2. Restore or reattach `/mnt/dpool/restic`.
3. Recreate `/mnt/spool/appdata`.
4. Let Argo CD deploy platform dependencies, External Secrets, and `restic`.
5. Create the restore job.
6. Confirm snapshots from the restore job.
7. Pause generated app changes:

   ```sh
   kubectl -n argocd patch applicationset apps --type merge \
     -p '{"spec":{"syncPolicy":{"applicationsSync":"create-only"}}}'
   ```

8. For each app being restored:
   - pause the Argo CD app
   - scale every app controller to `0`
   - delete each target PVC path under `/restore/data/appdata`
   - restore with `restic restore --target /restore --exclude-xattr '*'`
   - scale the app back up
   - verify app health and data
   - resume the Argo CD app
   - run `task argo:sync app=<app>`
9. Let the ApplicationSet manage apps again after every restored app is healthy:

   ```sh
   kubectl -n argocd patch applicationset apps --type merge \
     -p '{"spec":{"syncPolicy":null}}'
   ```

10. Delete the restore job.
11. Run a fresh backup after restored apps are healthy.

## Manual Checks

Run a full repository data check after disruptive storage work:

```sh
kubectl -n selfhosted exec job/restic-restore -- \
  restic --retry-lock 30m check --read-data --verbose
```
