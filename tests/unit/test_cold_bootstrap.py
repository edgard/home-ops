"""Cold recovery rejects live initialization and never admits on a flag alone."""

import pytest

from tests.support.runtime import load_module


def cold():
    return load_module("platform/filter_plugins/cold_recovery.py")


def registry():
    return {
        "version": 1,
        "consumers": {
            "demo": {
                "namespace": "selfhosted",
                "workloads": [{"kind": "Deployment", "name": "demo"}],
                "cronjobs": [],
            }
        },
        "file_consumers": {},
    }


def deployment(replicas=1):
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "demo"},
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": {"app": "demo"}},
            "template": {
                "spec": {
                    "containers": [
                        {"name": "app", "image": "example/demo@sha256:" + "a" * 64}
                    ]
                }
            },
        },
    }


def tooling_proof(journal):
    journal["executor"] = {"code_sha256": "d" * 64}
    return {
        "image": "example/tools@sha256:" + "f" * 64,
        "image_revision": "f" * 40,
        "code_sha256": "d" * 64,
        "pod_uid": "pod",
    }


def test_first_apply_stops_consumers_and_records_native_images():
    plan = cold().cold_resources(
        [
            deployment(),
            {
                "apiVersion": "gateway.networking.k8s.io/v1",
                "kind": "HTTPRoute",
                "metadata": {"name": "demo"},
            },
        ],
        registry(),
        ["demo"],
        "selfhosted",
        "demo",
        "token",
    )
    assert len(plan) == 1
    assert plan[0]["spec"]["replicas"] == 0
    assert plan[0]["spec"]["template"]["spec"]["containers"][0]["image"].endswith(
        "a" * 64
    )


@pytest.mark.parametrize("kind", ["Pod", "Job", "DaemonSet"])
def test_unregistered_running_resource_fails_closed(kind):
    with pytest.raises(ValueError, match="unsupported"):
        cold().cold_resources(
            [{"apiVersion": "v1", "kind": kind, "metadata": {"name": "demo"}}],
            registry(),
            ["demo"],
            "selfhosted",
            "demo",
            "token",
        )


def test_registered_controller_must_match_real_render():
    value = deployment()
    value["metadata"]["name"] = "unexpected"
    with pytest.raises(ValueError, match="registered"):
        cold().cold_resources(
            [value], registry(), ["demo"], "selfhosted", "demo", "token"
        )


def test_existing_consumer_refuses_initialization_even_if_zero():
    with pytest.raises(ValueError, match="cold"):
        cold().cold_existing(
            {}, [deployment(0)], registry(), ["demo"], "a" * 40, "recover", "hash"
        )


def test_retry_binds_revision_scope_operation_and_source():
    journal = {
        "version": 1,
        "apps": ["demo"],
        "revision": "a" * 40,
        "operation": "recover",
        "source_sha256": "hash",
        "phase": "held",
    }
    assert cold().cold_existing(
        journal, [], registry(), ["demo"], "a" * 40, "recover", "hash"
    )
    for key, value in [
        ("apps", []),
        ("revision", "b" * 40),
        ("operation", "other"),
        ("source_sha256", "different"),
    ]:
        with pytest.raises(ValueError):
            cold().cold_existing(
                {**journal, key: value},
                [],
                registry(),
                ["demo"],
                "a" * 40,
                "recover",
                "hash",
            )


def test_admission_requires_database_aware_completed_receipt_for_exact_scope():
    journal = {
        "version": 1,
        "apps": ["demo"],
        "revision": "a" * 40,
        "operation": "recover",
        "source_sha256": "hash",
        "phase": "held",
        "token": "token",
    }
    journal["source_sha256"] = cold().digest(
        {"registry": registry(), "revision": journal["revision"]}
    )
    with pytest.raises(ValueError):
        cold().cold_admission(journal, {"confirm": True})
    receipt = {
        "operation_id": "restore",
        "cold_token": "token",
        "apps": ["demo"],
        "revision": "a" * 40,
        "phase": "complete",
        "operation_kind": "restore",
        "recovery": {"selection_sha256": "b" * 64, "manifest_sha256": "c" * 64},
        "cold_steps": [
            "provision",
            "redis-provision",
            "validate",
            "postgres",
            "files",
            "redis:not-required",
            "validate",
        ],
    }
    receipt["source_sha256"] = journal["source_sha256"]
    receipt["restore_tooling"] = tooling_proof(journal)
    assert cold().cold_admission(journal, receipt, registry())["apps"] == ["demo"]
    for field in ["cold_token", "apps", "revision", "recovery", "cold_steps"]:
        with pytest.raises(ValueError):
            cold().cold_admission(
                journal, {k: v for k, v in receipt.items() if k != field}, registry()
            )


