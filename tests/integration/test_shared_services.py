"""Disposable tests execute the exact draft init commands and server args."""

import subprocess
import time
import uuid

import pytest
import yaml

from tests.support.runtime import ROOT

root = ROOT
values = {
    name: yaml.safe_load(
        (root / f"apps/platform-system/{name}/values.yaml").read_text()
    )
    for name in ["postgresql", "redis"]
}
prefix = "home-ops-stage2-" + uuid.uuid4().hex[:10]
containers = []
volumes = []
password = "synthetic-only-" + uuid.uuid4().hex


def run(*args, check=True, input=None):
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, input=input
    )
    if check and result.returncode:
        raise RuntimeError("docker command failed: " + result.stderr[-2000:])
    return result.stdout.strip()


def fullimage(name):
    d = values[name]["controllers"]["main"]["containers"]["app"]["image"]
    return d["repository"] + ":" + d["tag"] + "@" + d["digest"]


def volume(suffix):
    name = prefix + "-" + suffix
    run("volume", "create", name)
    volumes.append(name)
    return name


def initialize(name, data, runvolume=None, secret=password):
    for init_name, c in sorted(
        values[name]["controllers"]["main"]["initContainers"].items()
    ):
        context = c["securityContext"]
        args = [
            "run",
            "--rm",
            "--read-only",
            "--user",
            str(context["runAsUser"]) + ":" + str(context["runAsGroup"]),
            "--cap-drop",
            "ALL",
            "-v",
            data + (":/var/lib/postgresql" if name == "postgresql" else ":/data"),
        ]
        for capability in context["capabilities"].get("add", []):
            args += ["--cap-add", capability]
        if runvolume:
            args += ["-v", runvolume + ":/var/run/postgresql"]
        if name == "redis" and c.get("env"):
            args += ["-e", "REDIS_ADMIN_PASSWORD=" + secret]
        run(*args, fullimage(name), *c["command"])


def pgstart(data, runvolume):
    name = prefix + "-pg"
    containers.append(name)
    args = [
        "run",
        "-d",
        "--name",
        name,
        "--read-only",
        "--user",
        "999:999",
        "--cap-drop",
        "ALL",
        "--tmpfs",
        "/tmp:rw",
        "--shm-size",
        "256m",
        "-v",
        data + ":/var/lib/postgresql",
        "-v",
        runvolume + ":/var/run/postgresql",
        "-e",
        "POSTGRES_PASSWORD=" + password,
        "-e",
        "PGPASSWORD=" + password,
        "-e",
        "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256 --auth-local=scram-sha-256",
        "-e",
        "PGDATA=/var/lib/postgresql/18/docker",
    ]
    run(
        *args,
        fullimage("postgresql"),
        *values["postgresql"]["controllers"]["main"]["containers"]["app"]["args"],
    )
    for _ in range(120):
        r = run(
            "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", check=False
        )
        if "accepting connections" in r:
            return name
        time.sleep(0.25)
    raise RuntimeError(
        "Postgres readiness timeout: " + run("logs", name, check=False)[-2000:]
    )


def sql(name, query):
    return run(
        "exec",
        "-e",
        "PGPASSWORD=" + password,
        name,
        "psql",
        "-h",
        "127.0.0.1",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-w",
        "-Atqc",
        query,
    )


def redisstart(data, config):
    name = prefix + "-redis"
    containers.append(name)
    run(
        "run",
        "-d",
        "--name",
        name,
        "--read-only",
        "--user",
        "999:999",
        "--cap-drop",
        "ALL",
        "--tmpfs",
        "/tmp:rw",
        "-v",
        data + ":/data",
        "-v",
        config + ":/etc/redis:ro",
        "-e",
        "REDISCLI_AUTH=" + password,
        fullimage("redis"),
        *values["redis"]["controllers"]["main"]["containers"]["app"]["command"],
    )
    for _ in range(80):
        if cli(name, "PING", check=False) == "PONG":
            return name
        time.sleep(0.25)
    raise RuntimeError(
        "Redis readiness timeout: " + run("logs", name, check=False)[-2000:]
    )


