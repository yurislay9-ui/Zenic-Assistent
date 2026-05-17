import Link from "next/link";
import { Shield, Home } from "lucide-react";
import { Button } from "@/components/ui/button";

// Zenic-Agents v3.0 — 404 Not Found

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0F1225]">
      <div className="text-center space-y-6 max-w-md px-6">
        <div className="flex justify-center">
          <div className="w-20 h-20 rounded-full bg-white/5 flex items-center justify-center">
            <Shield className="h-10 w-10 text-white/20" />
          </div>
        </div>
        <div className="space-y-2">
          <h2 className="text-6xl font-bold text-white/10">404</h2>
          <p className="text-white/50 text-sm">
            Ruta no encontrada. El gateway no reconoce esta dirección.
          </p>
        </div>
        <Link href="/">
          <Button className="bg-emerald-600 hover:bg-emerald-700 text-white">
            <Home className="h-4 w-4 mr-2" />
            Volver al Dashboard
          </Button>
        </Link>
      </div>
    </div>
  );
}
