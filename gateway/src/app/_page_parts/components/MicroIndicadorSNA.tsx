import React from "react";
import { Cpu, Zap, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { EstadoMonitorSNA } from "../types";

export function MicroIndicadorSNA({ monitor }: { monitor: EstadoMonitorSNA }) {
  const colorMap: Record<string, string> = {
    optimo: "#10b981",
    normal: "#3b82f6",
    alerta: "#f59e0b",
    critico: "#ef4444",
  };
  const bgMap: Record<string, string> = {
    optimo: "bg-emerald-50",
    normal: "bg-blue-50",
    alerta: "bg-amber-50",
    critico: "bg-red-50",
  };
  const iconMap: Record<string, React.ReactNode> = {
    ligero: <Cpu className="h-4 w-4" />,
    medio: <Zap className="h-4 w-4" />,
    pesado: <ShieldCheck className="h-4 w-4" />,
  };
  const color = colorMap[monitor.estado];
  const circumferencia = 2 * Math.PI * 28;
  // Garantizar que el valor mostrado nunca sea negativo
  const valorSeguro = Math.max(0, monitor.valor);
  const offset = circumferencia - (valorSeguro / 100) * circumferencia;

  return (
    <div
      className={`flex items-center gap-4 rounded-xl p-4 overflow-hidden ${bgMap[monitor.estado]}`}
    >
      <div className="relative w-16 h-16 shrink-0">
        <svg className="w-16 h-16 -rotate-90" viewBox="0 0 72 72">
          <circle
            cx="36"
            cy="36"
            r="28"
            fill="none"
            stroke="currentColor"
            className="text-white"
            strokeWidth="6"
          />
          <circle
            cx="36"
            cy="36"
            r="28"
            fill="none"
            stroke={color}
            strokeWidth="6"
            strokeDasharray={circumferencia}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className="transition-all duration-1000 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-sm font-bold text-gray-800">
            {valorSeguro}%
          </span>
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span
            className={`${monitor.estado === "optimo" ? "text-emerald-600" : monitor.estado === "normal" ? "text-blue-600" : monitor.estado === "alerta" ? "text-amber-600" : "text-red-600"}`}
          >
            {iconMap[monitor.tipo]}
          </span>
          <span className="text-xs font-bold text-gray-700 uppercase tracking-wider truncate">
            {monitor.etiqueta}
          </span>
          <Badge
            className={`text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 ${
              monitor.estado === "optimo"
                ? "bg-emerald-100 text-emerald-700"
                : monitor.estado === "normal"
                  ? "bg-blue-100 text-blue-700"
                  : monitor.estado === "alerta"
                    ? "bg-amber-100 text-amber-700"
                    : "bg-red-100 text-red-700"
            }`}
          >
            {monitor.estado.toUpperCase()}
          </Badge>
        </div>
        <p className="text-[10px] text-gray-500 truncate">{monitor.detalle}</p>
      </div>
    </div>
  );
}
