const ICONO_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  Heart,
  Landmark,
  GraduationCap,
  Scale,
  Factory,
  Building2,
  Pill,
  Microscope,
  Stethoscope,
  ShieldCheck,
  Truck,
  ShoppingCart,
  Megaphone,
  Plane,
  Zap,
  Cpu,
  Smartphone,
  Workflow,
  Lock,
  Waves,
  TreePine,
};

/** Renderiza el icono de un nicho por su nombre — lazy, sin crear elementos al nivel del módulo */
function getIcono(nombre: string, className = "h-4 w-4") {
  const Icon = ICONO_MAP[nombre];
  return Icon ? <Icon className={className} /> : null;
}

// Colores por categoría para los badges de categoría
const COLOR_CATEGORIA: Record<string, { bg: string; text: string }> = {
  salud: { bg: "bg-emerald-100", text: "text-emerald-700" },
  financiero: { bg: "bg-amber-100", text: "text-amber-700" },
  educacion: { bg: "bg-blue-100", text: "text-blue-700" },
  legal: { bg: "bg-rose-100", text: "text-rose-700" },
  industrial: { bg: "bg-slate-100", text: "text-slate-700" },
  publico: { bg: "bg-gray-100", text: "text-gray-700" },
  comercio: { bg: "bg-violet-100", text: "text-violet-700" },
  tecnologia: { bg: "bg-cyan-100", text: "text-cyan-700" },
  servicios: { bg: "bg-pink-100", text: "text-pink-700" },
};

const ETIQUETA_CATEGORIA: Record<string, string> = {
  salud: "Salud",
  financiero: "Financiero",
  educacion: "Educación",
  legal: "Legal",
  industrial: "Industrial",
  publico: "Sector Público",
  comercio: "Comercio",
  tecnologia: "Tecnología",
  servicios: "Servicios",
};

// ═══════════════════════════════════════════════════════════════════════════════
// UTILIDADES
// ═══════════════════════════════════════════════════════════════════════════════

function tiempoRelativo(fechaStr: string): string {
  const d = new Date(fechaStr);
  const ahora = new Date();
  const diff = Math.floor((ahora.getTime() - d.getTime()) / 1000);
  if (diff < 60) return `hace ${diff}s`;
  if (diff < 3600) return `hace ${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)}h`;
  return `hace ${Math.floor(diff / 86400)}d`;
}

function formatoTamañoArchivo(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ═══════════════════════════════════════════════════════════════════════════════
// PROPS DEL COMPONENTE
// ═══════════════════════════════════════════════════════════════════════════════

