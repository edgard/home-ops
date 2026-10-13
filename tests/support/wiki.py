"""Check the wiki against repository sources and local links."""

from collections import Counter
from pathlib import Path
import re
from urllib.parse import unquote


def local_links(text, directory):
    for link in re.findall(r"(?<!\!)\[[^\]]+\]\(([^)]+)\)", text):
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^#", link):
            continue
        target = unquote(link).split("#", 1)[0].split("?", 1)[0]
        yield link, (directory / target).resolve()


def wiki_errors(root):
    root = Path(root).resolve()
    wiki = root / "docs/wiki"
    pages = set(wiki.rglob("*.md"))
    app_pages = set((wiki / "apps").glob("*/*.md"))
    expected = {
        wiki / "apps" / path.parent.parent.name / (path.parent.name + ".md")
        for path in (root / "apps").glob("*/*/app.yaml")
    }
    errors = [f"missing app page: {page}" for page in sorted(expected - app_pages)]
    errors += [
        f"app page without app metadata: {page}" for page in sorted(app_pages - expected)
    ]
    index = wiki / "index.md"
    if not index.is_file():
        return errors + ["missing wiki index"]
    indexed = [path for _, path in local_links(index.read_text(), wiki)]
    errors += [f"not indexed: {page}" for page in sorted(pages - {index} - set(indexed))]
    if any(
        count > 1
        for path, count in Counter(indexed).items()
        if path.is_relative_to(wiki / "apps")
    ):
        errors.append("duplicate app page in index")
    for page in sorted(pages | {root / "README.md", root / "AGENTS.md"}):
        if not page.is_file():
            errors.append(f"missing root document: {page}")
            continue
        text = page.read_text()
        if page in pages and page.name not in {
            "index.md",
            "log.md",
            "sources.md",
            "AGENTS.md",
        }:
            if not re.search(r"(?m)^Purpose: .+", text):
                errors.append(f"{page}: missing purpose")
            if not re.search(
                r"(?m)^Status: (current|historical)[.] Reviewed against: .*([0-9a-f]{40}).*$",
                text,
            ):
                errors.append(f"{page}: missing status or reviewed commit")
            sources = (
                text.split("## Sources", 1)[1].split("## ", 1)[0]
                if "## Sources" in text
                else ""
            )
            if "[" not in sources or "](" not in sources:
                errors.append(f"{page}: missing source link")
            if "## Related pages" not in text:
                errors.append(f"{page}: missing related pages")
        for link, target in local_links(text, page.parent):
            if not target.exists() or not target.is_relative_to(root):
                errors.append(f"{page}: broken local link: {link}")
    return errors
