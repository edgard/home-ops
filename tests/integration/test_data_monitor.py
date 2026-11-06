"""Watchdog health delivery uses API state and actual authenticated HTTP."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tests.integration import test_data_maintenance as api
from tests.support.runtime import run_role


@pytest.mark.parametrize("failed_watchdog", [False, True])
def test_monitor_reports_stale_backup_separately_and_has_no_storage_reads(
    tmp_path, failed_watchdog
):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            received.append((self.path, self.headers.get("Authorization")))
            self.send_response(200)
            self.end_headers()

    token = tmp_path / "gatus-token"
    token.write_text("synthetic-test-token")
    objects = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "shared-data-operation",
                "namespace": "selfhosted",
                "uid": "journal",
                "resourceVersion": "1",
            },
            "data": {"journal.json": json.dumps({"phase": "complete"})},
        }
    ]
    if failed_watchdog:
        objects[0]["data"]["journal.json"] = json.dumps({"phase": "held"})
        objects.append(
            {
                "apiVersion": "coordination.k8s.io/v1",
                "kind": "Lease",
                "metadata": {
                    "name": "shared-data-operation",
                    "namespace": "selfhosted",
                    "uid": "lease",
                    "resourceVersion": "1",
                },
                "spec": {
                    "holderIdentity": "old:uid",
                    "renewTime": "2020-01-01T00:00:00Z",
                    "leaseDurationSeconds": 900,
                },
            }
        )
    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with api.maintenance_api(tmp_path, objects) as (connection, state):
            result = run_role(
                tmp_path,
                "shared_data",
                "watchdog",
                {
                    **connection,
                    "shared_data_confirm": True,
                    "shared_data_monitor_enabled": True,
                    "shared_data_monitor_url": f"http://127.0.0.1:{server.server_port}",
                    "shared_data_monitor_token_file": str(token),
                },
            )
            assert (result.returncode != 0) == failed_watchdog, (
                result.stdout + result.stderr
            )
            assert received == [
                (
                    "/api/v1/endpoints/operations_shared-data/external?success="
                    + ("false" if failed_watchdog else "true"),
                    "Bearer synthetic-test-token",
                ),
                (
                    "/api/v1/endpoints/backups_shared-data/external?success=false",
                    "Bearer synthetic-test-token",
                ),
            ]
            assert "synthetic-test-token" not in result.stdout + result.stderr
            assert all(event["method"] == "GET" for event in state["events"])
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
