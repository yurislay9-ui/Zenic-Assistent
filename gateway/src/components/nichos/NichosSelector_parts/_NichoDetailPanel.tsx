"use client";

import { ShieldCheck, AlertTriangle, Lock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { NichoIndustrial } from "./_types";
import { COLOR_CATEGORIA, ETIQUETA_CATEGORIA } from "./_helpers";

interface NichoDetailPanelProps {
  nicho: NichoIndustrial;
  animacionActiva: boolean;
}

export default function NichoDetailPanel({ nicho, animacionActiva }: NichoDetailPanelProps) {
  return (
    <div
      key={nicho.id}
      className={`space-y-6 transition-all duration-300 ease-out ${
        animacionActiva
          ? "opacity-100 translate-y-0"
          : "opacity-0 translate-y-2"
      }`}
    >
      {/* Estándar de Cumplimiento */}
      <Card className="border-0 shadow-sm overflow-hidden">
        <CardContent className="p-5">
          <div className="flex flex-col sm:flex-row sm:items-start gap-4">
            {/* Icono grande */}
            <div className={`w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 ${
              COLOR_CATEGORIA[nicho.categoria]?.bg || "bg-gray-100"
            }`}>
              <span className="text-2xl">{nicho.emoji}</span>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <h3 className="text-base font-bold text-gray-900 truncate">
                  {nicho.nombre}
                </h3>
                <Badge className={`text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 ${COLOR_CATEGORIA[nicho.categoria]?.bg || "bg-gray-100"} ${COLOR_CATEGORIA[nicho.categoria]?.text || "text-gray-600"}`}>
                  {ETIQUETA_CATEGORIA[nicho.categoria] || nicho.categoria}
                </Badge>
              </div>
              {/* Caja de estándar */}
              <div className="bg-amber-50 rounded-xl p-4 mt-3 overflow-hidden">
                <p className="text-[10px] font-semibold text-amber-600 uppercase tracking-wider mb-1">
                  Estándar de Cumplimiento
                </p>
                <p className="text-sm font-bold text-amber-800">
                  {nicho.standardNombre}
                </p>
                <p className="text-[10px] text-amber-600 mt-1">
                  {nicho.standard} — {nicho.standardDescripcion}
                </p>
              </div>
            </div>
          </div>

          <Separator className="my-4" />

          {/* Reglas de Dominio del Experto */}
          <div>
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Reglas de Seguridad Aplicadas
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {nicho.reglas.map((regla, idx) => (
                <div
                  key={idx}
                  className="flex items-start gap-2 bg-gray-50 rounded-lg p-2.5"
                >
                  <ShieldCheck className="h-3.5 w-3.5 text-emerald-500 shrink-0 mt-0.5" />
                  <span className="text-[11px] text-gray-600 leading-tight">
                    {regla}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* DENY Absolutos */}
          {nicho.denyAbsolutos.length > 0 && (
            <div className="mt-4">
              <p className="text-[10px] font-semibold text-red-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                <AlertTriangle className="h-3.5 w-3.5" />
                Denegaciones Absolutas — Bloqueadas desde la Raíz
              </p>
              <div className="space-y-2">
                {nicho.denyAbsolutos.map((deny, idx) => (
                  <div
                    key={idx}
                    className="flex items-start gap-2 bg-red-50 border border-red-100 rounded-lg p-2.5"
                  >
                    <Lock className="h-3.5 w-3.5 text-red-500 shrink-0 mt-0.5" />
                    <span className="text-[11px] text-red-700 font-medium leading-tight">
                      {deny}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
