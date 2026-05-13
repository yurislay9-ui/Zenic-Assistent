#!/usr/bin/env bash
# =============================================================================
# ZENIC-AGENTS v18 — Fix Conexión Cline
# =============================================================================
# Este script resuelve los 3 problemas que impiden que Cline se conecte:
#
#   PROBLEMA 1: IP link-local 169.254.x.x → Cline no puede llegar
#   PROBLEMA 2: Modelo "zenic-agentsr" → nombre incorrecto (es sin "r")
#   PROBLEMA 3: AsyncIOScheduler no definido → APScheduler faltante
#
# USO en Termux:
#   bash scripts/fix_cline_connection.sh
# =============================================================================

set -e

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ZENIC-AGENTS v18 — Fix Conexión Cline                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── PROBLEMA 1: Obtener IP WiFi correcta ──
echo "━━━ PASO 1: Detectando IP WiFi del teléfono ─━━"

WIFI_IP=""

# Método 1: ip addr (más confiable en Termux/proot)
if command -v ip &>/dev/null; then
    # Buscar interfaces wlan0, wlan1, wifi, o cualquier IP que no sea 127.x o 169.254.x
    WIFI_IP=$(ip addr show 2>/dev/null | grep -oP 'inet \K(?!127\.|169\.254\.)[\d.]+' | head -1)
fi

# Método 2: ifconfig (fallback)
if [ -z "$WIFI_IP" ] && command -v ifconfig &>/dev/null; then
    WIFI_IP=$(ifconfig 2>/dev/null | grep -oP 'inet addr:\K(?!127\.|169\.254\.)[\d.]+' | head -1)
fi

# Método 3: netstat (último recurso)
if [ -z "$WIFI_IP" ] && command -v netstat &>/dev/null; then
    WIFI_IP=$(netstat -rn 2>/dev/null | grep "^0.0.0.0" | awk '{print $2}' | grep -v "127\.\|169\.254\." | head -1)
fi

