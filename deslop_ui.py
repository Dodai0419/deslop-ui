#!/usr/bin/env python3
"""deslop-ui: find the AI look and the launch blockers in a built site, straight from disk.

  python deslop_ui.py <build-dir | file.html> [--json] [--only slop|audit]
  python deslop_ui.py demo          # scans the two vibecoded pages in examples/

Two passes over every .html file (and the .css it links or contains):
  slop   the signs of a vibecoded UI that can be found mechanically: purple gradients, gradient text, glows,
         heavy headings, shouty labels, emoji icons, sparkles, arbitrary Tailwind values, hype copy, greeting
         headlines, unsourced social proof. Signs and fixes after heydamir/unslop (CC BY 4.0).
  audit  the static launch audit of juliobsz/skills jury/audit.mjs (MIT), ported check for check: lang, title,
         description, canonical, Open Graph, viewport, favicon, one h1, heading order, main landmark, alt text,
         image sizes, accessible names, noopener, clickable divs, dashes, placeholders, AI-copy tells,
         repeated sentences, doubled headings, thin pages, 404 page, robots.txt, sitemap, og:image, page weight.
No server, no crawl, no browser: files are read once. Exit 1 if any FAIL.
"""
import gzip
import json
import re
import sys
from pathlib import Path

# ---------- jury/audit.mjs helpers, ported ----------
ATTR = re.compile(r"""\s([^\s"'>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?""")
TAG_BODY = r"""(?:"[^"]*"|'[^']*'|[^'">])*"""


def strip(html):
    html = re.sub(r"(?is)<script.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?</style>", " ", html)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;|&#160;", " ", html).replace("&amp;", "&")
    html = re.sub(r"&#x27;|&#39;|&rsquo;", "'", html)
    return re.sub(r"\s+", " ", html)


def attrs(tag):
    out = {}
    for m in ATTR.finditer(re.sub(r"^<[^\s>]+", "", tag)):
        k = m.group(1).lower()
        if k not in out:
            out[k] = next((g for g in m.groups()[1:] if g is not None), "")
    return out


def attr(tag, name):
    return attrs(tag).get(name)


def tags(html, name):
    return re.findall(rf"(?i)<{name}\b{TAG_BODY}>", html)


def rels(tag):
    return (attr(tag, "rel") or "").lower().split()


def meta(html, key):
    for t in tags(html, "meta"):
        if any((v or "").lower() == key for v in (attr(t, "name"), attr(t, "property"))):
            return attr(t, "content")
    return None


PLACEHOLDERS = [r"(?i)lorem ipsum", r"\bName Surname\b", r"example\.com", r"(?i)Replace with", r"\bTODO\b", r"\bAcme\b",
                r"(?i)\bJohn Doe\b", r"(?i)\bJane Doe\b", r"(?i)One plain sentence about"]
TELLS = [
    (r"(?i)\b(elevate|seamless(ly)?|unleash|revolutioni[sz]e|cutting-edge|next-gen|synergy|game-chang)", "filler marketing verb"),
    (r"(?i)\b(crafting digital experiences|pixel[- ]perfect|passionate about)\b", "portfolio cliche"),
    (r"(?i)scroll to explore", "generic scroll cue copy"),
    (r"(?i)\bwhere\s+(?:[^\s.!?]+\s+){1,3}meets?\s+[^\s.!?,;:]+", "portfolio cliche"),
    (r"(?i)\b(?:not|\w+n['’]t)\s+just\b[^.!?]{1,80}?\bbut\b", "portfolio cliche"),
]