def cli(name, *args, check=True):
    return run(
        "exec",
        "-e",
        "REDISCLI_AUTH=" + password,
        name,
        "redis-cli",
        "-e",
        "--raw",
        "--no-auth-warning",
        "--user",
        "admin",
        *args,
        check=check,
    )


def stop(name):
    run("stop", "--time", "30", name)
    run("rm", name)
    containers.remove(name)


pg_settings = dict(
    value.split("=", 1)
    for value in values["postgresql"]["controllers"]["main"]["containers"]["app"][
        "args"
    ]
    if "=" in value
)


@pytest.mark.parametrize("existing_empty", [False, True])
def test_shared_services_bootstrap_and_restart_persistence(existing_empty):
    try:
        pgdata = volume("pgdata")
        pgrun = volume("pgrun")
        redisdata = volume("redisdata")
        run(
            "run",
            "--rm",
            "-v",
            pgdata + ":/data",
            fullimage("postgresql"),
            "sh",
            "-ec",
            "chmod 2775 /data",
        )
        if existing_empty:
            run(
                "run",
                "--rm",
                "-v",
                pgdata + ":/data",
                fullimage("postgresql"),
                "sh",
                "-ec",
                "install -d -m 0700 -o 999 -g 999 /data/18/docker; test \"$(stat -c '%u:%g:%a' /data/18/docker)\" = 999:999:2700",
            )
        initialize("postgresql", pgdata, pgrun)
        pg = pgstart(pgdata, pgrun)
        assert run("exec", pg, "id", "-u") == "999"
        assert sql(
            pg,
            "SELECT current_setting('max_connections'),current_setting('shared_buffers'),current_setting('work_mem')",
        ) == "|".join(
            pg_settings[key]
            for key in ["max_connections", "shared_buffers", "work_mem"]
        )
        assert (
            sql(
                pg,
                "SELECT bool_and(auth_method='scram-sha-256') FROM pg_hba_file_rules WHERE error IS NULL",
            )
            == "t"
        )
        assert (
            sql(
                pg,
                "SELECT rolpassword LIKE 'SCRAM-SHA-256$%' FROM pg_authid WHERE rolname='postgres'",
            )
            == "t"
        )
        sql(
            pg,
            "CREATE TABLE bootstrap_proof(value text);INSERT INTO bootstrap_proof VALUES('persisted')",
        )
        stop(pg)
        initialize("postgresql", pgdata, pgrun)
        pg = pgstart(pgdata, pgrun)
        assert sql(pg, "SELECT value FROM bootstrap_proof") == "persisted"
        config = volume("redisconfig")
        run(
            "run",
            "--rm",
            "-i",
            "-v",
            config + ":/etc/redis",
            fullimage("redis"),
            "sh",
            "-c",
            "cat > /etc/redis/redis.conf; chmod 0755 /etc/redis; chmod 0644 /etc/redis/redis.conf",
            input=values["redis"]["configMaps"]["config"]["data"]["redis.conf"],
        )
        initialize("redis", redisdata)
        redis = redisstart(redisdata, config)
        assert run("exec", redis, "id", "-u") == "999"
        for probe in values["redis"]["controllers"]["main"]["containers"]["app"][
            "probes"
        ].values():
            assert run("exec", redis, *probe["spec"]["exec"]["command"]) == ""
        wrong_probe = subprocess.run(
            [
                "docker",
                "exec",
                "-e",
                "REDISCLI_AUTH=wrong-synthetic-password",
                redis,
                *values["redis"]["controllers"]["main"]["containers"]["app"]["probes"][
                    "readiness"
                ]["spec"]["exec"]["command"],
            ],
            capture_output=True,
            text=True,
        )
        assert wrong_probe.returncode != 0
        assert cli(redis, "CONFIG", "GET", "maxmemory") == "maxmemory\n268435456", repr(
            cli(redis, "CONFIG", "GET", "maxmemory")
        )
        assert (
            cli(redis, "CONFIG", "GET", "maxmemory-policy")
            == "maxmemory-policy\nnoeviction"
        )
        assert cli(redis, "CONFIG", "GET", "appendfsync") == "appendfsync\neverysec"
        assert cli(redis, "CONFIG", "GET", "appendonly") == "appendonly\nyes"
        cli(
            redis,
            "ACL",
            "SETUSER",
            "proof-user",
            "on",
            ">synthetic-app-password",
            "~proof:*",
            "&proof:*",
            "+get",
            "+set",
        )
        cli(redis, "ACL", "SAVE")
        cli(redis, "SET", "proof:key", "persisted")
        acl_before = run("exec", redis, "sha256sum", "/data/users.acl").split()[0]
        stop(redis)
        initialize("redis", redisdata, secret="synthetic-should-not-replace-admin")
        redis = redisstart(redisdata, config)
        assert (
            run("exec", redis, "sha256sum", "/data/users.acl").split()[0] == acl_before
        )
        assert cli(redis, "GET", "proof:key") == "persisted"
        assert "proof-user" in cli(redis, "ACL", "USERS")
        unauth = run(
            "exec", "-e", "REDISCLI_AUTH=", redis, "redis-cli", "PING", check=False
        )
        assert "NOAUTH" in unauth

    finally:
        for name in containers:
            run("rm", "-f", name, check=False)
        for name in volumes:
            run("volume", "rm", name, check=False)


