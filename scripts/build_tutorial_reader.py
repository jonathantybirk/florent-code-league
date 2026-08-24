"""Build a self-contained HTML reader from the scraped tutorial Markdown."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from markdown_it import MarkdownIt


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "tutorials"
OUTPUT = SOURCE / "index.html"

CHAPTERS = (
    ("movement-sensing", "Movement & Sensing"),
    ("harvesting-titanium", "Harvesting Titanium"),
    ("conveyors-logistics", "Conveyors & Logistics"),
    ("turrets-combat", "Turrets & Combat"),
    ("comms-strategy", "Comms & Strategy"),
)


def title_of(markdown: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def lesson_name(markdown: str, fallback: str) -> str:
    match = re.search(r"^##\s+(.+)$", markdown, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def main() -> None:
    renderer = MarkdownIt("commonmark", {"html": False, "linkify": True})
    tutorials = []
    for chapter_slug, chapter_title in CHAPTERS:
        for path in sorted((SOURCE / chapter_slug).glob("*.md")):
            markdown = path.read_text()
            # The source URL is provenance, not part of the original lesson UI.
            markdown = re.sub(r"^Source: https?://\S+\s*\n", "", markdown, count=1, flags=re.MULTILINE)
            tutorials.append(
                {
                    "id": f"{chapter_slug}/{path.stem}",
                    "chapter": chapter_title,
                    "title": title_of(markdown, path.stem),
                    "name": lesson_name(markdown, path.stem),
                    "body": renderer.render(markdown),
                }
            )

    nav = []
    for chapter_slug, chapter_title in CHAPTERS:
        links = []
        for index, tutorial in enumerate(tutorials):
            if tutorial["chapter"] != chapter_title:
                continue
            links.append(
                f'<button class="lesson-link" data-index="{index}">' 
                f'<span>{len(links) + 1:02}</span>{html.escape(tutorial["name"])}</button>'
            )
        nav.append(f'<section><h2>{html.escape(chapter_title)}</h2>{"".join(links)}</section>')

    data = json.dumps(tutorials).replace("</", "<\\/")
    document = TEMPLATE.replace("{{NAV}}", "".join(nav)).replace("{{DATA}}", data)
    OUTPUT.write_text(document)
    print(f"Built {OUTPUT.relative_to(ROOT)} with {len(tutorials)} lessons")


TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Florent Code League Tutorials</title>
  <style>
    :root { color-scheme: light; --ink:#17201b; --muted:#68736b; --line:#dce3dd; --paper:#fbfcf9; --accent:#147d55; --soft:#eaf4ee; }
    * { box-sizing:border-box; }
    html { scroll-behavior:smooth; }
    body { margin:0; color:var(--ink); background:var(--paper); font:16px/1.65 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    .layout { min-height:100vh; display:grid; grid-template-columns:320px minmax(0,1fr); }
    aside { position:sticky; top:0; height:100vh; overflow:auto; padding:30px 22px; border-right:1px solid var(--line); background:#f3f6f1; }
    .brand { margin:0 0 4px; font-size:18px; letter-spacing:-.02em; }
    .eyebrow { margin:0 0 26px; color:var(--accent); font-size:12px; font-weight:800; letter-spacing:.12em; text-transform:uppercase; }
    aside section { margin:0 0 24px; }
    aside h2 { margin:0 0 8px; color:var(--muted); font-size:11px; letter-spacing:.1em; text-transform:uppercase; }
    .lesson-link { width:100%; display:flex; gap:12px; align-items:flex-start; padding:8px 10px; border:0; border-radius:7px; color:var(--ink); background:transparent; font:inherit; font-size:14px; line-height:1.35; text-align:left; cursor:pointer; }
    .lesson-link span { color:#94a097; font:11px/1.8 ui-monospace,SFMono-Regular,Menlo,monospace; }
    .lesson-link:hover { background:#e7ede8; }
    .lesson-link.active { color:#0b6241; background:#dcece2; font-weight:700; }
    main { width:min(900px,100%); margin:0 auto; padding:70px clamp(28px,6vw,80px) 100px; }
    article h1 { margin:0 0 38px; font-size:clamp(32px,5vw,52px); line-height:1.08; letter-spacing:-.045em; }
    article h2 { margin:46px 0 14px; font-size:25px; line-height:1.25; letter-spacing:-.025em; }
    article h3 { margin-top:36px; }
    article p, article li { max-width:74ch; }
    article a { color:var(--accent); }
    pre { overflow:auto; margin:22px 0; padding:20px 22px; border:1px solid #263a30; border-radius:10px; color:#e7f2eb; background:#18251e; font:14px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace; }
    code { padding:.12em .35em; border-radius:4px; color:#075d3d; background:var(--soft); font:0.9em ui-monospace,SFMono-Regular,Menlo,monospace; }
    pre code { padding:0; color:inherit; background:transparent; }
    blockquote { margin:24px 0; padding:4px 20px; border-left:4px solid var(--accent); color:#445149; background:var(--soft); }
    .pager { display:flex; justify-content:space-between; gap:16px; margin-top:60px; padding-top:28px; border-top:1px solid var(--line); }
    .pager button { padding:10px 15px; border:1px solid var(--line); border-radius:7px; color:var(--ink); background:white; font:inherit; cursor:pointer; }
    .pager button:disabled { visibility:hidden; }
    .menu { display:none; }
    @media (max-width:760px) {
      .layout { display:block; }
      aside { position:fixed; z-index:2; inset:0 15% 0 0; height:auto; transform:translateX(-110%); transition:transform .2s; box-shadow:10px 0 40px #0002; }
      aside.open { transform:translateX(0); }
      .menu { display:block; position:sticky; z-index:1; top:12px; margin:12px 16px 0 auto; padding:8px 12px; border:1px solid var(--line); border-radius:7px; background:white; }
      main { padding-top:35px; }
    }
  </style>
</head>
<body>
  <button class="menu" aria-label="Open tutorial menu">Lessons</button>
  <div class="layout">
    <aside><p class="eyebrow">Offline archive</p><h1 class="brand">Florent Code League</h1><p class="eyebrow">Tutorials</p>{{NAV}}</aside>
    <main><article id="lesson"></article><nav class="pager"><button id="previous">← Previous</button><button id="next">Next →</button></nav></main>
  </div>
  <script>
    const tutorials = {{DATA}};
    const article = document.querySelector('#lesson');
    const links = [...document.querySelectorAll('.lesson-link')];
    const aside = document.querySelector('aside');
    let current = 0;
    function show(index, updateHash = true) {
      current = Math.max(0, Math.min(tutorials.length - 1, index));
      article.innerHTML = tutorials[current].body;
      links.forEach((link, i) => link.classList.toggle('active', i === current));
      document.querySelector('#previous').disabled = current === 0;
      document.querySelector('#next').disabled = current === tutorials.length - 1;
      if (updateHash) history.replaceState(null, '', '#' + tutorials[current].id);
      document.title = tutorials[current].title + ' — FCL Tutorials';
      aside.classList.remove('open');
      window.scrollTo(0, 0);
    }
    links.forEach(link => link.addEventListener('click', () => show(Number(link.dataset.index))));
    document.querySelector('#previous').addEventListener('click', () => show(current - 1));
    document.querySelector('#next').addEventListener('click', () => show(current + 1));
    document.querySelector('.menu').addEventListener('click', () => aside.classList.toggle('open'));
    document.addEventListener('keydown', event => {
      if (event.key === 'ArrowLeft' && current > 0) show(current - 1);
      if (event.key === 'ArrowRight' && current < tutorials.length - 1) show(current + 1);
    });
    const fromHash = tutorials.findIndex(tutorial => tutorial.id === location.hash.slice(1));
    show(fromHash >= 0 ? fromHash : 0, false);
  </script>
</body>
</html>
'''


if __name__ == "__main__":
    main()