# Método 4: conexión UDP a DNS (como hace get_local_ip en Python)
if [ -z "$WIFI_IP" ]; then
    WIFI_IP=$(python3 -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    ip = s.getsockname()[0]
    s.close()
    if ip.startswith('169.254.') or ip.startswith('127.'):
        # Fallback: buscar en interfaces
        import subprocess
        result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if 'inet ' in line and '127.0.0.1' not in line and '169.254.' not in line:
                ip = line.strip().split()[1].split('/')[0]
                break
    print(ip)
except Exception:
    print('0.0.0.0')
" 2>/dev/null)
fi

if [ -z "$WIFI_IP" ] || [ "$WIFI_IP" = "0.0.0.0" ]; then
    echo "⚠️  No se pudo detectar la IP WiFi automáticamente."
    echo "   Intenta obtenerla manualmente con: ip addr show wlan0"
    echo "   O busca en: Configuración → WiFi → Info de la red"
    echo ""
    echo "   Ingresa tu IP WiFi manualmente:"
    read -r WIFI_IP
fi

echo "✅ IP WiFi detectada: $WIFI_IP"
echo ""

# ── PROBLEMA 2: Verificar nombre del modelo ──
echo "━━━ PASO 2: Verificando nombre del modelo ─━━"

CORRECT_MODEL="zenic-agents"
echo "✅ Modelo correcto para Cline: $CORRECT_MODEL"
echo "   (NO uses 'zenic-agentsr' — la 'r' al final es incorrecta)"
echo ""

# ── PROBLEMA 3: Verificar APScheduler ──
echo "━━━ PASO 3: Verificando dependencias ─━━"

# Verificar APScheduler
if python3 -c "import apscheduler" 2>/dev/null; then
    APS_VERSION=$(python3 -c "import apscheduler; print(apscheduler.__version__)" 2>/dev/null || echo "unknown")
    echo "✅ APScheduler instalado: v$APS_VERSION"
else
    echo "⚠️  APScheduler NO instalado. Instalando..."
    pip install apscheduler 2>/dev/null || pip3 install apscheduler 2>/dev/null
    if python3 -c "import apscheduler" 2>/dev/null; then
        echo "✅ APScheduler instalado correctamente"
    else
        echo "❌ No se pudo instalar APScheduler. Ejecuta manualmente:"
        echo "   pip install apscheduler"
    fi
fi

# Verificar otras dependencias críticas
echo ""
echo "Verificando dependencias críticas..."
for pkg in fastapi uvicorn pydantic aiosqlite numpy pyyaml; do
    if python3 -c "import $pkg" 2>/dev/null; then
        echo "  ✅ $pkg"
    else
        echo "  ❌ $pkg FALTANTE — instala con: pip install $pkg"
    fi
done

echo ""

# ── Resumen de configuración para Cline ──
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  CONFIGURACIÓN PARA CLINE — Copia estos valores             ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                              ║"
echo "║  API Provider:  OpenAI Compatible                            ║"
echo "║  Base URL:      http://$WIFI_IP:5000/v1"
echo "║  Model:         $CORRECT_MODEL"
echo "║  API Key:       (cualquier texto, ej: sk-local)             ║"
echo "║                                                              ║"
echo "║  ⚠️  IMPORTANTE:                                             ║"
echo "║  • El teléfono y la PC deben estar en la MISMA red WiFi     ║"
echo "║  • Si usas proot-distro, la IP puede ser diferente          ║"
echo "║  • El servidor DEBE escuchar en 0.0.0.0 (no 169.254.x.x)   ║"
echo "║  • El modelo es '$CORRECT_MODEL' (SIN la 'r' al final)"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Test de conectividad ──
echo "━━━ PASO 4: Test de conectividad ─━━"
echo ""

# Verificar que el puerto 5000 está abierto
if command -v ss &>/dev/null; then
    PORT_CHECK=$(ss -tlnp 2>/dev/null | grep ":5000" || echo "")
elif command -v netstat &>/dev/null; then
    PORT_CHECK=$(netstat -tlnp 2>/dev/null | grep ":5000" || echo "")
else
    PORT_CHECK=""
fi

if [ -n "$PORT_CHECK" ]; then
    echo "✅ Puerto 5000 está en ESCUCHA"
else
    echo "⚠️  Puerto 5000 NO detectado en escucha."
    echo "   Asegúrate de que el servidor esté corriendo con:"
    echo "   python3 logger_debug.py --host 0.0.0.0 --port 5000"
fi

echo ""

# ── Generar archivo de configuración para Cline ──
CLINE_CONFIG_DIR="$HOME/.config/cline"
mkdir -p "$CLINE_CONFIG_DIR" 2>/dev/null || true

CLINE_CONFIG_FILE="$CLINE_CONFIG_DIR/zenic-agents-config.json"

cat > "$CLINE_CONFIG_FILE" << EOF
{
  "apiKey": "sk-local",
  "baseURL": "http://${WIFI_IP}:5000/v1",
  "model": "${CORRECT_MODEL}",
  "temperature": 0.15,
  "maxTokens": 600
}
EOF

echo "📄 Configuración guardada en: $CLINE_CONFIG_FILE"
echo ""

# ── Comando para iniciar el servidor correctamente ──
echo "━━━ COMANDO PARA INICIAR EL SERVIDOR ─━━"
echo ""
echo "  python3 logger_debug.py --host 0.0.0.0 --port 5000"
echo ""
echo "  NOTA: --host 0.0.0.0 es CRUCIAL para que Cline pueda conectar"
echo "  Si usas main_headless.py:"
echo "  python3 main_headless.py --host 0.0.0.0 --port 5000"
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Si Cline sigue sin conectar, verifica:                     ║"
echo "║                                                              ║"
echo "║  1. ¿Teléfono y PC están en la misma red WiFi?              ║"
echo "║  2. ¿El firewall del teléfono bloquea el puerto 5000?       ║"
echo "║  3. ¿Probar con curl desde la PC?                           ║"
echo "║     curl http://${WIFI_IP}:5000/health"
echo "║  4. ¿Estás usando proot-distro? La IP puede ser diferente   ║"
echo "║     Dentro de proot, intenta: ip addr show                  ║"
echo "║  5. Si usas Termux sin proot, intenta:                      ║"
echo "║     ifconfig wlan0                                           ║"
echo "║     O busca en Configuración → WiFi → Info de la red        ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
