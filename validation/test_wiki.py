"""Local links and app-page coverage; prose quality belongs to review."""

import re
from urllib.parse import unquote


def test_wiki_links_and_application_pages(repo_root):
    wiki = repo_root / "docs/wiki"
    assert (wiki / "index.md").is_file(), "missing wiki index"
    expected = {
        wiki / "apps" / app.parent.parent.name / (app.parent.name + ".md")
        for app in (repo_root / "apps").glob("*/*/app.yaml")
    }
    assert expected and expected == set((wiki / "apps").glob("*/*.md")), (
        "wiki app pages must match app definitions"
    )
    for page in [*wiki.rglob("*.md"), repo_root / "README.md", repo_root / "AGENTS.md"]:
        for link in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", page.read_text()):
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^#", link):
                continue
            target = unquote(link).split("#", 1)[0].split("?", 1)[0]
            path = (page.parent / target).resolve()
            assert path.is_relative_to(repo_root) and path.exists(), (
                f"{page.relative_to(repo_root)}: broken local link: {link}"
            )
