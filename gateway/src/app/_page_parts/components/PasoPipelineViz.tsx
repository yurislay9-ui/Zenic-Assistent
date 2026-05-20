import { Lock, Play, CheckCircle2, CircleDot } from "lucide-react";
import type { PasoPipeline } from "../types";

export function PasoPipelineViz({
  paso,
  esActual,
  esUltimo,
  bloqueado,
}: {
  paso: PasoPipeline;
  esActual: boolean;
  esUltimo: boolean;
  bloqueado: boolean;
}) {
  const estaActivo = !bloqueado && (paso.status === "active" || paso.status === "processing");
  const estaProcesando = !bloqueado && paso.status === "processing";

  return (
    <div className={`flex items-start gap-0 ${bloqueado ? "opacity-40" : ""}`}>
      <div className="flex flex-col items-center">
        <div
          className={`w-10 h-10 rounded-full flex items-center justify-center border-2 transition-all duration-500 ${
            bloqueado
              ? "bg-gray-100 border-gray-200"
              : estaProcesando
                ? "bg-emerald-500 border-emerald-400 shadow-lg shadow-emerald-200 animate-pulse"
                : estaActivo
                  ? "bg-emerald-100 border-emerald-400"
                  : "bg-gray-50 border-gray-200"
          }`}
        >
          {bloqueado ? (
            <Lock className="h-4 w-4 text-gray-300" />
          ) : estaProcesando ? (
            <Play className="h-4 w-4 text-white" />
          ) : estaActivo ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          ) : (
            <CircleDot className="h-4 w-4 text-gray-300" />
          )}
        </div>
        {!esUltimo && (
          <div
            className={`w-0.5 h-6 ${estaActivo ? "bg-emerald-300" : "bg-gray-200"}`}
          />
        )}
      </div>
      <div className="ml-3 pb-4">
        <p
          className={`text-xs font-semibold ${bloqueado ? "text-gray-300" : estaProcesando ? "text-emerald-700" : estaActivo ? "text-gray-800" : "text-gray-400"}`}
        >
          {paso.id}. {paso.name}
        </p>
        <p className="text-[10px] text-gray-400 mt-0.5 max-w-[180px] truncate">
          {paso.description}
        </p>
      </div>
    </div>
  );
}
