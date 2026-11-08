# deslop-ui

Find the AI look and the launch blockers in your built site, straight from disk: one Python file, no server.

Use this tool when a website or web app UI was built or changed and should not look AI-generated, or before a launch.

## Run

```bash
python deslop_ui.py <build-dir | file.html>            # both passes
python deslop_ui.py <build-dir> --only slop             # just the AI-look signs
python deslop_ui.py <build-dir> --only audit --json     # just the launch audit, machine-readable
```

Point it at the built output (`dist/`, `out/`, `build/`) or a single HTML file. Exit code 1 if any FAIL.

## Act on the result

- `slop:` lines name the sign, the count, the first line where it appears and the fix. Fix them in the source: replace purple gradients and glows with one neutral surface, set headings to weight 400-500, drop emoji icons and sparkles, use the 4px spacing scale, rewrite hype words and greeting headlines into what the product does, remove unsourced social proof.
- `FAIL` lines are launch blockers: missing lang, title, description, viewport, h1, main landmark, alt text, accessible names, placeholders, missing 404 page.
- `WARN` lines are worth fixing before launch: Open Graph tags, canonical, favicon, heading order, image sizes, heavy assets.

Re-run until no FAIL remains. Python 3 standard library only.
