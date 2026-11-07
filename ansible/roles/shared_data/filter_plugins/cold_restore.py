"""Cold restore bindings are pure; only role tasks touch the Kubernetes API."""

import hashlib
import json
import re


def shared_data_cold_source_digest(registry, revision):
    return hashlib.sha256(
        json.dumps(
            {"registry": registry, "revision": revision},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def shared_data_cold_restore(cold, restore, registry):
    if cold.get("source_sha256") != shared_data_cold_source_digest(
        registry, cold.get("revision")
    ):
        raise ValueError("restore registry source differs from bootstrap")
    if (
        cold.get("phase") != "held"
        or cold.get("apps") != restore.get("apps")
        or not re.fullmatch(r"[a-z0-9]{32}", cold.get("token", ""))
        or not re.fullmatch(r"[a-f0-9]{40}", cold.get("revision", ""))
    ):
        raise ValueError(
            "cold restore needs the exact held bootstrap identity and scope"
        )
    for snapshot in restore.get("snapshots", []):
        identity = {
            k: snapshot[k] for k in ["api_version", "kind", "namespace", "name", "uid"]
        }
        if not any(
            all(row.get(k) == v for k, v in identity.items())
            for row in cold.get("inventory", [])
        ):
            raise ValueError(
                "cold restore resource identity differs from infrastructure inventory"
            )
        role = snapshot["role"]
        value = snapshot.get("value")
        if (
            (role in {"workload", "tuppr"} and value != 0)
            or (role == "cronjob" and value is not True)
            or (
                role in {"root", "application"}
                and isinstance(value, dict)
                and value.get("automated") is not None
            )
        ):
            raise ValueError(
                "cold restore refuses any positive original writer or automatic reconciliation"
            )
    return True


class FilterModule:
    def filters(self):
        return {
            "shared_data_cold_restore": shared_data_cold_restore,
            "shared_data_cold_source_digest": shared_data_cold_source_digest,
        }
