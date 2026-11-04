"""Native data adapters. Kubernetes orchestration belongs to the Ansible role."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import yaml

NAME = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
KEY = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


def validate_registry(registry):
    if not isinstance(registry, dict) or registry.get("version") != 1:
        raise ValueError("unsupported registry version")
    consumers = registry.get("consumers")
    if not isinstance(consumers, dict):
        raise ValueError("consumer mapping required")
    databases, roles, redis_dbs, redis_users, prefixes = (
        set(),
        set(),
        set(),
        set(),
        set(),
    )
    budget = 0
    for app, consumer in consumers.items():
        if not NAME.fullmatch(app) or not isinstance(consumer, dict):
            raise ValueError("invalid consumer")
        if not NAME.fullmatch(consumer.get("namespace", "")):
            raise ValueError("invalid namespace")
        if type(consumer.get("enabled")) is not bool:
            raise ValueError("explicit adoption state required")
        owned = set()
        for role in consumer.get("roles", []):
            name = role.get("name", "")
            limit = role.get("connection_limit", 10)
            if (
                not NAME.fullmatch(name)
                or name in roles
                or not KEY.fullmatch(role.get("password_key", ""))
                or type(limit) is not int
                or not 1 <= limit <= 40
            ):
                raise ValueError("invalid, shared or unbounded application role")
            roles.add(name)
            owned.add(name)
            budget += limit
        for database in consumer.get("databases", []):
            name = database.get("name", "")
            if (
                not NAME.fullmatch(name)
                or name in databases
                or database.get("owner") not in owned
            ):
                raise ValueError("invalid database or cross-application owner")
            if name in {"postgres", "template0", "template1"}:
                raise ValueError("reserved database")
            databases.add(name)
        for pvc in consumer.get("pvcs", []):
            parts = pvc.split("/")
            if len(parts) != 2 or not all(NAME.fullmatch(part) for part in parts):
                raise ValueError("invalid PVC path")
        for workload in consumer.get("workloads", []):
            if workload.get("kind") not in {
                "Deployment",
                "StatefulSet",
            } or not NAME.fullmatch(workload.get("name", "")):
                raise ValueError("invalid writer")
        redis = consumer.get("redis")
        if redis:
            db, user, prefix = (
                redis.get("database"),
                redis.get("username", ""),
                redis.get("prefix", ""),
            )
            if (
                type(db) is not int
                or not 1 <= db <= 15
                or db in redis_dbs
                or not NAME.fullmatch(user)
                or user in redis_users
                or not KEY.fullmatch(redis.get("password_key", ""))
                or not re.fullmatch(r"[a-z][a-z0-9_-]*:", prefix)
                or prefix in prefixes
            ):
                raise ValueError("invalid or overlapping Redis allocation")
            redis_dbs.add(db)
            redis_users.add(user)
            prefixes.add(prefix)
    if budget > 180:
        raise ValueError("application connection budget exceeds reserved capacity")
    return registry


def select_consumers(registry, apps=None):
    validate_registry(registry)
    names = (
        apps
        if apps is not None
        else [name for name, app in registry["consumers"].items() if app["enabled"]]
    )
    if (
        not names
        or len(names) != len(set(names))
        or any(name not in registry["consumers"] for name in names)
    ):
        raise ValueError("nonempty, unique registered application selection required")
    return {name: registry["consumers"][name] for name in names}


def secret(directory, key):
    if not KEY.fullmatch(key):
        raise ValueError("invalid credential reference")
    root = Path(directory).resolve(strict=True)
    path = (root / key).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("credential must be a file under the mounted secret")
    value = path.read_text().rstrip("\r\n")
    if not value or value.startswith(("changeme", "replace_with")):
        raise ValueError("missing or placeholder credential")
    return value


def connect_pg(args, database="postgres"):
    import psycopg

    return psycopg.connect(
        host=args.pg_host,
        port=args.pg_port,
        dbname=database,
        user=args.pg_user,
        password=secret(args.credentials, "postgresql_admin_password"),
        connect_timeout=10,
        autocommit=True,
        application_name="home-ops-data",
    )


def provision(args, registry):
    import psycopg
    from psycopg import sql

    consumers = select_consumers(registry, args.apps)
    with connect_pg(args) as connection:
        connection.execute("REVOKE ALL ON DATABASE postgres FROM PUBLIC")
        connection.execute("REVOKE CONNECT ON DATABASE template1 FROM PUBLIC")
        for app in consumers.values():
            for role in app.get("roles", []):
                name, password = (
                    role["name"],
                    secret(args.credentials, role["password_key"]),
                )
                row = connection.execute(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, rolreplication FROM pg_roles WHERE rolname=%s",
                    [name],
                ).fetchone()
                memberships = connection.execute(
                    "SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)",
                    [name],
                ).fetchone()[0]
                if row and (any(row) or memberships):
                    raise ValueError(
                        "existing application role has unexpected elevated privileges"
                    )
                if not row:
                    connection.execute(
                        sql.SQL(
                            "CREATE ROLE {} LOGIN PASSWORD {} CONNECTION LIMIT {}"
                        ).format(
                            sql.Identifier(name),
                            sql.Literal(password),
                            sql.Literal(role.get("connection_limit", 10)),
                        )
                    )
                else:
                    # Authenticate before changing an existing role: a rerun is not a rotation.
                    try:
                        database = next(db["name"] for db in app["databases"])
                        with psycopg.connect(
                            host=args.pg_host,
                            port=args.pg_port,
                            dbname=database,
                            user=name,
                            password=password,
                            connect_timeout=5,
                        ):
                            pass
                    except psycopg.errors.InvalidPassword:
                        if not args.allow_rotation:
                            raise ValueError(
                                "credential rotation requires a held maintenance transaction"
                            ) from None
                        connection.execute(
                            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                                sql.Identifier(name), sql.Literal(password)
                            )
                        )
                    except psycopg.errors.InvalidCatalogName:
                        pass
                    connection.execute(
                        sql.SQL("ALTER ROLE {} CONNECTION LIMIT {}").format(
                            sql.Identifier(name),
                            sql.Literal(role.get("connection_limit", 10)),
                        )
                    )
            for database in app.get("databases", []):
                name, owner = database["name"], database["owner"]
                row = connection.execute(
                    "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s",
                    [name],
                ).fetchone()
                if row and row[0] != owner:
                    raise ValueError("existing database has unexpected ownership")
                if not row:
                    connection.execute(
                        sql.SQL(
                            "CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'"
                        ).format(sql.Identifier(name), sql.Identifier(owner))
                    )
                connection.execute(
                    sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                        sql.Identifier(name)
                    )
                )
                for role in app.get("roles", []):
                    connection.execute(
                        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                            sql.Identifier(name), sql.Identifier(role["name"])
                        )
                    )
                with connect_pg(args, name) as db:
                    db.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
                    db.execute(
                        sql.SQL("GRANT ALL ON SCHEMA public TO {}").format(
                            sql.Identifier(owner)
                        )
                    )
                    if database.get("extensions"):
                        if database["extensions"] != ["pgcrypto"] or name != "sure":
                            raise ValueError("unapproved database extension")
                        db.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        for app in consumers.values():
            allowed = [db["name"] for db in app.get("databases", [])]
            for role in app.get("roles", []):
                unexpected = connection.execute(
                    "SELECT datname FROM pg_database WHERE datallowconn AND NOT (datname=ANY(%s)) AND has_database_privilege(%s,oid,'CONNECT')",
                    [allowed, role["name"]],
                ).fetchall()
                if unexpected:
                    raise ValueError(
                        "application role retains unexpected database access"
                    )


def pg_environment(args):
    return {
        **os.environ,
        "PGHOST": args.pg_host,
        "PGPORT": str(args.pg_port),
        "PGUSER": args.pg_user,
        "PGPASSWORD": secret(args.credentials, "postgresql_admin_password"),
    }


def native(command, *, env=None):
    result = subprocess.run(
        command,
        env=env,
        capture_output=True,
        timeout=max(
            1,
            float(os.environ.get("HOME_OPS_DATA_DEADLINE", time.time() + 3600))
            - time.time(),
        ),
        check=False,
    )
    if result.returncode:
        raise ValueError(
            f"native {Path(command[0]).name} operation failed (exit {result.returncode}); private diagnostics required"
        )
    return result.stdout


def assert_quiet(args, registry):
    consumers = select_consumers(registry, args.apps)
    databases = [
        db["name"] for app in consumers.values() for db in app.get("databases", [])
    ]
    with connect_pg(args) as connection:
        if connection.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname=ANY(%s)", [databases]
        ).fetchone()[0]:
            raise ValueError("selected database still has connected clients")
    users = {app["redis"]["username"] for app in consumers.values() if app.get("redis")}
    if users and any(
        client.get("user") in users for client in redis_connection(args).client_list()
    ):
        raise ValueError("selected Redis clients still connected")


def dump_postgres(args, registry):
    for app in select_consumers(registry, args.apps).values():
        root = Path(args.root) / app["pvcs"][0] / ".home-ops/databases"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for db in app.get("databases", []):
            destination = root / (db["name"] + ".dump")
            native(
                ["pg_dump", "--format=custom", "--file", str(destination), db["name"]],
                env=pg_environment(args),
            )
            native(["pg_restore", "--list", str(destination)])


def restore_postgres(args, registry):
    from psycopg import sql

    consumers = select_consumers(registry, args.apps)
    for app in consumers.values():
        for db in app.get("databases", []):
            source = (
                Path(args.root)
                / app["pvcs"][0]
                / ".home-ops/databases"
                / (db["name"] + ".dump")
            )
            if not source.is_file():
                raise ValueError("required database dump missing")
            native(["pg_restore", "--list", str(source)])
    with connect_pg(args) as connection:
        for app in consumers.values():
            for db in app.get("databases", []):
                active = connection.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname=%s",
                    [db["name"]],
                ).fetchone()[0]
                if active:
                    raise ValueError("database still has connected writers")
                connection.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(
                        sql.Identifier(db["name"])
                    )
                )
                connection.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                        sql.Identifier(db["name"]), sql.Identifier(db["owner"])
                    )
                )
                connection.execute(
                    sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                        sql.Identifier(db["name"])
                    )
                )
                for role in app["roles"]:
                    connection.execute(
                        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                            sql.Identifier(db["name"]), sql.Identifier(role["name"])
                        )
                    )
                source = (
                    Path(args.root)
                    / app["pvcs"][0]
                    / ".home-ops/databases"
                    / (db["name"] + ".dump")
                )
                native(
                    [
                        "pg_restore",
                        "--exit-on-error",
                        "--single-transaction",
                        "--dbname",
                        db["name"],
                        str(source),
                    ],
                    env=pg_environment(args),
                )
                with connect_pg(args, db["name"]) as restored:
                    restored.execute("ANALYZE")


def redis_connection(args, *, source=False, database=0):
    import redis

    return redis.Redis(
        host=args.redis_source_host if source else args.redis_host,
        port=args.redis_source_port if source else args.redis_port,
        db=database,
        username=None if source else "admin",
        password=None if source else secret(args.credentials, "redis_admin_password"),
        socket_connect_timeout=10,
        socket_timeout=30,
    )


def provision_redis(args, registry):
    connection = redis_connection(args)
    for app in select_consumers(registry, args.apps).values():
        allocation = app.get("redis")
        if not allocation:
            continue
        password = secret(args.credentials, allocation["password_key"])
        # Logical DBs share a trust domain. Deny global/destructive operations;
        # key/channel behavior is exercised against the real applications.
        rules = [
            "reset",
            "on",
            ">" + password,
            "~*",
            "&" + allocation["prefix"] + "*",
            "+@all",
            "-@admin",
            "-client",
            "+client|id",
            "+client|getname",
            "+client|setname",
            "+client|setinfo",
            "+client|info",
            "-function",
            "-script|flush",
            "-script|kill",
            "-script|debug",
            "-monitor",
            "-acl",
            "-config",
            "-shutdown",
            "-debug",
            "-module",
            "-replicaof",
            "-slaveof",
            "-migrate",
            "-swapdb",
            "-flushall",
            "-flushdb",
            "-save",
            "-bgsave",
            "-bgrewriteaof",
        ]
        if allocation["username"] == "sure":
            rules.append("&sure_production*")
        connection.execute_command("ACL", "SETUSER", allocation["username"], *rules)
    connection.execute_command("ACL", "SAVE")


def snapshot_redis(args):
    destination = Path(args.root) / ".home-ops/redis.rdb"
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    native(
        [
            "redis-cli",
            "-h",
            args.redis_host,
            "-p",
            str(args.redis_port),
            "--user",
            "admin",
            "--rdb",
            str(destination),
        ],
        env={
            **os.environ,
            "REDISCLI_AUTH": secret(args.credentials, "redis_admin_password"),
        },
    )


def transfer_redis(args, registry):
    for app in select_consumers(registry, args.apps).values():
        allocation = app.get("redis")
        if not allocation:
            continue
        db = allocation["database"]
        source, target = (
            redis_connection(args, source=True, database=db),
            redis_connection(args, database=db),
        )
        source.ping()
        target.ping()
        # Clear only the selected DB, never FLUSHALL or another application's DB.
        for key in target.scan_iter(count=500):
            target.delete(key)
        for key in source.scan_iter(count=500):
            payload, expiry = (
                source.dump(key),
                source.execute_command("PEXPIRETIME", key),
            )
            if payload is None or expiry == -2:
                continue
            target.restore(
                key,
                0 if expiry == -1 else expiry,
                payload,
                replace=True,
                absttl=expiry != -1,
            )
        if source.dbsize() != target.dbsize():
            raise ValueError("Redis restore verification failed")


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def make_manifest(root, registry, apps, operation, images):
    root = Path(root).resolve()
    consumers = select_consumers(registry, apps)
    files, links = {}, {}
    for consumer in consumers.values():
        for pvc in consumer["pvcs"]:
            location = root / pvc
            if (
                not location.is_dir()
                or location.is_symlink()
                or not location.resolve().is_relative_to(root)
            ):
                raise ValueError("staged application PVC missing")
            for path in sorted(location.rglob("*")):
                relative = str(path.relative_to(root))
                if path.is_symlink():
                    links[relative] = os.readlink(path)
                elif path.is_file():
                    files[relative] = digest(path)
    redis = root / ".home-ops/redis.rdb"
    if redis.is_file():
        files[str(redis.relative_to(root))] = digest(redis)
    return {
        "version": 1,
        "operation": operation,
        "captured_at": datetime.now(UTC).isoformat(),
        "consumers": {
            name: {
                "backend": "postgresql",
                "databases": deepcopy(app.get("databases", [])),
                "redis": {"database": app["redis"]["database"]}
                if app.get("redis")
                else None,
                "pvcs": list(app["pvcs"]),
                "key_refs": list(app.get("key_refs", [])),
                "images": images.get(name, []),
            }
            for name, app in consumers.items()
        },
        "files": files,
        "symlinks": links,
    }


def verify_manifest(root, manifest, images=None, *, registry=None, apps=None):
    root = Path(root).resolve()
    if (
        manifest.get("version") != 1
        or not isinstance(manifest.get("consumers"), dict)
        or not manifest["consumers"]
    ):
        raise ValueError("required compatible database manifest missing")
    inventory = manifest.get("files")
    links = manifest.get("symlinks", {})
    if not isinstance(inventory, dict) or not isinstance(links, dict):
        raise ValueError("manifest file inventory required")
    if registry is not None:
        selected = select_consumers(
            registry, apps if apps is not None else list(manifest["consumers"])
        )
        if set(selected) != set(manifest["consumers"]):
            raise ValueError(
                "snapshot application scope differs from selected registry"
            )
        for app, expected in selected.items():
            data = manifest["consumers"][app]
            expected_redis = (
                {"database": expected["redis"]["database"]}
                if expected.get("redis")
                else None
            )
            if (
                data.get("databases") != expected.get("databases", [])
                or data.get("pvcs") != expected.get("pvcs", [])
                or data.get("redis") != expected_redis
                or data.get("key_refs", []) != expected.get("key_refs", [])
            ):
                raise ValueError(
                    "snapshot database or file mapping differs from selected registry"
                )
    pvcs = []
    for app, data in manifest["consumers"].items():
        if (
            not NAME.fullmatch(app)
            or data.get("backend") != "postgresql"
            or not data.get("pvcs")
            or not data.get("databases")
        ):
            raise ValueError("invalid database manifest consumer")
        for pvc in data["pvcs"]:
            if len(pvc.split("/")) != 2 or not all(
                NAME.fullmatch(part) for part in pvc.split("/")
            ):
                raise ValueError("invalid manifest PVC path")
            if pvc in pvcs:
                raise ValueError("shared manifest PVC allocation")
            pvcs.append(pvc)
        for database in data.get("databases", []):
            if not NAME.fullmatch(database.get("name", "")) or not NAME.fullmatch(
                database.get("owner", "")
            ):
                raise ValueError("invalid database dump mapping")
            expected = (
                data["pvcs"][0] + "/.home-ops/databases/" + database["name"] + ".dump"
            )
            if expected not in inventory:
                raise ValueError("required database dump missing from manifest")
        if data.get("redis") and ".home-ops/redis.rdb" not in inventory:
            raise ValueError("required Redis snapshot missing from manifest")
        if not data.get("images"):
            raise ValueError("required application image identity missing")
    for relative, expected in manifest.get("files", {}).items():
        path = root / relative
        if (
            not path.resolve().is_relative_to(root)
            or path.is_symlink()
            or not path.is_file()
        ):
            raise ValueError("manifest checksum path invalid or missing")
        if digest(path) != expected:
            raise ValueError("manifest checksum mismatch")
    for relative, expected in manifest.get("symlinks", {}).items():
        path = root / relative
        if (
            not path.parent.resolve().is_relative_to(root)
            or not path.is_symlink()
            or os.readlink(path) != expected
        ):
            raise ValueError("manifest symlink mismatch")
    actual_files, actual_links = set(), set()
    for pvc in pvcs:
        location = root / pvc
        if (
            location.is_symlink()
            or not location.is_dir()
            or not location.resolve().is_relative_to(root)
        ):
            raise ValueError("manifest PVC is missing or redirects outside generation")
        for path in location.rglob("*"):
            relative = str(path.relative_to(root))
            if path.is_symlink():
                actual_links.add(relative)
            elif path.is_file():
                actual_files.add(relative)
            elif not path.is_dir():
                raise ValueError("unsupported generation file type")
    if (root / ".home-ops/redis.rdb").is_file():
        actual_files.add(".home-ops/redis.rdb")
    if actual_files != set(inventory) or actual_links != set(links):
        raise ValueError("manifest inventory does not match generation files")
    if images is not None:
        for app, data in manifest["consumers"].items():
            if images.get(app) != data["images"]:
                raise ValueError(
                    "application image differs from snapshot; stage recorded version first"
                )
    return True


def successful_snapshot(code, messages):
    snapshots = [
        message.get("snapshot_id")
        for message in messages
        if message.get("message_type") == "summary" and message.get("snapshot_id")
    ]
    if code != 0 or len(snapshots) != 1:
        raise ValueError("incomplete upload must remain pending")
    return snapshots[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "validate",
            "quiet",
            "provision",
            "dump",
            "restore",
            "redis-provision",
            "redis-snapshot",
            "redis-restore",
            "manifest",
            "verify",
        ],
    )
    parser.add_argument(
        "--registry",
        default="/opt/home-ops/ansible/roles/shared_data/files/registry.yaml",
    )
    parser.add_argument("--credentials", default="/run/credentials")
    parser.add_argument("--apps", type=lambda value: value.split(","))
    parser.add_argument("--root", default="/staging")
    parser.add_argument("--operation", default="manual")
    parser.add_argument("--images", default="{}")
    parser.add_argument(
        "--pg-host", default="postgresql.platform-system.svc.cluster.local"
    )
    parser.add_argument("--pg-port", type=int, default=5432)
    parser.add_argument("--pg-user", default="postgres")
    parser.add_argument(
        "--redis-host", default="redis.platform-system.svc.cluster.local"
    )
    parser.add_argument("--redis-port", type=int, default=6379)
    parser.add_argument(
        "--redis-source-host", default="redis-recovery.selfhosted.svc.cluster.local"
    )
    parser.add_argument("--redis-source-port", type=int, default=6379)
    parser.add_argument("--allow-rotation", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    registry = validate_registry(yaml.safe_load(Path(args.registry).read_text()))
    if (
        args.action not in {"validate", "quiet", "manifest", "verify"}
        and not args.confirm
    ):
        parser.error("data changes require --confirm after the maintenance gate")
    if args.action == "quiet":
        assert_quiet(args, registry)
    elif args.action == "provision":
        provision(args, registry)
    elif args.action == "dump":
        dump_postgres(args, registry)
    elif args.action == "restore":
        restore_postgres(args, registry)
    elif args.action == "redis-provision":
        provision_redis(args, registry)
    elif args.action == "redis-snapshot":
        snapshot_redis(args)
    elif args.action == "redis-restore":
        transfer_redis(args, registry)
    elif args.action == "manifest":
        manifest = make_manifest(
            args.root, registry, args.apps, args.operation, json.loads(args.images)
        )
        path = Path(args.root) / ".home-ops/manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(json.dumps(manifest, indent=2) + "\n")
    elif args.action == "verify":
        verify_manifest(
            args.root,
            json.loads((Path(args.root) / ".home-ops/manifest.json").read_text()),
            json.loads(args.images) if args.images != "{}" else None,
            registry=registry,
            apps=args.apps,
        )
    print(json.dumps({"action": args.action, "status": "ok"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Drivers can embed connection parameters in errors. Never print them.
        print(
            json.dumps({"status": "failed", "error_type": type(error).__name__}),
            file=sys.stderr,
        )
        sys.exit(1)
