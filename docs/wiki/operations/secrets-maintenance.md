# Secrets maintenance and recovery

Purpose: provision and operate the unified Bitwarden delivery paths.
Status: current. Reviewed against: `d897e58d4dbc5cd0609e9b6dc3098d88fb887639`.

## Setup without cluster access

Bitwarden Secrets Manager is the value maintenance home. Maintain values in its
UI. Use two projects: the existing application project and `home-ops-operator`.
First check the human account's project capacity. Reuse the existing machine
account with read access to both configured projects. Operator commands and ESO
share this account and its token; ESO can therefore read operator secrets too.
Preserve existing application values, shared items, the token, and Talos identity.

Set the operator project's public UUID in the `operator` alias in
[secretspec.toml](../../../secretspec.toml) when provisioning a new environment.
The configured projects must be distinct and nonempty. The application alias
remains tied to the existing project. Both aliases read one
`home-ops/_provider/access_token` Keychain credential through SecretSpec.

Install Python 3.14 (the default `task deps` interpreter; `PYTHON_BIN` can
select a compatible interpreter) and the normal repository tools, then:

```bash
task deps
task secrets:setup
task secrets:login
task secrets:check scope=cluster
task secrets:check scope=terraform
```

The checksum-verified installer writes pinned binaries to `~/.local/bin`.
The [role defaults](../../../ansible/roles/operator_secrets/defaults/main.yml)
own the tool pins; SecretSpec validation and its real-provider integration
check use the same configured version. A pin update still has to pass the
provider compatibility fixtures before delivery.
Operator commands find that directory automatically. Login prompts securely;
do not paste tokens into commands, Git, documentation, or chat. On macOS,
SecretSpec's keyring provider uses Keychain. Recovery requires access to
Bitwarden and this credential or a replacement token; this design has no
offline value cache or fallback. CI uses synthetic inputs, without Keychain or
cloud access.

## Value inventory and ordinary use

The manifest owns the exact key references and scope membership. Put existing
Talos YAML, backend access/secret keys, and the shared machine-account token into
the operator project using the manifest's item names. Cloudflare's API token and the Tailscale OAuth client secret remain single
application-project items shared with ESO. The Cloudflare zone ID and Tailscale
OAuth client ID are operator-only inputs and belong in the operator project.
The manifest preserves the existing Bitwarden item names, including the
`tailscale_oauth_` names. Do not duplicate shared values.

`talos:gen`, `platform:create`, `cluster:create`, `tf:plan`, and `tf:apply` resolve
only their named scopes through the checked-in manifest. They clear inherited
legacy credentials and SecretSpec overrides. The native BWS provider reads
through a read-only adapter that rejects duplicates, malformed data, writes,
and unredacted provider diagnostics. Authentication is in subprocess environment,
never CLI arguments. Scopes minimize delivery; machine-account project
permissions are the access boundary. Bootstrap and token replacement validate
access to exactly the two configured projects, rejecting unconfigured projects.

Task launches the native SecretSpec CLI and then the selected Ansible playbook.
Ansible roles own tool installation, version checks, bootstrap preflight,
Talos generation, GitOps handoff, and token replacement. The role-owned BWS
adapter remains a small read-only CLI boundary required by SecretSpec's provider;
it does not orchestrate workflows or maintain values.

Keep only nonsecret node, disk, context, and path settings in ignored `.envrc`.
`KUBECONFIG` is a single destination file, not a colon-separated list;
`TALOSCONFIG` selects the Talos client file; `TALOS_CONTROLPLANE_CONFIG_PATH`
selects the machine-config destination. `TALOS_CONFIG_DIR` changes the default
directory for both. Generation writes restricted
client files and cleans its temporary YAML/output directory even on failure.
Upgrades, Argo refresh, cleanup, formatting, and lint use existing clients and
do not resolve cloud secrets.

## Shared token rotation

Create a replacement token on the existing read-only machine account and retain
the current token until verification passes. Update `eso_bws_access_token` in
the operator project through the Bitwarden UI, then run `task secrets:login`
with the replacement token to update the single Keychain credential. Run both
scope checks and `task secrets:sync-cluster-token`, then verify the consumers.
Revoke the old token only after success. The synchronization command retains and
restores the previous cluster token if reconciliation fails; restore the old
operator-project value and Keychain credential too when rolling back the whole
rotation. Project permissions remain the same.

## Migration history and protected state recovery

The unified delivery refactor retired the active Vault workflow, global secret
exports, and Terraform's Bitwarden data sources. The original round-trip and
retirement procedure is preserved in the
[immutable migration runbook](https://github.com/edgard/home-ops/blob/8a41b43d2b9ec1d0eaa815500132e42ef9b5abe1/docs/wiki/operations/secrets-maintenance.md).
Current operation uses the Bitwarden items declared in the manifest; the old
Vault file, verification command, and formatter/linter exceptions are retired.
Keep legacy plaintext, backup, state, plan, and crash-artifact ignores.

The one-time Terraform data-source retirement command and its migration-only
tests are retired after successful migration. Preserve the protected state
recovery backup and historical B2 versions. If restoring a pre-migration state,
consult the immutable migration procedure before retiring its data entries;
do not force overwrite newer concurrent state. Historical state retention and
native state encryption remain separate work.

For operator recovery, sign in through the human Bitwarden account, verify
machine-account read access to the two configured projects, and run setup and
login on the new Mac. Restore nonsecret node/disk/path settings, then use
`task talos:gen` with the existing Talos identity to regenerate restricted client
and machine configuration. Do not generate a new identity for an existing
cluster. Verify client access before applying node configuration. Kubernetes
Secrets remain ESO delivery artifacts; maintain their values in Bitwarden.

A full cold bootstrap is proved only on a disposable Talos environment with the
external NAS/storage/network prerequisites. Do not rebuild production to validate
this refactor. Bootstrap preflight authenticates to Bitwarden and Git and requires
a clean checkout matching remote `master` before node mutation. ESO readiness
must pass before Argo root handoff; handoff checks the captured revision and
ApplicationSet children, followed by fresh ExternalSecret reconciliation.

## Sources

- [SecretSpec manifest](../../../secretspec.toml)
- [Operator delivery role](../../../ansible/roles/operator_secrets/tasks/validate.yml)
- [Operator tool defaults](../../../ansible/roles/operator_secrets/defaults/main.yml)
- [Read-only BWS adapter](../../../ansible/roles/operator_secrets/files/bws_readonly.py)
- [Bootstrap preflight](../../../ansible/roles/platform/tasks/preflight.yml)
- [Cluster checks and token replacement](../../../ansible/roles/platform/tasks/sync_token.yml)
- [Original secrets refactor, PR #433](https://github.com/edgard/home-ops/pull/433)
- [Tool installation](../../../ansible/roles/operator_secrets/tasks/setup.yml)
- [Task interface](../../../Taskfile.yaml)
- [SecretSpec credentials](https://secretspec.dev/reference/provider-credentials/) — credential precedence and keyring sources.
- [SecretSpec BWS implementation](https://github.com/cachix/secretspec/blob/v0.21.1/secretspec/src/provider/bws.rs) — native project reads and process-memory caching.

## Related pages

- [Secrets](../architecture/secrets.md)
- [Talos bootstrap](../architecture/talos-bootstrap.md)
- [Terraform](../architecture/terraform.md)
- [Backup and recovery](../architecture/backup-recovery.md)
