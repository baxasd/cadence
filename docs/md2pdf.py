#!/usr/bin/env python3
"""Render a Markdown file (with local SVG figures) to PDF via headless Chrome.

Usage:  python3 md2pdf.py setup-guide.md
Output: setup-guide.pdf  (next to the source)

Needs: pip install markdown  +  Google Chrome on PATH.
Run from the docs/ folder so the figures/ paths resolve.
"""
import sys, subprocess, tempfile, pathlib, markdown

src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "setup-guide.md").resolve()
body = markdown.markdown(
    src.read_text(encoding="utf-8"),
    extensions=["tables", "fenced_code", "sane_lists"],
)

# A4, comfortable margins, printable colours, figures never overflow the page.
html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
  @page {{ size: A4; margin: 20mm 18mm; }}
  * {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  body {{ font-family: Georgia, 'Times New Roman', serif; font-size: 11pt;
         line-height: 1.5; color: #14130f; max-width: 100%; }}
  h1,h2,h3 {{ font-family: Helvetica, Arial, sans-serif; line-height: 1.25; }}
  h1 {{ font-size: 22pt; }} h2 {{ font-size: 15pt; margin-top: 1.6em; }}
  h3 {{ font-size: 12pt; }}
  img {{ max-width: 100%; height: auto; display: block; margin: 0.4em auto; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; page-break-inside: avoid; }}
  th,td {{ border: 1px solid #ccc; padding: 8px 10px; text-align: left; vertical-align: top; }}
  th {{ background: #f4f2ee; }}
  blockquote {{ border-left: 3px solid #d24e2b; margin: 1em 0; padding: 0.2em 1em;
               background: #faf8f4; }}
  code {{ font-family: ui-monospace, Consolas, monospace; font-size: 0.9em; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 1.6em 0; }}
  a {{ color: #1f6f8f; }}
</style></head><body>{body}</body></html>"""

tmp = src.with_suffix(".rendered.html")
tmp.write_text(html, encoding="utf-8")
out = src.with_suffix(".pdf")
subprocess.run([
    "google-chrome", "--headless", "--no-sandbox", "--disable-gpu",
    "--no-pdf-header-footer", f"--print-to-pdf={out}",
    tmp.as_uri(),
], check=True)
tmp.unlink()
print(f"wrote {out}")
