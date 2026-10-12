import json
import subprocess

from tests.support.runtime import ROOT
from tests.support.sources import read_json5, read_yaml


def node(source, data):
    result = subprocess.run(
        ["node", "-e", source], input=json.dumps(data), capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_operator_pin_discovery_uses_native_regexes():
    path = "ansible/roles/operator_secrets/defaults/main.yml"
    defaults = read_yaml(ROOT / path)
    found = node(
        """const fs=require('fs');const input=JSON.parse(fs.readFileSync(0,'utf8'));const result=[];
for(const manager of input.managers){
 if(manager.customType!=='regex'||!manager.managerFilePatterns.some(p=>new RegExp(p.slice(1,-1)).test(input.path)))continue;
 for(const pattern of manager.matchStrings)for(const match of input.source.matchAll(new RegExp(pattern,'g'))){const g=match.groups;result.push([g.datasource||manager.datasourceTemplate,g.depName||manager.depNameTemplate,g.currentValue]);}
}console.log(JSON.stringify(result));""",
        {
            "path": path,
            "source": (ROOT / path).read_text(),
            "managers": read_json5(ROOT / ".renovaterc.json5")["customManagers"],
        },
    )
    assert sorted(found) == sorted(
        [
            [
                "github-releases",
                "cachix/secretspec",
                defaults["operator_secrets_secretspec_version"],
            ],
            ["github-releases", "bitwarden/sdk-sm", defaults["operator_secrets_bws_version"]],
        ]
    )


def test_bws_release_filter():
    rules = [
        rule
        for rule in read_json5(ROOT / ".renovaterc.json5")["packageRules"]
        if "github-releases" in rule.get("matchDatasources", [])
        and "bitwarden/sdk-sm" in rule.get("matchPackageNames", [])
    ]
    assert len(rules) == 1
    tags = [
        "bws-v2.1.1",
        "bws-v3.0.0-beta.1",
        "rust-v3.0.0",
        "python-v3.0.0",
        "dotnet-v3.0.0",
        "v3.0.0",
    ]
    matches = node(
        "const fs=require('fs');const i=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(i.tags.map(tag=>new RegExp(i.pattern).exec(tag)?.groups.version||null)));",
        {"pattern": rules[0]["extractVersion"], "tags": tags},
    )
    assert matches == ["2.1.1", "3.0.0-beta.1", None, None, None, None]
