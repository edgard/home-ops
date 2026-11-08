"""Invalid Talos identity must fail without exposing private parser excerpts."""

import yaml


def test_talos_material_rejects_incomplete_or_malformed_identity(module_loader):
    material = module_loader("talos/filter_plugins/material.py")
    identity = {
        "cluster": {"id": "synthetic", "secret": "synthetic"},
        "secrets": {
            "bootstraptoken": "synthetic",
            "secretboxencryptionsecret": "synthetic",
        },
        "trustdinfo": {"token": "synthetic"},
        "certs": {
            name: {"crt": "synthetic", "key": "synthetic"}
            for name in ("etcd", "k8s", "k8saggregator", "k8sserviceaccount", "os")
        },
    }
    assert material.valid_talos_material(yaml.safe_dump(identity))
    del identity["cluster"]["secret"]
    assert not material.valid_talos_material(yaml.safe_dump(identity))
    assert not material.valid_talos_material("SYNTHETIC-PRIVATE: [")
