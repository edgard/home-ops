"""Disposable PG18 / Redis RDB acceptance against native adapters."""

import argparse
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import psycopg
import pytest
import redis

from tests.support.data_generation import fixture_actor, schema_metadata
from tests.support.runtime import ROOT

PG = "postgres:18.3-trixie@sha256:7e32e9833a6fb1c92c32552794cb6ed569d51b445a54907d35fc112ef39684db"
REDIS = "redis:8.10.3@sha256:de1068af6f552240dfab67bcc9bfef99bfc60f776bb4580ef077ea4c8c97e848"


def docker(*args):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=True, timeout=120
    ).stdout.strip()


@pytest.fixture
def services(tmp_path, adapters, monkeypatch):
    suffix = uuid.uuid4().hex[:10]
    tmp_path = ROOT / ".pytest_cache" / ("native-" + suffix)
    tmp_path.mkdir(mode=0o700, parents=True)
    names = [
        "capture-pg-" + suffix,
        "capture-redis-" + suffix,
        "capture-recovery-" + suffix,
    ]
    password = "disposable-" + suffix
    try:
        docker(
            "run",
            "-d",
            "--name",
            names[0],
            "-e",
            "POSTGRES_PASSWORD=" + password,
            "-p",
            "127.0.0.1::5432",
            "-v",
            f"{tmp_path}:{tmp_path}",
            PG,
        )
        docker(
            "run",
            "-d",
            "--name",
            names[1],
            "-p",
            "127.0.0.1::6379",
            "-v",
            f"{tmp_path}:{tmp_path}",
            REDIS,
            "redis-server",
            "--save",
            "",
            "--appendonly",
            "no",
        )
        ports = [
            int(docker("port", name, str(port)).split(":")[-1])
            for name, port in zip(names, [5432, 6379])
        ]
        args = argparse.Namespace(
            pg_host="127.0.0.1",
            pg_port=ports[0],
            pg_user="postgres",
            redis_host="127.0.0.1",
            redis_port=ports[1],
            credentials=str(tmp_path / "credentials"),
            apps=["demo", "other"],
            root=str(tmp_path / "generation"),
            allow_rotation=False,
        )
        credentials = Path(args.credentials)
        credentials.mkdir()
        for key in [
            "postgresql_admin_password",
            "redis_admin_password",
            "demo_password",
            "other_password",
        ]:
            (credentials / key).write_text(password)
        (credentials / "redis_recovery_password").write_text("ephemeral-" + suffix * 6)
        for _ in range(120):
            try:
                with adapters["data_tools"].connect_pg(args):
                    break
            except psycopg.OperationalError:
                time.sleep(0.2)
        else:
            pytest.fail("Disposable PostgreSQL did not start")
        client = redis.Redis(host="127.0.0.1", port=ports[1])
        client.execute_command(
            "ACL", "SETUSER", "admin", "on", ">" + password, "~*", "&*", "+@all"
        )
        original = adapters["data_tools"].native

        def native(command, *, env=None):
            command = list(command)
            environment = dict(env or {})
            if command[0].startswith("pg_"):
                name = names[0]
                environment.update(PGHOST="127.0.0.1", PGPORT="5432")
                keys = ["PGHOST", "PGPORT", "PGUSER", "PGPASSWORD"] if env else []
            else:
                name = names[1]
                command[command.index("-p") + 1] = "6379"
                keys = ["REDISCLI_AUTH"]
            prefix = ["docker", "exec", *fixture_actor()]
            for key in keys:
                prefix += ["-e", key + "=" + environment[key]]
            return original(prefix + [name] + command)

        monkeypatch.setattr(adapters["data_tools"], "native", native)
        yield args, names, client
    finally:
        subprocess.run(["docker", "rm", "-fv", *names], capture_output=True, timeout=60)
        shutil.rmtree(tmp_path)


def native_registry():
    return {
        "version": 1,
        "consumers": {
            name: {
                "namespace": "selfhosted",
                "enabled": True,
                "backend": "postgresql",
                "roles": [
                    {
                        "name": name,
                        "password_key": name + "_password",
                        "connection_limit": 10,
                    }
                ],
                "databases": [{"name": name, "owner": name}],
                "pvcs": ["selfhosted/" + name],
                "workloads": [],
                "key_refs": [],
                **(
                    {
                        "redis": {
                            "database": 1,
                            "username": "demo",
                            "password_key": "demo_password",
                            "prefix": "demo:",
                        }
                    }
                    if name == "demo"
                    else {}
                ),
            }
            for name in ["demo", "other"]
        },
    }


