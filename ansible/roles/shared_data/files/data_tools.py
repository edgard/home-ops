"""Native data adapters. Kubernetes orchestration belongs to the Ansible role."""

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
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
    file_consumers = registry.get("file_consumers", {})
    if not isinstance(file_consumers, dict) or set(file_consumers) & set(consumers):
        raise ValueError("file consumers must have separate registered identities")
    consumers = {
        **consumers,
        **{
            name: {
                **app,
                "enabled": True,
                "backend": "sqlite",
                "roles": [],
                "databases": [],
            }
            for name, app in file_consumers.items()
        },
    }
    allocated_pvcs = set()
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
        if consumer.get("backend") not in {"sqlite", "postgresql"}:
            raise ValueError("unsupported application backend")
        for path in consumer.get("sqlite_files", []):
            if (
                Path(path).is_absolute()
                or ".." in Path(path).parts
                or not any(
                    path.startswith(pvc + "/") for pvc in consumer.get("pvcs", [])
                )
            ):
                raise ValueError("SQLite database must belong to the application PVC")
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
            if pvc in allocated_pvcs:
                raise ValueError("PVC belongs to more than one consumer")
            allocated_pvcs.add(pvc)
            if pvc in {
                "platform-system/postgresql",
                "platform-system/redis",
                "selfhosted/shared-data-staging",
            }:
                raise ValueError(
                    "raw database engines and staging are reserved outside appdata"
                )
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
                type(redis.get("adopted", True)) is not bool
                or type(db) is not int
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


def remaining(deadline=None, default=3600):
    if deadline is None:
        deadline = float(
            os.environ.get("HOME_OPS_DATA_DEADLINE", time.time() + default)
        )
    budget = deadline - time.time()
    if budget <= 0:
        raise TimeoutError("capture deadline expired before starting native work")
    return budget


def native(command, *, env=None):
    result = subprocess.run(
        command,
        env=env,
        capture_output=True,
        timeout=remaining(),
        check=False,
    )
    if result.returncode:
        raise ValueError(
            f"native {Path(command[0]).name} operation failed (exit {result.returncode}); private diagnostics required"
        )
    return result.stdout


def uses_shared_redis(app):
    return bool(app.get("redis")) and app["redis"].get("adopted", True)


def legacy_pvcs(registry, apps):
    """Current file consumers plus SQLite applications awaiting enrollment."""
    selected = {
        pvc for app in apps for pvc in registry["consumers"][app].get("pvcs", [])
    }
    consumers = list(registry.get("file_consumers", {}).values()) + [
        app
        for app in registry["consumers"].values()
        if not app["enabled"] and app["backend"] == "sqlite"
    ]
    return sorted({pvc for app in consumers for pvc in app["pvcs"]} - selected)


def legacy_consumers(registry, apps):
    """Record exactly the live file scope covered beside a native generation.

    These mappings carry no stopped-writer, image, key or schema claim.
    """
    covered = set(legacy_pvcs(registry, apps))
    return {
        name: {
            "namespace": app["namespace"],
            "pvcs": list(app["pvcs"]),
            "backend": app.get("backend", "files"),
            "sqlite_files": list(app.get("sqlite_files", [])),
            "mode": "live-files",
        }
        for name, app in {
            **registry["consumers"],
            **registry.get("file_consumers", {}),
        }.items()
        if app.get("pvcs") and set(app["pvcs"]) <= covered
    }


def assert_quiet(args, registry):
    consumers = select_consumers(registry, args.apps)
    databases = [
        db["name"]
        for app in consumers.values()
        if app["backend"] == "postgresql"
        for db in app.get("databases", [])
    ]
    if databases:
        with connect_pg(args) as connection:
            if connection.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=ANY(%s)",
                [databases],
            ).fetchone()[0]:
                raise ValueError("selected database still has connected clients")
    users = {
        app["redis"]["username"] for app in consumers.values() if uses_shared_redis(app)
    }
    if users and any(
        client.get("user") in users for client in redis_connection(args).client_list()
    ):
        raise ValueError("selected Redis clients still connected")


def estimate_capture(args, registry):
    """Conservative estimates, not a promise that free space cannot change."""
    consumers = select_consumers(registry, args.apps)
    databases = [
        db["name"]
        for app in consumers.values()
        if app["backend"] == "postgresql"
        for db in app.get("databases", [])
    ]
    database_bytes = 0
    if databases:
        remaining()
        with connect_pg(args) as connection:
            for name in databases:
                remaining()
                size = connection.execute(
                    "SELECT pg_database_size(%s)", [name]
                ).fetchone()[0]
                database_bytes += size * 2 + 1024 * 1024
    redis_bytes = 0
    if any(uses_shared_redis(app) for app in consumers.values()):
        remaining()
        info = redis_connection(args).info("memory")
        redis_bytes = int(info["used_memory"] * 1.2) + 1024 * 1024
    return {"database_bytes": database_bytes, "redis_bytes": redis_bytes}


