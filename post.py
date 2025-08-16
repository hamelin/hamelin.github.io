# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "bs4",
#     "mistune",
#     "pygments",
# ]
# ///

from bs4 import BeautifulSoup
from bs4.formatter import HTMLFormatter
from collections import defaultdict
from copy import copy
import datetime as dt
from http.server import HTTPServer, SimpleHTTPRequestHandler
import mistune
from pathlib import Path
from pygments import highlight
from pygments.formatters import html
from pygments.lexers import get_lexer_by_name
import re
import sys
from typing import Optional


PATH_BACKUP = Path("backup.md")


def get_backup() -> Optional[Path]:
    if PATH_BACKUP.is_file():
        return PATH_BACKUP
    return None


class HighlightingRenderer(mistune.HTMLRenderer):

    def block_code(self, code, info=None):
        if info:
            lexer = get_lexer_by_name(info, stripall=True)
            return highlight(code, lexer, html.HtmlFormatter())
        return f"<pre><code>{mistune.escape(code)}</code></pre>"


md2html = mistune.create_markdown(renderer=HighlightingRenderer())

    
def get_code_markdown() -> str:
    if len(sys.argv) > 1:
        path_markdown = Path(sys.argv[1])
        print(f"=== Taking Markdown code from file {path_markdown} ===")
        code = path_markdown.read_text(encoding="utf-8")
    elif (path_backup := get_backup()):
        code = path_backup.read_text(encoding="utf-8")
    else:
        print("=== Paste Markdown code of post in standard input, then type Ctrl+D to end it ===")
        code = sys.stdin.read()
    code = code.strip()
    if not code:
        print("No Markdown code given. No post.", file=sys.stderr)
        sys.exit(0)
    return code


def parse_date(markdown) -> tuple[dt.date, str]:
    if m := re.match(
        r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})",
        markdown.strip()
    ):
        date = dt.date(*[int(m.group(n)) for n in ["year", "month", "day"]])
        markdown = markdown[m.end():].strip()
    else:
        print("Can't parse post date, will use today's.", file=sys.stderr)
        date = dt.date.today()
    return date, markdown
    

WEEKDAYS = {
    "fr": "lundi mardi mercredi jeudi vendredi samedi dimanche".split(),
    "en": "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split(),
}
MONTHS = {
    "fr": """
        janvier février mars avril mai juin
        juillet août septembre octobre novembre décembre
    """.split(),
    "en": """
        January February March April May June
        July August September October November December
    """.split(),
}


def format_date_fr(date: dt.date) -> str:
    return (
        f"{WEEKDAYS['fr'][date.weekday()].capitalize()}, "
        f"{date.day} {MONTHS['fr'][date.month - 1]} {date.year}"
    )


def format_date_en(date: dt.date) -> str:
    return (
        f"{WEEKDAYS['en'][date.weekday()]}, "
        f"{MONTHS['en'][date.month - 1]} {date.day}, {date.year}"
    )


FORMAT_DATE = defaultdict(
    lambda: lambda date: "",
    {
        "fr": format_date_fr,
        "en": format_date_en,
    }
)


class Post:

    def __init__(self, markdown) -> None:
        self.date, markdown = parse_date(markdown)
        self._soups = dict(
            zip(
                ["fr", "en", "suffix"], 
                [
                    BeautifulSoup(md2html(text), features="html.parser")
                    for text in (markdown.split("---\n") + ["", ""])[:3]
                ],
            )
        )

    def get_id(self) -> str:
        soup_en = self._soups["en"]
        ts = self.date.strftime("%Y%m%d")
        title_sanitized = re.sub(
            r"[^a-z0-9]",
            " ",
            (soup_en.h1 or soup_en.h2).get_text().lower()
        )
        return "-".join([ts, *[w for w in title_sanitized.split() if w]])

    def part(self, part: str) -> BeautifulSoup:
        if part not in self._soups:
            return BeautifulSoup("", features="html.parser")
        soup = copy(self._soups[part])
        if heading := (soup.h1 or soup.h2):
            link = soup.new_tag("a")
            link["class"] = "selflink"
            link["href"] = f"#{self.get_id()}"
            link.append("Λ")
            heading.append(link)
            title = heading.wrap(soup.new_tag("div"))
            title["class"] = "post-meta"
            div_date = title.append(soup.new_tag("div"))
            div_date.append(FORMAT_DATE[part](self.date))
        return soup

    def assemble(self) -> BeautifulSoup:
        parts = BeautifulSoup('<div class="polyglot"></div>', features="html.parser")
        for lang, class_ in [("fr", "fr"), ("en", "en noshow")]:
            part = self.part(lang)
            div_part = part.new_tag("div")
            div_part["class"] = class_
            div_part.append(part)
            parts.append(div_part)
        if str(suffix := self.part("suffix")):
            parts.append(suffix)
        post_full = BeautifulSoup(
            f'<article><a id="{self.get_id()}"></a></article>',
            features="html.parser"
        )
        post_full.article.append(parts)
        return post_full


def insert_post(post: BeautifulSoup) -> None:
    path_index = Path("index.html")
    index = BeautifulSoup(
        path_index.read_text(encoding="utf-8"),
        features="html.parser"        
    )
    index.main.insert(0, post)
    path_index.write_text(
        index.prettify(formatter=HTMLFormatter(indent=4)),
        encoding="utf-8",
    )


def serve_forever() -> None:
    httpd = HTTPServer(("", 0), SimpleHTTPRequestHandler)
    print()
    print(f"=== Post added. Check it out at http://{httpd.server_address[0]}:{httpd.server_address[1]}/ ===")
    try:
        print("(Ctrl+C to end service)")
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)

def main() -> None:
    try:
        markdown = get_code_markdown()
        PATH_BACKUP.write_text(markdown + "\n", encoding="utf-8")
        try:
            soup = Post(markdown).assemble()
            insert_post(soup)
            PATH_BACKUP.unlink(missing_ok=True)
        except Exception as err:
            err.add_note("=== Markdown code is backed up in backup.md. Run again without argument to resume. ===")
            raise
    except KeyboardInterrupt:
        print("Interrupt. No post.", file=sys.stderr)
        sys.exit(1)
    serve_forever()


if __name__ == "__main__":
    main()
