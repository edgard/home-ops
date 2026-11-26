# Cloudflare Tunnel

Purpose: give enrolled Karakeep and Atuin clients remote HTTPS access.
Status: current. Reviewed against: `198230c4` and this revision.

## Network and credentials

One stateless connector opens outbound connections to Cloudflare on port 7844
(UDP or TCP). The kubelet checks its internal `/ready` endpoint. It needs
cluster DNS and a trusted HTTPS connection to the Envoy proxy Service.
Each public hostname fixes the origin Host and TLS server name, checks its own
Access application audience, and retains application authentication. An unmatched
hostname receives 404. A LAN or tailnet client can use the private Envoy route
during an internet outage. Both app routes strip the Cloudflare client ID and
secret headers before proxying.

## Provision and publish

1. Use the existing Zero Trust organization. Enable independent MFA enrollment
   for biometrics and security keys in Access settings and enroll the user's
   authenticator. The Karakeep browser policy requires WebAuthn after email PIN.
   The Cloudflare operator token needs zone DNS write, zone read, account Tunnel
   write, Access applications/policies write, identity provider write and
   organization read. Use an administrator for one-time organization setup.
2. Supply the following local operator inputs in
   `terraform/private-access.auto.tfvars.json` (mode 0600). Back up these
   inputs with your operator configuration. Copy service token **resource
   UUIDs** here. The client ID ending in `.access` and client secret belong
   in the installation's password manager.

   ```json
   {
     "private_access": {
       "karakeep_email": "owner@example.com",
       "karakeep_token_ids": [],
       "atuin_token_ids": []
     }
   }
   ```

3. Run `task tf:plan` and apply the reviewed initial configuration with
   `published_apps` empty. Obtain the remotely managed tunnel's connector
   token from Cloudflare and save only the token in the Bitwarden Secrets
   Manager item `cloudflared_tunnel_token`. ESO mounts it for the Deployment.
   Verify Argo sync, ExternalSecret readiness, connector readiness, and the
   tunnel's connected status. Check that the origin address matches the current
   Envoy proxy Service and that each hostname passes certificate validation.
4. Issue a separately named, expiring service token for each Atuin machine,
   Karakeep mobile installation and browser extension. Save each one-time secret
   directly in the password manager. Add its resource UUID to the matching
   input set, then plan and apply. Configure the client ID and secret in
   `CF-Access-Client-Id` and `CF-Access-Client-Secret`. Atuin reads these
   from `extra_headers` in the client config. Karakeep clients accept custom
   headers in server settings. Protect client settings from dotfile publication.
5. Verify the zone's managed WAF in Cloudflare Security and review existing
   Access and WAF rules for hostname overlap. Publish one app by adding its
   name to `published_apps` in a reviewed change and applying the plan.
   From outside the LAN with Tailscale disconnected, check anonymous rejection,
   cross-app token rejection, and application authentication. Test Atuin sync,
   Karakeep browser PIN plus WebAuthn, and a bookmark capture and reopen on
   both clients. Inspect WAF events for rejected legitimate requests. LAN
   probes exercise the private gateway independently of this public path.

## Recovery

Add the affected app to `suspended_apps` and apply. Unmatched requests then
receive 404 at the connector. Remove it from `published_apps` in the following
apply, keeping Access in force through DNS expiry. For a connector-wide
emergency stop all its replicas and reconcile the GitOps configuration.
Restore the origin and check the connector before restoring public DNS.
When revoking the last token for a published app, suspend the origin first.
For a lost installation revoke its token, remove its UUID and verify denial
with a fresh request. Rotate the connector token in Cloudflare and Bitwarden,
verify that Reloader restarts the pod and the new connection is healthy.
Disconnect established old connectors in Cloudflare when responding to a leak.
There is no connector PVC to restore.

## Sources

- [Tunnel routes, Access policies and publication controls](../../../../terraform/private-access.tf)
- [Connector app](../../../../apps/platform-system/cloudflared/app.yaml), [pod](../../../../apps/platform-system/cloudflared/values.yaml) and [token mapping](../../../../apps/platform-system/cloudflared/manifests/cloudflared-credentials.externalsecret.yaml)
- [Cloudflare origin parameters and JWT validation](https://developers.cloudflare.com/tunnel/reference/origin-parameters/)
- [Access authentication and MFA enrollment](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/independent-mfa/)
- [Free managed WAF deployment](https://developers.cloudflare.com/waf/get-started/)
- [Atuin sync headers](https://docs.atuin.sh/18.25/configuration/config/#extra_headers) and [Karakeep client headers](https://github.com/karakeep-app/karakeep/issues/1287)

## Related pages

- [Networking](../../architecture/networking.md)
- [Terraform](../../architecture/terraform.md)
- [Secrets maintenance](../../operations/secrets-maintenance.md)
