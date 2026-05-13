#!/bin/bash
# ============================================================
#  ZENIC-AGENTS v1 - Instalador para Termux + proot-distro
#
#  Diseñado para: Xiaomi Redmi 12R Pro (12+8GB RAM)
#  Requisitos: Termux (F-Droid), conexión a Internet
#
#  Uso:
#    1. Instalar Termux desde F-Droid (NO Play Store)
#    2. Abrir Termux y correr:
#       pkg update && pkg upgrade -y
#    3. Descargar este script:
#       curl -O https://raw.githubusercontent.com/yurislay9-ui/Zenic-Agents-/main/install_termux.sh
#    4. Ejecutar:
#       chmod +x install_termux.sh
#       ./install_termux.sh
#
# ============================================================

set -e

# Configurable install path (override with: ZENIC_HOME=/path/to/repo ./install_termux.sh)
ZENIC_HOME="${ZENIC_HOME:-/root/Zenic-Agents-}"

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ZENIC-AGENTS v1 - Instalador Termux/proot-distro   ║"
echo "║  Motor de IA Quirurgico Local                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ============================================================
#  PASO 0: Verificar que estamos en Termux
# ============================================================

echo -e "${YELLOW}[PASO 0] Verificando entorno...${NC}"

if [ ! -d "/data/data/com.termux" ] && [ -z "$(which termux-info 2>/dev/null)" ]; then
    if [ ! -f "/.proot-env" ] && [ -z "$(which proot 2>/dev/null)" ]; then
        echo -e "${RED}ERROR: Este script debe ejecutarse dentro de Termux.${NC}"
        echo -e "${RED}Instala Termux desde F-Droid: https://f-droid.org/packages/com.termux/${NC}"
        exit 1
    fi
fi

# Detectar si ya estamos dentro de proot-distro
INSIDE_PROOT=false
if [ -f "/.proot-env" ] || [ -n "$(cat /proc/version 2>/dev/null | grep -i debian)" ]; then
    INSIDE_PROOT=true
    echo -e "${GREEN}Detectado: Corriendo dentro de proot-distro Debian${NC}"
fi

# ============================================================
#  PASO 1: Instalar proot-distro y Debian (si no estamos dentro)
# ============================================================

if [ "$INSIDE_PROOT" = false ]; then
    echo -e "${YELLOW}[PASO 1] Instalando proot-distro y Debian...${NC}"

    # Actualizar paquetes de Termux
    pkg update -y 2>/dev/null || true
    pkg upgrade -y 2>/dev/null || true

    # Instalar proot-distro
    if [ -z "$(which proot-distro 2>/dev/null)" ]; then
        pkg install proot-distro -y
        echo -e "${GREEN}proot-distro instalado${NC}"
    else
        echo -e "${GREEN}proot-distro ya instalado${NC}"
    fi

    # Instalar Debian
    if ! proot-distro list 2>/dev/null | grep -q "debian.*installed"; then
        echo -e "${YELLOW}Instalando Debian ARM... (esto tarda 2-5 minutos)${NC}"
        proot-distro install debian
        echo -e "${GREEN}Debian instalado${NC}"
    else
        echo -e "${GREEN}Debian ya instalado${NC}"
    fi

    # Crear script de inicio rapido (ZENIC_HOME expanded at install time)
    cat > $PREFIX/bin/zenic << ZENIC_SCRIPT
#!/bin/bash
# Script para iniciar ZENIC-AGENTS rapidamente
proot-distro login debian -- bash -c "cd ${ZENIC_HOME} && source venv/bin/activate && python3 main_headless.py --port 5000 --ram-limit 4096"
ZENIC_SCRIPT
    chmod +x $PREFIX/bin/zenic

    echo -e "${GREEN}Comando 'zenic' creado. Puedes iniciar el motor con solo escribir: zenic${NC}"
    echo ""
    echo -e "${YELLOW}Ahora entrando a Debian para continuar la instalacion...${NC}"
    echo -e "${YELLOW}El script se re-ejecutara dentro de Debian.${NC}"
    sleep 2

    # Copiar el script al home de Debian y ejecutarlo ahi
    # proot-distro Debian filesystem is at the installed-rootfs path
    DEBIAN_ROOT="/data/data/com.termux/files/usr/var/proot-distro/installed-rootfs/debian"
    cp "$0" "$DEBIAN_ROOT/root/install_termux.sh" 2>/dev/null || true
    proot-distro login debian -- bash -c "cd /root && bash install_termux.sh --inside-proot"
    exit 0
fi

# ============================================================
#  A partir de aqui, corremos dentro de proot-distro Debian
# ============================================================

echo -e "${CYAN}=== Instalando dentro de Debian ARM ===${NC}"

# ============================================================
#  PASO 2: Actualizar Debian e instalar dependencias
# ============================================================

