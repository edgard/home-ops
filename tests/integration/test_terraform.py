import json
import subprocess
from pathlib import Path

import hcl2
import pytest

from tests.support.configuration import terraform_sources
from tests.support.runtime import ROOT, environment, executable, run_role

CREDENTIALS = [
    "tofu_aws_access_key_id",
    "tofu_aws_secret_access_key",
    "tofu_cloudflare_api_token",
    "tofu_cloudflare_zone_id",
    "tofu_tailscale_client_id",
    "tofu_tailscale_client_secret",
]


def test_native_variable_and_resource_state_sensitivity(tmp_path):
    with (ROOT / "terraform/variables.tf").open() as file:
        variables = hcl2.load(file)
    (tmp_path / "main.tf").write_text(hcl2.dumps(variables))
    parsed = terraform_sources(ROOT)
    assignment = next(
        module["cloudflare"]["zone_id"]
        for module in parsed[Path("terraform/main.tf")]["module"]
        if "cloudflare" in module
    )
    expressions = [
        "issensitive(var." + name + ")"
        for name in [
            "cloudflare_api_token",
            "cloudflare_zone_id",
            "tailscale_client_id",
            "tailscale_client_secret",
        ]
    ]
    expressions.append(
        "issensitive(" + assignment.removeprefix("${").removesuffix("}") + ")"
    )
    (tmp_path / "fixture.auto.tfvars").write_text(
        "\n".join(
            name + ' = "synthetic-' + name + '"'
            for name in [
                "cloudflare_api_token",
                "cloudflare_zone_id",
                "tailscale_client_id",
                "tailscale_client_secret",
            ]
        )
    )
    result = subprocess.run(
        ["tofu", "console", "-no-color"],
        cwd=tmp_path,
        env=environment(tmp_path),
        input="jsonencode([" + ",".join(expressions) + "])\n",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(json.loads(result.stdout)) == [True, False, True, True, True]
    wiring = [
        ("provider", "cloudflare", "api_token", "cloudflare_api_token"),
        ("module", "cloudflare", "zone_id", "cloudflare_zone_id"),
        ("provider", "tailscale", "oauth_client_secret", "tailscale_client_secret"),
    ]
    declarations = []
    expected = []
    for kind, name, attribute, variable in wiring:
        found = [
            block[name][attribute]
            for document in parsed.values()
            for block in document.get(kind, [])
            if name in block and attribute in block[name]
        ]
        assert len(found) == 1, f"unambiguous native {name}.{attribute} wiring"
        declarations.append(
            "wired_" + attribute + " = " + found[0].removeprefix("${").removesuffix("}")
        )
        expected.append("synthetic-" + variable)
    (tmp_path / "wiring.tf").write_text(
        "locals {\n" + "\n".join(declarations) + "\n}\n"
    )
    result = subprocess.run(
        ["tofu", "console", "-no-color"],
        cwd=tmp_path,
        env=environment(tmp_path),
        input="nonsensitive(jsonencode(["
        + ",".join("local.wired_" + item[2] for item in wiring)
        + "]))\n",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(json.loads(result.stdout)) == expected


@pytest.mark.parametrize("entry", ["plan", "apply"])
@pytest.mark.parametrize("missing", CREDENTIALS)
def test_missing_credentials_prevent_tofu_invocation(tmp_path, entry, missing):
    marker = tmp_path / "contact"
    binary = executable(
        tmp_path,
        "tofu",
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise SystemExit(93)\n",
    )
    result = run_role(
        tmp_path,
        "tofu",
        entry,
        {
            **{
                name: "" if name == missing else "synthetic-" + name
                for name in CREDENTIALS
            },
            "tofu_binary_path": str(binary),
            "tofu_project_path": str(tmp_path),
        },
    )
    assert result.returncode != 0
    assert not marker.exists()


@pytest.mark.parametrize("check", [False, True])
def test_cleanup_preserves_sources_and_nested_artifacts(tmp_path, check):
    generated = [
        "saved.tfplan",
        "terraform.tfstate",
        "terraform.tfstate.backup",
        ".bw-provider-state",
        ".terraform/provider-cache",
    ]
    preserved = [
        ".terraform.lock.hcl",
        "main.tf",
        "local.tfvars",
        "notes.txt",
        "nested/saved.tfplan",
        "nested/terraform.tfstate",
    ]
    for name in generated + preserved:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("fixture")
    result = run_role(
        tmp_path, "tofu", "clean", {"tofu_project_path": str(tmp_path)}, check=check
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for name in generated + preserved:
        assert (tmp_path / name).exists() == (check or name in preserved), name


@pytest.mark.parametrize(
    "entry,failure", [("plan", False), ("apply", False), ("apply", True)]
)
def test_native_tofu_receives_scoped_inputs_and_redacts_output(
    tmp_path, entry, failure
):
    variables = {name: "SYNTHETIC_PRIVATE_" + name for name in CREDENTIALS}
    executable(
        tmp_path,
        "tofu",
        """import json,os,pathlib,sys
args=sys.argv[1:]
assert args[0] in ['version','workspace','init','validate','plan','show','apply','output'],args
base=pathlib.Path(__file__).parent
with (base/'tofu-events.jsonl').open('a') as f:f.write(json.dumps({'args':args,'env':{k:v for k,v in os.environ.items() if k.startswith(('AWS_','TF_VAR_','BWS_','BW_'))}})+'\\n')
if args[0]=='version':print(json.dumps({'terraform_version':'1.13.0'}))
elif args[0]=='workspace':print('* default')
elif args[0]=='show':print(json.dumps({'resource_changes':[]}))
elif args[0]=='plan':
 for arg in args:
  if arg.startswith('-out='):pathlib.Path(arg.split('=',1)[1]).touch()
 print('SYNTHETIC_PRIVATE_DIAGNOSTIC');sys.exit(2)
elif args[0]=='output':print('{}')
elif args[0]=='apply':
 print('SYNTHETIC_PRIVATE_DIAGNOSTIC');sys.exit(int(os.environ.get('TOFU_FAIL','0')))
""",
    )
    result = run_role(
        tmp_path,
        "tofu",
        entry,
        {
            **variables,
            "tofu_project_path": str(tmp_path),
            "tofu_binary_path": str(tmp_path / "tofu"),
        },
        env={"TOFU_FAIL": str(int(failure))},
    )
    assert (result.returncode == 0) == (not failure), result.stdout + result.stderr
    events = [
        json.loads(line)
        for line in (tmp_path / "tofu-events.jsonl").read_text().splitlines()
    ]
    expected = dict(
        zip(
            [
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "TF_VAR_cloudflare_api_token",
                "TF_VAR_cloudflare_zone_id",
                "TF_VAR_tailscale_client_id",
                "TF_VAR_tailscale_client_secret",
            ],
            variables.values(),
        )
    )
    assert events and all(event["env"] == expected for event in events)
    assert any(event["args"][0] == "plan" for event in events)
    assert any(event["args"][0] == "apply" for event in events) == (entry == "apply")
    assert "SYNTHETIC_PRIVATE" not in result.stdout + result.stderr
