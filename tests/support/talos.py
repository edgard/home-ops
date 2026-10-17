import yaml

MATERIAL = yaml.safe_dump(
    {
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
)
