"""Convierte docs/informe/informe.md en HTML (con KaTeX) y, opcionalmente, en PDF con Chrome headless.

En esta Mac no hay LaTeX ni pandoc. El flujo es:
    Markdown -> HTML (paquete `markdown` de Python si está instalado; si no, un conversor mínimo propio)
             -> KaTeX auto-render desde cdnjs (única dependencia de red, la resuelve Chrome al imprimir)
             -> Chrome headless --print-to-pdf

Uso (desde la raíz del repo):
    python docs/informe/render_pdf.py                 # escribe docs/informe/informe.html e imprime el comando de Chrome
    python docs/informe/render_pdf.py --pdf           # además ejecuta Chrome y deja docs/informe/informe.pdf
    python docs/informe/render_pdf.py --final         # oculta los marcadores RESULTADOS/COMPLETAR (versión de entrega)

Las fórmulas se escriben con $...$ (en línea) y $$...$$ (en bloque). Se protegen antes de convertir el
Markdown para que `_`, `*` y `\\` no se interpreten como Markdown, y KaTeX las renderiza en el navegador.
Las figuras se referencian como ../figures/<nombre>.png (relativas a docs/informe/); si una no existe se
dibuja un recuadro con su nombre, para que el borrador se pueda imprimir antes de tener resultados.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KATEX = "https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9"
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
    "chromium-browser",
]

CSS = """
@page { size: Letter; margin: 1.9cm 1.9cm 2cm 1.9cm; }
body { font-family: "Georgia", "Times New Roman", serif; font-size: 10pt; line-height: 1.36; color: #111;
       max-width: 18cm; margin: 0 auto; background: #fff; }
h1 { font-size: 19pt; text-align: center; margin: 0 0 0.6em; line-height: 1.2; }
h2 { font-size: 13.5pt; margin: 1.4em 0 0.5em; border-bottom: 1px solid #999; padding-bottom: 2px; }
h3 { font-size: 11.5pt; margin: 1.1em 0 0.4em; }
p, li { text-align: justify; hyphens: auto; }
hr { border: 0; border-top: 1px solid #ccc; margin: 1.2em 0; }
blockquote { margin: 0.8em 0; padding: 0.4em 0.9em; border-left: 3px solid #b55; background: #fbf3f3; }
table { border-collapse: collapse; margin: 0.6em auto 1em; font-size: 9pt; }
tr { page-break-inside: avoid; }
th, td { border-top: 1px solid #bbb; border-bottom: 1px solid #bbb; padding: 3px 6px; vertical-align: top; }
th { background: #f0f0f0; }
table.num { font-size: 8.2pt; }
table.num th, table.num td { padding: 2px 4px; }
table.num td { white-space: nowrap; }
code { font-family: Menlo, monospace; font-size: 8.8pt; background: #f4f4f4; padding: 0 2px; }
pre { background: #f4f4f4; padding: 0.6em; overflow-x: auto; font-size: 8.5pt; }
img { display: block; max-width: 100%; max-height: 8cm; margin: 0.8em auto 0.2em; }
.fig-missing { border: 1.5px dashed #999; color: #666; text-align: center; padding: 1.2em 1em; margin: 0.6em auto;
               font-family: Menlo, monospace; font-size: 8.5pt; background: #fafafa; }
.caption { text-align: center; font-size: 9pt; color: #333; margin: 0 1cm 1em; }
.placeholder { border: 1px solid #e0b000; background: #fff8dc; color: #6b5200; font-family: Menlo, monospace;
               font-size: 8pt; padding: 4px 8px; margin: 0.4em 0; white-space: pre-wrap; text-align: left; display: block; }
.refs li { font-size: 8.8pt; text-align: left; margin-bottom: 2px; }
.katex-display { margin: 0.6em 0; overflow-x: auto; overflow-y: hidden; }
h2, h3 { page-break-after: avoid; }
"""

TEMPLATE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{katex}/katex.min.css">
<script defer src="{katex}/katex.min.js"></script>
<script defer src="{katex}/contrib/auto-render.min.js"></script>
<style>{css}</style>
</head>
<body>
{body}
<script>
document.addEventListener("DOMContentLoaded", function () {{
  if (typeof renderMathInElement !== "function") {{ document.title += " (sin KaTeX)"; return; }}
  renderMathInElement(document.body, {{
    delimiters: [{{left: "$$", right: "$$", display: true}}, {{left: "$", right: "$", display: false}}],
    throwOnError: false, strict: "ignore"
  }});
  document.body.setAttribute("data-math", "ok");
}});
</script>
</body>
</html>
"""

MATH_RE = re.compile(r"\$\$(.+?)\$\$|(?<![\\$])\$(?!\s)([^$\n]+?)(?<![\s\\])\$", re.S)
COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
PLACEHOLDER_KEYS = ("RESULTADOS", "COMPLETAR", "FIGURA", "DATO", "PENDIENTE", "INSTRUCCIONES", "BORRADOR")


# ------------------------------------------------------------------ preprocesado
def protect_math(text: str) -> tuple[str, list[str]]:
    """Reemplaza cada fórmula por un token sin caracteres especiales de Markdown."""
    store: list[str] = []

    def sub(m: re.Match) -> str:
        store.append(html.escape(m.group(0), quote=False))
        return f"@@MATH{len(store) - 1}@@"

    # no tocar bloques de código
    parts = re.split(r"(```.*?```|`[^`\n]*`)", text, flags=re.S)
    return "".join(p if p.startswith("`") else MATH_RE.sub(sub, p) for p in parts), store


def restore_math(html_text: str, store: list[str]) -> str:
    return re.sub(r"@@MATH(\d+)@@", lambda m: store[int(m.group(1))], html_text)


def handle_comments(text: str, final: bool) -> str:
    """Comentarios HTML: en borrador, los marcadores (RESULTADOS, COMPLETAR, ...) se muestran como recuadros."""

    def sub(m: re.Match) -> str:
        body = m.group(1).strip()
        if final or not body.startswith(PLACEHOLDER_KEYS):
            return ""
        return f'<span class="placeholder">{html.escape(body)}</span>'

    return COMMENT_RE.sub(sub, text)


def escape_angle_placeholders(text: str) -> str:
    """`<completar>` y `<completar: ...>` no son etiquetas HTML: se escapan para que se vean."""
    return re.sub(r"<(completar[^<>]*)>", lambda m: f"&lt;{m.group(1)}&gt;", text)


# ------------------------------------------------------------------ conversión
def md_to_html(text: str) -> str:
    try:
        import markdown  # type: ignore
    except ImportError:
        return minimal_markdown(text)
    return markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"], output_format="html5")


def _inline(s: str) -> str:
    s = re.sub(r"`([^`]+)`", lambda m: f"<code>{html.escape(m.group(1))}</code>", s)
    s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<img alt="\1" src="\2">', s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    return s


def minimal_markdown(text: str) -> str:
    """Conversor mínimo (títulos, párrafos, listas, tablas, citas, código, imágenes, negrita/cursiva).
    Solo se usa si el paquete `markdown` no está instalado."""
    out: list[str] = []
    lines = text.splitlines()
    i = 0
    para: list[str] = []

    def flush():
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    while i < len(lines):
        ln = lines[i]
        st = ln.strip()
        if st.startswith("```"):
            flush()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1 : j])) + "</code></pre>")
            i = j + 1
            continue
        if not st:
            flush()
        elif m := re.match(r"(#{1,6})\s+(.*)", st):
            flush()
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
        elif re.fullmatch(r"-{3,}|\*{3,}", st):
            flush()
            out.append("<hr>")
        elif st.startswith("|") and i + 1 < len(lines) and re.fullmatch(r"\|?[\s:|-]+\|?", lines[i + 1].strip()):
            flush()
            cells = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]  # noqa: E731
            rows = ["<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in cells(ln)) + "</tr></thead><tbody>"]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells(lines[i])) + "</tr>")
                i += 1
            out.append("".join(rows) + "</tbody></table>")
            continue
        elif st.startswith(">"):
            flush()
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f"<blockquote><p>{_inline(' '.join(q))}</p></blockquote>")
            continue
        elif re.match(r"([-*]|\d+\.)\s+", st):
            flush()
            ordered = bool(re.match(r"\d+\.", st))
            items: list[str] = []
            while i < len(lines) and lines[i].strip():
                s2 = lines[i].strip()
                if re.match(r"([-*]|\d+\.)\s+", s2):
                    items.append(re.sub(r"^([-*]|\d+\.)\s+", "", s2))
                else:
                    items[-1] += " " + s2
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(it)}</li>" for it in items) + f"</{tag}>")
            continue
        else:
            para.append(st)
        i += 1
    flush()
    return "\n".join(out)


def postprocess(body: str, base: Path) -> str:
    """Figuras: pie de figura desde el alt y recuadro si el archivo no existe."""

    def img(m: re.Match) -> str:
        tag = m.group(0)
        src = re.search(r'src="([^"]+)"', tag).group(1)
        alt_m = re.search(r'alt="([^"]*)"', tag)
        alt = alt_m.group(1) if alt_m else ""
        local = (base / src).resolve()
        if src.startswith(("http://", "https://")) or local.exists():
            fig = tag
        else:
            fig = f'<div class="fig-missing">[figura pendiente: {html.escape(src)}]</div>'
        # el alt no pasa por Markdown: cursiva y código a mano en el pie de figura
        alt_html = re.sub(r"`([^`]+)`", r"<code>\1</code>", alt)
        alt_html = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"<em>\1</em>", alt_html)
        cap = f'<div class="caption">{alt_html}</div>' if alt else ""
        return fig + cap

    body = re.sub(r"<img [^>]*>", img, body)

    # tablas de resultados (celdas "media ± IC95"): clase "num" para que las celdas no se partan
    def num_table(m: re.Match) -> str:
        tab = m.group(0)
        if "±" not in tab:
            return tab
        return tab.replace("<table>", '<table class="num">', 1)

    body = re.sub(r"<table>.*?</table>", num_table, body, flags=re.S)
    # referencias en letra más pequeña: todo lo que sigue al título "Referencias"
    body = re.sub(r"(<h2>Referencias</h2>)(.*)$", r'\1<div class="refs">\2</div>', body, flags=re.S)
    # un <p> que solo contiene la figura no debe envolver los <div>
    return re.sub(r"<p>\s*((?:<img [^>]*>|<div class=\"fig-missing\">.*?</div>)<div class=\"caption\">.*?</div>)\s*</p>",
                  r"\1", body, flags=re.S)


def build_html(md_path: Path, out_html: Path, final: bool = False) -> Path:
    text = md_path.read_text(encoding="utf-8")
    text = handle_comments(text, final)
    text = escape_angle_placeholders(text)
    text, store = protect_math(text)
    body = postprocess(md_to_html(text), md_path.parent)
    body = restore_math(body, store)
    title_m = re.search(r"^#\s+(.+)$", md_path.read_text(encoding="utf-8"), re.M)
    title = html.escape(title_m.group(1).strip()) if title_m else md_path.stem
    out_html.write_text(TEMPLATE.format(title=title, katex=KATEX, css=CSS, body=body), encoding="utf-8")
    return out_html


# ------------------------------------------------------------------ Chrome
def find_chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        if os.path.isabs(c) and os.path.exists(c):
            return c
        if not os.path.isabs(c) and shutil.which(c):
            return shutil.which(c)
    return None


def chrome_cmd(chrome: str, html_path: Path, pdf_path: Path, profile_dir: str) -> list[str]:
    return [
        chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        f"--user-data-dir={profile_dir}", "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=15000", "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}", html_path.as_uri(),
    ]  # fmt: skip


def run_chrome(cmd: list[str], pdf_path: Path, timeout: float = 90.0) -> bool:
    """En esta Mac Chrome headless escribe el PDF pero a veces no termina: se espera a que el archivo
    exista con tamaño estable y luego se termina el proceso."""
    if pdf_path.exists():
        pdf_path.unlink()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0, last, stable = time.time(), -1, 0
    try:
        while time.time() - t0 < timeout:
            if proc.poll() is not None and pdf_path.exists():
                break
            if pdf_path.exists():
                size = pdf_path.stat().st_size
                stable = stable + 1 if size == last and size > 0 else 0
                last = size
                if stable >= 3:
                    break
            time.sleep(0.5)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
    return pdf_path.exists() and pdf_path.stat().st_size > 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--md", type=Path, default=HERE / "informe.md")
    ap.add_argument("--html", type=Path, default=None, help="por defecto, junto al .md")
    ap.add_argument("--out", type=Path, default=None, help="PDF de salida (por defecto, junto al .md)")
    ap.add_argument("--pdf", action="store_true", help="ejecutar Chrome headless y escribir el PDF")
    ap.add_argument("--final", action="store_true", help="ocultar los marcadores RESULTADOS/COMPLETAR")
    a = ap.parse_args(argv)

    md = a.md.resolve()
    html_path = (a.html or md.with_suffix(".html")).resolve()  # junto al .md: así ../figures/ resuelve bien
    pdf_path = (a.out or md.with_suffix(".pdf")).resolve()
    build_html(md, html_path, final=a.final)
    try:
        import markdown  # noqa: F401
        conv = "markdown (Python)"
    except ImportError:
        conv = "conversor mínimo"
    print(f"[render] HTML: {html_path}  ({conv}; KaTeX desde cdnjs)")

    chrome = find_chrome()
    if not chrome:
        print("[render] No se encontró Chrome/Chromium. Abre el HTML en un navegador e imprime a PDF.")
        return 0 if not a.pdf else 1
    profile = tempfile.mkdtemp(prefix="informe-chrome-")
    cmd = chrome_cmd(chrome, html_path, pdf_path, profile)
    print("[render] Comando de Chrome headless:")
    print("  " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    if not a.pdf:
        print("[render] (agrega --pdf para ejecutarlo; Chrome puede no terminar solo: si el PDF ya existe, ciérralo con Ctrl-C)")
        shutil.rmtree(profile, ignore_errors=True)
        return 0
    ok = run_chrome(cmd, pdf_path)
    shutil.rmtree(profile, ignore_errors=True)
    print(f"[render] PDF: {pdf_path}" if ok else "[render] Chrome no produjo el PDF")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
