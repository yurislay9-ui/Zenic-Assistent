import { Badge } from "@/components/ui/badge";

export function getStatusBadge(status: string) {
  switch (status) {
    case "valid":
      return <Badge className="text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 bg-emerald-100 text-emerald-700">VÁLIDA</Badge>;
    case "invalid":
      return <Badge className="text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 bg-red-100 text-red-700">INVÁLIDA</Badge>;
    case "error":
      return <Badge className="text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 bg-amber-100 text-amber-700">ERROR</Badge>;
    default:
      return <Badge className="text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 bg-gray-100 text-gray-500">SIN PROBAR</Badge>;
  }
}

export function getServerStatusBadge(status: string) {
  switch (status) {
    case "active":
      return <Badge className="text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 bg-emerald-100 text-emerald-700">ACTIVO</Badge>;
    case "unhealthy":
      return <Badge className="text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 bg-amber-100 text-amber-700">DEGRADADO</Badge>;
    case "offline":
      return <Badge className="text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 bg-red-100 text-red-700">OFFLINE</Badge>;
    default:
      return <Badge className="text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 bg-gray-100 text-gray-500">{status.toUpperCase()}</Badge>;
  }
}

export function getApiGroupColor(color: string): { bg: string; text: string; border: string; iconBg: string } {
  const map: Record<string, { bg: string; text: string; border: string; iconBg: string }> = {
    emerald: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200", iconBg: "bg-emerald-100" },
    teal: { bg: "bg-teal-50", text: "text-teal-700", border: "border-teal-200", iconBg: "bg-teal-100" },
    amber: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200", iconBg: "bg-amber-100" },
    rose: { bg: "bg-rose-50", text: "text-rose-700", border: "border-rose-200", iconBg: "bg-rose-100" },
    sky: { bg: "bg-sky-50", text: "text-sky-700", border: "border-sky-200", iconBg: "bg-sky-100" },
    violet: { bg: "bg-violet-50", text: "text-violet-700", border: "border-violet-200", iconBg: "bg-violet-100" },
    orange: { bg: "bg-orange-50", text: "text-orange-700", border: "border-orange-200", iconBg: "bg-orange-100" },
    pink: { bg: "bg-pink-50", text: "text-pink-700", border: "border-pink-200", iconBg: "bg-pink-100" },
    slate: { bg: "bg-slate-50", text: "text-slate-700", border: "border-slate-200", iconBg: "bg-slate-100" },
    gray: { bg: "bg-gray-50", text: "text-gray-700", border: "border-gray-200", iconBg: "bg-gray-100" },
    indigo: { bg: "bg-indigo-50", text: "text-indigo-700", border: "border-indigo-200", iconBg: "bg-indigo-100" },
  };
  return map[color] || map.gray;
}
