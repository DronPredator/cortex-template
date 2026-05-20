"""Scraping de páginas de producto + generación de PDFs con branding del cliente.

Dos funciones públicas:
  - fetch_product_data(url) -> dict con title/text/tables
  - generate_datasheet_pdf(out_dir, ...) -> dict con filename/url/size
"""

import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                  TableStyle, HRFlowable)



def _company_name() -> str:
    try:
        from app.config import settings
        return settings.company_full_name
    except Exception:
        return 'Demo Company S.A.'

def _company_short() -> str:
    try:
        from app.config import settings
        return settings.company_name
    except Exception:
        return 'Demo Company'


_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


# ── Scraping ──────────────────────────────────────────────────────────────────

def fetch_product_data(url: str, timeout: int = 10, max_html: int = 1_500_000) -> dict:
    """Descarga URL, extrae título + texto principal + hasta 8 tablas."""
    if not url or not isinstance(url, str):
        return {"error": "URL vacía o inválida"}
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        return {"error": "URL debe empezar con http:// o https://"}

    # SSRF guard — bloquear IPs privadas, loopback, link-local, metadata services
    try:
        from app.security.url_safety import UnsafeURLError, require_safe_url
        require_safe_url(url)
    except UnsafeURLError as e:
        return {"error": f"URL bloqueada por política de seguridad: {e}"}

    headers = {
        "User-Agent":      _UA,
        "Accept":          "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    }
    try:
        req = urllib.request.Request(url, method="GET", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            ct = (resp.headers.get("Content-Type") or "").lower()
            final_url = resp.url
            if "pdf" in ct:
                return {"error": f"URL es PDF (Content-Type: {ct}), no HTML — usar verify_pdf_url"}
            html_bytes = resp.read(max_html)
            html = html_bytes.decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {getattr(e, 'reason', '')}"}
    except urllib.error.URLError as e:
        return {"error": f"Error de red: {str(getattr(e, 'reason', e))[:80]}"}
    except Exception as e:
        return {"error": f"Error: {str(e)[:120]}"}

    soup = BeautifulSoup(html, "html.parser")

    # Quitar elementos ruidosos
    for tag in soup(["script", "style", "noscript", "iframe", "nav", "footer", "header",
                      "aside", "form", "button", "svg"]):
        tag.decompose()

    # Título
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h1 = soup.find("h1")
        if h1: title = h1.get_text(strip=True)

    # Cuerpo principal — preferir main/article/.product
    body = soup.find("main") or soup.find("article")
    if not body:
        body = (soup.find("div", class_=re.compile(r"product|content|main|specs", re.I))
                or soup.body or soup)

    text = body.get_text(separator="\n", strip=True)
    # Compactar saltos de línea
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()[:10_000]  # cap 10K caracteres

    # Tablas (típicamente specs)
    tables = []
    for tbl in soup.find_all("table")[:8]:
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells and any(c for c in cells):
                rows.append(cells)
        if len(rows) >= 1:
            tables.append(rows)

    # Listas de definiciones <dl>
    dl_items = []
    for dl in soup.find_all("dl")[:5]:
        terms = dl.find_all("dt")
        defs  = dl.find_all("dd")
        for t, d in zip(terms, defs):
            dl_items.append([t.get_text(strip=True), d.get_text(strip=True)])
    if dl_items:
        tables.append(dl_items)

    return {
        "url":         final_url,
        "status":      status,
        "title":       title[:300],
        "text":        text,
        "tables":      tables,
        "char_count":  len(text),
        "table_count": len(tables),
    }


# ── Generación de PDF ─────────────────────────────────────────────────────────

_BRAND_BLUE = colors.HexColor("#1a4ea0")
_BRAND_DARK = colors.HexColor("#0f3a7a")
_LIGHT_BG     = colors.HexColor("#f0f4f9")
_TEXT_GRAY    = colors.HexColor("#4a5b75")


def _make_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "FdmTitle", parent=base["Title"],
            fontName="Helvetica-Bold", fontSize=20, leading=24,
            textColor=_BRAND_DARK, spaceAfter=4, alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "FdmSubtitle", parent=base["Normal"],
            fontName="Helvetica", fontSize=11, leading=14,
            textColor=_TEXT_GRAY, alignment=TA_CENTER, spaceAfter=14,
        ),
        "h2": ParagraphStyle(
            "FdmH2", parent=base["Heading2"],
            fontName="Helvetica-Bold", fontSize=13, leading=16,
            textColor=_BRAND_BLUE, spaceBefore=12, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "FdmBody", parent=base["BodyText"],
            fontName="Helvetica", fontSize=10, leading=14,
            textColor=colors.HexColor("#1a2740"), spaceAfter=6, alignment=TA_JUSTIFY,
        ),
        "kv_key":   ParagraphStyle("BrandKVK", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=_BRAND_DARK),
        "kv_val":   ParagraphStyle("FdmKVV", fontName="Helvetica",      fontSize=9.5, leading=12, textColor=colors.HexColor("#1a2740")),
        "footer":   ParagraphStyle("FdmFoot", fontName="Helvetica-Oblique", fontSize=8.5, leading=11,
                                   textColor=_TEXT_GRAY, alignment=TA_JUSTIFY),
        "source":   ParagraphStyle("FdmSrc",  fontName="Helvetica", fontSize=8, leading=10, textColor=_TEXT_GRAY),
        "head_logo": ParagraphStyle("FdmLogo", fontName="Helvetica-Bold", fontSize=22, leading=26,
                                    textColor=_BRAND_DARK, alignment=TA_CENTER),
        "head_sub":  ParagraphStyle("FdmHeadSub", fontName="Helvetica", fontSize=8, leading=10,
                                     textColor=_TEXT_GRAY, alignment=TA_CENTER),
    }