def audit_page(html, where, add):
    """Page checks of jury/audit.mjs, in its order and with its levels and messages."""
    head = (re.search(r"(?is)<head.*?</head>", html) or [""])[0]
    nohead = re.sub(r"(?is)<head.*?</head>", "", html, count=1)
    text = strip(nohead)
    if not (attr((tags(html, "html") or [""])[0], "lang") or "").strip():
        add("FAIL", where, "<html> has no lang")
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    title = m.group(1).strip() if m else ""
    if not title:
        add("FAIL", where, "missing <title>")
    elif len(title) > 70:
        add("WARN", where, f"title is {len(title)} chars (keep <= 70)")
    desc = meta(html, "description")
    if not desc:
        add("FAIL", where, "missing meta description")
    elif len(desc) < 50 or len(desc) > 170:
        add("WARN", where, f"meta description is {len(desc)} chars (aim 50-160)")
    links = tags(html, "link")
    if not any("canonical" in rels(t) for t in links):
        add("WARN", where, "no canonical link")
    for k in ("og:title", "og:description", "og:image", "twitter:card"):
        if not meta(html, k):
            add("WARN", where, f"missing {k}")
    if not any((attr(t, "name") or "").lower() == "viewport" for t in tags(html, "meta")):
        add("FAIL", where, "missing viewport meta")
    if not any("icon" in rels(t) for t in links):
        add("WARN", where, "no favicon link")
    h1s = re.findall(r"(?i)<h1[\s>]", html)
    if len(h1s) != 1:
        add("FAIL", where, f"{len(h1s)} <h1> elements (want exactly 1)")
    levels = [int(x) for x in re.findall(r"(?i)<h([1-6])[\s>]", html)]
    for a, b in zip(levels, levels[1:]):
        if b > a + 1:
            add("WARN", where, f"heading level skips h{a} -> h{b}")
            break
    if not re.search(r"(?i)<main[\s>]", html):
        add("FAIL", where, "no <main> landmark")
    for tag in tags(html, "img"):
        src = attr(tag, "src") or ""
        if attr(tag, "alt") is None:
            add("FAIL", where, f"img without alt: {src[:60]}")
        if not attr(tag, "width") and not re.search(r"\bfill\b|position:\s*absolute", tag):
            add("WARN", where, f"img without width/height (layout shift): {src[:60]}")
    for m in re.finditer(rf"(?is)<a\b({TAG_BODY})>(.*?)</a>", html):
        a = f"<a {m.group(1)}>"
        if (not strip(m.group(2)).strip() and attr(a, "aria-label") is None
                and not any((attr(t, "alt") or "").strip() for t in tags(m.group(2), "img"))):
            add("FAIL", where, f"link with no accessible name: {attr(a, 'href')}")
        if (attr(a, "target") or "").lower() == "_blank" and "noopener" not in rels(a):
            add("WARN", where, "target=_blank without rel=noopener")
    for m in re.finditer(rf"(?is)<button\b({TAG_BODY})>(.*?)</button>", html):
        if not strip(m.group(2)).strip() and attr(f"<button {m.group(1)}>", "aria-label") is None:
            add("FAIL", where, "button with no accessible name")
    if re.search(r"(?i)<div[^>]+onclick=", html):
        add("FAIL", where, "clickable <div> (use <button> or <a>)")
    dashes = len(re.findall("[—–]", text))
    if dashes:
        add("WARN", where, f"{dashes} em/en dash(es) in visible text (read as AI tell; rewrite)")
    for p in PLACEHOLDERS:
        if re.search(p, text) or re.search(p, head):
            add("FAIL", where, f"placeholder content: /{p.replace('(?i)', '')}/")
    for p, why in TELLS:
        m = re.search(p, text)
        if m:
            add("WARN", where, f'{why}: "{m.group(0)}"')
    body = re.sub(r"(?is)<script.*?</script>", "", nohead)
    sentences = [s.strip() for m in re.finditer(r"(?is)<(p|h[1-6]|li|blockquote|figcaption|dd)\b[^>]*>(.*?)</\1>", body)
                 for s in re.split(r"(?<=[.!?])\s+", strip(m.group(2)))]
    counts = {}
    for s in (s for s in sentences if len(s.split(" ")) >= 6):
        counts[s] = counts.get(s, 0) + 1
    for s, n in counts.items():
        if n > 1:
            add("WARN", where, f'sentence repeated {n}x: "{s[:70]}"')
    for m in re.finditer(r"(?is)<h([1-3])[^>]*>(.*?)</h\1>", html):
        t = [w for w in strip(m.group(2)).strip().split(" ") if w]
        h = len(t) // 2
        if len(t) >= 2 and len(t) % 2 == 0 and " ".join(t[:h]).lower() == " ".join(t[h:]).lower():
            add("FAIL", where, f'<h{m.group(1)}> text is duplicated ("{" ".join(t)}"): move decorative copies out of the heading')
    words = len([w for w in text.split(" ") if w])
    if words < 60:
        add("WARN", where, f"only {words} words of visible text (thin content)")


