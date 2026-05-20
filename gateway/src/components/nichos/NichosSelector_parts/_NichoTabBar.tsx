"use client";

import { CheckCircle2, FolderOpen } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { NichoIndustrial } from "./_types";
import { COLOR_CATEGORIA } from "./_helpers";

interface NichoTabBarProps {
  nichos: NichoIndustrial[];
  nichoSeleccionado: string | null;
  nichoActual: NichoIndustrial | null;
  onSeleccionar: (nichoId: string) => void;
  tabScrollRef: React.RefObject<HTMLDivElement | null>;
}

export default function NichoTabBar({
  nichos,
  nichoSeleccionado,
  nichoActual,
  onSeleccionar,
  tabScrollRef,
}: NichoTabBarProps) {
  return (
    <Card className="border-0 shadow-sm overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2">
            <FolderOpen className="h-4 w-4 text-amber-500" />
            Nichos de Industria
          </CardTitle>
          <Badge className="bg-amber-100 text-amber-700 text-[9px] px-2 py-0 border-0 font-semibold shrink-0">
            {nichos.length} disponibles
          </Badge>
        </div>
        <p className="text-[10px] text-gray-400">
          Seleccione su industria para ver las reglas de cumplimiento y generar plantillas
        </p>
      </CardHeader>
      <CardContent>
        {/* Indicador de nicho activo (móvil) */}
        {nichoActual && (
          <div className="md:hidden flex items-center gap-2 mb-2 px-1">
            <span className="text-lg shrink-0">{nichoActual.emoji}</span>
            <span className="text-xs font-bold text-gray-800 truncate">{nichoActual.nombre}</span>
            <Badge className={`text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 ${COLOR_CATEGORIA[nichoActual.categoria]?.bg || "bg-gray-100"} ${COLOR_CATEGORIA[nichoActual.categoria]?.text || "text-gray-600"}`}>
              {nichoActual.standard}
            </Badge>
          </div>
        )}

        {/* Barra de tabs scrollable — visible en TODAS las pantallas */}
        <div ref={tabScrollRef}>
          <div
            className="flex gap-1 overflow-x-auto pb-2 scrollbar-thin relative"
            style={{
              WebkitOverflowScrolling: "touch",
              scrollbarWidth: "thin",
              maskImage: "linear-gradient(to right, black 90%, transparent 100%)",
              WebkitMaskImage: "linear-gradient(to right, black 90%, transparent 100%)",
            }}
          >
            {nichos.map((nicho) => {
              const activo = nichoSeleccionado === nicho.id;
              return (
                <button
                  key={nicho.id}
                  data-nicho={nicho.id}
                  onClick={() => onSeleccionar(nicho.id)}
                  className={`flex items-center gap-1.5 rounded-lg whitespace-nowrap transition-all shrink-0 ${
                    activo
                      ? "bg-[#1A1D2E] text-white shadow-md"
                      : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                  } ${
                    "px-2 py-1.5 text-[10px] md:px-3 md:py-2 md:text-xs md:gap-2"
                  }`}
                >
                  <span className="text-xs md:text-sm">{nicho.emoji}</span>
                  <span className="truncate max-w-[80px] md:max-w-[130px]">{nicho.nombre}</span>
                  {activo && (
                    <CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
