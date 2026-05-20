"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { type ApiGroup } from "./_constants";
import { getApiGroupColor } from "./_helpers";

export function ApiGroupCard({ group }: { group: ApiGroup }) {
  const [expandido, setExpandido] = useState(false);
  const colors = getApiGroupColor(group.color);
  const Icon = group.icon;

  return (
    <Card className="border-0 shadow-sm overflow-hidden hover:shadow-md transition-shadow">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className={`w-9 h-9 rounded-lg ${colors.iconBg} flex items-center justify-center shrink-0`}>
              <Icon className={`h-4.5 w-4.5 ${colors.text}`} />
            </div>
            <div className="min-w-0">
              <CardTitle className="text-xs font-bold text-gray-900 truncate">
                {group.nombre}
              </CardTitle>
              <p className="text-[10px] text-gray-400 font-mono truncate">
                {group.basePath}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Badge className="text-[8px] px-1.5 py-0 border-0 font-bold bg-gray-100 text-gray-600">
              {group.endpoints} endpoints
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-3 space-y-2">
        <p className="text-[10px] text-gray-500 leading-relaxed line-clamp-2">
          {group.descripcion}
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          {group.auth.map((a) => (
            <Badge key={a} className="text-[7px] px-1.5 py-0 border font-semibold shrink-0" variant="outline">
              {a === "api_key" ? "🔑 API KEY" : a === "bearer" ? "🎫 BEARER" : a.toUpperCase()}
            </Badge>
          ))}
          <div className="flex items-center gap-1">
            {group.metodos.map((m) => (
              <span key={m} className={`text-[7px] font-bold px-1 py-0.5 rounded ${m === "GET" ? "bg-emerald-50 text-emerald-600" : m === "POST" ? "bg-blue-50 text-blue-600" : m === "PUT" ? "bg-amber-50 text-amber-600" : m === "DELETE" ? "bg-red-50 text-red-600" : "bg-gray-50 text-gray-600"}`}>
                {m}
              </span>
            ))}
          </div>
        </div>

        <button onClick={() => setExpandido(!expandido)} className="flex items-center gap-1 text-[9px] text-gray-400 hover:text-gray-600 transition-colors w-full">
          {expandido ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          {expandido ? "Ocultar rutas" : `Ver ${group.rutas.length} rutas`}
        </button>

        {expandido && (
          <div className="space-y-1 pt-1 border-t border-gray-100">
            {group.rutas.map((ruta, idx) => {
              const methodMatch = ruta.match(/^(GET|POST|PUT|DELETE|PATCH)/);
              const method = methodMatch ? methodMatch[1] : "";
              const path = ruta.replace(/^(GET|POST|PUT|DELETE|PATCH)\s+/, "").split(" — ");
              const methodColor = method === "GET" ? "text-emerald-600" : method === "POST" ? "text-blue-600" : method === "PUT" ? "text-amber-600" : method === "DELETE" ? "text-red-600" : "text-gray-500";
              return (
                <div key={idx} className="flex items-start gap-2 py-1 text-[9px]">
                  <span className={`font-bold shrink-0 w-10 ${methodColor}`}>{method}</span>
                  <div className="min-w-0">
                    <span className="font-mono text-gray-600">{path[0]}</span>
                    {path[1] && <span className="text-gray-400 ml-1">— {path[1]}</span>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
