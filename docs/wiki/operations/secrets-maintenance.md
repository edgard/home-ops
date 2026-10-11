# Secrets maintenance and migration

Purpose: provision and operate the unified Bitwarden delivery paths.
Status: current. Reviewed against: `d9a1261970b4d6607056507421a71ad52b5d07ce`.

## Setup without cluster access

Bitwarden Secrets Manager is the value maintenance home. Maintain values in its
UI. Use two projects: the existing application project and `home-ops-operator`.
First check the human account's project and machine-account capacity. Create an
operator machine account with read access to both projects and an ESO machine
account with read access only to the application project. Generate separate
tokens; preserve existing application values, shared items, and Talos identity.

Set the operator project's public UUID in the `operator` alias in
[secretspec.toml](../../../secretspec.toml). A nil UUID deliberately fails setup
instead of silently reusing the application project. The application alias
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
Operator commands find that directory automatically. Login prompts securely;
do not paste tokens into commands, Git, documentation, or chat. On macOS,
SecretSpec's keyring provider uses Keychain. Recovery requires access to
Bitwarden and this credential or a replacement token; this design has no
offline value cache or fallback. CI uses synthetic inputs, without Keychain or
cloud access.

## Value inventory and ordinary use

The manifest owns the exact key references and scope membership. Put existing
Talos YAML, backend access/secret keys, and the application-only ESO token into
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
permissions are the access boundary.

Direct playbook execution requires the same wrapper, for example:

```bash
.venv/bin/python scripts/operator_secrets.py run talos -- \
  .venv/bin/ansible-playbook ansible/playbooks/talos-generate.yml
```

Keep only nonsecret node, disk, context, and path settings in ignored `.envrc`.
`KUBECONFIG` is a single destination file, not a colon-separated list;
`TALOSCONFIG` selects the Talos client file; `TALOS_CONTROLPLANE_CONFIG_PATH`
selects the machine-config destination. `TALOS_CONFIG_DIR` changes the default
directory for both. Generation writes restricted
client files and cleans its temporary YAML/output directory even on failure.
Upgrades, Argo refresh, cleanup, formatting, and lint use existing clients and
do not resolve cloud secrets.

## One-time migration and retirement

This branch's runtime paths no longer use Vault or globally exported secrets.
The encrypted Talos file and its linter exclusions remain as a temporary recovery
input until real migration checks pass. Do not retire them on mocked evidence.

1. Provision the projects/accounts, then import existing Talos YAML and backend
   values, zone ID, and Tailscale OAuth client ID through the Bitwarden UI. Store
   the new ESO account token in the operator project. Retain the original
   operator-only application-project items during round-trip verification;
   the one-time verifier compares their original IDs. Keep the previous inputs
   and token available for rollback.
2. Load the existing ignored operator environment only for migration. Run
   `task secrets:verify-migration`. It decrypts Vault using a temporary `0600`
   password file, compares Talos/backend/infrastructure values in memory, and
   reports pass/fail without printing them. New values resolve through SecretSpec;
   the legacy token is used only to verify the original infrastructure item IDs.
3. Generate Talos config into an isolated directory, then remove that directory:

   ```bash
   generation_dir=$(mktemp -d)
   TALOSCONFIG="$generation_dir/talosconfig" \
     TALOS_CONTROLPLANE_CONFIG_PATH="$generation_dir/controlplane.yaml" \
     task talos:gen
   # Inspect only versions and installer; never print the whole config.
   rm -r -- "$generation_dir"
   ```

   Inspect versions and installer without printing credential fields. This
   validates generation without applying to the production node.
4. Stop concurrent infrastructure writers. Run `task tf:migrate-secret-state`.
   It pulls state, writes and verifies a `0600` backup in a `0700` directory under
   `~/.local/state/home-ops/state-recovery`, checks a private temporary plan for
   managed-resource changes before any remote state write, removes only the four
   retired data addresses, checks managed state is unchanged, and requires a
   zero-change plan.
   Retain the printed backup path. On failure, inspect the redacted stage and
   investigate before further state writes; restore with `tofu state push` from
   the verified backup if needed. Do not force overwrite newer concurrent state.
   Historical B2 state versions may still contain old data values; retention and
   native state encryption are separate work.
5. After the PR is merged, use the clean merged checkout for platform bootstrap
   or Argo reconciliation. Run `task secrets:sync-cluster-token` to patch only
   ESO's bootstrap Secret. It validates the new account's project access first,
   waits for fresh application-secret refreshes and target keys, and restores the
   previous token if reconciliation fails. An invalid token fails before patch.
   A restore failure is reported distinctly. The command does not reinstall Helm
   or apply the root Application.
6. Independently check affected application endpoints, controller events/logs,
   and consumers. Ready/Synced and target keys alone do not prove application
   behavior. Keep existing values stable throughout this migration.
7. Only after round-trip, generation, infrastructure, and live acceptance pass,
   delete the tracked encrypted Talos recovery file and its old exclusions/tests
   in a follow-up PR. Remove secret assignments from the ignored `.envrc` while
   preserving its nonsecret settings. Retire old machine tokens and obsolete
   local provider artifacts after rollback is no longer needed. Retire the two
   original operator-only application-project items after their operator-project
   copies have passed round-trip and infrastructure checks, so each value has
   one maintained item. Retain ignores
   for old plaintext, credential files, plans, state, and crash artifacts.

A full cold bootstrap is proved only on a disposable Talos environment with the
external NAS/storage/network prerequisites. Do not rebuild production to validate
this refactor. Bootstrap preflight authenticates to Bitwarden and Git and requires
a clean checkout matching remote `master` before node mutation. ESO readiness
must pass before Argo root handoff; handoff checks the captured revision and
ApplicationSet children, followed by fresh ExternalSecret reconciliation.

## Sources

- [SecretSpec manifest](../../../secretspec.toml)
- [Operator wrapper](../../../scripts/operator_secrets.py)
- [Read-only BWS adapter](../../../scripts/bws_readonly.py)
- [Bootstrap preflight](../../../scripts/bootstrap.py)
- [Cluster checks and token replacement](../../../scripts/cluster_secrets.py)
- [Migration verification](../../../scripts/verify_migration.py)
- [State retirement](../../../scripts/migrate_state.py)
- [Tool installation](../../../scripts/install_secrets_tools.py)
- [Task interface](../../../Taskfile.yaml)
- [SecretSpec credentials](https://secretspec.dev/reference/provider-credentials/) — credential precedence and keyring sources.
- [SecretSpec BWS implementation](https://github.com/cachix/secretspec/blob/v0.21.1/secretspec/src/provider/bws.rs) — native project reads and process-memory caching.

## Related pages

- [Secrets](../architecture/secrets.md)
- [Talos bootstrap](../architecture/talos-bootstrap.md)
- [Terraform](../architecture/terraform.md)
- [Backup and recovery](../architecture/backup-recovery.md)
