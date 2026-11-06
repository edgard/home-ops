"""Paperless 3.3.4 local native controls; no network orchestration or credentials."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

PRODUCERS = ("svc-consumer", "svc-scheduler")


def status(service):
    return subprocess.check_output(
        ["s6-svstat", "-o", "up,wantedup", "/run/service/" + service], text=True
    ).strip()


def http_connections(table, port):
    """Every live accepted connection counts, including kubelet probes and uploads.

    TIME_WAIT and LISTEN cannot contain an in-flight request. All other states
    fail closed, including CLOSE_WAIT and pending SYN/FIN handshakes.
    """
    return sum(
        1
        for row in table.splitlines()[1:]
        if row.split()
        and int(row.split()[1].rsplit(":", 1)[1], 16) == port
        and row.split()[3] not in {"0A", "06"}
    )


def http_idle():
    port = int(os.environ.get("PAPERLESS_PORT", "8000"))
    count = sum(
        http_connections(Path(path).read_text(), port)
        for path in ("/proc/net/tcp", "/proc/net/tcp6")
    )
    assert count == 0, "HTTP connections remain"


def pause(app, name, call=subprocess.check_call):
    # Do not stop the old HTTP liveness target or worker.
    for service in PRODUCERS:
        call(["s6-svc", "-d", "/run/service/" + service])
    reply = app.control.cancel_consumer(
        "celery", destination=[name], reply=True, timeout=3
    )
    assert reply and "ok" in reply[0].get(name, {}), "native cancel reply missing"


def idle(app, name):
    assert all(status(service) == "false false" for service in PRODUCERS)
    assert status("svc-webserver") == "true true"
    assert status("svc-worker") == "true true"
    http_idle()
    inspect = app.control.inspect(destination=[name], timeout=3)
    assert inspect.active_queues() == {name: []}
    assert inspect.scheduled() == {name: []}
    assert inspect.reserved() == {name: []}
    assert inspect.active() == {name: []}
    http_idle()


def main(action):
    from paperless.celery import app

    name = "celery@" + socket.gethostname()
    assert not os.environ.get("REMAP_SIGTERM")
    assert app.conf.task_time_limit == 1800
    if action == "inspect":
        states = {
            service: status(service)
            for service in (*PRODUCERS, "svc-webserver", "svc-worker")
        }
        assert all(value == "true true" for value in states.values())
        queues = app.control.inspect(destination=[name], timeout=3).active_queues()
        assert queues and [row["name"] for row in queues[name]] == ["celery"]
        print(
            json.dumps(
                {"services": states, "queues": ["celery"], "hard_timeout_seconds": 1800}
            )
        )
    elif action == "pause":
        pause(app, name)
    elif action == "idle":
        idle(app, name)
    elif action == "http-idle":
        http_idle()
    else:
        raise ValueError("unknown native enrollment action")


if __name__ == "__main__":
    main(sys.argv[1])