echo -e "${YELLOW}[PASO 2] Actualizando Debian e instalando dependencias...${NC}"

apt update -y
apt upgrade -y

# Dependencias del sistema
apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    libsqlite3-dev \
    build-essential \
    git \
    curl \
    wget \
    nano \
    procps \
    2>/dev/null

echo -e "${GREEN}Dependencias del sistema instaladas${NC}"

# ============================================================
#  PASO 3: Verificar SQLite3
# ============================================================

echo -e "${YELLOW}[PASO 3] Verificando SQLite3...${NC}"

if python3 -c "import sqlite3; print('SQLite3 OK:', sqlite3.sqlite_version)" 2>/dev/null; then
    echo -e "${GREEN}SQLite3 funciona correctamente${NC}"
else
    echo -e "${RED}ERROR: SQLite3 no funciona. Instalando manualmente...${NC}"
    apt install -y libsqlite3-dev
    pip3 install pysqlite3 2>/dev/null || true
fi

# ============================================================
#  PASO 4: Clonar el repositorio
# ============================================================

echo -e "${YELLOW}[PASO 4] Clonando repositorio...${NC}"

if [ -d "$ZENIC_HOME" ]; then
    echo -e "${GREEN}Repositorio ya existe. Actualizando...${NC}"
    cd "$ZENIC_HOME"
    git pull 2>/dev/null || true
else
    git clone https://github.com/yurislay9-ui/Zenic-Agents-.git "$ZENIC_HOME"
    cd "$ZENIC_HOME"
fi

echo -e "${GREEN}Repositorio listo en $ZENIC_HOME/${NC}"

# ============================================================
#  PASO 5: Instalar dependencias Python
# ============================================================

echo -e "${YELLOW}[PASO 5] Instalando dependencias Python...${NC}"

# Create virtual environment for isolation (avoids breaking system Python)
echo -e "${CYAN}Creando entorno virtual...${NC}"
python3 -m venv "$ZENIC_HOME/venv" 2>/dev/null || true
if [ -d "$ZENIC_HOME/venv" ]; then
    source "$ZENIC_HOME/venv/bin/activate"
    echo -e "${GREEN}Entorno virtual creado y activado${NC}"
fi

# Actualizar pip
python3 -m pip install --upgrade pip 2>/dev/null || true

# Install ALL project dependencies from requirements.txt
echo -e "${CYAN}Instalando requirements.txt... (puede tardar 3-10 minutos)${NC}"
cd "$ZENIC_HOME"
pip3 install -r requirements.txt 2>/dev/null && echo -e "${GREEN}requirements.txt instalado${NC}" || {
    echo -e "${YELLOW}Algunas dependencias de requirements.txt fallaron. Instalando las criticas...${NC}"
    # Install core deps individually with error tolerance
    for pkg in fastapi uvicorn jinja2 python-multipart pydantic aiosqlite numpy pyyaml apscheduler aiohttp aiofiles python-jose "passlib[bcrypt]" gunicorn; do
        pip3 install "$pkg" 2>/dev/null && echo -e "  ${GREEN}✓ $pkg${NC}" || echo -e "  ${YELLOW}⚠ $pkg (skipped)${NC}"
    done
}

# Instalar Z3 solver (la pieza clave - funciona en proot-distro Debian ARM)
echo -e "${CYAN}Instalando Z3 SMT Solver... (puede tardar 1-3 minutos)${NC}"
pip3 install z3-solver 2>/dev/null && echo -e "${GREEN}Z3 instalado correctamente!${NC}" || {
    echo -e "${YELLOW}Z3 fallo en instalarse. Usando AC-3 fallback (menos potente pero funcional).${NC}"
    echo -e "${YELLOW}Para intentar instalar Z3 manualmente luego: pip3 install z3-solver${NC}"
}

# Install optional but useful packages for Termux
echo -e "${CYAN}Instalando paquetes opcionales...${NC}"
pip3 install textual 2>/dev/null && echo -e "${GREEN}Textual TUI instalado${NC}" || echo -e "${YELLOW}Textual no disponible (solo modo headless)${NC}"

echo -e "${GREEN}Dependencias Python instaladas${NC}"

# ============================================================
#  PASO 6: Verificar que todo funciona
# ============================================================

echo -e "${YELLOW}[PASO 6] Verificando instalacion...${NC}"

ERRORS=0

# Test 1: Python3
if python3 -c "print('Python3 OK')" 2>/dev/null; then
    echo -e "  ${GREEN}✓ Python3${NC}"
else
    echo -e "  ${RED}✗ Python3${NC}"
    ERRORS=$((ERRORS+1))
fi

# Test 2: SQLite3
if python3 -c "import sqlite3; conn = sqlite3.connect(':memory:'); print('SQLite3 OK')" 2>/dev/null; then
    echo -e "  ${GREEN}✓ SQLite3${NC}"
