"""Render app-owned appdata claims with the same names and values Argo uses."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


def render_claims(root):
    claims = []
    with tempfile.TemporaryDirectory(prefix="home-ops-claims-") as cache:
        charts = {}
        for metadata in sorted(root.glob("apps/*/*/app.yaml")):
            app = metadata.parent
            values_file = app / "values.yaml"
            values = yaml.safe_load(values_file.read_text())
            persistence = values.get("persistence") or {}
            if not any(
                isinstance(volume, dict)
                and volume.get("type") == "persistentVolumeClaim"
                and not volume.get("existingClaim")
                and volume.get("enabled", True)
                for volume in persistence.values()
            ):
                continue
            chart = yaml.safe_load(metadata.read_text())["chart"]
            namespace = app.parent.name
            url, version = chart["repo"], str(chart["version"])
            if not url.startswith("oci://") or not url.endswith("/app-template"):
                raise ValueError(
                    f"unsupported appdata chart for {namespace}/{app.name}"
                )
            if (url, version) not in charts:
                directory = Path(cache) / str(len(charts))
                directory.mkdir()
                subprocess.run(
                    [
                        "helm",
                        "pull",
                        url,
                        "--version",
                        version,
                        "--destination",
                        str(directory),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                (charts[url, version],) = directory.glob("*.tgz")
            rendered = subprocess.check_output(
                [
                    "helm",
                    "template",
                    app.name,
                    str(charts[url, version]),
                    "--namespace",
                    namespace,
                    "--values",
                    str(values_file),
                ],
                text=True,
            )
            owned = [
                d
                for d in yaml.safe_load_all(rendered)
                if d and d.get("kind") == "PersistentVolumeClaim"
            ]
            if not owned:
                raise ValueError(
                    f"no appdata claim rendered for {namespace}/{app.name}"
                )
            for claim in owned:
                meta, spec = claim["metadata"], claim["spec"]
                if (
                    meta.get("namespace", namespace) != namespace
                    or spec.get("storageClassName", "zfs-appdata") != "zfs-appdata"
                    or spec.get("volumeName")
                    or spec.get("dataSource")
                    or spec["accessModes"] != ["ReadWriteOnce"]
                ):
                    raise ValueError(
                        f"unexpected claim binding for {namespace}/{app.name}"
                    )
                meta["namespace"] = namespace
                spec["storageClassName"] = "zfs-appdata"
                claims.append(claim)
    keys = [(d["metadata"]["namespace"], d["metadata"]["name"]) for d in claims]
    if not keys or len(keys) != len(set(keys)):
        raise ValueError("missing or duplicate appdata claims")
    return claims


if __name__ == "__main__":
    print(json.dumps(render_claims(Path(sys.argv[1]))))
