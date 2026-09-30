# Preserve shared media ownership

Purpose: explain the group policy for workloads mounting the shared media claim.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

[PR #406](https://github.com/edgard/home-ops/pull/406) records that MeTube's
initial group setting caused kubelet to change group ownership on the shared
media volume during startup. Workloads mounting `existingClaim: media` therefore
use `fsGroup: 0` and `fsGroupChangePolicy: OnRootMismatch`; processes can still
run as UID/GID 1000. Source and rendered policy enforce this shared-volume
contract. Check every consumer when changing permissions, not just the app that
motivated the edit.

## Sources

- [Shared media change, PR #406](https://github.com/edgard/home-ops/pull/406)
- [Source policy](../../../policy/source/app_template_values.rego)
- [Rendered workload policy](../../../policy/kubernetes/workload_security.rego)
- [Media claim](../../../apps/kube-system/nfs-provisioner/manifests/nfs-provisioner-media.persistentvolumeclaim.yaml)

## Related pages

- [Storage](../architecture/storage.md)
- [MeTube](../apps/media/metube.md)
- [Unpackerr](../apps/media/unpackerr.md)
