# VictoriaMetrics

Purpose: collect and store one year of metrics for Grafana.
Status: current. Reviewed against: `fd5a0c41` and this revision.

One process discovers application probes from labeled Services, scrapes the explicit infrastructure targets and serves the private query API. The appdata claim retains samples across pod replacements. Recover the data from the platform-system Restic snapshot after pool loss. Authenticate kubelet scrapes with the dedicated service account and validate its serving certificate against the public kubelet CA for homelab.

The query and ingestion API is reachable on the cluster network. The deletion
API requires a rotating projected token with its own audience, mounted only
in the VictoriaMetrics pod. Ordinary scrapes use a separate credential.

## Renew the kubelet CA

The default self-signed kubelet serving chain can change when kubelet is
restarted or upgraded, as well as when the node is reprovisioned. The pinned
public CA must then be renewed; it is not the Kubernetes cluster CA. A scrape
error containing `x509: certificate signed by unknown authority` is a reason
to compare the current chain with the pin, not to disable TLS verification.

Retrieve the public certificate chain through authenticated Talos access. Extract the CA from
`/var/lib/kubelet/pki/kubelet.crt`, verify the leaf with
`openssl verify -CAfile ca.crt -verify_hostname homelab kubelet.crt`, and
update the public CA ConfigMap through Git. After sync, restart VictoriaMetrics
to reload the CA file if the scrape still uses the old trust. Check
`up{job="kubelet"} == 1` and query pod working-set memory. The local
metrics-server has a different TLS configuration. Check kubelet scrape health
after Kubernetes upgrades; refreshing this pin repairs the current chain but
does not enable automatic trust renewal.

## Sources

- [Application](../../../../apps/platform-system/victoria-metrics/app.yaml)
- [Helm values](../../../../apps/platform-system/victoria-metrics/values.yaml)

## Related pages

- [Monitoring and cutover](../../architecture/uptime.md)
