"""Execute the exact parsed idle command against deterministic native-state transitions.

Only external Celery inspection and S6 status are doubled. A task that moves
upstream-to-downstream between separate replies must never be admitted as idle.
"""

import shlex
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from tests.support.runtime import ROOT

REGISTRY = ROOT / "ansible/roles/shared_data/files/registry.yaml"
WORKER = "celery@queue-regression"


class Inspector:
    def __init__(
        self,
        state=None,
        route=None,
        missing_reply=None,
        consuming=False,
        transition_after="active",
    ):
        self.state = state
        self.route = route
        self.missing_reply = missing_reply
        self.consuming = consuming
        self.transition_after = transition_after
        self.calls = []
        self.transitions = []

    def snapshot(self, field):
        self.calls.append(field)
        if field == self.missing_reply:
            return None
        requests = [{"id": "synthetic-request"}] if self.state == field else []
        # Each RPC captures its reply before the request advances downstream.
        # Reserved/the ETA timer may no longer contain an already-active request.
        if (
            field
            in (
                (self.transition_after,)
                if isinstance(self.transition_after, str)
                else self.transition_after
            )
            and self.route
            and self.state == self.route[0]
        ):
            for next_state in self.route[1:]:
                self.transitions.append((self.state, next_state))
                self.state = next_state
        return {WORKER: requests}

    def active_queues(self):
        self.calls.append("active_queues")
        response = {WORKER: [{"name": "celery"}] if self.consuming else []}
        if self.transition_after == "active_queues" and self.route:
            for next_state in self.route[1:]:
                self.transitions.append((self.state, next_state))
                self.state = next_state
        return response

    def scheduled(self):
        return self.snapshot("scheduled")

    def reserved(self):
        return self.snapshot("reserved")

    def active(self):
        return self.snapshot("active")


def admitted(inspector):
    spec = yaml.safe_load(REGISTRY.read_text())["consumers"]["paperless"]["drain"]
    command = shlex.split(spec["idle_command"])
    assert command[:2] == ["python3", "-c"]
    assert len(command) == 3
    celery = ModuleType("paperless.celery")

    def inspect(**kwargs):
        assert kwargs == {"destination": [WORKER], "timeout": 3}
        return inspector

    celery.app = SimpleNamespace(control=SimpleNamespace(inspect=inspect))

    def s6_status(command, *, text):
        assert text is True
        assert command[:2] == ["s6-svstat", "-o"]
        service = command[3].removeprefix("/run/service/")
        if service == "svc-worker":
            assert command[2] == "up,wantedup"
            return "true true\n"
        assert service in {"svc-webserver", "svc-consumer", "svc-scheduler"}
        assert command[2] == "up"
        return "false\n"

    with (
        patch.dict(
            sys.modules,
            {"paperless": ModuleType("paperless"), "paperless.celery": celery},
        ),
        patch("socket.gethostname", return_value="queue-regression"),
        patch("subprocess.check_output", side_effect=s6_status),
    ):
        try:
            exec(compile(command[2], "<exact Paperless idle_command>", "exec"), {})
        except AssertionError:
            return False
    return True


@pytest.mark.parametrize(
    "route",
    [
        ("reserved", "active"),
        ("scheduled", "active"),
        ("scheduled", "reserved", "active"),
    ],
)
def test_pending_request_cannot_disappear_between_rpc_snapshots(route):
    inspector = Inspector(state=route[0], route=route)
    assert not admitted(inspector), (
        f"admitted while state={inspector.state}; calls={inspector.calls}; "
        f"transitions={inspector.transitions}"
    )


@pytest.mark.parametrize("state", ["scheduled", "reserved", "active"])
def test_any_stable_inflight_request_blocks_shutdown(state):
    assert not admitted(Inspector(state=state))


@pytest.mark.parametrize("field", ["scheduled", "reserved", "active"])
def test_missing_native_reply_is_not_an_idle_snapshot(field):
    assert not admitted(Inspector(missing_reply=field))


def test_quiet_worker_with_no_inflight_work_is_idle():
    assert admitted(Inspector())


def test_broker_dispatch_still_enabled_blocks_shutdown():
    assert not admitted(Inspector(consuming=True))


@pytest.mark.parametrize(
    "route,transition_after",
    [
        (("reserved", "active"), ("scheduled", "active")),
        (("scheduled", "reserved", "active"), "active_queues"),
    ],
)
def test_request_that_advances_between_new_guard_snapshots_is_still_rejected(
    route, transition_after
):
    inspector = Inspector(
        state=route[0], route=route, transition_after=transition_after
    )
    assert not admitted(inspector), (
        f"admitted while state={inspector.state}; calls={inspector.calls}; "
        f"transitions={inspector.transitions}"
    )
    assert inspector.state == "active"
    assert inspector.transitions
