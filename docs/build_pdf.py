"""
Build the user-facing product manual PDF from 产品手册.md.

  python3 docs/build_pdf.py

Output: frontend/public/manual.pdf (served by nginx as /manual.pdf)
Requires: pip install markdown ; brew install wkhtmltopdf
"""
import os
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
MD_PATH = DOCS / "产品手册.md"
HTML_OUT = DOCS / ".manual.html"           # intermediate, ignored
PDF_OUT = ROOT / "frontend" / "public" / "manual.pdf"

# Inline CSS — Chinese-friendly fonts, print-friendly typography
CSS = """
@page { size: A4; margin: 18mm 16mm; }
body {
  font-family: "PingFang SC", "Microsoft YaHei", "Heiti SC", "Hiragino Sans GB",
               -apple-system, "Segoe UI", sans-serif;
  font-size: 11pt; line-height: 1.6; color: #1a1f2e;
}
h1 { font-size: 22pt; border-bottom: 2px solid #2563eb; padding-bottom: 8px; margin-top: 0; }
h2 { font-size: 16pt; color: #2563eb; margin-top: 28px;
     border-left: 4px solid #2563eb; padding-left: 10px; }
h3 { font-size: 13pt; color: #1e40af; margin-top: 18px; }
p, li { font-size: 11pt; }
code {
  font-family: "SF Mono", Menlo, Consolas, monospace;
  background: #f1f5f9; padding: 1px 5px; border-radius: 3px; font-size: 10pt;
}
pre {
  background: #1e293b; color: #e2e8f0; padding: 12px 14px;
  border-radius: 6px; font-size: 9.5pt; overflow-x: auto;
  page-break-inside: avoid;
}
pre code { background: transparent; color: inherit; padding: 0; }
table { border-collapse: collapse; margin: 12px 0; width: 100%;
        page-break-inside: avoid; font-size: 10.5pt; }
th, td { border: 1px solid #d1d5db; padding: 6px 10px; text-align: left; }
th { background: #f1f5f9; font-weight: 600; }
blockquote {
  border-left: 4px solid #f59e0b; background: #fffbeb;
  padding: 8px 14px; margin: 12px 0; color: #78350f;
}
img { max-width: 100%; border: 1px solid #e5e7eb; border-radius: 4px;
      display: block; margin: 12px auto; page-break-inside: avoid; }
hr { border: none; border-top: 1px dashed #cbd5e1; margin: 22px 0; }
a { color: #2563eb; text-decoration: none; }
ul, ol { padding-left: 22px; }
li { margin: 3px 0; }
"""


def md_to_html(md_text: str) -> str:
    """Convert markdown to HTML with extensions for tables, fenced code, etc."""
    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
        output_format="html5",
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>MRO 工业品 AI 采购助手 — 产品手册</title>
<style>{CSS}</style>
</head>
<body>
{html_body}
</body>
</html>"""


def main() -> int:
    if not MD_PATH.exists():
        print(f"FAIL: {MD_PATH} not found", file=sys.stderr)
        return 1

    md_text = MD_PATH.read_text(encoding="utf-8")
    html = md_to_html(md_text)
    HTML_OUT.write_text(html, encoding="utf-8")

    PDF_OUT.parent.mkdir(parents=True, exist_ok=True)

    # wkhtmltopdf renders the HTML, resolves relative image paths against the HTML's directory
    cmd = [
        "wkhtmltopdf",
        "--enable-local-file-access",
        "--encoding", "utf-8",
        "--margin-top", "18mm",
        "--margin-bottom", "18mm",
        "--margin-left", "16mm",
        "--margin-right", "16mm",
        "--print-media-type",
        "--footer-center", "第 [page] 页 / 共 [topage] 页",
        "--footer-font-size", "9",
        "--footer-spacing", "5",
        str(HTML_OUT),
        str(PDF_OUT),
    ]
    print("→ running wkhtmltopdf …")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FAIL:", result.stderr, file=sys.stderr)
        return result.returncode

    HTML_OUT.unlink(missing_ok=True)
    size_kb = PDF_OUT.stat().st_size // 1024
    print(f"✓ PDF generated: {PDF_OUT.relative_to(ROOT)} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
