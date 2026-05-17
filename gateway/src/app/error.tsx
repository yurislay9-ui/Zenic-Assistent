"use client";

// Zenic-Agents v3.0 — Error Boundary
// Captura errores de renderizado y permite recovery sin crash total.

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log del error para debugging — solo en desarrollo
    if (process.env.NODE_ENV === "development") {
      console.error("[Zenic Error Boundary]", error);
    }
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0F1225]">
      <div className="text-center space-y-6 max-w-md px-6">
        <div className="flex justify-center">
          <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center">
            <AlertTriangle className="h-8 w-8 text-red-400" />
          </div>
        </div>
        <div className="space-y-2">
          <h2 className="text-xl font-bold text-white">
            Error del Sistema
          </h2>
          <p className="text-white/50 text-sm">
            Se produjo un error inesperado en el motor del dashboard.
            Los datos no se han perdido.
          </p>
          {process.env.NODE_ENV === "development" && (
            <p className="text-red-400/70 text-xs font-mono mt-2 break-all">
              {error.message}
            </p>
          )}
        </div>
        <Button
          onClick={reset}
          className="bg-emerald-600 hover:bg-emerald-700 text-white"
        >
          <RefreshCw className="h-4 w-4 mr-2" />
          Reintentar
        </Button>
      </div>
    </div>
  );
}
