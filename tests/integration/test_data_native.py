"""Real disposable PostgreSQL/Redis verification; never uses cluster credentials."""

import argparse
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from tests.support.runtime import load_module


@pytest.fixture(scope="module")
def native_services(tmp_path_factory):
    docker = shutil.which("docker")
    if not docker or subprocess.run([docker, "info"], capture_output=True).returncode:
        pytest.fail(
            "Start a local Docker engine for required native database verification"
        )
    directory = tmp_path_factory.mktemp("native-data")
    suffix = uuid.uuid4().hex[:12]
    names = ["home-ops-postgres-" + suffix, "home-ops-redis-" + suffix]
    password = "synthetic-only-" + suffix

    def run(*args):
        return subprocess.run(
            [docker, *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        run(
            "run",
            "-d",
            "--name",
            names[0],
            "-e",
            "POSTGRES_PASSWORD=" + password,
            "-p",
            "127.0.0.1::5432",
            "postgres:18.3-trixie",
        )
        run(
            "run",
            "-d",
            "--name",
            names[1],
            "-p",
            "127.0.0.1::6379",
            "redis:8.10.3",
            "sh",
            "-c",
            "printf 'user default on nopass ~* &* +@all\\n' > /data/users.acl; exec redis-server --save '' --appendonly no --aclfile /data/users.acl",
        )
        ports = [
            int(run("port", name, str(port)).split(":")[-1])
            for name, port in zip(names, [5432, 6379])
        ]
        import psycopg
        import redis

        for _ in range(120):
            try:
                with psycopg.connect(
                    host="127.0.0.1",
                    port=ports[0],
                    user="postgres",
                    password=password,
                    connect_timeout=1,
                ):
                    break
            except psycopg.OperationalError:
                time.sleep(0.5)
        else:
            pytest.fail("disposable PostgreSQL did not become ready")
        r = redis.Redis(host="127.0.0.1", port=ports[1])
        r.execute_command(
            "ACL", "SETUSER", "admin", "on", ">" + password, "~*", "&*", "+@all"
        )
        for key in [
            "postgresql_admin_password",
            "redis_admin_password",
            "demo_db_password",
            "demo_redis_password",
            "other_db_password",
        ]:
            (directory / key).write_text(password)
        args = argparse.Namespace(
            pg_host="127.0.0.1",
            pg_port=ports[0],
            pg_user="postgres",
            credentials=str(directory),
            redis_host="127.0.0.1",
            redis_port=ports[1],
            allow_rotation=False,
            apps=["demo"],
        )
        args.pg_container = names[0]
        yield directory, args, password
    finally:
        subprocess.run([docker, "rm", "-fv", *names], capture_output=True, check=False)


def native_registry():
    return {
        "version": 1,
        "consumers": {
            name: {
                "namespace": "selfhosted",
                "enabled": True,
                "backend": "postgresql",
                "databases": [{"name": name, "owner": name}],
                "roles": [
                    {
                        "name": name,
                        "password_key": name + "_db_password",
                        "connection_limit": 10,
                    }
                ],
                "workloads": [],
                "cronjobs": [],
                "pvcs": ["selfhosted/" + name],
                "key_refs": [],
                **(
                    {
                        "redis": {
                            "database": 1,
                            "username": "demo",
                            "password_key": "demo_redis_password",
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


def test_real_postgres_provision_is_idempotent_and_isolated(native_services):
    import psycopg

    directory, args, password = native_services
    adapter = load_module("shared_data/files/data_tools.py")
    registry = native_registry()
    args.apps = ["demo", "other"]
    adapter.provision(args, registry)
    with adapter.connect_pg(args) as admin:
        admin.execute("ALTER ROLE demo CONNECTION LIMIT -1")
    adapter.provision(args, registry)
    with psycopg.connect(
        host=args.pg_host,
        port=args.pg_port,
        dbname="demo",
        user="demo",
        password=password,
        autocommit=True,
    ) as app:
        app.execute(
            "CREATE TABLE IF NOT EXISTS evidence(id integer PRIMARY KEY, value text)"
        )
        app.execute(
            "INSERT INTO evidence VALUES (1, 'preserved') ON CONFLICT DO NOTHING"
        )
        flags = app.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert flags == (False, False, False, False)
        assert app.execute(
            "SELECT rolconnlimit FROM pg_roles WHERE rolname=current_user"
        ).fetchone() == (10,)
    with pytest.raises(psycopg.OperationalError, match="permission denied"):
        psycopg.connect(
            host=args.pg_host,
            port=args.pg_port,
            dbname="other",
            user="demo",
            password=password,
        )
    with pytest.raises(psycopg.OperationalError, match="permission denied"):
        psycopg.connect(
            host=args.pg_host,
            port=args.pg_port,
            dbname="postgres",
            user="demo",
            password=password,
        )
    args.apps = ["demo"]


def test_real_postgres_restore_preserves_types_sequences_and_other_database(
    native_services,
):
    import psycopg

    directory, args, password = native_services
    adapter = load_module("shared_data/files/data_tools.py")
    args.apps = ["demo", "other"]
    adapter.provision(args, native_registry())

    def application():
        return psycopg.connect(
            host=args.pg_host,
            port=args.pg_port,
            dbname="demo",
            user="demo",
            password=password,
            autocommit=True,
        )

    with application() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS recovery_evidence(id bigserial PRIMARY KEY, payload bytea, happened_at timestamptz)"
        )
        db.execute("TRUNCATE recovery_evidence RESTART IDENTITY")
        db.execute(
            "INSERT INTO recovery_evidence(payload,happened_at) VALUES (%s, '2026-11-04T12:30:00Z')",
            [b"\x00\xff"],
        )
    with adapter.connect_pg(args, "other") as db:
        db.execute("CREATE TABLE IF NOT EXISTS untouched(value text)")
        db.execute("TRUNCATE untouched")
        db.execute("INSERT INTO untouched VALUES ('preserved')")
    args.apps = ["demo"]
    args.root = str(directory)

    def native(command, *, env=None):
        environment = {
            **(env or {}),
            "PGHOST": "127.0.0.1",
            "PGPORT": "5432",
            "PGUSER": "postgres",
            "PGPASSWORD": password,
        }
        command = list(command)
        payload = None
        destination = None
        if command[0] == "pg_dump" and "--file" in command:
            position = command.index("--file")
            destination = Path(command[position + 1])
            del command[position : position + 2]
        elif command[0] == "pg_restore":
            payload = Path(command.pop()).read_bytes()
        docker_command = ["docker", "exec", "-i"]
        for key in ["PGHOST", "PGPORT", "PGUSER", "PGPASSWORD"]:
            docker_command.extend(["-e", key + "=" + environment[key]])
        result = subprocess.run(
            [*docker_command, args.pg_container, *command],
            input=payload,
            capture_output=True,
            check=True,
        )
        if destination:
            destination.write_bytes(result.stdout)
        return result.stdout

    adapter.native = native
    adapter.dump_postgres(args, native_registry())
    with application() as db:
        db.execute("DROP TABLE recovery_evidence")
    adapter.restore_postgres(args, native_registry())
    with application() as db:
        row = db.execute(
            "SELECT id,payload,extract(epoch from happened_at)::bigint FROM recovery_evidence"
        ).fetchone()
        assert row == (1, b"\x00\xff", 1793795400)
        assert db.execute(
            "INSERT INTO recovery_evidence(payload) VALUES ('next') RETURNING id"
        ).fetchone() == (2,)
    with adapter.connect_pg(args, "other") as db:
        assert db.execute("SELECT value FROM untouched").fetchall() == [("preserved",)]


def test_real_redis_acl_blocks_global_operations_and_preserves_channels(
    native_services,
):
    import redis

    directory, args, password = native_services
    adapter = load_module("shared_data/files/data_tools.py")
    adapter.provision_redis(args, native_registry())
    app = redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        db=1,
        username="demo",
        password=password,
    )
    app.set("demo:queue", "payload")
    assert app.get("demo:queue") == b"payload"
    assert app.publish("demo:events", "event") == 0
    with pytest.raises(redis.exceptions.NoPermissionError):
        app.publish("other:events", "event")
    for command in ["FLUSHALL", "FLUSHDB", "CONFIG GET *", "ACL LIST"]:
        with pytest.raises(redis.exceptions.NoPermissionError):
            app.execute_command(*command.split())
    admin = adapter.redis_connection(args)
    for command in [
        ["CLIENT", "PAUSE", "10000"],
        ["CLIENT", "KILL", "TYPE", "normal"],
        ["FUNCTION", "FLUSH"],
        ["SCRIPT", "FLUSH"],
        ["MONITOR"],
    ]:
        try:
            verdict = admin.execute_command("ACL", "DRYRUN", "demo", *command)
        except redis.exceptions.ResponseError as error:
            assert "permission" in str(error).lower()
        else:
            assert b"permission" in verdict.lower(), (command, verdict)


@pytest.mark.parametrize("privilege", ["replication", "membership", "cross_database"])
def test_provision_rejects_existing_privilege_or_connection_escape(
    native_services, privilege
):
    directory, args, password = native_services
    adapter = load_module("shared_data/files/data_tools.py")
    args.apps = ["demo", "other"]
    adapter.provision(args, native_registry())
    changes = {
        "replication": ("ALTER ROLE demo REPLICATION", "ALTER ROLE demo NOREPLICATION"),
        "membership": (
            "GRANT pg_read_all_data TO demo",
            "REVOKE pg_read_all_data FROM demo",
        ),
        "cross_database": (
            "GRANT CONNECT ON DATABASE other TO demo",
            "REVOKE CONNECT ON DATABASE other FROM demo",
        ),
    }
    change, undo = changes[privilege]
    with adapter.connect_pg(args) as admin:
        admin.execute(change)
    args.apps = ["demo"]
    try:
        with pytest.raises(ValueError):
            adapter.provision(args, native_registry())
    finally:
        with adapter.connect_pg(args) as admin:
            admin.execute(undo)


def test_real_redis_restore_rejects_live_instance_alias_before_deletion(
    native_services,
):
    import redis

    directory, args, password = native_services
    adapter = load_module("shared_data/files/data_tools.py")
    # A hostname alias and logical DB do not make an isolated recovery instance.
    args.redis_source_host = "localhost"
    args.redis_source_port = args.redis_port
    source = redis.Redis(host=args.redis_host, port=args.redis_port, db=3)
    target = redis.Redis(host=args.redis_host, port=args.redis_port, db=1)
    other = redis.Redis(host=args.redis_host, port=args.redis_port, db=2)
    source.set("demo:pending", "job", px=60000)
    expiry = source.execute_command("PEXPIRETIME", "demo:pending")
    other.set("paperless:keep", "untouched")
    target.set("stale", "remove")
    original = adapter.redis_connection
    adapter.redis_connection = lambda a, source=False, database=0: redis.Redis(
        host=args.redis_host, port=args.redis_port, db=3 if source else database
    )
    try:
        with pytest.raises(ValueError, match="isolated"):
            adapter.transfer_redis(args, native_registry())
    finally:
        adapter.redis_connection = original
    assert source.get("demo:pending") == b"job"
    assert target.get("stale") == b"remove"
    assert source.execute_command("PEXPIRETIME", "demo:pending") == expiry
    assert other.get("paperless:keep") == b"untouched"
