"""Bootstrap mutation authority belongs to a real bound-token Job worker."""

from copy import deepcopy

import pytest

from tests.support.runtime import load_module


def executor():
    return load_module("platform/filter_plugins/cold_executor.py")


def sample():
    module = executor()
    image = "ghcr.io/edgard/home-ops-data-tools:" + "a" * 40 + "@sha256:" + "b" * 64
    template = {
        "serviceAccountName": "boot",
        "containers": [{"name": "bootstrap", "image": image}],
    }
    job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": "boot", "namespace": "platform-system", "uid": "job"},
        "spec": {"suspend": False, "template": {"spec": template}},
    }
    pod = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "boot-pod",
            "namespace": "platform-system",
            "uid": "pod",
            "ownerReferences": [
                {"kind": "Job", "name": "boot", "uid": "job", "controller": True}
            ],
        },
        "spec": deepcopy(template),
        "status": {"phase": "Running"},
    }
    pod["spec"]["nodeName"] = "node"
    sa = {"metadata": {"name": "boot", "namespace": "platform-system", "uid": "sa"}}
    ssr = {
        "status": {
            "userInfo": {
                "uid": "sa",
                "username": "system:serviceaccount:platform-system:boot",
                "extra": {
                    "authentication.kubernetes.io/pod-uid": ["pod"],
                    "authentication.kubernetes.io/node-name": ["node"],
                    "authentication.kubernetes.io/node-uid": ["node-original"],
                },
            }
        }
    }
    context = {
        "apps": ["demo"],
        "revision": "a" * 40,
        "source_sha256": "c" * 64,
        "image": image,
        "code_sha256": "d" * 64,
        "bundle_sha256": "e" * 64,
    }
    journal = {
        "version": 1,
        "operation": "recover",
        "phase": "bootstrap-claimed",
        "apps": ["demo"],
        "revision": context["revision"],
        "source_sha256": context["source_sha256"],
        "executor": {
            "job_uid": "job",
            "job_name": "boot",
            "namespace": "platform-system",
            "image": image,
            "code_sha256": context["code_sha256"],
            "bundle_sha256": context["bundle_sha256"],
            "job_template_sha256": module.digest(template),
        },
    }
    actor = {
        "kind": "Job",
        "name": "boot",
        "namespace": "platform-system",
        "uid": "job",
    }
    lease = {
        "metadata": {"uid": "lease", "resourceVersion": "1"},
        "spec": {"holderIdentity": "recover:job"},
    }
    import jsonpatch

    lease = jsonpatch.apply_patch(
        lease,
        module.cold_lease_patch(lease, "recover:job", "recover", actor, context, 0),
    )
    return job, pod, sa, ssr, journal, lease, context


def test_admin_or_placeholder_identity_is_not_a_worker():
    job, pod, sa, ssr, journal, lease, context = sample()
    assert executor().cold_worker_proof(job, pod, sa, ssr, journal, lease, context)
    ssr["status"]["userInfo"]["extra"] = {}
    with pytest.raises(ValueError, match="authenticated|bound"):
        executor().cold_worker_proof(job, pod, sa, ssr, journal, lease, context)


@pytest.mark.parametrize("change", ["image", "code", "source", "owner", "job_template"])
def test_executor_image_source_and_owner_chain_are_bound(change):
    job, pod, sa, ssr, journal, lease, context = sample()
    if change == "image":
        pod["spec"]["containers"][0]["image"] = "other@sha256:" + "f" * 64
    if change == "code":
        context["code_sha256"] = "f" * 64
    if change == "source":
        context["source_sha256"] = "f" * 64
    if change == "owner":
        pod["metadata"]["ownerReferences"][0]["uid"] = "other"
    if change == "job_template":
        job["spec"]["template"]["spec"]["hostNetwork"] = True
    with pytest.raises(ValueError):
        executor().cold_worker_proof(job, pod, sa, ssr, journal, lease, context)


def test_active_competing_lease_is_not_an_expired_bootstrap_retry():
    job, pod, sa, ssr, journal, lease, context = sample()
    import json

    record = json.loads(lease["metadata"]["annotations"]["home-ops/data-coordinator"])
    record["operation_kind"] = "restore"
    lease["metadata"]["annotations"]["home-ops/data-coordinator"] = json.dumps(record)
    with pytest.raises(ValueError, match="competing"):
        executor().cold_dispatch_ownership(lease, journal, context, "recover")


