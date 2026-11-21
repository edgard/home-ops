# Home Ops

A single-node Talos Linux homelab managed by Argo CD. OpenEBS provisions application volumes on ZFS. Local ZFS datasets hold the Restic repository and the files shared over SMB. Ansible bootstraps the node and platform, and OpenTofu manages external infrastructure.

The [knowledge wiki](docs/wiki/index.md) covers the architecture, applications and operating procedures.

## Install or recover the cluster

Set up the [operator tools](docs/wiki/agent-workflow.md#local-setup) and [Bitwarden access](docs/wiki/operations/secrets-maintenance.md#setup-without-cluster-access). Identify the [system SSD, uplink](docs/wiki/architecture/talos-bootstrap.md#identify-the-node) and [storage pool](docs/wiki/architecture/storage.md#prepare-storage-for-a-talos-install). Choose the procedure that matches the state you have.

| Starting point | Procedure |
| --- | --- |
| First installation with empty appdata | Follow [first boot and pool enrollment](docs/wiki/architecture/talos-bootstrap.md#first-boot-and-pool-enrollment), then the [first-installation handoff](docs/wiki/architecture/gitops-delivery.md#first-installation-and-recovery). |
| Rebuilding with a matching etcd snapshot | [Restore the existing control plane from its snapshot](docs/wiki/architecture/talos-bootstrap.md#recover-the-existing-control-plane) to preserve and verify the existing volume bindings. |
| Rebuilding without etcd, with appdata to recover | [Bootstrap fresh etcd and enroll the pool](docs/wiki/architecture/talos-bootstrap.md#first-boot-and-pool-enrollment), then [restore and verify the fresh claims](docs/wiki/operations/restic-backup-restore.md#new-cluster-or-lost-etcd-state) before starting workloads. |

## Operate the homelab

- [Back up and restore application data](docs/wiki/operations/restic-backup-restore.md)
- [Connect to the dump and media SMB shares](docs/wiki/apps/selfhosted/samba.md#lan-access-and-recovery)
- [Find an application and its configuration](docs/wiki/index.md#applications)

## Contribute

Read [AGENTS.md](AGENTS.md) for the pull request workflow. After installing the [local tools](docs/wiki/agent-workflow.md#local-setup), use these commands to set up the checkout, list tasks and validate a change.

```sh
task deps
task --list
task fmt
task check
```
