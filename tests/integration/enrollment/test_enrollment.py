"""Pure safety contracts; native and actual-role coverage are separate."""

import importlib.util
import os

import jsonpatch
import pytest

from tests.support.runtime import ROOT

ROLE = ROOT / "ansible/roles/shared_data"


def module(name, folder="filter_plugins"):
    path = ROLE / folder / (name + ".py")
    assert path.is_file(), f"Missing executable {name} enrollment prerequisite"
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def template():
    return {
        "metadata": {"labels": {"app": "paperless-main"}},
        "spec": {
            "terminationGracePeriodSeconds": 30,
            "volumes": [
                {"name": "data", "persistentVolumeClaim": {"claimName": "paperless"}}
            ],
            "containers": [
                {
                    "name": "app",
                    "image": "ghcr.io/paperless-ngx/paperless-ngx:3.3.4",
                    "env": [
                        {
                            "name": "PAPERLESS_REDIS",
                            "value": "redis://paperless-redis:6379",
                        }
                    ],
                    "livenessProbe": {"httpGet": {"path": "/", "port": 8000}},
                }
            ],
        },
    }


def protected():
    result = template()
    result["spec"]["terminationGracePeriodSeconds"] = 2000
    app = result["spec"]["containers"][0]
    app["image"] += "@sha256:" + "a" * 64
    app["livenessProbe"] = {
        "exec": {
            "command": [
                "sh",
                "-c",
                'test "$(s6-svstat -o up /run/service/svc-worker)" = true',
            ]
        }
    }
    app["env"] += [
        {"name": "PAPERLESS_WORKER_TIMEOUT", "value": "1800"},
        {"name": "S6_KILL_GRACETIME", "value": "3000"},
    ]
    return result


def test_shutdown_patch_never_temporarily_restores_positive_replicas():
    m = module("enrollment")
    current = {
        "metadata": {"uid": "main-uid", "resourceVersion": "17"},
        "spec": {"replicas": 0, "template": template()},
    }
    patch = m.shared_data_enrollment_patch(current, "main-uid", protected())
    updated = jsonpatch.apply_patch(current, patch)
    assert updated["spec"]["replicas"] == 0
    assert updated["spec"]["template"] == protected()
    current["spec"]["replicas"] = 1
    with pytest.raises(ValueError, match="zero"):
        m.shared_data_enrollment_patch(current, "main-uid", protected())
    current["spec"]["replicas"] = 0
    current["metadata"]["uid"] = "replacement"
    with pytest.raises(ValueError, match="identity"):
        m.shared_data_enrollment_patch(current, "main-uid", protected())


@pytest.mark.parametrize(
    "mutation", ["redis", "storage", "image", "secret", "extra-env", "init"]
)
def test_protected_patch_rejects_covert_cutover(mutation):
    m = module("enrollment")
    desired = protected()
    app = desired["spec"]["containers"][0]
    if mutation == "redis":
        app["env"][0]["value"] = "redis://shared-redis:6379"
    elif mutation == "storage":
        desired["spec"]["volumes"][0]["persistentVolumeClaim"]["claimName"] = "new"
    elif mutation == "image":
        app["image"] = app["image"].replace("3.3.4", "3.3.5")
    elif mutation == "secret":
        app["env"].append({"name": "PAPERLESS_SECRET_KEY", "value": "do-not-journal"})
    elif mutation == "extra-env":
        app["env"].append({"name": "PAPERLESS_DBHOST", "value": "postgresql"})
    else:
        desired["spec"]["initContainers"] = [{"name": "change-db", "image": "evil"}]
    with pytest.raises(ValueError, match="shutdown-only"):
        m.shared_data_enrollment_delta(template(), desired)


def test_http_probe_connections_are_not_exempted_from_drain():
    m = module("paperless_enrollment", "files")
    header = "sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n"
    # Includes node-origin kubelet probe, an upload, and CLOSE_WAIT: all block.
    rows = [
        "0: 0100007F:1F40 0200007F:CE11 01 0:0 0:0 0 0 0 1",
        "1: 0100007F:1F40 0300007F:CE11 08 0:0 0:0 0 0 0 2",
    ]
    assert m.http_connections(header + "\n".join(rows), 8000) == 2
    assert (
        m.http_connections(
            header + "0: 00000000:1F40 00000000:0000 0A 0:0 0:0 0 0 0 3", 8000
        )
        == 0
    )
    assert (
        m.http_connections(
            header + "0: 0100007F:1F40 0300007F:CE11 06 0:0 0:0 0 0 0 0", 8000
        )
        == 0
    )


def test_native_pause_leaves_old_web_and_worker_up():
    m = module("paperless_enrollment", "files")
    calls = []

    class Control:
        def cancel_consumer(self, queue, **kwargs):
            calls.append(("cancel", queue))
            return [{"celery@test": {"ok": "ok"}}]

    app = type("App", (), {"control": Control()})()
    m.pause(app, "celery@test", lambda args: calls.append(tuple(args)))
    assert ("cancel", "celery") in calls
    assert all(
        "svc-webserver" not in str(call) and "svc-worker" not in str(call)
        for call in calls
    )
    assert any("svc-consumer" in str(call) for call in calls)
    assert any("svc-scheduler" in str(call) for call in calls)


def test_session_rejects_uid_impersonation_and_arbitrary_command_inputs(monkeypatch):
    import json

    m = module("operator_session", "files")
    payload = {
        "shared_data_action": "operator_execute",
        "shared_data_confirm": True,
        "shared_data_operator_step": "renew",
        "shared_data_holder_pod_uid": "original",
    }
    monkeypatch.setenv("POD_UID", "different")
    with pytest.raises(ValueError, match="original immutable actor"):
        m.main(json.dumps(payload))
    monkeypatch.setenv("POD_UID", "original")
    payload["command"] = "arbitrary shell"
    with pytest.raises(ValueError, match="named operator"):
        m.main(json.dumps(payload))


def test_session_serializes_same_actor_exec_without_background_heartbeat(
    tmp_path, monkeypatch
):
    import builtins
    import fcntl
    import json

    m = module("operator_session", "files")
    monkeypatch.setenv("POD_UID", "original")
    executable = tmp_path / "ansible-playbook"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    lock = tmp_path / "session.lock"
    monkeypatch.setattr(
        m, "open", lambda *_args, **_kwargs: builtins.open(lock, "w"), raising=False
    )
    payload = json.dumps(
        {
            "shared_data_action": "operator_execute",
            "shared_data_confirm": True,
            "shared_data_operator_step": "renew",
            "shared_data_holder_pod_uid": "original",
        }
    )
    with builtins.open(lock, "w") as competing:
        fcntl.flock(competing, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            m.main(payload)
    assert m.main(payload) == 0
