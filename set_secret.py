"""Setea una variable secreta en .env de forma segura.

Uso:
    python set_secret.py GOOGLE_API_KEY
    python set_secret.py ANTHROPIC_API_KEY
    python set_secret.py JWT_SECRET

La key se ingresa con getpass — NO se ve al tipear, NO queda en terminal history,
NO toca el portapapeles. Después se escribe al .env reemplazando solo esa línea
(las demás variables quedan intactas).
"""

import getpass
import re
import sys
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"

# Whitelist de variables que pueden setearse con este script
ALLOWED = {
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "TAVILY_API_KEY",
    "JWT_SECRET",
    "CHAT_PASSWORD",
    "ADMIN_PASSWORD",
}


def main():
    if len(sys.argv) != 2:
        print("Uso: python set_secret.py <VAR_NAME>")
        print(f"Variables permitidas: {', '.join(sorted(ALLOWED))}")
        sys.exit(1)

    var = sys.argv[1].strip().upper()
    if var not in ALLOWED:
        print(f"❌ Variable '{var}' no está en la lista permitida.")
        print(f"Permitidas: {', '.join(sorted(ALLOWED))}")
        sys.exit(1)

    if not ENV_PATH.exists():
        print(f"❌ No existe {ENV_PATH}. Creá el archivo primero.")
        sys.exit(1)

    # Prompt invisible — NO aparece en pantalla ni queda en history
    print(f"Ingresá el valor para {var} (no se va a mostrar al tipear):")
    value = getpass.getpass("→ ")
    if not value.strip():
        print("❌ Valor vacío, cancelado.")
        sys.exit(1)

    value = value.strip()

    # Confirmación adicional para chequear que no hubo error
    print(f"   Longitud: {len(value)} caracteres")
    print(f"   Primeros 4 caracteres: {value[:4]}…")
    confirm = input("¿Es correcto? [s/N]: ").strip().lower()
    if confirm not in ("s", "si", "y", "yes"):
        print("Cancelado.")
        sys.exit(0)

    # Reemplazo línea por línea preservando todo lo demás
    content = ENV_PATH.read_text(encoding="utf-8")
    pattern = rf"^{re.escape(var)}=.*$"
    new_line = f"{var}={value}"

    if re.search(pattern, content, flags=re.MULTILINE):
        new_content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
        action = "actualizada"
    else:
        new_content = content.rstrip() + f"\n{new_line}\n"
        action = "agregada"

    # Escritura atómica: tmp + replace
    tmp = ENV_PATH.with_suffix(".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    tmp.replace(ENV_PATH)

    print(f"✓ Variable {var} {action} en .env")
    print("⚠️  Reiniciá el servidor para que tome el cambio.")


if __name__ == "__main__":
    main()
