import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import deslop_ui as d

CLEAN = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ledger: invoices for small studios</title>
<meta name="description" content="Ledger sends invoices, tracks who paid and reminds the rest, for studios of one to ten people.">
<link rel="canonical" href="https://ledger.test/"><link rel="icon" href="/favicon.svg">
<meta property="og:title" content="Ledger"><meta property="og:description" content="Invoices for small studios.">
<meta property="og:image" content="https://ledger.test/og.png"><meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="/site.css"></head>
<body><main><h1>Invoices for small studios</h1>
<p>Ledger sends each invoice on the day you finish the work, tracks which clients have paid and which have not, and sends
one polite reminder a week to the rest. It reads your calendar to know when a project ends.</p>
<h2>How it works</h2><p>Connect a bank account, add a client and the hourly rate, and mark a project done. The first
invoice goes out that evening, and the reminder schedule starts the week after it.</p>
<img src="/shot.png" alt="The invoice list" width="1200" height="800"><a href="/pricing">Pricing</a>
<button>Start a trial</button></main></body></html>"""


def write_site(root, index=CLEAN, extra=True):
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(index, encoding="utf-8")
    (root / "site.css").write_text("body{font-family:system-ui;color:#222}", encoding="utf-8")
    if extra:
        (root / "404.html").write_text("<html lang=en><h1>Not here</h1></html>", encoding="utf-8")
        (root / "robots.txt").write_text("Sitemap: https://ledger.test/sitemap.xml\n", encoding="utf-8")
        (root / "sitemap.xml").write_text("<urlset/>", encoding="utf-8")
        (root / "og.png").write_bytes(b"\x89PNG")
        (root / "shot.png").write_bytes(b"\x89PNG")


def run(html):
    out = []
    d.audit_page(html, "/x", lambda lv, w, m: out.append((lv, m)))
    return out


class CleanSite(unittest.TestCase):
    def test_clean_site_has_no_findings(self):
        with tempfile.TemporaryDirectory() as t:
            write_site(Path(t))
            files, res = d.scan(t)
            self.assertEqual([], res)
            self.assertEqual(0, d.main([t]))


class AuditPortMatchesJury(unittest.TestCase):
    """Each audit.mjs page check, one fixture each, with its level and message."""

    def has(self, html, level, text):
        self.assertTrue(any(lv == level and text in m for lv, m in run(html)), run(html))

    def test_lang_title_description(self):
        self.has("<html><head></head><main><h1>a</h1></main></html>", "FAIL", "<html> has no lang")
        self.has("<html lang=en><main><h1>a</h1></main></html>", "FAIL", "missing <title>")
        self.has(f"<html lang=en><title>{'x' * 71}</title></html>", "WARN", "title is 71 chars")
        self.has("<html lang=en><meta name=description content='short'></html>", "WARN", "meta description is 5 chars")

    def test_unquoted_attributes_parse(self):
        self.assertFalse(any("no lang" in m for _, m in run("<html lang=en><title>t</title></html>")))

    def test_headings_and_landmarks(self):
        self.has("<html lang=en><h1>a</h1><h1>b</h1></html>", "FAIL", "2 <h1> elements")
        self.has("<html lang=en><h1>a</h1><h3>b</h3></html>", "WARN", "heading level skips h1 -> h3")
        self.has("<html lang=en><h1>a</h1></html>", "FAIL", "no <main> landmark")
        self.has("<html lang=en><h1>Studio Studio</h1></html>", "FAIL", "text is duplicated")

    def test_images_links_buttons(self):
        self.has('<img src="a.png">', "FAIL", "img without alt: a.png")
        self.has('<img src="a.png" alt="">', "WARN", "img without width/height")
        self.has('<a href="/x"></a>', "FAIL", "link with no accessible name: /x")
        self.has('<a href="/x" target="_blank">x</a>', "WARN", "target=_blank without rel=noopener")
        self.has("<button></button>", "FAIL", "button with no accessible name")
        self.has('<div class="c" onclick="go()">x</div>', "FAIL", "clickable <div>")
        self.assertFalse(any("accessible name" in m for _, m in run('<a href="/x"><img src="l.svg" alt="Home"></a>')))

    def test_copy_checks(self):
        self.has("<p>Fast — and cheap</p>", "WARN", "1 em/en dash(es)")
        self.has("<p>Lorem ipsum dolor</p>", "FAIL", "placeholder content")
        self.has("<p>We elevate your brand</p>", "WARN", 'filler marketing verb: "elevate"')
        self.has("<p>Where design meets code.</p>", "WARN", "portfolio cliche")
        self.has("<p>It is not just fast but kind.</p>", "WARN", "portfolio cliche")
        s = "This exact sentence has more than six words in it."
        self.has(f"<p>{s}</p><li>{s}</li>", "WARN", "sentence repeated 2x")
        self.has("<p>few words</p>", "WARN", "only 2 words of visible text")


class SiteAndWeight(unittest.TestCase):
    def test_site_level_from_disk(self):
        with tempfile.TemporaryDirectory() as t:
            write_site(Path(t), extra=False)
            msgs = [r["msg"] for r in d.scan(t)[1]]
            for want in ("no 404.html", "no robots.txt", "no sitemap", "og:image https://ledger.test/og.png is not in the build"):
                self.assertTrue(any(want in m for m in msgs), (want, msgs))

    def test_heavy_image_and_ttf(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            write_site(root)
            (root / "shot.png").write_bytes(os.urandom(600 * 1024))
            (root / "site.css").write_text("@font-face{font-family:X;src:url(x.ttf)}", encoding="utf-8")
            (root / "x.ttf").write_bytes(b"0" * 10)
            msgs = [r["msg"] for r in d.scan(t)[1]]
            self.assertTrue(any(m.startswith("image 600 KB") for m in msgs), msgs)
            self.assertTrue(any("ttf/otf font shipped: x.ttf" in m for m in msgs), msgs)


class SlopSigns(unittest.TestCase):
    def test_unslop_examples_show_the_signs(self):
        _, res = d.scan(str(HERE / "examples"), only="slop")
        msgs = " | ".join(r["msg"] for r in res)
        for sign in ("purple/violet gradient", "gradient text", "colored glow", "heading weight 800/900",
                     "uppercase label", "arbitrary Tailwind value", "sparkle for AI", "emoji as icon",
                     "greeting headline", "hype word", "exclamation mark", "unsourced social proof", "pill badge"):
            self.assertIn(sign, msgs)

    def test_clean_page_has_no_slop(self):
        out = []
        d.slop_scan(CLEAN, "/x", lambda *a: out.append(a))
        self.assertEqual([], out)

    def test_cli_exit_codes(self):
        self.assertEqual(0, d.main(["demo"]))
        self.assertEqual(1, d.main([str(HERE / "examples")]))
        self.assertEqual(2, d.main([str(HERE / "no-such-dir")]))


if __name__ == "__main__":
    unittest.main()
