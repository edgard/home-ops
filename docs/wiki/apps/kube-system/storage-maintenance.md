# ZFS and disk maintenance

Purpose: describe storage dependencies, recovery and monitoring for ZFS and disk maintenance.
Status: current. Reviewed against: `fd5a0c41` and this revision.

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

## Initialize SMART maintenance

On first handoff, the weekly SMART schedule may not have run yet. A missing
`org.home-ops:last-smart` pool property keeps storage readiness down even when
current device health passes. Start the existing job once rather than setting
the timestamp manually:

```sh
job="storage-maintenance-smart-initial-$(date -u +%Y%m%d%H%M%S)"
kubectl -n kube-system create job --from=cronjob/storage-maintenance-smart "$job"
kubectl -n kube-system wait --for=condition=complete "job/$job" --timeout=120s
kubectl -n kube-system logs "job/$job"
```

Job completion records successful test initiation, not completed extended
self-tests. Read their results after the completion estimates in the logs.
Allow the five-minute readiness check and two successful uptime probes before
expecting the Grafana storage alert to recover. If readiness still fails,
inspect the pool, device checks and other maintenance timestamps.

## Sources

- [Application](../../../../apps/kube-system/storage-maintenance/app.yaml)
- [Values](../../../../apps/kube-system/storage-maintenance/values.yaml)
- [Manifests](../../../../apps/kube-system/storage-maintenance/manifests)

## Related pages

- [Storage](../../architecture/storage.md)
- [Talos bootstrap](../../architecture/talos-bootstrap.md)
