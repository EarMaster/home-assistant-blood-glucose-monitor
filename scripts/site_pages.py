"""Create the pages of a site language (site/<language>/*.html).

The pages only set the language and include the shared templates; the texts
are in site/_data/i18n/<language>.json. Usage: python scripts/site_pages.py es
"""

from __future__ import annotations

from pathlib import Path
import sys

SITE = Path(__file__).resolve().parent.parent / "site"
PAGES = {
    "index.html": ("home", "", "home"),
    "builder.html": ("builder", "builder.html", "page"),
    "docs.html": ("docs", "docs.html", "page"),
}


def front_matter(language: str, key: str, ref: str, layout: str) -> str:
    """Return the page file of one language."""
    root = "/" if language == "en" else f"/{language}/"
    lines = [
        "---",
        f"layout: {layout}",
        f"lang: {language}",
        f"key: {key}",
        f'ref: "{ref}"',
        f"permalink: {root}{ref}",
    ]
    if key == "home" and language == "en":
        lines.append("redirect_by_language: true")
    if key == "builder":
        lines += [
            "wide: true",
            "scripts:",
            "  - /assets/js/data.js",
            "  - /assets/js/builder.js",
        ]
    if key == "docs":
        lines += ["scripts:", "  - /assets/js/data.js", "  - /assets/js/docs.js"]
    lines += ["---", f"{{% include pages/{key}.html %}}", ""]
    return "\n".join(lines)


def main() -> int:
    """Write the pages of the languages given as arguments."""
    for language in sys.argv[1:]:
        folder = SITE if language == "en" else SITE / language
        folder.mkdir(exist_ok=True)
        for name, (key, ref, layout) in PAGES.items():
            (folder / name).write_text(
                front_matter(language, key, ref, layout), encoding="utf-8", newline="\n"
            )
        print(f"Wrote pages of {language}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