def test_pg18_estimate_custom_dump_and_selected_recovery(services, adapters):
    args, _, _ = services
    tools = adapters["data_tools"]
    data = native_registry()
    tools.provision(args, data)
    with tools.connect_pg(args, "demo") as db:
        db.execute(
            "CREATE TABLE evidence(id bigserial primary key, data bytea, happened timestamptz)"
        )
        db.execute(
            "INSERT INTO evidence(data,happened) VALUES (%s,'2026-11-04T12:30:00Z')",
            [b"\x00\xff"],
        )
    with tools.connect_pg(args, "other") as db:
        db.execute("CREATE TABLE untouched(data text)")
        db.execute("INSERT INTO untouched VALUES ('preserved')")
    estimate = tools.estimate_capture(args, data)
    assert estimate["database_bytes"] > 2 * 1024 * 1024
    assert estimate["redis_bytes"] > 1024 * 1024
    args.apps = ["demo"]
    tools.dump_postgres(args, data)
    tools.snapshot_redis(args)
    for name in ["demo"]:
        (Path(args.root) / "selfhosted" / name / "file").write_text("original")
    manifest = tools.make_manifest(
        args.root, data, args.apps, "op", {"demo": ["test:1"]}
    )
    assert tools.verify_manifest(
        args.root, manifest, {"demo": ["test:1"]}, registry=data, apps=args.apps
    )
    with tools.connect_pg(args, "demo") as db:
        db.execute("DROP TABLE evidence")
    tools.restore_postgres(args, data)
    with tools.connect_pg(args, "demo") as db:
        assert db.execute(
            "SELECT id,data,extract(epoch FROM happened)::bigint FROM evidence"
        ).fetchone() == (1, b"\x00\xff", 1793795400)
        assert db.execute(
            "INSERT INTO evidence(data) VALUES ('next') RETURNING id"
        ).fetchone() == (2,)
    with tools.connect_pg(args, "other") as db:
        assert db.execute("SELECT data FROM untouched").fetchall() == [("preserved",)]
    schema = Path(args.root) / "selfhosted/demo/.home-ops/databases/demo.schema.json"
    metadata = json.loads(schema.read_text())
    assert metadata["server_version_num"] // 10000 == 18
    metadata["schema_sha256"] = "0" * 64
    schema.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="schema"):
        tools.restore_postgres(args, data)


def test_redis_real_rdb_isolated_selected_restore_preserves_absttl(
    services, adapters, operations_image
):
    args, names, client = services
    tools = adapters["data_tools"]
    args.apps = ["demo"]
    selected = redis.Redis(host=args.redis_host, port=args.redis_port, db=1)
    other = redis.Redis(host=args.redis_host, port=args.redis_port, db=2)
    selected.set("demo:queue", "payload", px=120000)
    selected.set("demo:persistent", "stable")
    expiry = selected.execute_command("PEXPIRETIME", "demo:queue")
    other.set("other:keep", "untouched")
    tools.snapshot_redis(args)
    rdb = Path(args.root) / ".home-ops/redis.rdb"
    assert rdb.read_bytes().startswith(b"REDIS")
    selected.delete("demo:queue", "demo:persistent")
    selected.set("demo:stale", "discard")
    args.redis_source_host = "127.0.0.1"
    password = (Path(args.credentials) / "redis_recovery_password").read_text()
    volume = "home-ops-real-rdb-" + uuid.uuid4().hex
    docker("volume", "create", "--label", "home-ops-test=redis-rdb", volume)
    # The same init adapter and ACL used by the temporary recovery Pod.
    try:
        docker(
            "run",
            "--rm",
            "--entrypoint",
            "python",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "CHOWN",
            "--cap-add",
            "DAC_READ_SEARCH",
            "-v",
            f"{rdb.parent}:{rdb.parent}:ro",
            "-v",
            f"{args.credentials}:/auth:ro",
            "-v",
            volume + ":/redis",
            "-v",
            f"{ROOT / 'ansible/roles/shared_data/files'}:/adapters:ro",
            operations_image,
            "/adapters/redis_source.py",
            "--source",
            str(rdb),
            "--destination",
            "/redis",
            "--sha256",
            tools.digest(rdb),
            "--password-file",
            "/auth/redis_recovery_password",
        )
        docker(
            "run",
            "-d",
            "--name",
            names[2],
            "--user",
            "999:999",
            "--cap-drop",
            "ALL",
            "-p",
            "127.0.0.1::6379",
            "-v",
            volume + ":/redis",
            REDIS,
            "redis-server",
            "--dir",
            "/redis",
            "--dbfilename",
            "dump.rdb",
            "--aclfile",
            "/redis/recovery.acl",
            "--save",
            "",
            "--appendonly",
            "no",
        )
    except BaseException:
        subprocess.run(["docker", "rm", "-fv", names[2]], capture_output=True)
        docker("volume", "rm", volume)
        raise
    try:
        args.redis_source_port = int(docker("port", names[2], "6379").split(":")[-1])
        source = redis.Redis(
            host=args.redis_source_host,
            port=args.redis_source_port,
            db=1,
            password=password,
        )
        for _ in range(100):
            try:
                source.ping()
                break
            except redis.exceptions.ConnectionError:
                time.sleep(0.1)
        tools.transfer_redis(args, native_registry())
        assert selected.get("demo:queue") == b"payload"
        assert selected.get("demo:persistent") == b"stable"
        assert selected.get("demo:stale") is None
        assert selected.execute_command("PEXPIRETIME", "demo:queue") == expiry
        assert selected.execute_command("PEXPIRETIME", "demo:persistent") == -1
        assert other.get("other:keep") == b"untouched"
        assert source.dump("demo:queue") == selected.dump("demo:queue")
        with pytest.raises(redis.exceptions.NoPermissionError):
            source.set("demo:blocked", "forbidden")
    finally:
        subprocess.run(
            ["docker", "rm", "-fv", names[2]], capture_output=True, timeout=60
        )
        docker("volume", "rm", volume)


