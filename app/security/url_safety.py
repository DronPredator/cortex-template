"""Defensa contra Server-Side Request Forgery (SSRF).

Cuando el agente fetchea URLs (verify_pdf_url, fetch_product_data), un usuario
malicioso podría pedirle que acceda a recursos internos:
- `http://localhost:8000/api/admin/users` → leak de datos internos
- `http://192.168.1.1/admin` → ataque a router de la red interna
- `http://169.254.169.254/` → metadata service de cloud (AWS/GCP/Azure)
- `http://10.0.0.5:8080/secret` → cualquier servicio interno de la VPN

Este módulo resuelve el DNS y bloquea cualquier URL que apunte a una IP
privada, reservada, loopback, link-local, multicast, o ranges de cloud
metadata. La verificación es CONTRA LA IP RESUELTA, no contra el hostname
(un atacante podría poner un dominio público que resuelve a 127.0.0.1).
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.request
from urllib.parse import urlparse

from loguru import logger


# Cloud metadata services y otras IPs que NUNCA deben fetchearse.
# Estas vienen además de los rangos privados detectados por ipaddress.
_EXTRA_BLOCKED_IPS = {
    "169.254.169.254",  # AWS / GCP / Azure metadata
    "fd00:ec2::254",    # AWS IPv6 metadata
    "100.100.100.200",  # Alibaba Cloud metadata
}


class UnsafeURLError(ValueError):
    """URL bloqueada por política SSRF."""


def is_safe_url(url: str, *, allow_schemes: tuple[str, ...] = ("http", "https")) -> tuple[bool, str]:
    """Verifica si una URL es segura para fetchear desde el server.

    Retorna `(safe, reason)`. Si safe=False, `reason` explica por qué.

    Bloquea:
    - Schemes no http(s)
    - Hostnames vacíos o malformados
    - URLs cuyas IPs resueltas sean: loopback, link-local, privadas (RFC 1918),
      multicast, reservadas, unspecified
    - IPs en la lista de metadata services
    """
    if not isinstance(url, str) or not url.strip():
        return False, "URL vacía"

    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False, "URL malformada"

    if parsed.scheme not in allow_schemes:
        return False, f"Scheme no permitido: {parsed.scheme or '(vacío)'} (solo http/https)"

    host = parsed.hostname
    if not host:
        return False, "Hostname vacío"

    # Resolver DNS — todas las IPs A y AAAA del host
    try:
        addrinfo = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        return False, f"No se pudo resolver DNS: {e}"

    for family, _, _, _, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        if ip_str in _EXTRA_BLOCKED_IPS:
            return False, f"IP bloqueada (metadata service): {ip_str}"
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, f"IP no parseable: {ip_str}"

        # Política: bloquear todo lo que no sea pública global
        if ip.is_loopback:
            return False, f"IP loopback bloqueada: {ip_str}"
        if ip.is_private:
            return False, f"IP privada bloqueada: {ip_str}"
        if ip.is_link_local:
            return False, f"IP link-local bloqueada: {ip_str}"
        if ip.is_multicast:
            return False, f"IP multicast bloqueada: {ip_str}"
        if ip.is_reserved:
            return False, f"IP reservada bloqueada: {ip_str}"
        if ip.is_unspecified:
            return False, f"IP unspecified bloqueada: {ip_str}"

    return True, "ok"


def require_safe_url(url: str) -> None:
    """Versión que levanta excepción si la URL es insegura. Útil como guard."""
    safe, reason = is_safe_url(url)
    if not safe:
        logger.warning("ssrf_blocked | url={} reason={}", url[:200], reason)
        raise UnsafeURLError(reason)


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that re-validates every hop against the SSRF policy."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require_safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_urlopen(req_or_url, *, timeout: int):
    """Open an HTTP(S) URL after SSRF checks, including every redirect hop."""
    if isinstance(req_or_url, urllib.request.Request):
        require_safe_url(req_or_url.full_url)
    else:
        require_safe_url(str(req_or_url))
    opener = urllib.request.build_opener(SafeRedirectHandler)
    return opener.open(req_or_url, timeout=timeout)