def audit_site(root, pages, add):
    """Site checks of audit.mjs, answered from the build folder instead of HTTP."""
    if not root.is_dir():
        return
    nf = next((p for p in (root / "404.html", root / "404" / "index.html") if p.exists()), None)
    if not nf:
        add("FAIL", "site", "no 404.html in the build (a missing URL will not return a designed 404)")
    elif not re.search(r"(?i)<h1[\s>]", nf.read_text(encoding="utf-8", errors="replace")):
        add("WARN", "site", "404 page has no <h1> (design it: a way back, in the site voice)")
    robots = root / "robots.txt"
    rtext = robots.read_text(encoding="utf-8", errors="replace") if robots.exists() else ""
    if not robots.exists():
        add("WARN", "site", "no robots.txt")
    elif "example.com" in rtext:
        add("WARN", "site", "robots.txt still points at example.com")
    maps = [re.sub(r"^https?://[^/]+", "", m) for m in re.findall(r"(?im)^sitemap:\s*(\S+)", rtext)]
    if not any((root / m.lstrip("/")).exists() for m in maps + ["sitemap.xml", "sitemap-index.xml"]):
        add("WARN", "site", "no sitemap")
    for og in sorted({meta(h, "og:image") for h in pages.values()} - {None}):
        local = root / re.sub(r"^https?://[^/]+", "", og).lstrip("/")   # a production URL mapped onto the build
        if not local.exists():
            add("FAIL", "site", f"og:image {og} is not in the build (create a 1200x630 image)")


def weight(root, f, html, add, where):
    def size(p):
        if not p.exists():
            return 0
        b = p.read_bytes()
        return len(gzip.compress(b, 9, mtime=0)) if p.suffix.lower() in (".js", ".mjs", ".css", ".html", ".json", ".svg") else len(b)

    def local(u):
        if not u or re.match(r"^(https?:)?//|^data:", u):
            return None
        u = u.split("?")[0].split("#")[0]
        return (root / u.lstrip("/")) if u.startswith("/") else (f.parent / u)

    kb = lambda b: round(b / 1024)
    js = {p for p in (local(attr(t, "src")) for t in tags(html, "script")) if p}
    css = {p for p in (local(attr(t, "href")) for t in tags(html, "link") if "stylesheet" in rels(t)) if p}
    t = {"html": size(f), "js": sum(map(size, js)), "css": sum(map(size, css)), "fonts": 0, "img": 0}
    fonts = set()
    for c in css:
        if c.exists():
            for face in re.findall(r"@font-face\s*{[^}]+}", c.read_text(encoding="utf-8", errors="replace")):
                rng = re.search(r"unicode-range:\s*([^;}]+)", face)
                if rng and not re.search(r"(?i)U\+0000|U\+0020|U\+00?20-", rng.group(1)):
                    continue
                u = re.search(r"""url\(["']?([^"')]+\.(?:woff2?|ttf|otf))""", face)
                if u:
                    fonts.add(c.parent / u.group(1))
    for p in fonts:
        t["fonts"] += size(p)
        if p.suffix.lower() in (".ttf", ".otf"):
            add("WARN", where, f"ttf/otf font shipped: {p.name} (use woff2)")
    for tag in tags(html, "img"):
        p = local(attr(tag, "src"))
        s = size(p) if p else 0
        t["img"] += s
        if s > 500 * 1024:
            add("WARN", where, f"image {kb(s)} KB: {attr(tag, 'src')[:70]} (compress, AVIF/WebP, smaller variant)")
    total = sum(t.values())
    if kb(t["js"]) > 300:
        add("WARN", where, f"JS {kb(t['js'])} KB gzipped (aim < 300 KB; lazy-load heavy libraries)")
    if kb(t["fonts"]) > 300:
        add("WARN", where, f"fonts {kb(t['fonts'])} KB (fewer weights, variable font, subset)")
    if kb(total) > 3000:
        add("WARN", where, f"page weight ~{kb(total)} KB (aim < 3 MB)")
    return total