def test_linux_rsync_preseed_final_publish_and_selected_files(
    adapters, operations_image
):
    import json

    import yaml

    suffix = uuid.uuid4().hex[:10]
    directory = ROOT / ".pytest_cache" / ("native-files-" + suffix)
    source = directory / "appdata/selfhosted/demo"
    source.mkdir(parents=True)
    (source / "file").write_text("online")
    (source / ".home-ops").mkdir()
    (source / ".home-ops/private").write_text("not-appdata")
    data = native_registry()
    data["consumers"].pop("other")
    data["consumers"]["demo"].pop("redis")
    (directory / "registry.yaml").write_text(yaml.safe_dump(data))
    files = ROOT / "ansible/roles/shared_data/files"

    def invoke(action, *extra, check=True):
        return subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                *fixture_actor(),
                "--entrypoint",
                "python",
                "-v",
                f"{files}:/drafts:ro",
                "-v",
                f"{directory}:/work",
                operations_image,
                "/drafts/capture.py",
                action,
                "--registry",
                "/work/registry.yaml",
                "--apps",
                "demo",
                "--root",
                "/work/appdata",
                "--staging",
                "/work/staging",
                "--operation",
                "op",
                *extra,
            ],
            capture_output=True,
            text=True,
            check=check,
            timeout=60,
        )

    try:
        invoke("preseed", "--database-bytes", "100")
        staged = directory / "staging/in-progress/op"
        assert (staged / "selfhosted/demo/file").read_text() == "online"
        assert not (staged / "selfhosted/demo/.home-ops").exists()
        (source / "file").write_text("stopped")
        assert (
            invoke("final", "--deadline", str(time.time() - 1), check=False).returncode
            != 0
        )
        assert (staged / "selfhosted/demo/file").read_text() == "online"
        invoke("final", "--deadline", str(time.time() + 30))
        assert (staged / "selfhosted/demo/file").read_text() == "stopped"
        dump = staged / "selfhosted/demo/.home-ops/databases/demo.dump"
        dump.parent.mkdir(parents=True)
        dump.write_bytes(b"synthetic-native-file-test")
        schema_metadata(dump)
        manifest = adapters["data_tools"].make_manifest(
            staged, data, ["demo"], "op", {"demo": ["image:1"]}
        )
        (staged / ".home-ops").mkdir()
        (staged / ".home-ops/manifest.json").write_text(json.dumps(manifest))
        result = json.loads(invoke("publish").stdout)
        published = directory / "staging/generations/op"
        assert result["manifest_sha256"] == adapters["data_tools"].digest(
            published / ".home-ops/manifest.json"
        )
        live = directory / "live/selfhosted/demo"
        live.mkdir(parents=True)
        (live / "file").write_text("stale")
        (live / "remove").write_text("remove")
        (directory / "live/selfhosted/other").mkdir()
        (directory / "live/selfhosted/other/keep").write_text("preserved")
        docker(
            "run",
            "--rm",
            *fixture_actor(),
            "--entrypoint",
            "python",
            "-v",
            f"{files}:/drafts:ro",
            "-v",
            f"{directory}:/work",
            operations_image,
            "-c",
            "import sys;sys.path.insert(0,'/drafts');import capture;capture.copy_files('/work/staging/generations/op','/work/live',['selfhosted/demo'])",
        )
        assert (live / "file").read_text() == "stopped"
        assert not (live / "remove").exists()
        assert (directory / "live/selfhosted/other/keep").read_text() == "preserved"
    finally:
        shutil.rmtree(directory)


def test_redis_alias_to_live_instance_is_rejected_before_delete(services, adapters):
    args, _, client = services
    tools = adapters["data_tools"]
    args.apps = ["demo"]
    password = (Path(args.credentials) / "redis_recovery_password").read_text()
    client.execute_command("ACL", "SETUSER", "default", "on", ">" + password)
    args.redis_source_host = "localhost"
    args.redis_source_port = args.redis_port
    selected = redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        db=1,
        username="admin",
        password=(Path(args.credentials) / "redis_admin_password").read_text(),
    )
    selected.set("demo:keep", "untouched")
    with pytest.raises(ValueError, match="isolated"):
        tools.transfer_redis(args, native_registry())
    assert selected.get("demo:keep") == b"untouched"
