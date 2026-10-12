import pytest

from tests.support.runtime import run_role

PAGE = """# Demo

Purpose: example.
Status: current. Reviewed against: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`.

## Sources

- [Values](../../../../apps/media/demo/values.yaml)

## Related pages

None.
"""
INDEX = "# Index\n\n- [Demo](apps/media/demo.md)\n- [Rules](AGENTS.md)\n- [Sources](sources.md)\n- [Log](log.md)\n"


@pytest.mark.parametrize(
    "scenario,reason",
    [
        ("valid", ""),
        ("broken-link", "broken local link"),
        ("orphan", "not indexed"),
        ("duplicate", "duplicate app page"),
        ("sources", "missing source link"),
        ("revision", "missing status or reviewed commit"),
        ("missing", "missing app page"),
        ("extra", "app page without app metadata"),
    ],
)
def test_wiki_role_contracts(tmp_path, scenario, reason):
    root = tmp_path / "repository with spaces"
    sources = {
        "README.md": "# Demo\n[Wiki](docs/wiki/index.md)\n",
        "AGENTS.md": "# Rules\n[Workflow](docs/wiki/AGENTS.md)\n",
        "apps/media/demo/app.yaml": "---\n",
        "apps/media/demo/values.yaml": "---\n",
        "docs/wiki/index.md": INDEX,
        "docs/wiki/AGENTS.md": "# Rules\n",
        "docs/wiki/sources.md": "# Sources\n",
        "docs/wiki/log.md": "# Log\n",
        "docs/wiki/apps/media/demo.md": PAGE,
    }
    for path, content in sources.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    page, index = root / "docs/wiki/apps/media/demo.md", root / "docs/wiki/index.md"
    if scenario == "broken-link":
        page.write_text(PAGE.replace("values.yaml", "missing.yaml"))
    if scenario == "orphan":
        index.write_text(INDEX.replace("- [Demo](apps/media/demo.md)\n", ""))
    if scenario == "duplicate":
        index.write_text(INDEX + "- [Again](apps/media/demo.md)\n")
    if scenario == "sources":
        page.write_text(
            PAGE.replace(
                "## Sources\n\n- [Values](../../../../apps/media/demo/values.yaml)\n\n", ""
            )
        )
    if scenario == "revision":
        page.write_text(PAGE.replace("a" * 40, "unknown"))
    if scenario == "missing":
        page.unlink()
    if scenario == "extra":
        page.with_name("unused.md").write_text(PAGE)
    result = run_role(tmp_path, "wiki_validation", "main", {"wiki_validation_root": str(root)})
    assert (result.returncode == 0) == (scenario == "valid"), result.stdout + result.stderr
    if reason:
        assert reason in result.stdout + result.stderr
