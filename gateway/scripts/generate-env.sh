#!/bin/bash
# ─── Zenic-Agents v3.0 — Generador de .env seguro ─────────────────
# Uso: bash scripts/generate-env.sh
# Genera un archivo .env con valores criptográficamente seguros.
# NO commitear el archivo .env al repositorio.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"
EXAMPLE_FILE="$SCRIPT_DIR/../.env.example"

if [ -f "$ENV_FILE" ]; then
  echo "⚠️  El archivo .env ya existe. ¿Sobrescribir? (y/N)"
  read -r CONFIRM
  if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Cancelado."
    exit 0
  fi
fi

# Copy template
cp "$EXAMPLE_FILE" "$ENV_FILE"

# Generate secure random values
ADMIN_KEY=$(openssl rand -hex 32)
DEMO_KEY=$(openssl rand -hex 32)
CERT_SECRET=$(openssl rand -hex 32)
SIGNING_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
DB_PASSPHRASE=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -hex 32)

# Replace empty values with generated ones
sed -i "s|^ZENIC_ADMIN_KEY=\"\"|ZENIC_ADMIN_KEY=\"$ADMIN_KEY\"|" "$ENV_FILE"
sed -i "s|^ZENIC_DEMO_KEY=\"\"|ZENIC_DEMO_KEY=\"$DEMO_KEY\"|" "$ENV_FILE"
sed -i "s|^PLAYBOOK_CERT_SECRET=\"\"|PLAYBOOK_CERT_SECRET=\"$CERT_SECRET\"|" "$ENV_FILE"
sed -i "s|^ZENIC_SIGNING_KEY=\"\"|ZENIC_SIGNING_KEY=\"$SIGNING_KEY\"|" "$ENV_FILE"
sed -i "s|^ZENIC_DB_PASSPHRASE=\"\"|ZENIC_DB_PASSPHRASE=\"$DB_PASSPHRASE\"|" "$ENV_FILE"
sed -i "s|^ZENIC_ENCRYPTION_KEY=\"\"|ZENIC_ENCRYPTION_KEY=\"$ENCRYPTION_KEY\"|" "$ENV_FILE"

# Set restrictive permissions
chmod 600 "$ENV_FILE"

echo "✅ Archivo .env generado con valores seguros en: $ENV_FILE"
echo "   Permisos: 600 (solo propietario puede leer/escribir)"
echo ""
echo "⚠️  IMPORTANTE:"
echo "   - NUNCA commitear .env al repositorio"
echo "   - Agregar .env a .gitignore"
echo "   - Rotar estos valores si el repositorio es público"
echo ""
echo "   Variables generadas:"
echo "   - ZENIC_ADMIN_KEY     (64 hex chars)"
echo "   - ZENIC_DEMO_KEY      (64 hex chars)"
echo "   - PLAYBOOK_CERT_SECRET (64 hex chars)"
echo "   - ZENIC_SIGNING_KEY   (64 hex chars)"
echo "   - ZENIC_DB_PASSPHRASE (64 hex chars)"
echo "   - ZENIC_ENCRYPTION_KEY (64 hex chars)"
