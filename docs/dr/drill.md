---
# DR Drill Procedure

Run a K8up restore drill monthly and after major storage, Talos, Kubernetes, or backup changes. A drill must restore into a temporary PVC, verify content exists, and clean up the temporary resources.

## Drill Steps

1. Confirm K8up snapshots exist for the app namespace:
   ```bash
   kubectl get snapshots.k8up.io -n selfhosted
   kubectl get snapshot.k8up.io <snapshot-name> -n selfhosted -o yaml
   ```
2. Confirm the snapshot `spec.paths` includes the source PVC path, for example `/data/atuin`.
3. Create a temporary PVC in the same namespace as the app:
   ```yaml
   ---
   apiVersion: v1
   kind: PersistentVolumeClaim
   metadata:
     name: drill-atuin
     namespace: selfhosted
   spec:
     accessModes:
       - ReadWriteOnce
     resources:
       requests:
         storage: 1Gi
   ```
4. Restore the selected snapshot into the temporary PVC:
   ```yaml
   ---
   apiVersion: k8up.io/v1
   kind: Restore
   metadata:
     name: drill-atuin
     namespace: selfhosted
   spec:
     snapshot: "<snapshot-id>"
     backend:
       repoPasswordSecretRef:
         name: k8up-restic-credentials
         key: RESTIC_PASSWORD
       rest:
         url: http://restic.selfhosted.svc.cluster.local:8000/k8up/selfhosted
         userSecretRef:
           name: k8up-restic-credentials
           key: RESTIC_USERNAME
         passwordSecretReg:
           name: k8up-restic-credentials
           key: RESTIC_PASSWORD
     restoreMethod:
       folder:
         claimName: drill-atuin
     paths:
       - /data/atuin
     delete: true
   ```
5. Apply the PVC and restore manifests:
   ```bash
   kubectl apply -f drill-pvc.yaml
   kubectl apply -f drill-restore.yaml
   kubectl get restore.k8up.io drill-atuin -n selfhosted -o yaml
   ```
6. Verify restored content with a short Job:
   ```yaml
   ---
   apiVersion: batch/v1
   kind: Job
   metadata:
     name: drill-check-atuin
     namespace: selfhosted
   spec:
     backoffLimit: 0
     ttlSecondsAfterFinished: 600
     template:
       spec:
         restartPolicy: Never
         containers:
           - name: check
             image: busybox:1.36
             command:
               - /bin/sh
               - -c
               - find /restore -mindepth 1 -print -quit | grep -q .
             volumeMounts:
               - name: restore
                 mountPath: /restore
         volumes:
           - name: restore
             persistentVolumeClaim:
               claimName: drill-atuin
   ```
7. Clean up the drill resources:
   ```bash
   kubectl delete job drill-check-atuin -n selfhosted --ignore-not-found
   kubectl delete restore.k8up.io drill-atuin -n selfhosted --ignore-not-found
   kubectl delete pvc drill-atuin -n selfhosted --ignore-not-found
   ```
