# Secrets maintenance and recovery

Purpose: provision and operate the unified Bitwarden delivery paths.
Status: current. Reviewed against: `6aed89365a1ea1eaca88216fdf9bac132a1e18e5`.

## Setup without cluster access

Bitwarden Secrets Manager is the value maintenance home. Maintain all homelab
values in one `home-ops` project. Reuse the existing read-only machine account for
CLI commands and ESO, granting it access to exactly this project. Preserve item
names, IDs, values, the existing token, and the Talos identity.

Set the project's public UUID in the `bitwarden` provider in
[secretspec.toml](../../../secretspec.toml) and in the
[ClusterSecretStore](../../../apps/platform-system/external-secrets/manifests/external-secrets-store.clustersecretstore.yaml).
They must match. The configured SecretSpec provider reads the existing
`home-ops/_provider/access_token` Keychain credential; renaming or consolidating
Bitwarden projects does not change that credential address.

Install Python 3.14 (the default `task deps` interpreter; `PYTHON_BIN` can
select a compatible interpreter) and the normal repository tools, then:

```bash
task deps
task secrets:login
task secrets:check scope=cluster
task secrets:check scope=terraform
```

Provision SecretSpec and BWS through the local Chezmoi/Homebrew machine setup.
This repository validates those tools but does not install local binaries.
The [CLI role defaults](../../../ansible/roles/cli_secrets/defaults/main.yml) own
the SecretSpec compatibility pin used by runtime validation and the
[CI toolchain action](../../../.github/actions/setup-toolchain/action.yml).
The action installs the existing validation dependencies before reading that
YAML value. Its isolated installer test covers checksum/version rejection and cleanup.
CI uses synthetic provider fixtures and installs only SecretSpec. A pin update
still has to pass the provider compatibility fixtures before delivery.
CLI commands include `~/.local/bin` on `PATH` automatically. Login prompts securely;
do not paste tokens into commands, Git, documentation, or chat. On macOS,
SecretSpec's keyring provider uses Keychain. Recovery requires access to
Bitwarden and this credential or a replacement token; this design has no
offline value cache or fallback. CI uses synthetic inputs, without Keychain or
cloud access.

## Value inventory and ordinary use

The manifest owns the exact CLI key references and scope membership. ExternalSecret
manifests own the cluster's item references. All referenced items live in the same
project. The Tailscale OAuth client secret is one item reused by Terraform and the
router. Terraform's `cloudflare_token` and certificates' separate
`cert_manager_cloudflare_api_token` remain distinct credentials. Preserve existing
names, including `tailscale_oauth_` names. Deduplicate records representing the same
credential and consumers; equal values alone do not make unrelated service accounts
or encryption/session keys interchangeable.

`talos:gen`, `platform:create`, `cluster:create`, `tf:plan`, and `tf:apply` resolve
only their named scopes through the checked-in manifest. They clear inherited
legacy credentials and SecretSpec overrides. The native BWS provider reads
through a read-only adapter that rejects duplicates, malformed data, writes,
and unredacted provider diagnostics. Authentication is in subprocess environment,
never CLI arguments. Scopes minimize delivery; machine-account project
permissions are the access boundary. Bootstrap and token replacement validate
access to exactly the shared project, rejecting unconfigured project access.

Task launches the native SecretSpec CLI and then the selected Ansible playbook.
Ansible roles own version checks, bootstrap preflight,
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
the `home-ops` project through the Bitwarden UI, then run `task secrets:login`
with the replacement token to update the single Keychain credential. Run both
scope checks and `task secrets:sync-cluster-token`, then verify the consumers.
Revoke the old token only after success. The synchronization command retains and
restores the previous cluster token if reconciliation fails; restore the old
Bitwarden item value and Keychain credential too when rolling back the whole
rotation. Project permissions remain the same.

## Project consolidation

The single project retains the former application project's UUID, preserving ESO
references. Move the former CLI project's items into it without recreating them.
Before moving, compare names and references, and check that project access grants
are compatible. Verify all item IDs, names, values, and notes after the move.
Remove the retired project's machine-account grant after its items are verified in
the retained project, then run the cluster and Terraform scope checks and the
read-only application-access preflight. That preflight requires exactly one
accessible project. Retire the empty project only after verification. If rollback
is needed, restore its previous read-only machine-account grant first, move the
affected items back using their original IDs, and restore the previous manifest
before running maintenance commands.

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

For CLI recovery, sign in through the human Bitwarden account, verify
machine-account read access to the shared project, provision the local
tools through Chezmoi/Homebrew, then run `task deps` and `task secrets:login`
on the new Mac. Restore nonsecret node/disk/path settings, then use
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
- [CLI delivery role](../../../ansible/roles/cli_secrets/tasks/validate.yml)
- [CLI tool defaults](../../../ansible/roles/cli_secrets/defaults/main.yml)
- [Read-only BWS adapter](../../../ansible/roles/cli_secrets/files/bws_readonly.py)
- [Bootstrap preflight](../../../ansible/roles/platform/tasks/preflight.yml)
- [Cluster checks and token replacement](../../../ansible/roles/platform/tasks/sync_token.yml)
- [Original secrets refactor, PR #433](https://github.com/edgard/home-ops/pull/433)
- [Tool validation](../../../ansible/roles/cli_secrets/tasks/validate.yml)
- [Task interface](../../../Taskfile.yaml)
- [SecretSpec credentials](https://secretspec.dev/reference/provider-credentials/) — credential precedence and keyring sources.
- [SecretSpec BWS implementation](https://github.com/cachix/secretspec/blob/v0.21.1/secretspec/src/provider/bws.rs) — native project reads and process-memory caching.

## Related pages

- [Secrets](../architecture/secrets.md)
- [Talos bootstrap](../architecture/talos-bootstrap.md)
- [Terraform](../architecture/terraform.md)
- [Backup and recovery](../architecture/backup-recovery.md)
