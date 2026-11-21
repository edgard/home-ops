# Samba

Purpose: publish selected NAS datasets as guest-writable SMB shares on the home LAN.
Status: current. Reviewed against: `50dc84a27f19eac0ca5d644abdeccc2d4383bc48` and this revision.

## Shares and ownership

One Samba pod runs in the existing `selfhosted` namespace on `homelab`. The share
configuration names each export. Each export gets a separate, exact host
directory mount. The existing media applications keep their Kubernetes claim.
Samba can serve datasets used by other namespaces because it mounts their ZFS
filesystems directly. No new copy of the media library or download tree is
created, and existing hardlinks keep referring to the same files.

Before opening its listener, the container checks the current boot's pool
verification marker and its own mount table. Every configured share must be
a writable mount of the root of the expected ZFS dataset. A missing or
incorrect mount stops startup. Keep the host ZFS `sharesmb` property off.

Guest operations run as Unix UID 1000. A guest with access can change and
delete files according to that identity's filesystem permissions. Guest
connections share one identity. Samba startup does not change ownership or
ACLs on existing files. SMB clients can manage file contents, while host-side
tools manage permissions. SMB does not follow symbolic links or expose the
ZFS snapshot directory. Existing media hardlinks work as before. The server uses a fixed local SID and rebuilds its
local Samba databases on pod replacement. Only the exported ZFS files need
independent data protection. When adding an export, add its exact mount, share
definition and startup check in the same change. Check the existing owner
permissions before enabling writes.

## LAN access and recovery

Connect to `smb://192.168.1.253/dump` or `smb://192.168.1.253/media`.
In Finder, use **Go → Connect to Server**, then **Guest**. The pod receives
the node's LAN TCP port 445 on its own high port. Samba restricts clients
by source address. Readiness opens each share as an SMB guest over loopback.
The server uses SMB2/3. Windows clients that require signed
sessions may reject guest access. [Microsoft guest SMB guidance](https://learn.microsoft.com/en-us/windows-server/storage/file-server/enable-insecure-guest-logons-smb2-and-smb3)

The hourly ZFS policy and the namespace Restic backups cover application
data. They do not cover files in these two shared datasets. Preserve an
independent copy of any files that need recovery. To validate an export,
connect as a guest from a LAN client, create a uniquely named temporary
file, read it back, rename it and remove it. Repeat on every writable share.
Cold recovery requires Samba and other direct pool writers to be fenced
before restoring or releasing workloads.

## Sources

- [Application metadata](../../../../apps/selfhosted/samba/app.yaml) and [pod, network and mounts](../../../../apps/selfhosted/samba/values.yaml)
- [Samba configuration](../../../../apps/selfhosted/samba/manifests/samba-config.configmap.yaml) and [startup mount check](../../../../apps/selfhosted/samba/manifests/samba-storage-check.configmap.yaml)
- [Selfhosted Argo project](../../../../argocd/projects/selfhosted.appproject.yaml)
- [Recovery writer detection](../../../../ansible/roles/platform/filter_plugins/storage.py)
- [Samba configuration reference](https://www.samba.org/samba/docs/current/man-html/smb.conf.5.html) — guest mapping, share access and client restrictions.

## Related pages

- [Storage and shared media](../../architecture/storage.md)
- [Networking and ingress](../../architecture/networking.md)
- [Restic backup and restore](../../operations/restic-backup-restore.md)
