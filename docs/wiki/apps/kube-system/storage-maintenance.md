# ZFS and disk maintenance

Purpose: describe storage dependencies, recovery and monitoring for ZFS and disk maintenance.
Status: current. Reviewed against: `e0ffdb032870a9272c7abd691788e9b4e4b48ee1` and this revision.

This application takes hourly recursive snapshots beneath `dpool/k8s`.
Retention applies only to snapshots carrying its own policy and name prefix.
It schedules a scrub after 35 days and weekly extended SMART tests across
the four pool members and the recorded system SSD. A successful SMART Job
records when it started the tests. Check their eventual device self-test
logs at acceptance. Readiness uses current SMART health, prefail attributes
and self-test results. Superseded historical errors alone do not hold it down. The private health
service exposes readiness to Blackbox Exporter. Pool errors, SMART failures and overdue
maintenance make it unready. After first handoff, start one Job from each
maintenance CronJob and check its successful completion before accepting the
new alert path. A complete node outage requires independent observation.
Keep an independent backup of any irreplaceable media and the Restic mirror
off-node. A pool snapshot and its source share the same disks.

## Sources

- [Application](../../../../apps/kube-system/storage-maintenance/app.yaml)
- [Values](../../../../apps/kube-system/storage-maintenance/values.yaml)
- [Manifests](../../../../apps/kube-system/storage-maintenance/manifests)

## Related pages

- [Storage](../../architecture/storage.md)
- [Talos bootstrap](../../architecture/talos-bootstrap.md)