def test_partial_capability_cannot_enable_global_root():
    journal = {"apps": ["demo"], "revision": "a" * 40, "token": "token"}
    receipt = {
        "operation_id": "restore",
        "cold_token": "token",
        "apps": ["demo"],
        "revision": "a" * 40,
        "phase": "complete",
        "operation_kind": "restore",
        "recovery": {"selection_sha256": "b" * 64, "manifest_sha256": "c" * 64},
        "cold_steps": [
            "provision",
            "redis-provision",
            "validate",
            "postgres",
            "files",
            "redis:not-required",
            "validate",
        ],
    }
    reg = {"consumers": {"demo": {}, "other": {}}, "file_consumers": {}}
    journal["source_sha256"] = cold().digest(
        {"registry": reg, "revision": journal["revision"]}
    )
    receipt["source_sha256"] = journal["source_sha256"]
    receipt["restore_tooling"] = tooling_proof(journal)
    result = cold().cold_admission(journal, receipt, reg)
    assert result["global_root_allowed"] is False
    assert result["unadmitted_apps"] == ["other"]


def test_actual_chart_crd_equals_is_safe_yaml():
    assert cold().cold_yaml("default: =\n") == [{"default": "="}]


def test_inventory_update_preserves_same_name_across_kinds_and_namespaces():
    resources = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "same", "namespace": "one", "uid": "first"},
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "same", "namespace": "one", "uid": "second"},
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "same", "namespace": "two", "uid": "third"},
        },
    ]
    inventory = cold().cold_inventory(resources)
    changed = {
        **resources[0],
        "metadata": {**resources[0]["metadata"], "annotations": {"updated": "true"}},
    }
    assert {r["uid"] for r in cold().cold_record(inventory, changed)} == {
        "first",
        "second",
        "third",
    }


def test_orphan_consumer_pod_refuses_cold_initialization():
    pod = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "demo-abc", "namespace": "selfhosted"},
        "status": {"phase": "Running"},
    }
    assert cold().cold_consumer_pods([pod], registry()) == [pod]
    pod["status"]["phase"] = "Succeeded"
    assert cold().cold_consumer_pods([pod], registry()) == []


def test_cold_restore_binding_requires_zero_originals_and_bootstrap_uids():
    module = load_module("shared_data/filter_plugins/cold_restore.py")
    snapshot = {
        "role": "workload",
        "api_version": "apps/v1",
        "kind": "Deployment",
        "namespace": "selfhosted",
        "name": "demo",
        "uid": "one",
        "value": 0,
    }
    cold_journal = {
        "phase": "held",
        "apps": ["demo"],
        "token": "t" * 32,
        "revision": "a" * 40,
        "inventory": [
            {k: v for k, v in snapshot.items() if k not in {"role", "value"}}
        ],
    }
    restore = {"apps": ["demo"], "snapshots": [snapshot]}
    cold_journal["source_sha256"] = cold().digest(
        {"registry": registry(), "revision": cold_journal["revision"]}
    )
    assert module.shared_data_cold_restore(cold_journal, restore, registry())
    for key, value in [("uid", "replaced"), ("value", 1)]:
        with pytest.raises(ValueError):
            module.shared_data_cold_restore(
                cold_journal,
                {**restore, "snapshots": [{**snapshot, key: value}]},
                registry(),
            )


def test_normal_bootstrap_accepts_only_absent_or_completed_global_admission():
    assert cold().cold_normal_bootstrap({})
    with pytest.raises(ValueError):
        cold().cold_normal_bootstrap({"phase": "held"})
    journal = {
        "phase": "admitted",
        "revision": "a" * 40,
        "apps": ["demo"],
        "token": "t" * 32,
        "admission": {
            "global_root_allowed": True,
            "unadmitted_apps": [],
            "revision": "a" * 40,
            "apps": ["demo"],
            "cold_token": "t" * 32,
        },
    }
    assert cold().cold_normal_bootstrap(journal)
    journal["admission"]["global_root_allowed"] = False
    with pytest.raises(ValueError):
        cold().cold_normal_bootstrap(journal)


def test_safe_resource_names_do_not_authorize_custom_api_groups():
    with pytest.raises(ValueError, match="API"):
        cold().cold_resources(
            [
                {
                    "apiVersion": "talos.dev/v1alpha1",
                    "kind": "ServiceAccount",
                    "metadata": {"name": "admin"},
                }
            ],
            registry(),
            ["demo"],
            "selfhosted",
            "tuppr",
            "token",
        )


def test_native_apply_has_server_enforced_identity_preconditions():
    desired = deployment()
    assert cold().cold_bound_apply(desired, [])["metadata"]["uid"] == ""
    current = {
        **desired,
        "metadata": {"name": "demo", "uid": "original", "resourceVersion": "7"},
    }
    bound = cold().cold_bound_apply(desired, [current])
    assert bound["metadata"]["uid"] == "original"
    assert bound["metadata"]["resourceVersion"] == "7"
