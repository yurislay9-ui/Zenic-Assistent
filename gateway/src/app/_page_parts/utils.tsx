import {
  Shield,
  Lock,
  KeyRound,
  Box,
  ShieldCheck,
  FileLock,
} from "lucide-react";
import type { MetricasDashboard, EstadoMonitorSNA } from "./types";

// ═══════════════════════════════════════════════════════════════════════════════
// UTILIDADES
// ═══════════════════════════════════════════════════════════════════════════════

export function tiempoRelativo(fechaStr: string): string {
  const d = new Date(fechaStr);
  const ahora = new Date();
  const diff = Math.floor((ahora.getTime() - d.getTime()) / 1000);
  if (diff < 60) return `hace ${diff}s`;
  if (diff < 3600) return `hace ${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)}h`;
  return `hace ${Math.floor(diff / 86400)}d`;
}

export function truncarHash(hash: string | null): string {
  if (!hash) return "génesis";
  return hash.length > 12 ? `${hash.slice(0, 8)}...${hash.slice(-4)}` : hash;
}

export function formatoMoneda(valor: number): string {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(valor);
}

export function formatoTimestamp(fecha: Date): string {
  return new Intl.DateTimeFormat("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(fecha);
}

export function formatoTamañoArchivo(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function categoriaColor(cat: string): {
  bg: string;
  text: string;
  border: string;
  label: string;
} {
  switch (cat) {
    case "destructive":
      return {
        bg: "bg-red-50",
        text: "text-red-700",
        border: "border-red-200",
        label: "DESTRUCTIVA",
      };
    case "financial":
      return {
        bg: "bg-amber-50",
        text: "text-amber-700",
        border: "border-amber-200",
        label: "FINANCIERA",
      };
    default:
      return {
        bg: "bg-gray-50",
        text: "text-gray-600",
        border: "border-gray-200",
        label: "SEGURA",
      };
  }
}

export function iconoCapa(nombre: string) {
  switch (nombre) {
    case "Shield":
      return <Shield className="h-5 w-5" />;
    case "Lock":
      return <Lock className="h-5 w-5" />;
    case "KeyRound":
      return <KeyRound className="h-5 w-5" />;
    case "Box":
      return <Box className="h-5 w-5" />;
    case "ShieldCheck":
      return <ShieldCheck className="h-5 w-5" />;
    case "FileLock":
      return <FileLock className="h-5 w-5" />;
    default:
      return <Shield className="h-5 w-5" />;
  }
}

/** Calcular monitores SNA con rango seguro 0–100 (NUNCA negativo) */
export function calcularMonitoresSNA(
  metricas: MetricasDashboard | null
): EstadoMonitorSNA[] {
  const avgExecTime = metricas?.avgExecutionTime ?? 0;

  // Ligero: CPU/Memoria — salud basada en tiempo de ejecución
  // <50ms = 100%, 50-200ms = degradación lineal, >200ms = crítico
  const saludLigero = Math.max(
    0,
    Math.min(100, Math.round(100 - (avgExecTime / 200) * 100))
  );

  // Medio: Latencia/Errores — basado en tasa de éxito
  const tasaExito = metricas?.successRate ?? 100;
  const saludMedio = Math.max(0, Math.min(100, Math.round(tasaExito)));

  // Pesado: Compliance/Integridad — basado en cero alucinaciones
  const saludPesado = Math.max(
    0,
    Math.min(100, metricas?.zeroHallucinationsPct ?? 100)
  );

  const estadoDe = (v: number): "optimo" | "normal" | "alerta" | "critico" => {
    if (v >= 90) return "optimo";
    if (v >= 70) return "normal";
    if (v >= 40) return "alerta";
    return "critico";
  };

  return [
    {
      tipo: "ligero",
      etiqueta: "Recursos",
      valor: Math.max(0, saludLigero),
      estado: estadoDe(saludLigero),
      detalle:
        saludLigero >= 90
          ? "CPU y memoria en rango óptimo"
          : saludLigero >= 70
            ? "Recursos estables con leve overhead"
            : "Consumo elevado de recursos",
    },
    {
      tipo: "medio",
      etiqueta: "Latencia",
      valor: Math.max(0, saludMedio),
      estado: estadoDe(saludMedio),
      detalle:
        saludMedio >= 90
          ? "Tasa de éxito excelente"
          : saludMedio >= 70
            ? "Algunas operaciones con errores"
            : "Degradación de rendimiento detectada",
    },
    {
      tipo: "pesado",
      etiqueta: "Integridad",
      valor: Math.max(0, saludPesado),
      estado: estadoDe(saludPesado),
      detalle:
        saludPesado >= 90
          ? "Postura de seguridad verificada"
          : "Posible desviación de compliance",
    },
  ];
}