def test_lease_claim_is_an_exact_single_winner_compare_and_swap():
    import jsonpatch

    lease = {"metadata": {"uid": "lease", "resourceVersion": "1"}, "spec": {}}
    context = {
        "apps": ["demo"],
        "revision": "a" * 40,
        "source_sha256": "c" * 64,
        "image": "image",
        "code_sha256": "d" * 64,
        "bundle_sha256": "e" * 64,
    }
    one = executor().cold_lease_patch(
        lease,
        "",
        "recover",
        {"kind": "Job", "name": "one", "namespace": "platform-system", "uid": "one"},
        context,
        0,
    )
    two = executor().cold_lease_patch(
        lease,
        "",
        "recover",
        {"kind": "Job", "name": "two", "namespace": "platform-system", "uid": "two"},
        context,
        0,
    )
    claimed = jsonpatch.apply_patch(lease, one)
    with pytest.raises(jsonpatch.JsonPatchException):
        jsonpatch.apply_patch(claimed, two)


def test_expiry_does_not_prove_old_worker_fenced():
    job, pod, sa, ssr, journal, lease, context = sample()
    with pytest.raises(ValueError, match="fence|active|expired"):
        executor().cold_fence_plan(lease, journal, [job], [pod], [], 10000, False)
    nodes = [
        {
            "metadata": {"name": "node"},
            "status": {"conditions": [{"type": "Ready", "status": "False"}]},
        }
    ]
    with pytest.raises(ValueError, match="node|Ready"):
        executor().cold_fence_plan(lease, journal, [job], [pod], nodes, 10000, True)


def test_watchdog_never_claims_a_cold_or_local_executor_as_backup():
    maintenance = load_module("shared_data/filter_plugins/maintenance.py")
    job, pod, sa, ssr, journal, lease, context = sample()
    with pytest.raises(ValueError, match="cold|executor|Pod"):
        maintenance.shared_data_watchdog_fence({}, lease, [], [], [], 10000, "watchdog")


def ready_node(uid="node-original"):
    return {
        "metadata": {"name": "node", "uid": uid},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }


def test_historical_worker_node_uid_cannot_be_rebound_during_retry():
    import json

    job, pod, sa, ssr, journal, lease, context = sample()
    pod["spec"]["nodeName"] = "node"
    actor = executor().cold_worker_actor(pod, ready_node(), ssr)
    actor["fence_nodes"] = [{"name": "node", "uid": "node-original"}]
    lease["metadata"]["annotations"][executor().RECORD] = json.dumps(
        {"operation_kind": "cold-bootstrap", "actor": actor}
    )
    job["status"] = {"failed": 1}
    pod["status"]["phase"] = "Failed"
    with pytest.raises(ValueError, match="node identity|historical"):
        executor().cold_fence_plan(
            lease, journal, [job], [pod], [ready_node("node-replaced")], 10000, True
        )


def test_old_pod_actor_without_durable_original_node_binding_refuses_fencing():
    import json

    job, pod, sa, ssr, journal, lease, context = sample()
    pod["spec"]["nodeName"] = "node"
    actor = executor().cold_worker_actor(pod, ready_node(), ssr)
    actor.pop("fence_nodes")
    lease["metadata"]["annotations"][executor().RECORD] = json.dumps(
        {"operation_kind": "cold-bootstrap", "actor": actor}
    )
    job["status"] = {"failed": 1}
    pod["status"]["phase"] = "Failed"
    with pytest.raises(ValueError, match="original node"):
        executor().cold_fence_plan(
            lease, journal, [job], [pod], [ready_node()], 10000, True
        )


@pytest.mark.parametrize(
    "failure",
    ["replacement", "name", "missing", "empty_uid", "ambiguous_uid", "ambiguous_name"],
)
def test_initial_actor_refuses_unproved_original_node(failure):
    job, pod, sa, ssr, journal, lease, context = sample()
    node = ready_node()
    extra = ssr["status"]["userInfo"]["extra"]
    if failure == "replacement":
        node["metadata"]["uid"] = "replacement-node"
    elif failure == "name":
        extra["authentication.kubernetes.io/node-name"] = ["other-node"]
    elif failure == "missing":
        extra.pop("authentication.kubernetes.io/node-name")
        extra.pop("authentication.kubernetes.io/node-uid")
    elif failure == "empty_uid":
        extra["authentication.kubernetes.io/node-uid"] = [""]
    elif failure == "ambiguous_uid":
        extra["authentication.kubernetes.io/node-uid"] = ["node-original", "other"]
    else:
        extra["authentication.kubernetes.io/node-name"] = ["node", "other"]
    with pytest.raises(ValueError, match="authenticated original node"):
        executor().cold_worker_actor(pod, node, ssr)


def test_initial_actor_persists_only_authenticated_original_node_equality():
    job, pod, sa, ssr, journal, lease, context = sample()
    actor = executor().cold_worker_actor(pod, ready_node(), ssr)
    assert actor["fence_nodes"] == [{"name": "node", "uid": "node-original"}]
