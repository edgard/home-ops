# VictoriaMetrics

Purpose: collect and store one year of metrics for Grafana.
Status: current. Reviewed against: `cdb7a398deaa06451737a5a43e895942443e7d3c` and this revision.

One process scrapes explicit targets and serves the private query API. The appdata claim retains samples across pod replacements. Recover the data from the platform-system Restic snapshot after pool loss. Authenticate kubelet scrapes with the dedicated service account and validate its serving certificate against the public kubelet CA for homelab.

The query and ingestion API is reachable on the cluster network. The deletion
API requires a rotating projected token with its own audience, mounted only
in the VictoriaMetrics pod. Ordinary scrapes use a separate credential.

## Renew the kubelet CA

After reprovisioning the node or renewing its kubelet CA, retrieve the public
certificate chain through authenticated Talos access. Extract the CA from
`/var/lib/kubelet/pki/kubelet.crt`, verify the leaf with
`openssl verify -CAfile ca.crt -verify_hostname homelab kubelet.crt`, and
update the public CA ConfigMap through Git. After sync, check
`up{job="kubelet"} == 1` and query pod working-set memory. The local
metrics-server has a different TLS configuration.

## Sources

- [Application](../../../../apps/platform-system/victoria-metrics/app.yaml)
- [Helm values](../../../../apps/platform-system/victoria-metrics/values.yaml)

## Related pages

- [Monitoring and cutover](../../architecture/uptime.md)
