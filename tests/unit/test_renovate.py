import json
import subprocess

from tests.support.runtime import ROOT
from tests.support.sources import read_json5


def node(source, data):
    result = subprocess.run(
        ["node", "-e", source], input=json.dumps(data), capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_operator_pin_discovery_uses_native_regexes():
    path = ".secretspec-version"
    version = (ROOT / path).read_text().strip()
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
    assert found == [["github-releases", "cachix/secretspec", version]]
