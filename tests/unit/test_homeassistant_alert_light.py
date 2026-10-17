import json
from datetime import UTC, datetime

import pytest
from jinja2 import Environment, StrictUndefined

from tests.support.sources import read_yaml

SOURCE = "apps/home-automation/homeassistant/manifests/homeassistant-gatus-alert-light.configmap.yaml"
NOW = 1_800_000_000


def test_production_template_exists(repo_root):
    assert (repo_root / SOURCE).is_file(), "Missing alert-light production templates"


@pytest.fixture
def macros(repo_root):
    source = read_yaml(repo_root / SOURCE)["data"]["gatus_alert_light.jinja"]
    env = Environment(undefined=StrictUndefined)

    def timestamp(value, default=None):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError, TypeError, AttributeError:
            return default

    env.filters["to_json"] = lambda value: json.dumps(value, separators=(",", ":"))
    env.globals["as_timestamp"] = timestamp
    return env.from_string(source).module


def history(successes):
    return [
        {
            "success": success,
            "timestamp": datetime.fromtimestamp(
                NOW - 60 * (len(successes) - index - 1), UTC
            ).isoformat(),
        }
        for index, success in enumerate(successes)
    ]


@pytest.mark.parametrize(
    "results,previous,active,transition",
    [
        ([False] * 4, False, False, ""),
        ([False] * 5, False, True, "triggered"),
        ([False] * 5 + [True], False, True, "triggered"),
        ([False] * 5 + [True, True], False, False, "resolved"),
        ([False, True, False], True, True, ""),
        ([True, True] + [False] * 5, False, True, "triggered"),
        ([True, True] + [False] * 4, True, False, "resolved"),
    ],
)
def test_history_hysteresis(macros, results, previous, active, transition):
    result = json.loads(macros.reduce_history(history(results), previous, NOW, 5, 2))
    assert result == {"valid": True, "active": active, "transition": transition}


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        {},
        [],
        [{"timestamp": "2027-01-15T08:00:00Z"}],
        [{"success": "true", "timestamp": "2027-01-15T08:00:00Z"}],
        [{"success": False, "timestamp": "invalid"}],
        history([True, True])[::-1],
        [history([True])[0]] * 2,
        [
            {
                "success": True,
                "timestamp": datetime.fromtimestamp(NOW - 181, UTC).isoformat(),
            }
        ],
        [
            {
                "success": True,
                "timestamp": datetime.fromtimestamp(NOW + 31, UTC).isoformat(),
            }
        ],
    ],
)
def test_invalid_history_preserves_open_warning(macros, invalid):
    result = json.loads(macros.reduce_history(invalid, True, NOW, 5, 2))
    assert result == {"valid": False, "active": True, "transition": ""}


@pytest.mark.parametrize("status", ["triggered", "resolved"])
def test_nested_event_identity(macros, status):
    payload = {"event_data": {"endpoint": "apps/argocd", "status": status}}
    assert json.loads(macros.normalize_event(payload, ["apps/argocd"])) == {
        "valid": True,
        "endpoint": "apps/argocd",
        "status": status,
    }


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"endpoint": "apps/argocd", "status": "triggered"},
        {"event_data": "invalid"},
        {"event_data": {"endpoint": "apps/argocd"}},
        {"event_data": {"endpoint": "argocd", "status": "triggered"}},
        {"event_data": {"endpoint": "apps/argocd", "status": "unknown"}},
        {"event_data": {"endpoint": ["apps/argocd"], "status": "triggered"}},
    ],
)
def test_malformed_events_are_not_alerts(macros, payload):
    assert (
        json.loads(macros.normalize_event(payload, ["apps/argocd"]))["valid"] is False
    )


@pytest.mark.parametrize(
    "state,attributes,snapshot",
    [
        ("off", {}, {"state": "off"}),
        (
            "on",
            {"brightness": 77, "color_mode": "color_temp", "color_temp_kelvin": 2202},
            {
                "state": "on",
                "brightness": 77,
                "color_mode": "color_temp",
                "color_temp_kelvin": 2202,
            },
        ),
        (
            "on",
            {"brightness": 128, "color_mode": "hs", "hs_color": [218.27, 50]},
            {
                "state": "on",
                "brightness": 128,
                "color_mode": "hs",
                "hs_color": [218.27, 50],
            },
        ),
        (
            "on",
            {"brightness": 255, "color_mode": "xy", "xy_color": [0.21, 0.22]},
            {
                "state": "on",
                "brightness": 255,
                "color_mode": "xy",
                "xy_color": [0.21, 0.22],
            },
        ),
    ],
)
def test_snapshot_restoration_fields(macros, state, attributes, snapshot):
    result = json.loads(macros.snapshot_light(state, attributes))
    assert result == {"valid": True, "snapshot": snapshot}
    assert len(json.dumps(result["snapshot"])) <= 255


@pytest.mark.parametrize(
    "state,attributes",
    [
        ("unknown", {}),
        ("unavailable", {}),
        ("on", {}),
        (
            "on",
            {"brightness": 77, "color_mode": "color_temp", "color_temp_kelvin": None},
        ),
        ("on", {"brightness": 0, "color_mode": "hs", "hs_color": [0, 100]}),
        ("on", {"brightness": 128, "color_mode": "hs", "hs_color": [400, 100]}),
        ("on", {"brightness": 128, "color_mode": "xy", "xy_color": [1.1, 0.3]}),
        ("on", {"brightness": 128, "color_mode": "hs", "hs_color": ["x" * 260, 50]}),
    ],
)
def test_invalid_snapshot_does_not_invent_original_state(macros, state, attributes):
    assert json.loads(macros.snapshot_light(state, attributes))["valid"] is False