def _page_header_footer(canvas, doc):
    """Header con logo del cliente + footer con paginación."""
    canvas.saveState()
    # Header bar
    canvas.setFillColor(_BRAND_BLUE)
    canvas.rect(0, A4[1] - 1.8 * cm, A4[0], 1.8 * cm, fill=1, stroke=0)
    # Texto del header
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(2 * cm, A4[1] - 1.15 * cm, _company_name().upper())
    canvas.setFont("Helvetica", 8.5)
    canvas.drawString(2 * cm, A4[1] - 1.55 * cm, "Ingeniería de fluidos · Instrumentación · Automatización industrial")
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 1.15 * cm, "FICHA TÉCNICA")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 1.55 * cm, "Documento de referencia")

    # Footer
    canvas.setFillColor(_TEXT_GRAY)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(2 * cm, 1.2 * cm,
                       "Documento generado por " + _company_name() + " en base a datos oficiales del fabricante.")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
    # Línea separadora del footer
    canvas.setStrokeColor(_BRAND_BLUE)
    canvas.setLineWidth(0.5)
    canvas.line(2 * cm, 1.7 * cm, A4[0] - 2 * cm, 1.7 * cm)
    canvas.restoreState()


def _esc(s: str) -> str:
    """Escape HTML para ReportLab (que usa una variante de HTML para texto)."""
    if not s: return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def generate_datasheet_pdf(
    out_dir: Path,
    *,
    title: str,
    manufacturer: str,
    model: str,
    description: str = "",
    specifications: dict | None = None,
    applications: str = "",
    source_urls: list[str] | None = None,
) -> dict:
    """Genera una ficha técnica con branding del cliente. Devuelve {filename, url, size_bytes}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_id   = uuid.uuid4().hex[:12]
    filename = f"cortex_{pdf_id}.pdf"
    filepath = out_dir / filename

    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=A4,
        topMargin=2.8 * cm,    # deja espacio para header
        bottomMargin=2.2 * cm, # deja espacio para footer
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        title=f"{_company_short()} — {title[:80]}",
        author=_company_name(),
    )

    styles = _make_styles()
    story = []

    # Título y subtítulo
    story.append(Paragraph(_esc(title), styles["title"]))
    sub_parts = []
    if manufacturer: sub_parts.append(f"Marca: <b>{_esc(manufacturer)}</b>")
    if model:        sub_parts.append(f"Modelo: <b>{_esc(model)}</b>")
    if sub_parts:
        story.append(Paragraph("&nbsp;&nbsp;·&nbsp;&nbsp;".join(sub_parts), styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_BRAND_BLUE, spaceAfter=10))

    # Descripción
    if description:
        story.append(Paragraph("Descripción", styles["h2"]))
        story.append(Paragraph(_esc(description), styles["body"]))

    # Especificaciones
    if specifications:
        story.append(Paragraph("Especificaciones técnicas", styles["h2"]))
        data = [[
            Paragraph("<b>Parámetro</b>", styles["kv_key"]),
            Paragraph("<b>Valor</b>",     styles["kv_key"]),
        ]]
        for k, v in specifications.items():
            data.append([
                Paragraph(_esc(str(k)), styles["kv_key"]),
                Paragraph(_esc(str(v)), styles["kv_val"]),
            ])
        tbl = Table(data, colWidths=[6 * cm, 10 * cm], hAlign="LEFT", repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), _BRAND_BLUE),
            ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
            ("GRID",        (0, 0), (-1, -1), 0.3, colors.HexColor("#c8d4e5")),
            ("VALIGN",      (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",(0, 0), (-1, -1), 8),
            ("TOPPADDING",  (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_BG]),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 6))

    # Aplicaciones
    if applications:
        story.append(Paragraph("Aplicaciones", styles["h2"]))
        story.append(Paragraph(_esc(applications), styles["body"]))

    # Disclaimer + fuentes al final
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=0.3, color=colors.HexColor("#c8d4e5")))
    story.append(Spacer(1, 6))
    disclaimer = (
        "Esta ficha técnica fue elaborada por <b>{_COMPANY_PLACEHOLDER_}</b> en base a información "
        "publicada por el fabricante en sus canales oficiales o por distribuidores autorizados. "
        "Para confirmación de especificaciones críticas, normas de aplicación y compatibilidad, "
        "consulte directamente al fabricante o contacte al área técnica de {_COMPANY_PLACEHOLDER_SHORT_}."
    )
    story.append(Paragraph(disclaimer, styles["footer"]))

    if source_urls:
        story.append(Spacer(1, 6))
        story.append(Paragraph("<b>Fuentes consultadas:</b>", styles["source"]))
        for u in source_urls[:10]:
            story.append(Paragraph(f"• {_esc(u)}", styles["source"]))

    # Fecha de generación
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<i>Documento generado: {now}</i>", styles["source"]))

    doc.build(story, onFirstPage=_page_header_footer, onLaterPages=_page_header_footer)

    return {
        "filename":   filename,
        "url":        f"/datasheets/{filename}",
        "size_bytes": filepath.stat().st_size,
    }
