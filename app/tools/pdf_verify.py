"""Verificación HTTP de URLs candidatas a PDF.

GET con Range para los primeros 2KB:
- Chequea status 200/206
- Magic bytes %PDF (chequeo más confiable que Content-Type)
- Detecta redirects a login (paywalls)
- Distingue 403 anti-bot de 404 not found
"""

from __future__ import annotations

import urllib.error
import urllib.request

from loguru import logger

from app.security.url_safety import UnsafeURLError, require_safe_url


_LOGIN_PATTERNS = (
    "/login",
    "/signin",
    "/sign-in",
    "/auth/",
    "/register",
    "/users/sign",
    "?login",
)


def verify_pdf_url(url: str, timeout: int = 8) -> dict:
    """Devuelve dict con {valid, status, content_type, size_bytes, final_url, reason}."""
    if not url or not isinstance(url, str):
        return {"valid": False, "reason": "URL vacía o inválida"}

    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        return {"valid": False, "reason": "URL debe empezar con http:// o https://"}

    # SSRF guard — bloquear IPs privadas, loopback, link-local, metadata services
    try:
        require_safe_url(url)
    except UnsafeURLError as e:
        return {"valid": False, "reason": f"URL bloqueada por política de seguridad: {e}"}

    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    headers = {
        "User-Agent": ua,
        "Accept": "application/pdf,application/octet-stream,*/*",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        "Range": "bytes=0-2047",
    }

    try:
        req = urllib.request.Request(url, method="GET", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            cl = resp.headers.get("Content-Length")
            final_url = resp.url
            try:
                size = int(cl) if cl else None
            except Exception:
                size = None
            head_bytes = resp.read(8)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return {
                "valid": False,
                "status": 403,
                "reason": "Bloqueado por el servidor (403 — puede ser anti-bot)",
            }
        if e.code == 404:
            return {
                "valid": False,
                "status": 404,
                "reason": "URL no existe (404 Not Found)",
            }
        return {
            "valid": False,
            "status": e.code,
            "reason": f"HTTP {e.code} {getattr(e, 'reason', '')}".strip(),
        }
    except urllib.error.URLError as e:
        return {
            "valid": False,
            "reason": f"Error de red: {str(getattr(e, 'reason', e))[:80]}",
        }
    except Exception as e:
        logger.warning("verify_pdf_url_unexpected | url={} err={}", url, e)
        return {"valid": False, "reason": f"Error: {str(e)[:100]}"}

    final_lower = (final_url or "").lower()
    ok_status = status in (200, 206)
    is_pdf_magic = head_bytes.startswith(b"%PDF")
    is_login_redirect = any(p in final_lower for p in _LOGIN_PATTERNS)
    is_pdf_ct = "pdf" in ct

    info: dict = {
        "status": status,
        "content_type": ct,
        "size_bytes": size,
        "final_url": final_url,
    }

    if not ok_status:
        info["valid"] = False
        info["reason"] = f"Status HTTP {status}"
    elif is_login_redirect:
        info["valid"] = False
        info["reason"] = (
            f"URL redirige a página de login/registro ({final_url}) — el PDF no es público"
        )
    elif is_pdf_magic:
        info["valid"] = True
        info["reason"] = "PDF verificado (magic bytes %PDF)"
    elif is_pdf_ct:
        info["valid"] = True
        info["reason"] = f"PDF (Content-Type: {ct})"
    else:
        snippet = head_bytes[:8].decode("ascii", errors="replace")
        info["valid"] = False
        info["reason"] = (
            f"URL accesible pero NO es PDF "
            f"(Content-Type: '{ct or 'desconocido'}', primeros bytes: '{snippet}')"
        )
    return info
