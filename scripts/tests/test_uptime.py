"""The configured uptime targets must cover routed applications."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "check_uptime.py"


class UptimeCoverageTests(unittest.TestCase):
    def run_check(self, routes: str, endpoints: str, *extra_args: str, raw_route: str = ""):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rendered = root / "rendered"
            rendered.mkdir()
            (rendered / "apps.yaml").write_text(routes)
            apps = root / "apps"
            gatus = apps / "platform-system" / "gatus"
            gatus.mkdir(parents=True)
            (gatus / "values.yaml").write_text(
                "gateway:\n  route:\n    hosts: [status.edgard.org]\n"
                "config:\n  endpoints:\n" + endpoints
            )
            if raw_route:
                manifests = apps / "platform-system" / "manual" / "manifests"
                manifests.mkdir(parents=True)
                (manifests / "manual.httproute.yaml").write_text(raw_route)
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(rendered), str(apps), *extra_args],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_missing_routed_app_fails(self):
        routes = """---
kind: HTTPRoute
spec:
  hostnames: [plex.edgard.org]
"""
        result = self.run_check(routes, "    - name: other\n      url: https://other.edgard.org\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("plex.edgard.org", result.stderr)

    def test_obsolete_target_fails(self):
        result = self.run_check("---\nkind: ConfigMap\n", "    - name: old\n      url: https://old.edgard.org\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("old.edgard.org", result.stderr)

    def test_chart_and_raw_routes_are_covered_without_monitoring_status_itself(self):
        routes = """---
kind: HTTPRoute
spec:
  hostnames: [plex.edgard.org]
---
kind: HTTPRoute
spec:
  hostnames: [status.edgard.org]
"""
        raw_route = "---\nkind: HTTPRoute\nspec:\n  hostnames: [argocd.edgard.org]\n"
        endpoints = (
            "    - name: plex\n      url: https://plex.edgard.org/identity\n"
            "    - name: argocd\n      url: https://argocd.edgard.org\n"
        )
        result = self.run_check(routes, endpoints, raw_route=raw_route)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
