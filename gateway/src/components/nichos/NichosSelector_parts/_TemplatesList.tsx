"use client";

import { FileText, FileCheck, Sparkles, RefreshCw, Clock, FolderOpen } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { PlantillaNicho } from "./_types";
import { tiempoRelativo } from "./_helpers";

interface TemplatesListProps {
  plantillas: PlantillaNicho[];
  cargandoPlantillas: boolean;
  totalNichos: number;
}

export default function TemplatesList({
  plantillas,
  cargandoPlantillas,
  totalNichos,
}: TemplatesListProps) {
  return (
    <Card className="border-0 shadow-sm overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2">
            <FileText className="h-4 w-4 text-emerald-500" />
            Plantillas Generadas
          </CardTitle>
          <Badge className="bg-emerald-100 text-emerald-700 text-[9px] px-2 py-0 border-0 font-semibold shrink-0">
            {plantillas.length} plantilla{plantillas.length !== 1 ? "s" : ""}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        {cargandoPlantillas ? (
          <div className="py-16 text-center">
            <RefreshCw className="h-8 w-8 text-gray-300 mx-auto mb-3 animate-spin" />
            <p className="text-xs text-gray-400">Cargando plantillas...</p>
          </div>
        ) : plantillas.length === 0 ? (
          <div className="py-16 text-center">
            <Sparkles className="h-12 w-12 text-gray-200 mx-auto mb-3" />
            <p className="text-sm font-medium text-gray-400">Sin plantillas aún</p>
            <p className="text-[10px] text-gray-300 mt-1 max-w-[240px] mx-auto">
              Sube documentos en la zona de carga y Yamil generará las plantillas automáticamente
            </p>
          </div>
        ) : (
          <ScrollArea className="max-h-[520px]">
            <div className="space-y-3 pr-1">
              {plantillas.map((plantilla) => (
                <div
                  key={plantilla.id}
                  className={`rounded-xl border-2 p-4 transition-all overflow-hidden ${
                    plantilla.estado === "lista"
                      ? "border-emerald-200 bg-emerald-50/30"
                      : "border-amber-200 bg-amber-50/30"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                        plantilla.estado === "lista"
                          ? "bg-emerald-100 text-emerald-600"
                          : "bg-amber-100 text-amber-600"
                      }`}
                    >
                      {plantilla.estado === "lista" ? (
                        <FileCheck className="h-5 w-5" />
                      ) : (
                        <FileText className="h-5 w-5" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <p className="text-xs font-bold text-gray-800 truncate">
                          {plantilla.nombre}
                        </p>
                        <Badge
                          className={`text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 ${
                            plantilla.estado === "lista"
                              ? "bg-emerald-100 text-emerald-700"
                              : "bg-amber-100 text-amber-700"
                          }`}
                        >
                          {plantilla.estado === "lista" ? "LISTA" : "BORRADOR"}
                        </Badge>
                      </div>
                      <p className="text-[10px] text-gray-500 line-clamp-2">
                        {plantilla.descripcion}
                      </p>
                      <div className="flex items-center gap-3 mt-2 text-[9px] text-gray-400">
                        <span className="flex items-center gap-1">
                          <FileText className="h-3 w-3 shrink-0" />
                          {plantilla.tipo}
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3 shrink-0" />
                          {tiempoRelativo(plantilla.fechaCreacion)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}

/** Empty state component for when no niche is selected */
export function NichoEmptyState({ totalNichos }: { totalNichos: number }) {
  return (
    <Card className="border-0 shadow-sm overflow-hidden">
      <CardContent className="py-16 text-center">
        <FolderOpen className="h-16 w-16 text-gray-200 mx-auto mb-4" />
        <p className="text-lg font-semibold text-gray-400">
          Seleccione un nicho de industria
        </p>
        <p className="text-sm text-gray-300 mt-1 max-w-[360px] mx-auto">
          Elija uno de los {totalNichos} nichos disponibles para ver su estándar de cumplimiento,
          subir documentos y generar plantillas con el agente Yamil.
        </p>
      </CardContent>
    </Card>
  );
}