def postgres_schema_metadata(args, database):
    with connect_pg(args, database) as connection:
        server = int(connection.execute("SHOW server_version_num").fetchone()[0])
    schema = native(
        [
            "pg_dump",
            "--schema-only",
            "--no-owner",
            "--no-privileges",
            "--restrict-key=homeopsSchemaFingerprint",
            database,
        ],
        env=pg_environment(args),
    )
    normalized = b"\n".join(
        line
        for line in schema.splitlines()
        if not line.startswith(
            (b"-- Dumped from database version", b"-- Dumped by pg_dump version")
        )
    )
    return {
        "server_version_num": server,
        "dump_version": native(["pg_dump", "--version"]).decode().strip(),
        "schema_sha256": hashlib.sha256(normalized).hexdigest(),
    }


def dump_postgres(args, registry):
    for app in select_consumers(registry, args.apps).values():
        if app.get("backend", "postgresql") != "postgresql":
            continue
        root = Path(args.root) / app["pvcs"][0] / ".home-ops/databases"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for db in app.get("databases", []):
            destination = root / (db["name"] + ".dump")
            native(
                ["pg_dump", "--format=custom", "--file", str(destination), db["name"]],
                env=pg_environment(args),
            )
            native(["pg_restore", "--list", str(destination)])
            metadata = postgres_schema_metadata(args, db["name"])
            destination.with_suffix(".schema.json").write_text(
                json.dumps(metadata) + "\n"
            )


def restore_postgres(args, registry):
    from psycopg import sql

    consumers = select_consumers(registry, args.apps)
    consumers = {
        name: app for name, app in consumers.items() if app["backend"] == "postgresql"
    }
    if not consumers:
        return
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
                expected_schema = json.loads(
                    source.with_suffix(".schema.json").read_text()
                )
                actual_schema = postgres_schema_metadata(args, db["name"])
                if expected_schema["schema_sha256"] != actual_schema["schema_sha256"]:
                    raise ValueError(
                        "restored PostgreSQL schema differs from capture; keep consumers held"
                    )


def redis_connection(args, *, source=False, database=0):
    import redis

    return redis.Redis(
        host=args.redis_source_host if source else args.redis_host,
        port=args.redis_source_port if source else args.redis_port,
        db=database,
        username=None if source else "admin",
        password=secret(
            (getattr(args, "redis_source_credentials", None) or args.credentials),
            "redis_recovery_password",
        )
        if source
        else secret(args.credentials, "redis_admin_password"),
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
        if not uses_shared_redis(app):
            continue
        db = allocation["database"]
        source, target = (
            redis_connection(args, source=True, database=db),
            redis_connection(args, database=db),
        )
        if (args.redis_source_host, args.redis_source_port) == (
            args.redis_host,
            args.redis_port,
        ):
            raise ValueError("Redis recovery source must be an isolated instance")
        remaining()
        source.ping()
        target.ping()
        if source.info("server")["run_id"] == target.info("server")["run_id"]:
            raise ValueError("Redis recovery source must be an isolated instance")
        # Clear only the selected DB, never FLUSHALL or another application's DB.
        for key in target.scan_iter(count=500):
            remaining()
            target.delete(key)
        for key in source.scan_iter(count=500):
            remaining()
            payload, expiry = (
                source.dump(key),
                source.execute_command("PEXPIRETIME", key),
            )
            if (
                payload is None
                or expiry == -2
                or (expiry > 0 and expiry <= time.time() * 1000)
            ):
                continue
            target.restore(
                key,
                0 if expiry == -1 else expiry,
                payload,
                replace=True,
                absttl=expiry != -1,
            )
        for key in source.scan_iter(count=500):
            remaining()
            payload = source.dump(key)
            expiry = source.execute_command("PEXPIRETIME", key)
            if (
                payload is None
                or expiry == -2
                or (expiry > 0 and expiry <= time.time() * 1000)
            ):
                continue
            if (
                target.dump(key) != payload
                or target.execute_command("PEXPIRETIME", key) != expiry
            ):
                raise ValueError("Redis restore verification failed")
        for key in target.scan_iter(count=500):
            remaining()
            if target.exists(key) and not source.exists(key):
                raise ValueError("Redis restore contains an unexpected key")


def digest(path, *, deadline=None):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            remaining(deadline)
            result.update(block)
    return result.hexdigest()


def make_manifest(root, registry, apps, operation, images, *, credentials=None):
    root = Path(root).resolve()
    consumers = select_consumers(registry, apps)
    if any(app.get("key_refs") for app in consumers.values()) and credentials is None:
        raise ValueError("mounted retained application key credentials required")
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
                "backend": app.get("backend", "postgresql"),
                "databases": deepcopy(app.get("databases", []))
                if app.get("backend", "postgresql") == "postgresql"
                else [],
                "sqlite_files": list(app.get("sqlite_files", []))
                if app.get("backend") == "sqlite"
                else [],
                "redis": {"database": app["redis"]["database"]}
                if uses_shared_redis(app)
                else None,
                "pvcs": list(app["pvcs"]),
                "key_refs": list(app.get("key_refs", [])),
                "key_fingerprints": {
                    key: hashlib.sha256(secret(credentials, key).encode()).hexdigest()
                    for key in app.get("key_refs", [])
                }
                if credentials is not None
                else {},
                "images": images.get(name, []),
                "schema_versions": {
                    db["name"]: json.loads(
                        (
                            root
                            / app["pvcs"][0]
                            / ".home-ops/databases"
                            / (db["name"] + ".schema.json")
                        ).read_text()
                    )
                    for db in app.get("databases", [])
                    if (
                        root
                        / app["pvcs"][0]
                        / ".home-ops/databases"
                        / (db["name"] + ".schema.json")
                    ).is_file()
                }
                if app.get("backend") == "postgresql"
                else {
                    relative: verify_sqlite(root / relative)
                    for relative in app.get("sqlite_files", [])
                },
            }
            for name, app in consumers.items()
        },
        "legacy_consumers": legacy_consumers(registry, list(consumers)),
        "files": files,
        "symlinks": links,
    }


