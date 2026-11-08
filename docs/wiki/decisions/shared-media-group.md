# Preserve shared media ownership

Purpose: explain the group policy for workloads mounting the shared media claim.
Status: current. Reviewed against: `f73a66d4d60b9fd7e373eb1cfcbde4e8df270083`.

[PR #406](https://github.com/edgard/home-ops/pull/406) records that MeTube's
initial group setting caused kubelet to change group ownership on the shared
media volume during startup. Workloads mounting `existingClaim: media` therefore
use `fsGroup: 0` and `fsGroupChangePolicy: OnRootMismatch`; processes can still
run as UID/GID 1000. The rendered data guard enforces this shared-volume contract. Check every consumer when changing permissions, not just the app that
motivated the edit.

## Sources

- [Shared media change, PR #406](https://github.com/edgard/home-ops/pull/406)
- [Rendered data guards](../../../validation/data.py)
- [Media claim](../../../apps/kube-system/nfs-provisioner/manifests/nfs-provisioner-media.persistentvolumeclaim.yaml)

## Related pages

- [Storage](../architecture/storage.md)
- [Unpackerr](../apps/media/unpackerr.md)
