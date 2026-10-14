# Preserve shared media ownership

Purpose: explain the group policy for workloads mounting the shared media claim.
Status: current. Reviewed against: `e66f8dac017406e0b72605aa16d5f7862aaa0c8a`.

[PR #406](https://github.com/edgard/home-ops/pull/406) records that MeTube's
initial group setting caused kubelet to change group ownership on the shared
media volume during startup. Workloads mounting `existingClaim: media` therefore
use `fsGroup: 0` and `fsGroupChangePolicy: OnRootMismatch`; processes can still
run as UID/GID 1000. Source and rendered policy enforce this shared-volume
contract. Check every consumer when changing permissions, not just the app that
motivated the edit.

## Sources

- [Shared media change, PR #406](https://github.com/edgard/home-ops/pull/406)
- [Source assertions](../../../tests/support/applications.py)
- [Rendered workload assertions](../../../tests/support/resources.py)
- [Media claim](../../../apps/kube-system/nfs-provisioner/manifests/nfs-provisioner-media.persistentvolumeclaim.yaml)

## Related pages

- [Storage](../architecture/storage.md)
- [Unpackerr](../apps/media/unpackerr.md)