def verify_sqlite(source):
    """SQLite reads may modify WAL shared memory; inspect a private disk copy."""
    suffixes = ["", "-wal", "-shm", "-journal"]
    sources = [Path(str(source) + suffix) for suffix in suffixes]
    if any(path.is_symlink() for path in sources):
        raise ValueError("SQLite database family must not redirect through symlinks")
    existing = [path for path in sources if path.is_file()]
    with tempfile.TemporaryDirectory(prefix="home-ops-sqlite-") as scratch:
        # Recovery/checkpointing can expand the main copy by the journal size.
        required = int(
            sum(path.stat().st_size * (1 if path == source else 2) for path in existing)
            * 1.2
        )
        if shutil.disk_usage(scratch).free < required:
            raise ValueError("insufficient SQLite verification scratch space")
        for path in existing:
            remaining()
            destination = Path(scratch) / path.name
            with path.open("rb") as incoming, destination.open("wb") as outgoing:
                for block in iter(lambda: incoming.read(1024 * 1024), b""):
                    remaining()
                    outgoing.write(block)
        try:
            with sqlite3.connect(Path(scratch) / source.name) as database:
                database.set_progress_handler(lambda: remaining() and 0, 10000)
                if database.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise ValueError("SQLite integrity verification failed")
                schema = database.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name,tbl_name"
                ).fetchall()
                return {
                    "client_version": sqlite3.sqlite_version,
                    "user_version": database.execute("PRAGMA user_version").fetchone()[
                        0
                    ],
                    "schema_version": database.execute(
                        "PRAGMA schema_version"
                    ).fetchone()[0],
                    "schema_sha256": hashlib.sha256(
                        json.dumps(schema, ensure_ascii=True).encode()
                    ).hexdigest(),
                }
        except sqlite3.DatabaseError as error:
            raise ValueError("SQLite integrity verification failed") from error


