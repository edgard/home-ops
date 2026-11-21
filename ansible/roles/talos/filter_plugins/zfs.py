"""Read the import policy from native Talos machine resources without logging credentials."""

import re
from uuid import UUID

import yaml
from ansible.errors import AnsibleFilterError


def talos_zfs_state(resources):
    try:
        result = {}
        configs = {}
        for resource in yaml.safe_load_all(resources):
            key = resource["metadata"]["id"]
            if key not in ("v1alpha1", "persistent") or key in configs:
                raise ValueError
            docs = list(yaml.safe_load_all(resource["spec"]))
            if not any("machine" in doc for doc in docs):
                raise ValueError
            configs[key] = docs
            policy = [
                doc
                for doc in docs
                if (doc.get("kind"), doc.get("name"))
                == ("ExtensionServiceConfig", "zfs-service")
            ]
            if len(policy) != 1 or set(policy[0]) != {
                "apiVersion",
                "kind",
                "name",
                "environment",
            }:
                raise ValueError
            env = policy[0]["environment"]
            if len(env) != 1 or not env[0].startswith("ZPOOL_IMPORT_PATH="):
                raise ValueError
            paths = env[0].removeprefix("ZPOOL_IMPORT_PATH=").split(":")
            if paths != ["/dev/null"]:
                if len(set(paths)) != 4 or len(paths) != 4:
                    raise ValueError
                for path in paths:
                    match = re.fullmatch(r"/dev/disk/by-partuuid/([0-9a-f-]+)", path)
                    if not match or str(UUID(match[1])) != match[1]:
                        raise ValueError
            result[key] = {
                "policy": policy[0],
                "module": any(
                    (doc.get("kind"), doc.get("name")) == ("KernelModuleConfig", "zfs")
                    for doc in docs
                ),
            }
        if "v1alpha1" not in result:
            raise ValueError
        result["pending"] = (
            "persistent" in configs and configs["persistent"] != configs["v1alpha1"]
        )
        active = result["v1alpha1"]
        result["released"] = (
            not result["pending"]
            and active["module"]
            and active["policy"]["environment"] != ["ZPOOL_IMPORT_PATH=/dev/null"]
        )
        return result
    except AttributeError, IndexError, KeyError, TypeError, ValueError, yaml.YAMLError:
        raise AnsibleFilterError(
            "Cannot verify the active or staged ZFS import policy on the target"
        ) from None


class FilterModule:
    def filters(self):
        return {"talos_zfs_state": talos_zfs_state}
