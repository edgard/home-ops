#!/usr/bin/env python3
"""Keep Gatus HTTP targets aligned with rendered Gateway routes."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit


def load_documents(paths):
    if not paths:
        return []
    result = subprocess.run(
        ["yq", "eval-all", "-o=json", "-I=0", "[.]", *(str(path) for path in paths)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def route_hosts(paths):
    hosts = set()
    for document in load_documents(paths):
        if isinstance(document, dict) and document.get("kind") == "HTTPRoute":
            hosts.update(document.get("spec", {}).get("hostnames", []))
    return hosts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rendered_root", type=Path)
    parser.add_argument("apps_root", type=Path)
    args = parser.parse_args()

    values_path = args.apps_root / "platform-system/gatus/values.yaml"
    values = load_documents((values_path,))[0]
    chart_routes = args.rendered_root.rglob("*.yaml")
    raw_routes = args.apps_root.rglob("*.httproute.yaml")
    expected = route_hosts((*chart_routes, *raw_routes))
    expected.difference_update(values.get("gateway", {}).get("route", {}).get("hosts", []))

    actual = set()
    duplicate_hosts = set()
    for endpoint in values["config"]["endpoints"]:
        parsed = urlsplit(endpoint["url"])
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.hostname in actual:
            duplicate_hosts.add(parsed.hostname)
        actual.add(parsed.hostname)

    errors = []
    if missing := expected - actual:
        errors.append(f"Unmonitored HTTPRoutes: {', '.join(sorted(missing))}")
    if obsolete := actual - expected:
        errors.append(f"Gatus targets without HTTPRoutes: {', '.join(sorted(obsolete))}")
    if duplicate_hosts:
        errors.append(f"Duplicate Gatus HTTP targets: {', '.join(sorted(duplicate_hosts))}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Gatus covers {len(actual)} routed applications")
    return 0


if __name__ == "__main__":
    sys.exit(main())
