"""
ZENIC-AGENTS v18 - Server Utilities

ThreadedHTTPServer, utilidades de red, rate limiter y funciones auxiliares
compartidas entre main.py (TUI/Textual) y main_headless.py (Termux).

v18: get_local_ip() mejorado con deteccion multi-metodo para
     Termux + datos moviles (rmnet0, ccmni0, wlan0, etc.)
"""

import os
import re
import socket
import subprocess
import logging
from http.server import HTTPServer
from socketserver import ThreadingMixIn

from src.server.rate_limiter import RateLimiter

logger = logging.getLogger("ZENIC.NET")

# Detectar plataforma
IS_TERMUX = os.path.exists("/data/data/com.termux")
IS_PROOT = os.path.exists("/data/data/com.termux/files/usr/bin/proot")
IS_ANDROID = 'ANDROID_ARGUMENT' in os.environ or IS_TERMUX


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Servidor HTTP multithread para manejar peticiones concurrentes."""
    daemon_threads = True
    allow_reuse_address = True


def _ip_from_udp_connect(target="8.8.8.8", port=80):
    """Metodo 1: UDP connect trick (original). Funciona si hay ruta a internet."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect((target, port))
        ip = s.getsockname()[0]
        s.close()
        if ip and ip != "0.0.0.0":
            return ip
    except Exception:
        pass
    return None


def _ip_from_udp_connect_ipv6():
    """Metodo 2: UDP connect via IPv6 (para redes dual-stack)."""
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("2001:4860:4860::8888", 80))
        ip = s.getsockname()[0]
        s.close()
        # Extraer IPv4 mapeado si es ::ffff:x.x.x.x
        if ip.startswith("::ffff:"):
            return ip[7:]
        if "%" in ip:
            ip = ip.split("%")[0]
        if ip and ip != "::":
            return ip
    except Exception:
        pass
    return None