def verify_manifest(
    root, manifest, images=None, *, registry=None, apps=None, credentials=None
):
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
                if uses_shared_redis(expected)
                else None
            )
            expected_databases = (
                expected.get("databases", [])
                if expected.get("backend", "postgresql") == "postgresql"
                else []
            )
            expected_sqlite = (
                expected.get("sqlite_files", [])
                if expected.get("backend") == "sqlite"
                else []
            )
            if (
                data.get("backend") != expected.get("backend", "postgresql")
                or data.get("databases") != expected_databases
                or data.get("sqlite_files", []) != expected_sqlite
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
            or data.get("backend") not in {"postgresql", "sqlite"}
            or not data.get("pvcs")
            or (data.get("backend") == "postgresql" and not data.get("databases"))
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
        if data.get("redis") and ".home-ops/redis.rdb" not in inventory:
            raise ValueError("required Redis snapshot missing from manifest")
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
            schema_path = (
                data["pvcs"][0]
                + "/.home-ops/databases/"
                + database["name"]
                + ".schema.json"
            )
            metadata = data.get("schema_versions", {}).get(database["name"], {})
            if (
                schema_path not in inventory
                or not isinstance(metadata.get("server_version_num"), int)
                or metadata["server_version_num"] // 10000 != 18
                or not re.fullmatch(
                    r"pg_dump \(PostgreSQL\) 18(?:\.[0-9]+)?(?: .*)?",
                    metadata.get("dump_version", ""),
                )
                or not re.fullmatch("[a-f0-9]{64}", metadata.get("schema_sha256", ""))
                or (root / schema_path).is_symlink()
                or not (root / schema_path).is_file()
                or json.loads((root / schema_path).read_text()) != metadata
            ):
                raise ValueError(
                    "required compatible PostgreSQL schema metadata missing or inconsistent"
                )
        if data.get("backend") == "sqlite":
            if not data.get("sqlite_files") or any(
                path not in inventory for path in data["sqlite_files"]
            ):
                raise ValueError("required SQLite database missing from manifest")
        if data.get("redis") and ".home-ops/redis.rdb" not in inventory:
            raise ValueError("required Redis snapshot missing from manifest")
        if not data.get("images"):
            raise ValueError("required application image identity missing")
        if data.get("key_refs") and credentials is None:
            raise ValueError("mounted retained application key credentials required")
        if credentials is not None:
            expected_keys = {
                key: hashlib.sha256(secret(credentials, key).encode()).hexdigest()
                for key in data.get("key_refs", [])
            }
            if data.get("key_fingerprints", {}) != expected_keys:
                raise ValueError(
                    "required retained application key differs from captured key"
                )
    for relative, expected in manifest.get("files", {}).items():
        path = root / relative
        if (
            Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not any(relative.startswith(pvc + "/") for pvc in pvcs)
            and relative != ".home-ops/redis.rdb"
        ):
            raise ValueError("manifest checksum path outside selected PVC scope")
        if (
            not path.resolve().is_relative_to(root)
            or path.is_symlink()
            or any(
                parent.is_symlink()
                for parent in path.parents
                if parent.is_relative_to(root)
            )
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
            or location.parent.is_symlink()
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
    for data in manifest["consumers"].values():
        if data["backend"] == "sqlite":
            for relative in data["sqlite_files"]:
                actual_schema = verify_sqlite(root / relative)
                expected_schema = data.get("schema_versions", {}).get(relative, {})
                if not re.fullmatch(
                    r"3\.[0-9]+\.[0-9]+", expected_schema.get("client_version", "")
                ) or any(
                    expected_schema.get(key) != value
                    for key, value in actual_schema.items()
                    if key != "client_version"
                ):
                    raise ValueError("SQLite schema metadata missing or inconsistent")
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
            "estimate",
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
        args.action not in {"validate", "estimate", "quiet", "manifest", "verify"}
        and not args.confirm
    ):
        parser.error("data changes require --confirm after the maintenance gate")
    if args.action == "estimate":
        print(
            json.dumps(
                {
                    **estimate_capture(args, registry),
                    "legacy_pvcs": legacy_pvcs(
                        registry, args.apps or list(select_consumers(registry))
                    ),
                }
            )
        )
        return
    if args.action == "quiet":
        assert_quiet(args, registry)
    elif args.action == "provision":
        provision(args, registry)
    elif args.action == "dump":
        dump_postgres(args, registry)
    elif args.action == "restore":
        verify_manifest(
            args.root,
            json.loads((Path(args.root) / ".home-ops/manifest.json").read_text()),
            json.loads(args.images),
            registry=registry,
            apps=args.apps,
            credentials=args.credentials,
        )
        restore_postgres(args, registry)
    elif args.action == "redis-provision":
        provision_redis(args, registry)
    elif args.action == "redis-snapshot":
        snapshot_redis(args)
    elif args.action == "redis-restore":
        verify_manifest(
            args.root,
            json.loads((Path(args.root) / ".home-ops/manifest.json").read_text()),
            json.loads(args.images),
            registry=registry,
            apps=args.apps,
            credentials=args.credentials,
        )
        transfer_redis(args, registry)
    elif args.action == "manifest":
        manifest = make_manifest(
            args.root,
            registry,
            args.apps,
            args.operation,
            json.loads(args.images),
            credentials=args.credentials,
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
            credentials=args.credentials,
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