# ---------- unslop signs that a regex can see ----------
EMOJI = "[\U0001F300-\U0001FAFF☀-➿⭐⬆↔-↪]"
SLOP = [
    # (pattern, where to look: "src" = raw HTML/CSS, "text" = visible text, sign, fix)
    (r"(?i)(?:from|via)-(?:purple|violet|fuchsia|indigo)-\d+[^\"'>]*?to-(?:blue|pink|indigo|purple|violet|fuchsia|cyan)-\d+"
     r"|linear-gradient\([^)]*(?:#(?:7c3aed|8b5cf6|a855f7|6366f1|9333ea|c026d3|ec4899|d946ef)|purple|violet)[^)]*\)",
     "src", "purple/violet gradient", "one neutral surface, accent only where it means something"),
    (r"(?i)bg-clip-text|background-clip:\s*text", "src", "gradient text", "solid primary text color"),
    (r"(?i)shadow-\[0_0_\d+px_rgba|drop-shadow-\[0_0|box-shadow:\s*0\s+0\s+\d+px\s+(?:rgba?\((?!0,\s*0,\s*0)|#(?!000))",
     "src", "colored glow", "remove; depth from surface steps and hairlines"),
    (r"(?i)blur-3xl|filter:\s*blur\((?:[4-9]\d|\d{3})px\)", "src", "blurred blob behind content", "remove"),
    (r"(?i)<h[1-3][^>]*class=\"[^\"]*\bfont-(?:extrabold|black)\b|font-weight:\s*(?:800|900)", "src",
     "heading weight 800/900", "400-500, size for hierarchy"),
    (r"class=\"[^\"]*\buppercase\b[^\"]*\btracking-(?:wide|wider|widest|\[)|class=\"[^\"]*\btracking-(?:wide|wider|widest|\[)[^\"]*\buppercase\b"
     r"|class=\"[^\"]*\btracking-(?:wide|wider|widest|\[)[^\"]*\"[^>]*>[^<a-z]*\b[A-Z]{3,}(?:\s+[A-Z]{2,})+\b",
     "src", "uppercase label with wide tracking", "sentence case, normal tracking"),
    (r"(?i)\b(?:m|p|mt|mb|ml|mr|mx|my|pt|pb|pl|pr|px|py|gap|h|w|top|left|right|bottom)-\[\d+px\]", "src",
     "arbitrary Tailwind value", "steps on the 4px scale"),
    (r"(?i)\brounded-full\b[^\"]*\b(?:px-\d|py-\d)", "src", "pill everything", "radius by size"),
    ("✨", "text", "sparkle for AI", "remove, or a plain icon where it explains something"),
    (rf"<(?:a|button|li|h[1-6]|span)[^>]*>\s*{EMOJI}", "src", "emoji as icon or label", "one line icon set, or nothing"),
    (r"(?i)\bwelcome back\b[^.!?]{0,30}[.!?]?", "text", "greeting headline", "the page or period as the title"),
    (r"(?i)\b(?:supercharge|seamless(?:ly)?|unlock|magic(?:al)?|revolutioni[sz]e|effortless(?:ly)?|10x)\b", "text",
     "hype word", "say what the thing actually does"),
    (r"!!|\w!(?=\s*<)", "src", "exclamation mark in UI copy", "plain statement"),
    (r"(?i)(?:trusted|loved|used) by\s+[\d,.]+\s*[kKmM+]*\s*\+?\s*(?:teams|users|companies|developers|people|customers)",
     "text", "unsourced social proof", "make it specific and sourced, or remove"),
    (r"(?i)\bintroducing\b[^<]{0,30}\d+\.\d", "text", "pill badge above the headline", "remove, or a quiet text link if it is real news"),
    (r"(?i)placeholder=\"(?:search anything|type anything|ask me anything)[^\"]*\"", "src", "wordy placeholder", "Search"),
    (r"\$1(?:23|,234),?4?56|\[X\]", "text", "fake-looking data", "plausible numbers"),
]


