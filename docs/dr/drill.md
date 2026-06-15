---
# DR Drill Procedure

Run a restore drill monthly and after major storage, Talos, Kubernetes, or backup changes.

## Drill Steps

1. Confirm the local repository is readable:
   ```bash
   task backup:snapshots
   ```
2. Check repository integrity:
   ```bash
   task backup:check
   ```
3. Restore a small critical app into the drill path:
   ```bash
   task dr:drill app=atuin snapshot=latest
   ```
4. Confirm the command completed successfully.

The drill task derives the appdata path from the app namespace and rendered PVC name, restores into `.drill/<app>-<timestamp>` under appdata, asserts restored content exists, and removes the drill path when the Job exits.
