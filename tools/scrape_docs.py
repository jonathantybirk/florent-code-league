"""Re-scrape the Florent Code League docs into docs/official/ as plain text.

Format matches the existing files: each block-level element becomes one
paragraph, blocks separated by a blank line, tables flattened cell-by-cell.
"""

import html.parser
import sys
import urllib.request

BLOCKS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "th", "td",
          "blockquote", "div"}
SKIP = {"script", "style"}


class Article(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0          # >0 while inside <article>
        self.stack = []
        self.blocks = []
        self.buf = None
        self.pre = False
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
            return
        if tag == "article" and self.depth == 0:
            self.depth = 1
            self.stack = ["article"]
            return
        if not self.depth:
            return
        self.stack.append(tag)
        if tag in BLOCKS:
            self.flush()
            self.buf = []
            self.pre = tag == "pre"
        elif tag == "br" and self.buf is not None:
            self.buf.append("\n")

    def handle_startendtag(self, tag, attrs):
        if self.depth and tag == "br" and self.buf is not None:
            self.buf.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if not self.depth:
            return
        if tag in BLOCKS:
            self.flush()
        while self.stack:
            top = self.stack.pop()
            if top == tag:
                break
        if tag == "article":
            self.depth = 0
            self.stack = []

    def handle_data(self, data):
        if not self.depth or self.skip:
            return
        if self.buf is None:
            if not data.strip():
                return
            self.buf = []          # loose text between blocks is its own block
        self.buf.append(data)

    def flush(self):
        if self.buf is None:
            return
        text = "".join(self.buf)
        if self.pre:
            text = text.strip("\n")
        else:
            # collapse runs of spaces/tabs but keep newlines the source wrote
            text = "\n".join(" ".join(l.split()) for l in text.split("\n")).strip()
        self.buf = None
        self.pre = False
        if text:
            self.blocks.append(text)


def scrape(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r:
        page = r.read().decode("utf-8")
    p = Article()
    p.feed(page)
    return "\n\n".join(p.blocks) + "\n"


if __name__ == "__main__":
    sys.stdout.write(scrape(sys.argv[1]))