def slop_scan(src, where, add):
    lines = src.splitlines()
    text = strip(src)
    for pat, scope, sign, fix in SLOP:
        if scope == "text":
            hits = [m.group(0) for m in re.finditer(pat, text)]
            if hits:
                add("WARN", where, f'slop: {sign} x{len(hits)} ("{hits[0].strip()[:40]}") -> {fix}')
            continue
        rx = re.compile(pat)
        rows = [i + 1 for i, l in enumerate(lines) if rx.search(l)]
        if rows:
            first = rx.search(lines[rows[0] - 1]).group(0).strip()
            add("WARN", where, f'slop: {sign} x{len(rows)}, line {rows[0]} ("{first[:40]}") -> {fix}')


def scan(target, only=None):
    root = Path(target)
    # the 404 page is checked by audit_site, as audit.mjs checks it apart from the crawled pages
    files = sorted(f for f in root.rglob("*.html") if f.relative_to(root).as_posix() not in ("404.html", "404/index.html"))         if root.is_dir() else [root]
    base = root if root.is_dir() else root.parent
    results, pages = [], {}
    add = lambda level, where, msg: results.append({"level": level, "where": where, "msg": msg})
    for f in files:
        html = f.read_text(encoding="utf-8", errors="replace")
        where = "/" + f.relative_to(base).as_posix()
        pages[where] = html
        if only != "slop":
            audit_page(html, where, add)
            weight(base, f, html, add, where)
        if only != "audit":
            css = "".join(p.read_text(encoding="utf-8", errors="replace") for p in
                          ((base / h.lstrip("/")) if h.startswith("/") else f.parent / h
                           for h in (attr(t, "href") or "" for t in tags(html, "link") if "stylesheet" in rels(t))
                           if h and not re.match(r"^(https?:)?//", h)) if p.exists())
            slop_scan(html + "\n" + css, where, add)
    if only != "slop" and root.is_dir():
        audit_site(root, pages, add)
    results.sort(key=lambda r: r["level"] != "FAIL")
    return files, results


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")   # emoji in findings must not crash a cp949/cp1252 console
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    demo = argv[0] == "demo"
    if demo:
        argv = [str(Path(__file__).resolve().parent / "examples")] + argv[1:]
    target, as_json = argv[0], "--json" in argv
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    if not Path(target).exists():
        print(f"deslop-ui: no such file or folder: {target}", file=sys.stderr)
        return 2
    files, results = scan(target, only)
    fails = sum(r["level"] == "FAIL" for r in results)
    slop = sum(r["msg"].startswith("slop:") for r in results)
    if as_json:
        print(json.dumps({"pages": len(files), "fail": fails, "warn": len(results) - fails, "results": results}, indent=1))
    else:
        for r in results:
            print(f"{r['level']:<4}  {r['where']:<24}  {r['msg']}")
        print(f"\n{len(files)} pages scanned in {target}")
        print(f"{fails} FAIL, {len(results) - fails} WARN ({slop} slop signs)")
    if demo:
        print("(demo: these are unslop's two vibecoded example pages; on your own build the exit code would be "
              f"{1 if fails else 0})")
        return 0
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