else
    echo -e "  ${RED}✗ SQLite3${NC}"
    ERRORS=$((ERRORS+1))
fi

# Test 3: Z3
if python3 -c "import z3; print('Z3 OK:', z3.get_version_string())" 2>/dev/null; then
    echo -e "  ${GREEN}✓ Z3 SMT Solver (verificacion formal completa)${NC}"
    HAS_Z3=true
else
    echo -e "  ${YELLOW}⚠ Z3 no disponible (usando AC-3 fallback)${NC}"
    HAS_Z3=false
fi

# Test 4: YAML
if python3 -c "import yaml; print('PyYAML OK')" 2>/dev/null; then
    echo -e "  ${GREEN}✓ PyYAML${NC}"
else
    echo -e "  ${YELLOW}⚠ PyYAML no disponible (usando defaults)${NC}"
fi

# Test 5: Threading
if python3 -c "import threading; e = threading.Event(); print('Threading OK')" 2>/dev/null; then
    echo -e "  ${GREEN}✓ Threading${NC}"
else
    echo -e "  ${RED}✗ Threading${NC}"
    ERRORS=$((ERRORS+1))
fi

# Test 6: AST
if python3 -c "import ast; tree = ast.parse('x = 1'); print('AST OK')" 2>/dev/null; then
    echo -e "  ${GREEN}✓ AST Parser${NC}"
else
    echo -e "  ${RED}✗ AST Parser${NC}"
    ERRORS=$((ERRORS+1))
fi

# Test 7: Import del engine
if python3 -c "
import sys
sys.path.insert(0, '$ZENIC_HOME')
from src.core.shared.contracts import HAS_Z3
from src.core.shared.resource_governor import get_governor
print('Engine imports OK')
" 2>/dev/null; then
    echo -e "  ${GREEN}✓ Engine imports${NC}"
else
    echo -e "  ${YELLOW}⚠ Engine imports falló - puede necesitar ajustes${NC}"
fi

echo ""

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}Hubo $ERRORS errores. Revisa los mensajes arriba.${NC}"
else
    echo -e "${GREEN}Todas las verificaciones pasaron!${NC}"
fi

# ============================================================
#  PASO 7: Crear servicio auto-start (opcional)
# ============================================================

echo -e "${YELLOW}[PASO 7] Creando script de inicio...${NC}"

cat > /root/start_zenic.sh << STARTSCRIPT
#!/bin/bash
# ZENIC-AGENTS v1 - Script de inicio
# Uso: bash /root/start_zenic.sh [opciones]

cd ${ZENIC_HOME}

# Activar entorno virtual si existe
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Iniciar el servidor headless
python3 main_headless.py \
    --port 5000 \
    --host 0.0.0.0 \
    --ram-limit 4096 \
    "$@"
STARTSCRIPT

chmod +x /root/start_zenic.sh
echo -e "${GREEN}Script creado: /root/start_zenic.sh${NC}"

# ============================================================
#  RESULTADO FINAL
# ============================================================

SOLVER_MSG="Z3 (verificacion formal completa)"
if [ "$HAS_Z3" = false ]; then
    SOLVER_MSG="AC-3 (fallback - Z3 no se pudo instalar)"
fi

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  INSTALACION COMPLETADA                                    ║${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║                                                              ║${NC}"
echo -e "${GREEN}║  Solver: ${SOLVER_MSG}           ║${NC}"
echo -e "${CYAN}║                                                              ║${NC}"
echo -e "${CYAN}║  PARA INICIAR EL MOTOR:                                     ║${NC}"
echo -e "${YELLOW}║    bash /root/start_zenic.sh                                 ║${NC}"
echo -e "${CYAN}║                                                              ║${NC}"
echo -e "${CYAN}║  O DESDE TERMUX (fuera de proot):                           ║${NC}"
echo -e "${YELLOW}║    zenic                                                     ║${NC}"
echo -e "${CYAN}║                                                              ║${NC}"
echo -e "${CYAN}║  CONECTAR CLINE/AIDE:                                       ║${NC}"
echo -e "${YELLOW}║    http://TU_IP:5000/v1                                      ║${NC}"
echo -e "${CYAN}║                                                              ║${NC}"
echo -e "${CYAN}║  OPCIONES:                                                   ║${NC}"
echo -e "${CYAN}║    --port 5000         Cambiar puerto                       ║${NC}"
echo -e "${CYAN}║    --ram-limit 4096    Subir limite RAM a 4GB               ║${NC}"
echo -e "${CYAN}║    --daemon            Correr en background                 ║${NC}"
echo -e "${CYAN}║    --debug             Logs verbose                         ║${NC}"
echo -e "${CYAN}║                                                              ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
