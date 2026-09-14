# -*- coding: utf-8 -*-
"""
md2pdf.py — 마크다운을 인쇄용 PDF로 만든다.

    python md2pdf.py            # ho.md -> ho.pdf
    python md2pdf.py README.md  # README.md -> README.pdf

이 PC에 pandoc도 PDF 라이브러리도 없어서 Chrome 헤드리스 인쇄를 쓴다.
    md -> html -> pdf
중간 html도 남긴다. 스타일만 손볼 때는 그 파일을 고쳐서 다시 뽑으면 된다.

⚠️ 한글 경로 때문에 Chrome에 넘길 때 주의할 것이 두 가지 있다.
   · 출력은 반드시 **절대 경로**여야 한다. 상대 경로면 액세스 거부가 난다
   · 입력은 file:/// URL로 **퍼센트 인코딩**해서 넘겨야 한다
"""
import io, os, re, sys, subprocess, urllib.parse, shutil

sys.stdout.reconfigure(encoding="utf-8")

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm; }
* { box-sizing: border-box; }
/* 화면으로 열었을 때만 적용된다. 인쇄에는 @page가 쓰이므로 PDF는 그대로다.
   이게 없으면 브라우저에서 글줄이 창 너비 끝까지 늘어나 읽을 수가 없다. */
@media screen {
  body { max-width: 820px; margin: 48px auto 96px; padding: 0 28px; }
  h3 { margin-top: 34pt; }
}
body { font-family: "Malgun Gothic","맑은 고딕",system-ui,sans-serif;
       font-size: 10.5pt; line-height: 1.65; color: #1a1a1a; margin: 0;
       word-break: keep-all; overflow-wrap: anywhere; }
h1 { font-size: 20pt; font-weight: 600; margin: 0 0 6pt; letter-spacing: -.4pt; }
h1 + blockquote { margin-bottom: 22pt; }
h2 { font-size: 16pt; font-weight: 600; margin: 20pt 0 8pt; break-after: avoid; }
h3 { font-size: 14pt; font-weight: 600; margin: 22pt 0 8pt;
     padding-top: 8pt; border-top: 1.5px solid #1a1a1a; break-after: avoid; }
h4 { font-size: 11.5pt; font-weight: 600; margin: 15pt 0 5pt; break-after: avoid; }
h5 { font-size: 10.5pt; font-weight: 600; margin: 12pt 0 4pt; color: #333; break-after: avoid; }
p, li { margin: 3pt 0; }
ul, ol { margin: 4pt 0; padding-left: 17px; }
li { padding-left: 2px; }
li::marker { color: #999; }
ul ul { margin: 2pt 0; }
ul ul > li::marker { color: #bbb; }
blockquote { margin: 8pt 0; padding: 7pt 12pt; border-left: 2.5px solid #c9c9c9;
             background: #fafaf9; color: #444; }
pre { background: #f6f6f4; border: .5px solid #e0e0dc; border-radius: 4px;
      padding: 9pt 11pt; margin: 8pt 0; break-inside: avoid;
      font-family: Consolas,"D2Coding","Malgun Gothic",monospace;
      font-size: 9pt; line-height: 1.5; white-space: pre-wrap; }
code { font-family: Consolas,"D2Coding",monospace; font-size: 9.2pt;
       background: #f0f0ee; padding: 1px 4px; border-radius: 3px; }
pre code { background: none; padding: 0; font-size: inherit; }
.fig { margin: 12pt 0; text-align: center; break-inside: avoid; }
.fig svg { max-width: 100%; height: auto; }
table { border-collapse: collapse; margin: 8pt 0; font-size: 9.5pt; width: 100%; }
th, td { border: .5px solid #ddd; padding: 4pt 7pt; text-align: left; }
th { background: #f6f6f4; font-weight: 600; }
hr { border: none; border-top: .5px solid #ddd; margin: 16pt 0; }
"""


def build_html(src: str, dst: str) -> None:
    """마크다운을 읽어 인쇄용 html로 쓴다. svg는 파일째 심는다."""
    from markdown_it import MarkdownIt

    text = io.open(src, encoding="utf-8").read()
    base = os.path.dirname(os.path.abspath(src))

    def inline_svg(m):
        # 경로 의존을 없앤다 — pdf를 옮겨도 그림이 살아 있어야 한다
        path = os.path.join(base, m.group(1))
        if path.endswith(".svg") and os.path.exists(path):
            svg = io.open(path, encoding="utf-8").read()
            svg = re.sub(r'\s(width|height)="\d+"', "", svg, count=2)
            return f'<div class="fig">{svg}</div>'
        return m.group(0)

    text = re.sub(r"!\[[^\]]*\]\(([^)]+)\)", inline_svg, text)
    body = MarkdownIt("commonmark", {"html": True}).enable("table").render(text)
    title = os.path.splitext(os.path.basename(src))[0]
    io.open(dst, "w", encoding="utf-8").write(
        f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
        f"<title>{title}</title><style>{CSS}</style></head><body>\n{body}</body></html>"
    )


def to_pdf(html: str, pdf: str) -> None:
    browser = next((b for b in BROWSERS if os.path.exists(b)), None) \
        or shutil.which("chrome") or shutil.which("msedge")
    if not browser:
        sys.exit("Chrome이나 Edge를 찾지 못했다. BROWSERS에 경로를 추가할 것.")

    # 한글 경로 대응: 출력은 절대 경로, 입력은 file:/// 퍼센트 인코딩
    out = os.path.abspath(pdf)
    url = "file:///" + urllib.parse.quote(os.path.abspath(html).replace("\\", "/"))
    r = subprocess.run(
        [browser, "--headless", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer", f"--print-to-pdf={out}", url],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(out):
        sys.exit(f"PDF 생성 실패\n{r.stderr[-600:]}")


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "ho.md"
    if not os.path.exists(src):
        sys.exit(f"{src} 가 없다.")
    stem = os.path.splitext(src)[0]
    html, pdf = stem + ".html", stem + ".pdf"

    build_html(src, html)
    to_pdf(html, pdf)

    size = os.path.getsize(pdf)
    pages = len(re.findall(rb"/Type\s*/Page[^s]", io.open(pdf, "rb").read()))
    print(f"{src} -> {pdf}  ({size:,}바이트 · {pages}쪽)")
    print(f"중간 파일 {html} 도 남겼다. 스타일만 고칠 때는 이쪽을 손볼 것.")


if __name__ == "__main__":
    main()
