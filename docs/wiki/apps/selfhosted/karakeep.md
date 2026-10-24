# Karakeep

Purpose: Karakeep saves and indexes bookmarks and captured content.
Status: current. Reviewed against: `cdb8067ec7dd54be6afb5d4ee9c698a9db17c8d5`.

## Dependencies

The app, Chrome, and Meilisearch controllers share an appdata claim and credential ExternalSecret.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

Browser capture, search, and persisted content need separate acceptance checks.

The main container runs as root with all default capabilities dropped and only
`CHOWN`, `SETUID`, and `SETGID` restored for its s6 entrypoint. Karakeep 0.34
[changed the image's `/run` ownership to UID 1000](https://github.com/karakeep-app/karakeep/pull/3114).
Root startup must change that ownership back; without `CHOWN`, s6 exits before
the database migration, web server, or workers start. Keep privilege escalation
disabled. Chrome and Meilisearch retain their separate non-root profiles.

## Sources

- [App metadata](../../../../apps/selfhosted/karakeep/app.yaml)
- [Helm values](../../../../apps/selfhosted/karakeep/values.yaml)
- [Raw manifests](../../../../apps/selfhosted/karakeep/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
