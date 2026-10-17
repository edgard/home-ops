import pytest

from tests.support.wiki import wiki_errors

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
        ("purpose", "missing purpose"),
        ("related", "missing related pages"),
        ("root-link", "broken local link"),
        ("escape", "broken local link"),
        ("symlink", "broken local link"),
        ("no-index", "missing wiki index"),
        ("encoded-link", ""),
    ],
)
def test_wiki_contracts(tmp_path, scenario, reason):
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
                "## Sources\n\n- [Values](../../../../apps/media/demo/values.yaml)\n\n",
                "",
            )
        )
    if scenario == "revision":
        page.write_text(PAGE.replace("a" * 40, "unknown"))
    if scenario == "missing":
        page.unlink()
    if scenario == "extra":
        page.with_name("unused.md").write_text(PAGE)
    if scenario == "purpose":
        page.write_text(PAGE.replace("Purpose: example.", ""))
    if scenario == "related":
        page.write_text(PAGE.replace("## Related pages", ""))
    if scenario == "root-link":
        (root / "README.md").write_text("[Missing](missing.md)")
    if scenario in {"escape", "symlink"}:
        outside = tmp_path / "outside.md"
        outside.write_text("# External")
        target = "../outside.md"
        if scenario == "symlink":
            (root / "escape.md").symlink_to(outside)
            target = "escape.md"
        (root / "README.md").write_text(f"[Escaped]({target})")
    if scenario == "no-index":
        index.unlink()
    if scenario == "encoded-link":
        (root / "README.md").write_text(
            "[Wiki](docs/%77iki/index.md?query=yes#anchor)\n[Web](https://example.invalid)\n[Anchor](#local)\n![Image](absent.png)"
        )
    errors = wiki_errors(root)
    assert bool(errors) == (scenario not in {"valid", "encoded-link"}), errors
    if reason:
        assert any(reason in error for error in errors), errors


def test_repository_wiki(repo_root):
    assert not (errors := wiki_errors(repo_root)), "\n".join(errors)