def test_postgresql_init_refuses_to_rewrite_nonempty_data_permissions():
    try:
        pgdata = volume("unsafe-pgdata")
        pgrun = volume("unsafe-pgrun")
        run(
            "run",
            "--rm",
            "-v",
            pgdata + ":/data",
            fullimage("postgresql"),
            "sh",
            "-ec",
            "install -d -m 2700 -o 999 -g 999 /data/18/docker; printf retained > /data/18/docker/PG_VERSION",
        )
        with pytest.raises(RuntimeError, match="refusing unsafe startup"):
            initialize("postgresql", pgdata, pgrun)
        assert (
            run(
                "run",
                "--rm",
                "-v",
                pgdata + ":/data:ro",
                fullimage("postgresql"),
                "stat",
                "-c",
                "%u:%g:%a",
                "/data/18/docker",
            )
            == "999:999:2700"
        )
        assert (
            run(
                "run",
                "--rm",
                "-v",
                pgdata + ":/data:ro",
                fullimage("postgresql"),
                "cat",
                "/data/18/docker/PG_VERSION",
            )
            == "retained"
        )
    finally:
        for name in containers:
            run("rm", "-f", name, check=False)
        for name in volumes:
            run("volume", "rm", name, check=False)


@pytest.mark.parametrize("linked_parent", [False, True])
def test_postgresql_init_rejects_links_without_changing_the_target(linked_parent):
    try:
        pgdata = volume("linked-pgdata")
        pgrun = volume("linked-pgrun")
        setup = (
            "install -d -m 0700 -o 999 -g 999 /data/original/docker; "
            "printf retained > /data/original/docker/PG_VERSION; "
            "ln -s original /data/18; chown -h 999:999 /data/18"
            if linked_parent
            else "install -d -m 2700 -o 999 -g 999 /data/original; "
            "printf retained > /data/original/PG_VERSION; install -d /data/18; "
            "ln -s ../original /data/18/docker; chown -h 999:999 /data/18/docker"
        )
        run(
            "run",
            "--rm",
            "-v",
            pgdata + ":/data",
            fullimage("postgresql"),
            "sh",
            "-ec",
            setup,
        )
        with pytest.raises(RuntimeError, match="refusing unsafe startup"):
            initialize("postgresql", pgdata, pgrun)
        target = "/data/original/docker" if linked_parent else "/data/original"
        assert run(
            "run",
            "--rm",
            "-v",
            pgdata + ":/data:ro",
            fullimage("postgresql"),
            "stat",
            "-c",
            "%u:%g:%a",
            target,
        ) == ("999:999:700" if linked_parent else "999:999:2700")
        assert (
            run(
                "run",
                "--rm",
                "-v",
                pgdata + ":/data:ro",
                fullimage("postgresql"),
                "cat",
                target + "/PG_VERSION",
            )
            == "retained"
        )
    finally:
        for name in containers:
            run("rm", "-f", name, check=False)
        for name in volumes:
            run("volume", "rm", name, check=False)
