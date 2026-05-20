"""Extracción de texto desde PDF, Word, Excel y PowerPoint.

Devuelve siempre un dict {filename, content_type, text, char_count, error?}.
El texto se devuelve listo para pasar como contexto al LLM (limitado a MAX_CHARS).
"""

from __future__ import annotations

import io
from pathlib import Path

MAX_CHARS = 60_000  # Tope de caracteres a devolver al LLM (≈ 15K tokens)


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_CHARS:
        return text
    return text[:MAX_CHARS] + f"\n\n[...truncado en {MAX_CHARS} chars de {len(text)} totales]"


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    out = []
    for i, page in enumerate(reader.pages, 1):
        try:
            txt = page.extract_text() or ""
        except Exception as e:
            txt = f"[Error extrayendo página {i}: {e}]"
        if txt.strip():
            out.append(f"--- Página {i} ---\n{txt.strip()}")
    return "\n\n".join(out) or "[PDF sin texto extraíble — posiblemente escaneado]"


def _extract_docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    out = []
    for para in doc.paragraphs:
        if para.text.strip():
            out.append(para.text.strip())
    for ti, table in enumerate(doc.tables, 1):
        out.append(f"\n--- Tabla {ti} ---")
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            out.append(" | ".join(cells))
    return "\n".join(out) or "[Documento Word vacío]"


def _extract_pptx(data: bytes) -> str:
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    out = []
    for si, slide in enumerate(prs.slides, 1):
        out.append(f"\n--- Slide {si} ---")
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    txt = "".join(r.text for r in para.runs).strip()
                    if txt:
                        out.append(txt)
            if shape.has_table:
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells]
                    out.append(" | ".join(cells))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                out.append(f"[Notas]: {notes}")
    return "\n".join(out) or "[Presentación PowerPoint vacía]"


def _extract_xlsx(data: bytes) -> str:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    out = []
    for sheet in wb.worksheets:
        out.append(f"\n--- Hoja: {sheet.title} ---")
        rows_added = 0
        for row in sheet.iter_rows(values_only=True):
            cells = ["" if v is None else str(v) for v in row]
            if any(c.strip() for c in cells):
                out.append(" | ".join(cells))
                rows_added += 1
            if rows_added >= 500:
                out.append(f"[... hoja truncada en 500 filas]")
                break
    return "\n".join(out) or "[Excel vacío]"


def _extract_txt(data: bytes) -> str:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


_EXTRACTORS = {
    ".pdf":  _extract_pdf,
    ".docx": _extract_docx,
    ".pptx": _extract_pptx,
    ".xlsx": _extract_xlsx,
    ".xlsm": _extract_xlsx,
    ".csv":  _extract_txt,
    ".txt":  _extract_txt,
    ".md":   _extract_txt,
}


def extract(filename: str, data: bytes) -> dict:
    """Extrae texto del archivo según extensión. Retorna dict con text + metadata."""
    ext = Path(filename).suffix.lower()
    fn = _EXTRACTORS.get(ext)
    if not fn:
        return {
            "filename": filename,
            "text": "",
            "char_count": 0,
            "error": f"Formato no soportado: {ext}. Aceptados: PDF, DOCX, PPTX, XLSX, CSV, TXT.",
        }
    try:
        text = fn(data)
        text = _truncate(text)
        return {
            "filename": filename,
            "text": text,
            "char_count": len(text),
        }
    except Exception as e:
        return {
            "filename": filename,
            "text": "",
            "char_count": 0,
            "error": f"Error procesando archivo: {e}",
        }
