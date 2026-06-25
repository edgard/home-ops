---
# Shared Restic Backup And Restore Runbook

The `restic` app is the shared backup plane for Kubernetes appdata and
workstations. Kubernetes owns repository maintenance; workstations only write
backup snapshots.

## Facts

- In-cluster repo: `rest:http://restic.selfhosted.svc.cluster.local:8000/`
- Workstation repo: `rest:http://restic.edgard.org:8000/`
- Repo storage: `/mnt/dpool/restic`
- Appdata storage: `/mnt/spool/appdata`
- Snapshot root: `/data/appdata`
- PVC path: `/data/appdata/<namespace>/<pvc-name>`
- Restore mount: `/restore/data/appdata`
- Auth env: `RESTIC_REST_USERNAME`, `RESTIC_REST_PASSWORD`, `RESTIC_PASSWORD`

Schedules:

- Backup: daily `0 3 * * *`
- Maintenance: weekly `0 4 * * 1`
- Retention: daily 14, weekly 8, monthly 12, yearly 3
- Maintenance command: `forget --group-by host,paths,tags --prune`, then
  `check`, then `check --read-data-subset=10%`

Expected snapshot families:

```text
homelab         /data/appdata                    appdata
edgards-mini    /Users/edgard/Documents          documents
edgard-desktop  C:\Users\Edgard\Documents        documents
```

## Restore Job

Create a temporary job with read-write access to `restic-appdata`:

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

Useful restore-job commands:

```sh
kubectl -n selfhosted exec job/restic-restore -- \
  restic --retry-lock 30m snapshots --group-by host,paths,tags

kubectl -n selfhosted exec job/restic-restore -- \
  restic --retry-lock 30m check --read-data --verbose

kubectl -n selfhosted delete job restic-restore
```

## One PVC Restore

This example restores Home Assistant's single PVC from scratch. It pauses Argo
CD, stops the app, deletes the existing PVC contents, restores the selected
snapshot, then resumes sync.

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

kubectl -n argocd patch applicationset apps --type merge \
  -p '{"spec":{"syncPolicy":{"applicationsSync":"create-only"}}}'
argocd app set "$APP" --sync-policy none
kubectl -n "$NAMESPACE" scale "$WORKLOAD" --replicas=0

# Optional just-before-restore snapshot.
kubectl -n selfhosted create job --from=cronjob/restic-backup restic-before-restore

kubectl -n selfhosted exec job/restic-restore -- \
  sh -ceu "find '$RESTORE_PATH' -mindepth 1 -exec rm -rf -- {} +"

kubectl -n selfhosted exec job/restic-restore -- \
  restic --retry-lock 30m restore "$SNAPSHOT" \
    --include "$RESTIC_PATH" \
    --exclude-xattr '*' \
    --target /restore

kubectl -n "$NAMESPACE" scale "$WORKLOAD" --replicas=1
kubectl -n "$NAMESPACE" rollout status "$WORKLOAD"

argocd app set "$APP" --sync-policy automated --auto-prune --self-heal
kubectl -n argocd patch applicationset apps --type merge \
  -p '{"spec":{"syncPolicy":null}}'
task argo:sync app="$APP"
```

`--exclude-xattr '*'` is intentional for NFS-backed appdata restores.

## Multiple PVCs

Use the same restore flow, but set every PVC path and restore them together:

```sh
SNAPSHOT=<snapshot-id>
PATHS="
/data/appdata/selfhosted/example-data
/data/appdata/selfhosted/example-cache
"

INCLUDES=
for path in $PATHS; do
  case "/restore${path}" in
    /restore/data/appdata/*) ;;
    *) echo "Refusing unsafe restore path: /restore${path}" >&2; exit 1 ;;
  esac

  kubectl -n selfhosted exec job/restic-restore -- \
    sh -ceu "find '/restore${path}' -mindepth 1 -exec rm -rf -- {} +"
  INCLUDES="$INCLUDES --include $path"
done

kubectl -n selfhosted exec job/restic-restore -- \
  restic --retry-lock 30m restore "$SNAPSHOT" \
    $INCLUDES \
    --exclude-xattr '*' \
    --target /restore
```

## Cluster DR

1. Rebuild Talos and Kubernetes from Git.
2. Restore or reattach `/mnt/dpool/restic`.
3. Recreate `/mnt/spool/appdata`.
4. Let Argo CD deploy platform dependencies, External Secrets, and `restic`.
5. Create the restore job.
6. Confirm snapshots:

   ```sh
   kubectl -n selfhosted exec job/restic-restore -- \
     restic --retry-lock 30m snapshots --group-by host,paths,tags
   ```

7. Pause generated app changes before restoring data:

   ```sh
   kubectl -n argocd patch applicationset apps --type merge \
     -p '{"spec":{"syncPolicy":{"applicationsSync":"create-only"}}}'
   ```

8. For each restored app:
   - `argocd app set <app> --sync-policy none`
   - scale every app controller to `0`
   - delete each target PVC path under `/restore/data/appdata`
   - restore with `restic restore --target /restore --exclude-xattr '*'`
   - scale the app back to `1`
   - verify health and data
   - `argocd app set <app> --sync-policy automated --auto-prune --self-heal`
   - `task argo:sync app=<app>`
9. Let the ApplicationSet manage apps again:

   ```sh
   kubectl -n argocd patch applicationset apps --type merge \
     -p '{"spec":{"syncPolicy":null}}'
   ```

10. Delete the restore job.
11. Run a fresh backup after restored apps are healthy.
