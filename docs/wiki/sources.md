# Source catalog

Purpose: locate the evidence used to build and maintain this wiki.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

The immutable starting snapshot is Git commit
[`2b1488a2`](https://github.com/edgard/home-ops/tree/2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b).
Current claims link to the owning files on the active branch; historical reasons
link to merged PRs or commits. Git history is the raw source archive. This
catalog is a guide to it, not a copy of all tracked files.

## Current source areas

| Area | Primary source | Wiki synthesis |
| --- | --- | --- |
| App discovery and reconciliation | [ApplicationSet](../../argocd/appsets/apps.appset.yaml) | [GitOps delivery](architecture/gitops-delivery.md) |
| App definitions | [Apps](../../apps) | [App catalog](index.md#applications) |
| Bootstrap and operations | [Ansible](../../ansible) and [Taskfile](../../Taskfile.yaml) | [Talos](architecture/talos-bootstrap.md), [recovery](architecture/backup-recovery.md) |
| External infrastructure | [Terraform](../../terraform) | [Terraform](architecture/terraform.md) |
| Enforced contracts | [Policy](../../policy) and [CI](../../.github/workflows/ci.yml) | [Validation](architecture/validation.md) |

## Decision evidence

- [Operator credential split, PR #225](https://github.com/edgard/home-ops/pull/225)
- [Focused CI jobs, PR #258](https://github.com/edgard/home-ops/pull/258)
- [Shared Restic repository hardening, PR #260](https://github.com/edgard/home-ops/pull/260)
- [Restic restore automation, PR #261](https://github.com/edgard/home-ops/pull/261)
- [Gluetun health incident, PR #383](https://github.com/edgard/home-ops/pull/383)
- [Authenticated CrossWatch route, PR #387](https://github.com/edgard/home-ops/pull/387)
- [Talos Image Factory installer, PR #394](https://github.com/edgard/home-ops/pull/394)
- [Gatus deployment, PR #397](https://github.com/edgard/home-ops/pull/397),
  [retirement of the old stack, PR #398](https://github.com/edgard/home-ops/pull/398), and
  [grouped checks, PR #399](https://github.com/edgard/home-ops/pull/399)
- [Shared media ownership, PR #406](https://github.com/edgard/home-ops/pull/406)
- [Validation structure, PR #409](https://github.com/edgard/home-ops/pull/409)
- [Jellyfin staging, PR #411](https://github.com/edgard/home-ops/pull/411),
  [health probes, PR #412](https://github.com/edgard/home-ops/pull/412),
  [Plex removal, PR #413](https://github.com/edgard/home-ops/pull/413), and
  [LAN discovery, PR #414](https://github.com/edgard/home-ops/pull/414)

These PRs explain the current design. Retired components and routine version
updates are not treated as current architecture. External upstream docs may be
linked from an affected page with a short relevance note; they are not copied.

## Related pages

- [Index](index.md)
- [Wiki maintenance rules](AGENTS.md)