def _ip_from_ip_addr():
    """Metodo 3: Parsear 'ip addr' (disponible en Termux/proot-distro).

    Busca interfaces en orden de prioridad para datos moviles:
    - rmnet0, rmnet_data0, ccmni0 (datos moviles Android)
    - wlan0, wlan1 (WiFi)
    - eth0, usb0 (USB tethering)
    - rndis0 (USB networking)
    """
    # Orden de prioridad de interfaces para datos moviles
    priority_prefixes = [
        "rmnet", "ccmni",   # Datos moviles Android
        "wlan",             # WiFi
        "eth",              # Ethernet/USB
        "usb", "rndis",     # USB tethering
    ]

    try:
        result = subprocess.run(
            ["ip", "addr", "show"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    # Parsear interfaces y sus IPs
    interfaces = {}
    current_iface = None
    for line in result.stdout.splitlines():
        # Linea de interfaz: "2: rmnet0: <BROADCAST,MULTICAST,UP> ..."
        iface_match = re.match(r'^\d+:\s+(\S+):', line)
        if iface_match:
            current_iface = iface_match.group(1)
            interfaces[current_iface] = []
            continue

        # Linea de IP: "    inet 10.0.0.1/24 brd 10.0.0.255 scope global rmnet0"
        if current_iface and "inet " in line:
            ip_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', line)
            if ip_match:
                ip = ip_match.group(1)
                # Ignorar loopback
                if not ip.startswith("127."):
                    interfaces[current_iface].append(ip)

    # Buscar por prioridad
    for prefix in priority_prefixes:
        for iface_name, ips in interfaces.items():
            if iface_name.startswith(prefix) and ips:
                return ips[0]

    # Fallback: cualquier interfaz con IP que no sea loopback
    for iface_name, ips in interfaces.items():
        if iface_name == "lo":
            continue
        if ips:
            return ips[0]

    return None


def _ip_from_ifconfig():
    """Metodo 4: Parsear 'ifconfig' (alternativa en algunos Termux)."""
    try:
        result = subprocess.run(
            ["ifconfig"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    # Buscar inet addr en output de ifconfig
    for line in result.stdout.splitlines():
        match = re.search(r'inet\s+(?:addr:)?(\d+\.\d+\.\d+\.\d+)', line)
        if match:
            ip = match.group(1)
            if not ip.startswith("127."):
                return ip
    return None


def _ip_from_netifaces():
    """Metodo 5: Usar libreria netifaces si esta instalada."""
    try:
        import netifaces
        # Priorizar gateways
        gws = netifaces.gateways()
        default_gw = gws.get('default', {})
        for af_family in (netifaces.AF_INET, netifaces.AF_INET6):
            if af_family in default_gw:
                iface = default_gw[af_family][1]
                addrs = netifaces.ifaddresses(iface).get(af_family, [])
                for addr in addrs:
                    ip = addr.get('addr', '')
                    if '%' in ip:
                        ip = ip.split('%')[0]
                    if ip and not ip.startswith("127.") and not ip.startswith("::1"):
                        return ip
    except ImportError:
        pass
    except Exception:
        pass
    return None


def _ip_from_env():
    """Metodo 6: Variable de entorno ZENIC_BIND_IP (configuracion manual).

    Si el usuario configura ZENIC_BIND_IP en .env, se usa directamente.
    Util cuando ningun metodo automatico funciona en datos moviles.
    """
    ip = os.environ.get("ZENIC_BIND_IP", "").strip()
    if ip and not ip.startswith("127.") and ip != "0.0.0.0":
        return ip
    return None


def _ip_from_proc_net():
    """Metodo 7: Leer /proc/net/fib_trie para encontrar IPs locales.

    Disponible en la mayoria de kernels Linux, incluyendo Termux.
    """
    try:
        with open("/proc/net/fib_trie", "r") as f:
            content = f.read()

        # Buscar IPs locales que no sean loopback
        local_ips = []
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if "/32 host LOCAL" in line:
                # La IP esta en la linea anterior
                if i > 0:
                    prev = lines[i - 1].strip()
                    ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', prev)
                    if ip_match:
                        ip = ip_match.group(1)
                        if not ip.startswith("127."):
                            local_ips.append(ip)

        # Devolver la primera IP que no sea loopback
        if local_ips:
            return local_ips[0]
    except (FileNotFoundError, PermissionError):
        pass
    return None


def get_local_ip():
    """
    Obtiene la IP local del dispositivo usando multiples metodos.

    Intenta varios metodos en orden de confiabilidad, con soporte
    especial para Termux + datos moviles donde el metodo UDP basico
    puede fallar.

    Orden de intento:
      1. UDP connect a 8.8.8.8 (metodo original)
      2. UDP connect IPv6 (dual-stack)
      3. Variable de entorno ZENIC_BIND_IP (manual)
      4. Parsear 'ip addr' (rmnet0, ccmni0, wlan0, etc.)
      5. Leer /proc/net/fib_trie
      6. Parsear 'ifconfig'
      7. Libreria netifaces
      8. Fallback: 127.0.0.1

    Returns:
        str: IP local o "127.0.0.1" si todos los metodos fallan
    """
    methods = [
        ("UDP connect (8.8.8.8)", _ip_from_udp_connect),
        ("UDP connect IPv6", _ip_from_udp_connect_ipv6),
        ("ENV ZENIC_BIND_IP", _ip_from_env),
        ("ip addr (interfaces)", _ip_from_ip_addr),
        ("/proc/net/fib_trie", _ip_from_proc_net),
        ("ifconfig", _ip_from_ifconfig),
        ("netifaces library", _ip_from_netifaces),
    ]

    for method_name, method_fn in methods:
        try:
            ip = method_fn()
            if ip and ip != "0.0.0.0" and not ip.startswith("127."):
                logger.debug(f"IP detectada via {method_name}: {ip}")
                return ip
        except Exception as e:
            logger.debug(f"Metodo {method_name} fallo: {e}")
            continue

    logger.warning(
        "No se pudo detectar la IP local automaticamente. "
        "Usando 127.0.0.1 como fallback. "
        "Si usas datos moviles, configura ZENIC_BIND_IP en .env "
        "con tu IP manualmente (ej: ZENIC_BIND_IP=192.168.1.100)"
    )
    return "127.0.0.1"


def get_network_info():
    """
    Retorna informacion completa de red para diagnostico.

    Util para debugging en Termux con datos moviles donde
    la deteccion de IP es problematica.

    Returns:
        dict: Informacion de red detallada
    """
    info = {
        "platform": {
            "is_termux": IS_TERMUX,
            "is_proot": IS_PROOT,
            "is_android": IS_ANDROID,
        },
        "hostname": socket.gethostname(),
        "methods_tried": {},
        "recommended_ip": get_local_ip(),
        "bind_address": "0.0.0.0",
        "bind_ip_hint": os.environ.get("ZENIC_BIND_IP", ""),
    }

    # Probar cada metodo y registrar resultados
    for method_name, method_fn in [
        ("UDP connect (8.8.8.8)", _ip_from_udp_connect),
        ("UDP connect IPv6", _ip_from_udp_connect_ipv6),
        ("ENV ZENIC_BIND_IP", _ip_from_env),
        ("ip addr", _ip_from_ip_addr),
        ("/proc/net/fib_trie", _ip_from_proc_net),
        ("ifconfig", _ip_from_ifconfig),
        ("netifaces", _ip_from_netifaces),
    ]:
        try:
            ip = method_fn()
            info["methods_tried"][method_name] = ip or "FAILED"
        except Exception as e:
            info["methods_tried"][method_name] = f"ERROR: {e}"

    # Test de conectividad loopback
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        info["loopback_available"] = True
        info["loopback_test_port"] = port
        s.close()
    except Exception as e:
        info["loopback_available"] = False
        info["loopback_error"] = str(e)

    return info


def configure_handler(
    orchestrator,
    governor=None,
    start_time=None,
    platform_tag="",
    rate_limiter=None,
):
    """
    Configura ZenicHTTPHandler con las instancias necesarias.

    Debe llamarse antes de crear el servidor HTTP.

    Args:
        orchestrator: ZenicOrchestrator instance
        governor: ResourceGovernor instance (opcional, solo headless)
        start_time: float - timestamp de inicio (opcional)
        platform_tag: str - identificador de plataforma (e.g. "termux-proot")
        rate_limiter: RateLimiter instance (opcional, proteccion contra flood)
    """
    from src.server.http_handler import ZenicHTTPHandler
    ZenicHTTPHandler.orchestrator = orchestrator
    ZenicHTTPHandler.governor = governor
    ZenicHTTPHandler.start_time = start_time
    ZenicHTTPHandler.platform_tag = platform_tag
    ZenicHTTPHandler.rate_limiter = rate_limiter
