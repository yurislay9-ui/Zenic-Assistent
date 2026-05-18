"use client";

import React, { useEffect, useState, useCallback, useRef, useMemo } from "react";
import {
  LayoutDashboard,
  Gavel,
  Vault,
  Settings,
  User,
  LogOut,
  ChevronDown,
  ChevronRight,
  Cpu,
  Activity,
  Shield,
  ShieldCheck,
  Lock,
  FolderOpen,
  Key,
  RefreshCw,
  CheckCircle2,
  TrendingUp,
  Play,
  Hash,
  AlertTriangle,
  ArrowUpRight,
  Eye,
  XCircle,
  FileCheck,
  FileSearch,
  FileLock,
  Timer,
  Scale as ScaleIcon,
  Crown,
  CircleDot,
} from "lucide-react";
import NichosSelector from "@/components/nichos/NichosSelector";
import ApisMcpTab from "@/components/apis-mcp/ApisMcpTab";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { FEATURE_TIER_MAP } from "@/lib/pricing-engine/types";
import type { FeatureName } from "@/lib/pricing-engine/types";

import type {
  MetricasDashboard,
  PropuestaMemoria,
  AlertaSNA,
  EntradaLedger,
  EstadoPipeline,
  CapaDefensa,
  ReglaDenegacion,
  DatosROI,
  Nicho,
  ItemActividad,
  EvidenciaHITL,
  PlantillaNicho,
  ArchivoSubido,
  ContextoSuscripcion,
  ItemNav,
  EstadoMonitorSNA,
} from "./_page_parts/types";
import { construirContextoSuscripcion } from "./_page_parts/constants";
import {
  tiempoRelativo,
  truncarHash,
  formatoMoneda,
  formatoTimestamp,
  formatoTamañoArchivo,
  categoriaColor,
  iconoCapa,
  calcularMonitoresSNA,
} from "./_page_parts/utils";
import { MicroIndicadorSNA } from "./_page_parts/components/MicroIndicadorSNA";
import { WidgetBloqueado } from "./_page_parts/components/WidgetBloqueado";
import { PasoPipelineViz } from "./_page_parts/components/PasoPipelineViz";
import { ContadorConsumoPlan } from "./_page_parts/components/ContadorConsumoPlan";

export default function PaginaDashboard() {
  const [metricas, setMetricas] = useState<MetricasDashboard | null>(null);
  const [propuestas, setPropuestas] = useState<PropuestaMemoria[]>([]);
  const [alertasSNA, setAlertasSNA] = useState<AlertaSNA[]>([]);
  const [ledger, setLedger] = useState<EntradaLedger[]>([]);
  const [pipeline, setPipeline] = useState<EstadoPipeline | null>(null);
  const [capas, setCapas] = useState<CapaDefensa[]>([]);
  const [reglasDenegacion, setReglasDenegacion] = useState<ReglaDenegacion[]>([]);
  const [roi, setROI] = useState<DatosROI | null>(null);
  const [nichos, setNichos] = useState<Nicho[]>([]);
  const [actividades, setActividades] = useState<ItemActividad[]>([]);
  const [placaActiva, setPlacaActiva] = useState("comando");
  const [navExpandido, setNavExpandido] = useState<string[]>(["POLÍTICAS", "INTEGRACIONES"]);
  const [navActivo, setNavActivo] = useState("CENTRO DE COMANDO");
  const [cargando, setCargando] = useState(true);
  const [propuestaSeleccionada, setPropuestaSeleccionada] = useState<string | null>(null);
  const [evidencia, setEvidencia] = useState<EvidenciaHITL | null>(null);
  const [cargandoEvidencia, setCargandoEvidencia] = useState(false);
  const [checkEvidencia, setCheckEvidencia] = useState(false);
  const [justificacion, setJustificacion] = useState("");
  const [checkRiesgo, setCheckRiesgo] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [sosteniendoBoton, setSosteniendoBoton] = useState(false);
  const sostenidoRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [nichoSeleccionado, setNichoSeleccionado] = useState<string | null>(null);
  const [plantillas, setPlantillas] = useState<PlantillaNicho[]>([]);
  const [archivosSubidos, setArchivosSubidos] = useState<ArchivoSubido[]>([]);
  const [subiendoArchivos, setSubiendoArchivos] = useState(false);
  const [cargandoPlantillas, setCargandoPlantillas] = useState(false);
  const inputArchivosRef = useRef<HTMLInputElement>(null);
  const [dragActivo, setDragActivo] = useState(false);
  const [ultimaActualizacion, setUltimaActualizacion] = useState<Date | null>(null);

  const ctxSuscripcion = useMemo(() => construirContextoSuscripcion("enterprise"), []);
  const featureDisponible = useCallback((feature: FeatureName): boolean => {
    const tiers = FEATURE_TIER_MAP[feature];
    return tiers?.includes(ctxSuscripcion.tier) ?? false;
  }, [ctxSuscripcion.tier]);
  const monitoresSNA = useMemo(() => calcularMonitoresSNA(metricas), [metricas]);

  const itemsNav: ItemNav[] = useMemo(() => [
    { label: "CENTRO DE COMANDO", icon: <LayoutDashboard className="h-4 w-4" />, subtexto: "Activo" },
    { label: "ARBITRAJE", icon: <Gavel className="h-4 w-4" />, subtexto: metricas?.pendingApprovals ?? 0 > 0 ? `${metricas?.pendingApprovals ?? 0} Pendientes` : "Sin pendientes", badge: (metricas?.pendingApprovals ?? 0) > 0 ? String(metricas?.pendingApprovals ?? 0) : undefined, badgeColor: "bg-amber-500" },
    { label: "BÓVEDA DE SEGURIDAD", icon: <Vault className="h-4 w-4" /> },
    { label: "NICHOS Y PLANTILLAS", icon: <FolderOpen className="h-4 w-4" />, subtexto: `${nichos.length} nichos` },
    { label: "APIS & MCP", icon: <Key className="h-4 w-4" />, subtexto: "Conexiones" },
    { label: "POLÍTICAS", icon: <Shield className="h-4 w-4" />, children: [
      { label: "Reglas de Seguridad" },
      { label: "Aprobaciones de Arbitraje", badge: (metricas?.pendingApprovals ?? 0) > 0 ? String(metricas?.pendingApprovals ?? 0) : undefined, badgeColor: "bg-red-500" },
      { label: "Registro de Auditoría", bloqueado: !featureDisponible("AuditMerkleChain" as FeatureName), tierRequerido: "Business" },
    ]},
    { label: "INTEGRACIONES", icon: <Activity className="h-4 w-4" />, children: [
      { label: "Conexiones de Herramientas", bloqueado: !featureDisponible("McpCustomTools" as FeatureName), tierRequerido: "Business" },
      { label: "Herramientas" },
    ]},
    { label: "CONFIGURACIÓN", icon: <Settings className="h-4 w-4" /> },
    { label: "PERFIL", icon: <User className="h-4 w-4" /> },
    { label: "CERRAR SESIÓN", icon: <LogOut className="h-4 w-4" /> },
  ], [metricas?.pendingApprovals, featureDisponible, nichos.length]);

  const cargarTodo = useCallback(async () => {
    const controller = new AbortController();
    const signal = controller.signal;
    const urls = ["/api/dashboard/metrics","/api/dashboard/memory-proposals","/api/dashboard/sna-alerts","/api/dashboard/ledger","/api/dashboard/pipeline-status","/api/dashboard/defense-layers","/api/dashboard/deny-rules","/api/dashboard/roi","/api/dashboard/niches","/api/dashboard/activity"];
    const resultados = await Promise.allSettled(urls.map((url) => fetch(url, { signal }).catch(() => null)));
    const [resMetricas, resPropuestas, resSNA, resLedger, resPipeline, resCapas, resReglas, resROI, resNichos, resActividad] = resultados;
    try { if (resMetricas.status === "fulfilled" && resMetricas.value.ok) setMetricas(await resMetricas.value.json()); } catch { /* ignorar */ }
    try { if (resPropuestas.status === "fulfilled" && resPropuestas.value.ok) { const p = await resPropuestas.value.json(); setPropuestas(p.proposals || []); } } catch { /* ignorar */ }
    try { if (resSNA.status === "fulfilled" && resSNA.value.ok) { const s = await resSNA.value.json(); setAlertasSNA(s.alerts || []); } } catch { /* ignorar */ }
    try { if (resLedger.status === "fulfilled" && resLedger.value.ok) { const l = await resLedger.value.json(); setLedger(l.entries || []); } } catch { /* ignorar */ }
    try { if (resPipeline.status === "fulfilled" && resPipeline.value.ok) setPipeline(await resPipeline.value.json()); } catch { /* ignorar */ }
    try { if (resCapas.status === "fulfilled" && resCapas.value.ok) { const c = await resCapas.value.json(); setCapas(c.layers || []); } } catch { /* ignorar */ }
    try { if (resReglas.status === "fulfilled" && resReglas.value.ok) { const r = await resReglas.value.json(); setReglasDenegacion(r.rules || []); } } catch { /* ignorar */ }
    try { if (resROI.status === "fulfilled" && resROI.value.ok) setROI(await resROI.value.json()); } catch { /* ignorar */ }
    try { if (resNichos.status === "fulfilled" && resNichos.value.ok) { const n = await resNichos.value.json(); setNichos(n.niches || []); } } catch { /* ignorar */ }
    try { if (resActividad.status === "fulfilled" && resActividad.value.ok) { const a = await resActividad.value.json(); setActividades(a.activities || []); } } catch { /* ignorar */ }
    setUltimaActualizacion(new Date());
    setCargando(false);
  }, []);

  useEffect(() => { cargarTodo(); const intervalo = setInterval(() => { cargarTodo(); }, 15000); return () => { clearInterval(intervalo); }; }, [cargarTodo]);

  const cargarPlantillas = useCallback(async (nichoId: string) => { setCargandoPlantillas(true); try { const res = await fetch(`/api/dashboard/niche-templates?nichoId=${nichoId}`); if (res.ok) { const data = await res.json(); setPlantillas(data.plantillas || []); } } catch (err) { console.error("Error cargando plantillas:", err); setPlantillas([]); } finally { setCargandoPlantillas(false); } }, []);
  const cargarArchivos = useCallback(async (nichoId: string) => { try { const res = await fetch(`/api/dashboard/niche-templates?nichoId=${nichoId}&estado=archivos`); if (res.ok) { const data = await res.json(); setArchivosSubidos(data.archivos || []); } } catch (err) { console.error("Error cargando archivos:", err); setArchivosSubidos([]); } }, []);
  const seleccionarNicho = useCallback((nichoId: string) => { if (nichoSeleccionado === nichoId) { setNichoSeleccionado(null); setPlantillas([]); setArchivosSubidos([]); return; } setNichoSeleccionado(nichoId); cargarPlantillas(nichoId); cargarArchivos(nichoId); }, [nichoSeleccionado, cargarPlantillas, cargarArchivos]);
  const subirArchivos = useCallback(async (archivos: FileList | File[]) => { if (!nichoSeleccionado) return; setSubiendoArchivos(true); try { const formData = new FormData(); formData.append("nichoId", nichoSeleccionado); Array.from(archivos).forEach((archivo) => { formData.append("archivos", archivo); }); const res = await fetch("/api/dashboard/niche-templates", { method: "POST", body: formData }); if (res.ok) { cargarPlantillas(nichoSeleccionado); cargarArchivos(nichoSeleccionado); } } catch (err) { console.error("Error subiendo archivos:", err); } finally { setSubiendoArchivos(false); } }, [nichoSeleccionado, cargarPlantillas, cargarArchivos]);
  const manejarDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); if (nichoSeleccionado) setDragActivo(true); }, [nichoSeleccionado]);
  const manejarDragLeave = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setDragActivo(false); }, []);
  const manejarDrop = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setDragActivo(false); if (e.dataTransfer.files && e.dataTransfer.files.length > 0 && nichoSeleccionado) { subirArchivos(e.dataTransfer.files); } }, [nichoSeleccionado, subirArchivos]);
  const manejarInputArchivos = useCallback((e: React.ChangeEvent<HTMLInputElement>) => { if (e.target.files && e.target.files.length > 0) { subirArchivos(e.target.files); if (inputArchivosRef.current) { inputArchivosRef.current.value = ""; } } }, [subirArchivos]);

  const cargarEvidencia = useCallback(async (requestId: string) => { setCargandoEvidencia(true); setPropuestaSeleccionada(requestId); setCheckEvidencia(false); setJustificacion(""); setCheckRiesgo(false); const controller = new AbortController(); try { const res = await fetch(`/api/dashboard/hitl-evidence?requestId=${requestId}`, { signal: controller.signal }); if (res.ok) { setEvidencia(await res.json()); } } catch (err) { if (err instanceof DOMException && err.name === "AbortError") return; console.error("Error cargando evidencia:", err); } finally { setCargandoEvidencia(false); } return () => controller.abort(); }, []);

  const manejarAccionHITL = useCallback(async (requestId: string, accion: "approve" | "reject") => { setEnviando(true); try { const controller = new AbortController(); const res = await fetch(`/api/v1/hitl/${requestId}/${accion}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ justification: justificacion, admin_evidence_review: checkEvidencia, risk_acknowledgment: checkRiesgo }), signal: controller.signal }); if (res.ok) { setPropuestas((prev) => prev.filter((p) => p.requestId !== requestId)); setPropuestaSeleccionada(null); setEvidencia(null); setCheckEvidencia(false); setJustificacion(""); setCheckRiesgo(false); } } catch (err) { if (err instanceof DOMException && err.name === "AbortError") return; console.error("Error en acción HITL:", err); } finally { setEnviando(false); setSosteniendoBoton(false); } }, [justificacion, checkEvidencia, checkRiesgo]);

  const botonHabilitado = checkEvidencia && justificacion.length >= 50 && checkRiesgo;
  const iniciarSosten = () => { if (!botonHabilitado) return; setSosteniendoBoton(true); sostenidoRef.current = setTimeout(() => { if (evidencia) { manejarAccionHITL(evidencia.requestId, "approve"); } }, 1500); };
  const cancelarSosten = () => { setSosteniendoBoton(false); if (sostenidoRef.current) { clearTimeout(sostenidoRef.current); sostenidoRef.current = null; } };
  const alternarNav = (label: string) => { setNavExpandido((prev) => prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label]); };
  const manejarNav = (label: string) => { if (label === "CENTRO DE COMANDO") setPlacaActiva("comando"); else if (label === "ARBITRAJE") setPlacaActiva("arbitraje"); else if (label === "BÓVEDA DE SEGURIDAD") setPlacaActiva("boveda"); else if (label === "NICHOS Y PLANTILLAS") setPlacaActiva("nichos"); else if (label === "APIS & MCP") setPlacaActiva("apis"); else if (label === "POLÍTICAS") setPlacaActiva("comando"); else if (label === "INTEGRACIONES") setPlacaActiva("apis"); setNavActivo(label); };

  if (cargando) {
    return (<div className="min-h-screen flex items-center justify-center bg-[#0F1225]"><div className="text-center space-y-4"><div className="relative"><Cpu className="h-12 w-12 text-emerald-400 mx-auto animate-pulse" /></div><p className="text-white/60 text-sm tracking-widest uppercase">Iniciando Motor Zenic...</p><div className="flex items-center justify-center gap-2"><div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce [animation-delay:-0.3s]" /><div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce [animation-delay:-0.15s]" /><div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce" /></div></div></div>);
  }

  return (
    <div className="min-h-screen flex bg-[#F8F9FA]">
      {/* BARRA LATERAL */}
      <aside className="hidden md:flex w-64 bg-[#1A1D2E] text-white flex-col min-h-screen shrink-0">
        <div className="px-5 py-5 border-b border-white/10"><div className="flex items-center justify-between"><div><h1 className="text-lg font-bold tracking-wider">ZENIC</h1><p className="text-[11px] text-white/40 tracking-widest uppercase">Plataforma Empresarial</p></div><div className="flex items-center gap-1.5"><span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" /><span className="text-[10px] text-emerald-400">En línea</span></div></div></div>
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {itemsNav.map((item) => (
            <div key={item.label}>
              <button onClick={() => { if (item.children) { alternarNav(item.label); } else { manejarNav(item.label); } }} className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors ${navActivo === item.label ? "bg-white/10 text-white" : "text-white/60 hover:bg-white/5 hover:text-white/90"}`}>
                <span className="shrink-0">{item.icon}</span>
                <div className="flex-1 min-w-0"><span className="text-[11px] font-semibold tracking-wider block truncate">{item.label}</span>{item.subtexto && <span className="text-[10px] text-white/35 block truncate">{item.subtexto}</span>}</div>
                {item.badge && <span className={`text-[9px] px-1.5 py-0.5 rounded-full text-white shrink-0 ${item.badgeColor || "bg-amber-500"}`}>{item.badge}</span>}
                {item.children && <ChevronDown className={`h-3.5 w-3.5 shrink-0 transition-transform ${navExpandido.includes(item.label) ? "rotate-180" : ""}`} />}
              </button>
              {item.children && navExpandido.includes(item.label) && (
                <div className="ml-7 mt-1 space-y-0.5">
                  {item.children.map((child) => (
                    <button key={child.label} className={`w-full flex items-center justify-between px-3 py-1.5 text-[11px] rounded transition-colors ${child.bloqueado ? "text-white/20 cursor-not-allowed" : "text-white/45 hover:text-white/90"}`} disabled={child.bloqueado}>
                      <span className="flex items-center gap-1.5 truncate">{child.bloqueado && <Lock className="h-3 w-3 text-white/20 shrink-0" />}<span className="truncate">{child.label}</span></span>
                      {child.badge && !child.bloqueado && <span className={`text-[9px] px-1.5 py-0.5 rounded text-white shrink-0 ${child.badgeColor || "bg-red-500/80"}`}>{child.badge}</span>}
                      {child.bloqueado && <Badge className="bg-white/10 text-white/30 text-[7px] px-1 py-0 border-0 font-bold shrink-0"><Crown className="h-2.5 w-2.5 mr-0.5" />{child.tierRequerido}</Badge>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>
        <div className="px-4 py-4 border-t border-white/10">
          <div className="flex items-center gap-3 mb-3"><div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-400 to-teal-600 flex items-center justify-center text-xs font-bold">AD</div><div className="flex-1 min-w-0"><p className="text-sm font-medium truncate">Administrador</p><p className="text-[10px] text-white/35">Plan {ctxSuscripcion.nombreMostrar}</p></div><button className="text-white/30 hover:text-white/60"><ChevronRight className="h-4 w-4" /></button></div>
          <div className="bg-white/5 rounded-lg p-2.5 overflow-hidden">
            <div className="flex items-center justify-between mb-1.5"><span className="text-[9px] text-white/40 uppercase tracking-wider font-semibold">Nivel de Suscripción</span><Badge className="bg-emerald-500/20 text-emerald-400 text-[8px] px-1.5 py-0 border-0 font-bold shrink-0">{ctxSuscripcion.nombreMostrar}</Badge></div>
            <div className="space-y-1">
              <ContadorConsumoPlan etiqueta="Acciones hoy" actual={metricas?.executionsToday ?? 0} maximo={ctxSuscripcion.limites.max_actions_per_day} unlimited={ctxSuscripcion.limites.max_actions_per_day === 0} />
              <ContadorConsumoPlan etiqueta="Workflows" actual={3} maximo={ctxSuscripcion.limites.max_workflows} unlimited={ctxSuscripcion.limites.max_workflows === 0} />
            </div>
          </div>
        </div>
      </aside>

      {/* CONTENIDO PRINCIPAL */}
      <main className="flex-1 flex flex-col min-h-screen overflow-auto">
        <header className="sticky top-0 z-10 bg-white/80 backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="min-w-0"><h2 className="text-lg sm:text-xl font-bold text-gray-900 truncate">Panel de Control — Zenic v3.0</h2><p className="text-xs text-gray-400 mt-0.5">La IA nunca genera — solo arbitra SÍ/NO</p></div>
            <div className="flex items-center gap-2 shrink-0 flex-wrap">
              <Badge className="bg-emerald-100 text-emerald-700 text-[9px] px-2 py-1 border-0 font-semibold">{ctxSuscripcion.nombreMostrar}</Badge>
              <div className="flex items-center gap-1.5 bg-emerald-50 px-2 py-1 rounded-md"><span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" /><span className="text-[9px] text-emerald-700 font-semibold">En vivo</span></div>
              {ultimaActualizacion && <span className="text-[9px] text-gray-400 font-mono">{formatoTimestamp(ultimaActualizacion)}</span>}
              <Button variant="outline" size="sm" className="h-8 text-xs" onClick={cargarTodo}><RefreshCw className="h-3.5 w-3.5 mr-1" />Actualizar</Button>
            </div>
          </div>
        </header>

        <div className="flex-1 p-4 sm:p-6">
          <Tabs value={placaActiva} onValueChange={setPlacaActiva}>
            <div className="w-full overflow-x-auto mb-6 -mx-4 px-4 sm:mx-0 sm:px-0">
              <TabsList className="grid w-full grid-cols-5 bg-white shadow-sm border h-12 rounded-xl min-w-[580px]">
                <TabsTrigger value="comando" className="text-[10px] sm:text-xs font-semibold tracking-wide data-[state=active]:bg-[#1A1D2E] data-[state=active]:text-white rounded-lg transition-all flex items-center justify-center gap-1 sm:gap-2 overflow-hidden"><LayoutDashboard className="h-4 w-4 shrink-0" /><span className="hidden sm:inline truncate">Centro de Comando</span><span className="sm:hidden truncate">Comando</span></TabsTrigger>
                <TabsTrigger value="arbitraje" className="text-[10px] sm:text-xs font-semibold tracking-wide data-[state=active]:bg-[#1A1D2E] data-[state=active]:text-white rounded-lg transition-all relative flex items-center justify-center gap-1 sm:gap-2 overflow-hidden"><Gavel className="h-4 w-4 shrink-0" /><span className="hidden sm:inline truncate">Estación de Arbitraje</span><span className="sm:hidden truncate">Arbitraje</span>{propuestas.length > 0 && <span className="absolute -top-1 -right-1 w-5 h-5 bg-amber-500 text-white text-[9px] rounded-full flex items-center justify-center font-bold shrink-0">{propuestas.length}</span>}</TabsTrigger>
                <TabsTrigger value="boveda" className="text-[10px] sm:text-xs font-semibold tracking-wide data-[state=active]:bg-[#1A1D2E] data-[state=active]:text-white rounded-lg transition-all flex items-center justify-center gap-1 sm:gap-2 overflow-hidden"><Vault className="h-4 w-4 shrink-0" /><span className="hidden sm:inline truncate">Bóveda de Seguridad</span><span className="sm:hidden truncate">Bóveda</span></TabsTrigger>
                <TabsTrigger value="nichos" className="text-[10px] sm:text-xs font-semibold tracking-wide data-[state=active]:bg-[#1A1D2E] data-[state=active]:text-white rounded-lg transition-all flex items-center justify-center gap-1 sm:gap-2 overflow-hidden"><FolderOpen className="h-4 w-4 shrink-0" /><span className="hidden sm:inline truncate">Nichos y Plantillas</span><span className="sm:hidden truncate">Nichos</span></TabsTrigger>
                <TabsTrigger value="apis" className="text-[10px] sm:text-xs font-semibold tracking-wide data-[state=active]:bg-[#1A1D2E] data-[state=active]:text-white rounded-lg transition-all flex items-center justify-center gap-1 sm:gap-2 overflow-hidden"><Key className="h-4 w-4 shrink-0" /><span className="hidden sm:inline truncate">APIs & MCP</span><span className="sm:hidden truncate">APIs</span></TabsTrigger>
              </TabsList>
            </div>

            {/* PLACA 1: CENTRO DE COMANDO */}
            <TabsContent value="comando" className="space-y-6">
              <Card className="border-0 shadow-sm overflow-hidden"><CardHeader className="pb-2"><CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2"><Activity className="h-4 w-4 text-emerald-500" />Salud del Sistema — Monitores Autónomos</CardTitle></CardHeader><CardContent><div className="grid grid-cols-1 md:grid-cols-3 gap-4 py-2">{monitoresSNA.map((monitor) => (<MicroIndicadorSNA key={monitor.tipo} monitor={monitor} />))}</div>{alertasSNA.length > 0 && (<div className="mt-4 space-y-2"><p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Alertas activas</p><ScrollArea className="max-h-32">{alertasSNA.slice(0, 5).map((alerta) => (<div key={alerta.id} className="flex items-center gap-2 py-1.5"><AlertTriangle className={`h-3.5 w-3.5 shrink-0 ${alerta.severity === "critical" ? "text-red-500" : alerta.severity === "error" ? "text-orange-500" : "text-amber-500"}`} /><span className="text-xs text-gray-600 flex-1 truncate">{alerta.details || alerta.action}</span><span className="text-[10px] text-gray-400 shrink-0">{tiempoRelativo(alerta.createdAt)}</span></div>))}</ScrollArea></div>)}</CardContent></Card>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <Card className="border-0 shadow-sm overflow-hidden"><CardContent className="p-5"><div className="flex items-center justify-between mb-4"><p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider truncate">Registro de Integridad</p>{featureDisponible("AuditMerkleChain" as FeatureName) ? <Badge className="bg-emerald-100 text-emerald-700 text-[8px] px-1.5 py-0 border-0 font-bold shrink-0">BLAKE3</Badge> : <Badge className="bg-gray-100 text-gray-400 text-[8px] px-1.5 py-0 border-0 font-bold shrink-0">BÁSICO</Badge>}</div><div className="flex items-center gap-3 mb-4"><div className="w-12 h-12 rounded-xl bg-emerald-50 flex items-center justify-center shrink-0">{featureDisponible("AuditMerkleChain" as FeatureName) ? <FileLock className="h-6 w-6 text-emerald-600" /> : <FileSearch className="h-6 w-6 text-gray-400" />}</div><div className="min-w-0"><p className="text-sm font-bold text-emerald-700 truncate">{featureDisponible("AuditMerkleChain" as FeatureName) ? "VERIFICADA" : "REGISTRO BÁSICO"}</p><p className="text-[10px] text-gray-400 truncate">{featureDisponible("AuditMerkleChain" as FeatureName) ? "Cadena de auditoría inmutable (BLAKE3)" : "Actualiza a Business para cadena completa"}</p></div></div>{featureDisponible("AuditMerkleChain" as FeatureName) ? (<div className="space-y-1.5"><div className="flex items-center justify-between text-[10px]"><span className="text-gray-400">Entradas en cadena</span><span className="font-semibold text-gray-600 shrink-0">{ledger.length}</span></div><div className="flex items-center justify-between text-[10px]"><span className="text-gray-400">Último sello</span><span className="font-mono text-gray-500 text-[9px] truncate ml-2">{ledger.length > 0 ? truncarHash(ledger[0].contentHash) : "—"}</span></div><div className="flex items-center gap-1.5 mt-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" /><span className="text-[10px] text-emerald-600 font-semibold truncate">Integridad criptográfica confirmada</span></div></div>) : (<WidgetBloqueado etiqueta="Cadena de Registro Completa" descripcion="Registro inmutable con verificación BLAKE3" tierRequerido="business" />)}</CardContent></Card>

                <Card className="border-0 shadow-sm lg:col-span-2 overflow-hidden"><CardHeader className="pb-2"><div className="flex items-center justify-between"><CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2"><Play className="h-4 w-4 text-emerald-500" />Flujo de Procesamiento en Vivo</CardTitle><div className="flex items-center gap-2 shrink-0"><span className={`w-2 h-2 rounded-full ${pipeline?.isActive ? "bg-emerald-500 animate-pulse" : "bg-gray-300"}`} /><span className="text-[10px] text-gray-400 font-medium">{pipeline?.isActive ? "Procesando" : "En espera"}</span></div></div></CardHeader><CardContent><div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-0 py-2">{pipeline?.steps.map((paso, idx) => { const bloqueado = paso.id === 9 && !featureDisponible("PolicySimulation" as FeatureName); return (<PasoPipelineViz key={paso.id} paso={paso} esActual={paso.id === pipeline.currentStep} esUltimo={idx === pipeline.steps.length - 1 || idx === Math.floor(pipeline.steps.length / 2) - 1} bloqueado={bloqueado} />); })}</div><div className="mt-4 pt-3 border-t border-gray-100 flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-4 text-[10px]"><span className="text-gray-400">Procesadas: <span className="font-semibold text-gray-600">{pipeline?.totalProcessed ?? 0}</span></span><span className="text-emerald-600">Exitosas: <span className="font-semibold">{pipeline?.completedCount ?? 0}</span></span><span className="text-red-500">Bloqueadas: <span className="font-semibold">{pipeline?.deniedCount ?? 0}</span></span></div><div className="flex items-center gap-1.5"><Timer className="h-3 w-3 text-gray-400" /><span className="text-[10px] text-gray-400">Ciclo: ~{pipeline?.cycleTime ?? 90}s</span></div></div></CardContent></Card>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <Card className="border-0 shadow-sm overflow-hidden"><CardContent className="p-5"><p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider truncate">Agentes Activos</p><p className="text-3xl font-bold text-gray-900 mt-1">{metricas?.activeAgents ?? "—"}</p></CardContent></Card>
                <Card className="border-0 shadow-sm overflow-hidden"><CardContent className="p-5"><p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider truncate">Acciones Bloqueadas</p><p className="text-3xl font-bold text-gray-900 mt-1">{metricas?.securityGateBlocks ?? "—"}</p><p className="text-[10px] text-gray-400 mt-1 truncate">No autorizadas y denegadas</p></CardContent></Card>
                <Card className="border-0 shadow-sm bg-emerald-50/50 overflow-hidden"><CardContent className="p-5"><p className="text-[10px] font-semibold text-emerald-700 uppercase tracking-wider truncate">Cero Alucinaciones</p><p className="text-3xl font-bold text-emerald-700 mt-1">{Math.max(0, metricas?.zeroHallucinationsPct ?? 100)}%</p><div className="flex items-center gap-1.5 mt-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" /><span className="text-[10px] text-emerald-600 font-semibold truncate">Auditoría verificada</span></div></CardContent></Card>
                <Card className="border-0 shadow-sm overflow-hidden"><CardContent className="p-5 space-y-3"><p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider truncate">Consumo del Plan</p><ContadorConsumoPlan etiqueta="Acciones hoy" actual={metricas?.executionsToday ?? 0} maximo={ctxSuscripcion.limites.max_actions_per_day} unlimited={ctxSuscripcion.limites.max_actions_per_day === 0} /><ContadorConsumoPlan etiqueta="Workflows" actual={3} maximo={ctxSuscripcion.limites.max_workflows} unlimited={ctxSuscripcion.limites.max_workflows === 0} /><ContadorConsumoPlan etiqueta="Aprobaciones hoy" actual={metricas?.pendingApprovals ?? 0} maximo={ctxSuscripcion.limites.max_approval_requests_per_day} unlimited={ctxSuscripcion.limites.max_approval_requests_per_day === 0} /></CardContent></Card>
              </div>

              <Card className="border-0 shadow-sm overflow-hidden"><CardHeader className="pb-2"><div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2"><CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2"><TrendingUp className="h-4 w-4 text-emerald-500" />Impacto y Valor Generado</CardTitle><span className="text-[10px] text-gray-400 truncate">Plan {ctxSuscripcion.nombreMostrar} • {ctxSuscripcion.limites.max_actions_per_day === 0 ? "∞" : ctxSuscripcion.limites.max_actions_per_day} acciones/día</span></div></CardHeader><CardContent><div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6"><div className="bg-gradient-to-br from-emerald-50 to-teal-50 rounded-xl p-3 sm:p-4 overflow-hidden"><p className="text-[10px] font-semibold text-emerald-600 uppercase tracking-wider truncate">Valor Hoy</p><p className="text-xl sm:text-2xl font-bold text-emerald-700 mt-1 truncate">{formatoMoneda(roi?.valueToday ?? 0)}</p><p className="text-[10px] text-emerald-500 mt-1 flex items-center gap-1 truncate"><ArrowUpRight className="h-3 w-3 shrink-0" />Ahorro estimado</p></div><div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-3 sm:p-4 overflow-hidden"><p className="text-[10px] font-semibold text-blue-600 uppercase tracking-wider truncate">Horas Ahorradas</p><p className="text-xl sm:text-2xl font-bold text-blue-700 mt-1 truncate">{roi?.hoursSavedToday ?? 0}h</p><p className="text-[10px] text-blue-400 mt-1 truncate">A ~15 min por acción</p></div><div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-xl p-3 sm:p-4 overflow-hidden"><p className="text-[10px] font-semibold text-amber-600 uppercase tracking-wider truncate">Exitosas Hoy</p><p className="text-xl sm:text-2xl font-bold text-amber-700 mt-1 truncate">{roi?.actionsCompletedToday ?? 0}</p><p className="text-[10px] text-amber-500 mt-1 truncate">Completadas</p></div><div className="bg-gradient-to-br from-purple-50 to-fuchsia-50 rounded-xl p-3 sm:p-4 overflow-hidden"><p className="text-[10px] font-semibold text-purple-600 uppercase tracking-wider truncate">Valor 30 Días</p><p className="text-xl sm:text-2xl font-bold text-purple-700 mt-1 truncate">{formatoMoneda(roi?.value30d ?? 0)}</p><p className="text-[10px] text-purple-400 mt-1 truncate">Retorno acumulado</p></div></div><div><p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-3">Tendencia Semanal</p><div className="flex items-end gap-2 h-32">{roi?.weeklyTrend.map((dia) => { const maxVal = Math.max(...(roi?.weeklyTrend.map((d) => d.exitosas + d.bloqueadas) || [1]), 1); const total = dia.exitosas + dia.bloqueadas; const alturaPct = Math.max((total / maxVal) * 100, 4); return (<div key={dia.day} className="flex-1 flex flex-col items-center gap-1"><div className="w-full flex flex-col justify-end" style={{ height: `${alturaPct}%` }}><div className="bg-emerald-400 rounded-t-sm transition-all" style={{ flex: Math.max(dia.exitosas, 1) }} /><div className="bg-red-300 rounded-b-sm transition-all" style={{ flex: Math.max(dia.bloqueadas, 0.5) }} /></div><span className="text-[9px] text-gray-400 font-medium">{dia.day}</span></div>); })}</div><div className="flex items-center gap-4 mt-2 text-[10px] text-gray-400"><span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-emerald-400" />Exitosas</span><span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-red-300" />Bloqueadas</span></div></div></CardContent></Card>

              {!featureDisponible("PolicySimulation" as FeatureName) && (<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">{ctxSuscripcion.caracteristicas.filter((c) => !c.disponible).slice(0, 3).map((c) => (<WidgetBloqueado key={c.feature} etiqueta={c.etiqueta} descripcion={c.descripcion} tierRequerido={c.tierMinimo} />))}</div>)}
            </TabsContent>

            {/* PLACA 2: ESTACIÓN DE ARBITRAJE */}
            <TabsContent value="arbitraje" className="space-y-6">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 lg:gap-6 min-h-[500px]">
                {/* Bandeja de Veredictos */}
                <div className="lg:col-span-3"><Card className="border-0 shadow-sm h-full overflow-hidden"><CardHeader className="pb-2"><CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2"><Gavel className="h-4 w-4 text-amber-500" />Bandeja de Veredictos</CardTitle><p className="text-[10px] text-gray-400">{propuestas.length} solicitud{propuestas.length !== 1 ? "es" : ""} pendiente{propuestas.length !== 1 ? "s" : ""}</p></CardHeader><CardContent><ScrollArea className="max-h-[460px]">{propuestas.length === 0 ? (<div className="py-8 text-center"><CheckCircle2 className="h-8 w-8 text-emerald-300 mx-auto mb-2" /><p className="text-xs text-gray-400">Sin solicitudes pendientes</p></div>) : (<div className="space-y-3">{propuestas.map((prop) => { const cat = prop.priority === "critical" ? "destructive" : prop.targetAction?.includes("financial") ? "financial" : "safe"; const colores = categoriaColor(cat); const seleccionada = propuestaSeleccionada === prop.requestId; return (<button key={prop.id} onClick={() => cargarEvidencia(prop.requestId)} className={`w-full text-left rounded-xl border-2 p-3 transition-all overflow-hidden ${seleccionada ? `${colores.bg} ${colores.border} shadow-md` : "border-gray-100 hover:border-gray-200 hover:shadow-sm"}`}><div className="flex items-center justify-between mb-1.5 gap-2"><span className={`text-[9px] font-bold px-2 py-0.5 rounded-full shrink-0 ${colores.bg} ${colores.text}`}>{colores.label}</span><span className="text-[9px] text-gray-400 shrink-0">{tiempoRelativo(prop.createdAt)}</span></div><p className="text-xs font-semibold text-gray-800 line-clamp-2">{prop.title}</p><p className="text-[10px] text-gray-400 mt-1 line-clamp-1 truncate">{prop.requesterName}</p></button>); })}</div>)}</ScrollArea></CardContent></Card></div>

                {/* Visor de Evidencia */}
                <div className="lg:col-span-5"><Card className="border-0 shadow-sm h-full overflow-hidden"><CardHeader className="pb-2"><CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2"><Eye className="h-4 w-4 text-blue-500" />Visor de Evidencia y Consenso</CardTitle></CardHeader><CardContent>{!propuestaSeleccionada ? (<div className="py-16 text-center"><ScaleIcon className="h-12 w-12 text-gray-200 mx-auto mb-3" /><p className="text-sm text-gray-400">Seleccione una solicitud de la bandeja</p></div>) : cargandoEvidencia ? (<div className="py-16 text-center"><RefreshCw className="h-8 w-8 text-gray-300 mx-auto mb-3 animate-spin" /><p className="text-xs text-gray-400">Cargando evidencia...</p></div>) : evidencia ? (<ScrollArea className="max-h-[520px]"><div className="space-y-5 pr-2"><div className="flex items-center justify-center"><div className={`px-8 py-4 rounded-2xl border-2 text-center ${evidencia.llmVerdict ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"}`}><p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Veredicto del Motor de IA</p><p className={`text-4xl font-black ${evidencia.llmVerdict ? "text-emerald-600" : "text-red-600"}`}>{evidencia.llmVerdict ? "SÍ" : "NO"}</p><p className="text-[10px] text-gray-400 mt-1">{evidencia.llmVerdict ? "La IA clasifica la acción como segura" : "La IA clasifica la acción como riesgosa"}</p></div></div><div className="flex items-center justify-center"><span className={`text-[10px] font-bold px-3 py-1 rounded-full ${categoriaColor(evidencia.category).bg} ${categoriaColor(evidencia.category).text}`}>Categoría: {categoriaColor(evidencia.category).label}</span></div><Separator />{featureDisponible("HitlEvidence" as FeatureName) ? (<div><p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-3">Balanzas de Evidencia</p><div className="grid grid-cols-2 gap-3"><div className="space-y-2"><div className="flex items-center gap-1.5 mb-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" /><span className="text-[10px] font-bold text-emerald-600 uppercase">A Favor</span></div>{evidencia.evidenceFor.map((ev, idx) => (<div key={idx} className="bg-emerald-50 rounded-lg p-2.5 border border-emerald-100 overflow-hidden"><p className="text-[11px] text-emerald-800 font-medium line-clamp-2">{ev.point}</p><div className="flex items-center justify-between mt-1 gap-1"><span className="text-[9px] text-emerald-500 truncate">{ev.source}</span><div className="flex items-center gap-1 shrink-0"><Progress value={ev.weight * 100} className="h-1 w-12" /><span className="text-[9px] text-emerald-400">{Math.round(ev.weight * 100)}%</span></div></div></div>))}{evidencia.evidenceFor.length === 0 && <p className="text-[10px] text-gray-300 italic">Sin evidencia a favor</p>}</div><div className="space-y-2"><div className="flex items-center gap-1.5 mb-2"><XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" /><span className="text-[10px] font-bold text-red-600 uppercase">En Contra</span></div>{evidencia.evidenceAgainst.map((ev, idx) => (<div key={idx} className="bg-red-50 rounded-lg p-2.5 border border-red-100 overflow-hidden"><p className="text-[11px] text-red-800 font-medium line-clamp-2">{ev.point}</p><div className="flex items-center justify-between mt-1 gap-1"><span className="text-[9px] text-red-500 truncate">{ev.source}</span><div className="flex items-center gap-1 shrink-0"><Progress value={ev.weight * 100} className="h-1 w-12" /><span className="text-[9px] text-red-400">{Math.round(ev.weight * 100)}%</span></div></div></div>))}{evidencia.evidenceAgainst.length === 0 && <p className="text-[10px] text-gray-300 italic">Sin evidencia en contra</p>}</div></div></div>) : (<WidgetBloqueado etiqueta="Evidencia Detallada" descripcion="Balanzas de evidencia con pesos y fuentes" tierRequerido="business" />)}<div className="bg-gray-50 rounded-xl p-3 space-y-1.5 overflow-hidden"><p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Detalles</p><div className="grid grid-cols-2 gap-2 text-[10px]"><div className="truncate"><span className="text-gray-400">Solicitante:</span> <span className="text-gray-700 font-medium truncate">{evidencia.requesterName}</span></div><div className="truncate"><span className="text-gray-400">Prioridad:</span> <span className="text-gray-700 font-medium capitalize">{evidencia.priority}</span></div><div><span className="text-gray-400">Reversible:</span> <span className={`font-medium ${evidencia.isReversible ? "text-emerald-600" : "text-red-600"}`}>{evidencia.isReversible ? "Sí" : "No"}</span></div><div><span className="text-gray-400">Aprobaciones:</span> <span className="text-gray-700 font-medium">{evidencia.currentApprovals}/{evidencia.requiredApprovals}</span></div></div></div></div></ScrollArea>) : null}</CardContent></Card></div>

                {/* Consola de Aprobación */}
                <div className="lg:col-span-4"><Card className="border-0 shadow-sm h-full overflow-hidden"><CardHeader className="pb-2"><CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2"><Lock className="h-4 w-4 text-amber-500" />Consola de Aprobación</CardTitle><p className="text-[10px] text-gray-400">Requiere verificación paso a paso</p></CardHeader><CardContent>{!evidencia ? (<div className="py-16 text-center"><Lock className="h-12 w-12 text-gray-200 mx-auto mb-3" /><p className="text-xs text-gray-400">Seleccione una solicitud primero</p></div>) : (<div className="space-y-4"><div className={`rounded-xl border-2 p-3 transition-all ${checkEvidencia ? "border-emerald-200 bg-emerald-50" : "border-gray-200 bg-gray-50"}`}><div className="flex items-center justify-between"><div className="flex items-center gap-2 min-w-0"><div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${checkEvidencia ? "bg-emerald-500" : "bg-gray-200"}`}>{checkEvidencia ? <CheckCircle2 className="h-3.5 w-3.5 text-white" /> : <span className="text-[10px] font-bold text-gray-400">1</span>}</div><p className="text-xs font-semibold text-gray-800 truncate">He revisado la evidencia</p></div><Switch checked={checkEvidencia} onCheckedChange={setCheckEvidencia} /></div></div><div className={`rounded-xl border-2 p-3 transition-all ${justificacion.length >= 50 ? "border-emerald-200 bg-emerald-50" : "border-gray-200 bg-gray-50"}`}><div className="flex items-center gap-2 mb-2"><div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${justificacion.length >= 50 ? "bg-emerald-500" : "bg-gray-200"}`}>{justificacion.length >= 50 ? <CheckCircle2 className="h-3.5 w-3.5 text-white" /> : <span className="text-[10px] font-bold text-gray-400">2</span>}</div><div className="min-w-0"><p className="text-xs font-semibold text-gray-800">Justificación de la decisión</p><p className="text-[9px] text-gray-400">Mínimo 50 caracteres</p></div></div><Textarea value={justificacion} onChange={(e) => setJustificacion(e.target.value)} placeholder="Escriba aquí la razón de su decisión..." className="text-xs min-h-[80px] resize-none" disabled={!checkEvidencia} /><div className="flex items-center justify-between mt-1.5"><div className="flex items-center gap-2"><Progress value={Math.min((justificacion.length / 50) * 100, 100)} className={`h-1.5 w-16 ${justificacion.length >= 50 ? "[&>div]:bg-emerald-500" : ""}`} /><span className={`text-[10px] font-medium ${justificacion.length >= 50 ? "text-emerald-600" : "text-gray-400"}`}>{justificacion.length}/50</span></div>{justificacion.length >= 50 && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />}</div></div><div className={`rounded-xl border-2 p-3 transition-all ${checkRiesgo ? "border-emerald-200 bg-emerald-50" : "border-gray-200 bg-gray-50"}`}><div className="flex items-center justify-between"><div className="flex items-center gap-2 min-w-0"><div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${checkRiesgo ? "bg-emerald-500" : "bg-gray-200"}`}>{checkRiesgo ? <CheckCircle2 className="h-3.5 w-3.5 text-white" /> : <span className="text-[10px] font-bold text-gray-400">3</span>}</div><div className="min-w-0"><p className="text-xs font-semibold text-gray-800 truncate">Acepto la responsabilidad</p><p className="text-[9px] text-gray-400">Firmo digitalmente</p></div></div><Switch checked={checkRiesgo} onCheckedChange={setCheckRiesgo} disabled={justificacion.length < 50} /></div></div><Separator /><div className="space-y-2"><Button className={`w-full h-12 text-xs font-bold rounded-xl transition-all ${botonHabilitado ? sosteniendoBoton ? "bg-emerald-600 hover:bg-emerald-700 text-white scale-105 shadow-lg shadow-emerald-200" : "bg-emerald-500 hover:bg-emerald-600 text-white" : "bg-gray-200 text-gray-400 cursor-not-allowed"}`} disabled={!botonHabilitado || enviando} onMouseDown={iniciarSosten} onMouseUp={cancelarSosten} onMouseLeave={cancelarSosten} onTouchStart={iniciarSosten} onTouchEnd={cancelarSosten}>{enviando ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Procesando...</> : sosteniendoBoton ? <><Lock className="h-4 w-4 mr-2" />Mantenga presionado...</> : !botonHabilitado ? <><Lock className="h-4 w-4 mr-2" />Complete los 3 pasos</> : <><FileCheck className="h-4 w-4 mr-2" />Mantenga para Sellar y Aprobar</>}</Button><Button variant="outline" className="w-full h-9 text-xs font-semibold text-red-600 border-red-200 hover:bg-red-50 rounded-xl" disabled={!checkEvidencia || enviando} onClick={() => { if (evidencia) manejarAccionHITL(evidencia.requestId, "reject"); }}><XCircle className="h-4 w-4 mr-2" />Rechazar Solicitud</Button></div></div>)}</CardContent></Card></div>
              </div>
            </TabsContent>

            {/* PLACA 3: BÓVEDA DE SEGURIDAD */}
            <TabsContent value="boveda" className="space-y-6">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Card className="border-0 shadow-sm overflow-hidden"><CardHeader className="pb-2"><div className="flex items-center justify-between"><CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2"><Hash className="h-4 w-4 text-emerald-500" />Registro de Auditoría — Inmutable</CardTitle>{featureDisponible("AuditMerkleChain" as FeatureName) ? <Badge className="bg-emerald-100 text-emerald-700 text-[9px] px-2 py-0 border-0 font-semibold shrink-0">BLAKE3</Badge> : <Badge className="bg-gray-100 text-gray-500 text-[9px] px-2 py-0 border-0 font-semibold shrink-0">BÁSICO</Badge>}</div></CardHeader><CardContent>{ledger.length === 0 ? (<div className="py-8 text-center"><FileLock className="h-8 w-8 text-gray-200 mx-auto mb-2" /><p className="text-xs text-gray-400">Sin entradas de auditoría</p></div>) : (<ScrollArea className="max-h-[400px]"><div className="space-y-0">{ledger.map((entrada, idx) => { const esTipoImportante = ["approved","rejected","created","executed"].includes(entrada.eventType); return (<div key={entrada.id} className="relative flex items-start gap-3 py-3 group overflow-hidden">{idx < ledger.length - 1 && <div className="absolute left-[15px] top-8 w-0.5 h-full bg-gray-100" />}<div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 z-10 ${esTipoImportante ? "bg-emerald-100" : "bg-gray-50"}`}><Hash className={`h-3.5 w-3.5 ${esTipoImportante ? "text-emerald-600" : "text-gray-300"}`} /></div><div className="flex-1 min-w-0"><div className="flex items-center justify-between gap-2"><span className="text-xs font-semibold text-gray-700 truncate">{entrada.actorName || "Sistema"}</span><span className="text-[9px] text-gray-400 shrink-0">{tiempoRelativo(entrada.timestamp)}</span></div><p className="text-[10px] text-gray-500 mt-0.5 truncate">{entrada.eventType === "approved" && "Aprobó una solicitud"}{entrada.eventType === "rejected" && "Rechazó una solicitud"}{entrada.eventType === "created" && "Creó una nueva solicitud"}{entrada.eventType === "executed" && "Ejecutó una acción aprobada"}{entrada.eventType === "delegated" && "Delegó una solicitud"}{entrada.eventType === "escalated" && "Escaló una solicitud"}{entrada.eventType === "undone" && "Deshizo una acción"}{!["approved","rejected","created","executed","delegated","escalated","undone"].includes(entrada.eventType) && entrada.eventType}</p>{featureDisponible("AuditMerkleChain" as FeatureName) && (<div className="flex items-center gap-1.5 mt-1 opacity-0 group-hover:opacity-100 transition-opacity overflow-hidden"><ShieldCheck className="h-3 w-3 text-emerald-500 shrink-0" /><span className="text-[9px] text-emerald-600 font-mono truncate">Sello: {truncarHash(entrada.contentHash)}</span>{entrada.previousHash && <span className="text-[9px] text-gray-300 font-mono truncate">← {truncarHash(entrada.previousHash)}</span>}</div>)}</div></div>); })}</div></ScrollArea>)}</CardContent></Card>

                <Card className="border-0 shadow-sm overflow-hidden"><CardHeader className="pb-2"><div className="flex items-center justify-between"><CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2"><Shield className="h-4 w-4 text-emerald-500" />Las 6 Capas de Defensa</CardTitle><div className="flex items-center gap-1.5 shrink-0"><span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" /><span className="text-[10px] text-emerald-600 font-semibold">Todas activas</span></div></div></CardHeader><CardContent><div className="grid grid-cols-2 gap-3">{capas.map((capa) => (<div key={capa.id} className={`rounded-xl border-2 p-3 transition-all overflow-hidden ${capa.status === "active" ? "border-emerald-200 bg-emerald-50/50" : "border-red-200 bg-red-50/50"}`}><div className="flex items-center justify-between mb-2"><div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${capa.status === "active" ? "bg-emerald-100 text-emerald-600" : "bg-red-100 text-red-600"}`}>{iconoCapa(capa.icon)}</div><span className={`w-2 h-2 rounded-full shrink-0 ${capa.status === "active" ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} /></div><p className="text-xs font-semibold text-gray-800 truncate">{capa.name}</p><p className="text-[10px] text-gray-400 mt-0.5 line-clamp-2">{capa.details}</p></div>))}</div>{capas.some((c) => c.status !== "active") && (<div className="mt-4 bg-red-50 border border-red-200 rounded-xl p-3"><div className="flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-red-500 shrink-0" /><p className="text-xs font-bold text-red-700 truncate">Modo Degradado Activado</p></div><p className="text-[10px] text-red-500 mt-1">Una o más capas inactivas. El sistema entró automáticamente en modo protegido.</p></div>)}</CardContent></Card>
              </div>

              <Card className="border-0 shadow-sm border-t-4 border-t-red-500 overflow-hidden"><CardHeader className="pb-2"><div className="flex items-center justify-between"><CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2"><Lock className="h-4 w-4 text-red-500" />Muro de Bloqueo — 8 Denegaciones Absolutas</CardTitle><Badge className="bg-red-100 text-red-700 text-[9px] px-2 py-0 border-0 font-semibold shrink-0">SOLO LECTURA</Badge></div><p className="text-[10px] text-gray-400">Estas reglas están bloqueadas desde la raíz. Nadie — ni la IA, ni un administrador — puede desactivarlas.</p></CardHeader><CardContent><div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{reglasDenegacion.map((regla) => (<div key={regla.id} className="rounded-xl border border-red-200 bg-red-50/30 p-4 overflow-hidden"><div className="flex items-start gap-3"><div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center shrink-0"><Lock className="h-4 w-4 text-red-600" /></div><div className="flex-1 min-w-0"><div className="flex items-center justify-between gap-2"><p className="text-xs font-bold text-red-800 truncate">{regla.id}. {regla.rule}</p><Badge className="bg-red-200 text-red-800 text-[8px] px-1.5 py-0 border-0 font-bold shrink-0">{regla.niche}</Badge></div><p className="text-[10px] text-red-600/70 mt-1 line-clamp-2">{regla.description}</p></div></div></div>))}</div><div className="mt-4 bg-gray-50 rounded-xl p-3 flex items-center gap-2 overflow-hidden"><ShieldCheck className="h-4 w-4 text-emerald-500 shrink-0" /><p className="text-[10px] text-gray-500 truncate">Todas las denegaciones absolutas están activas y protegidas criptográficamente. Estado: <span className="font-bold text-emerald-600">Irrompible</span></p></div></CardContent></Card>
            </TabsContent>

            {/* PLACA 4: NICHOS Y PLANTILLAS */}
            <TabsContent value="nichos" className="space-y-6">
              <NichosSelector nichosApi={nichos} plantillas={plantillas} archivosSubidos={archivosSubidos} onSeleccionarNicho={seleccionarNicho} onSubirArchivos={subirArchivos} subiendoArchivos={subiendoArchivos} cargandoPlantillas={cargandoPlantillas} nichoSeleccionado={nichoSeleccionado} />
            </TabsContent>

            {/* PLACA 5: APIs & MCP */}
            <TabsContent value="apis" className="space-y-6">
              <ApisMcpTab />
            </TabsContent>
          </Tabs>
        </div>

        <footer className="border-t border-gray-200 bg-white px-4 sm:px-6 py-3 mt-auto">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-2 text-[10px] text-gray-400">
            <div className="flex items-center gap-4"><span>Versión: v3.0.0</span><span>© 2026 Zenic Logic</span></div>
            <div className="flex items-center gap-3"><div className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" /><span className="text-emerald-600 font-medium">Motor Central: En Línea</span></div>{ultimaActualizacion && <span className="text-gray-300">Última actualización: {formatoTimestamp(ultimaActualizacion)}</span>}</div>
          </div>
        </footer>
      </main>
    </div>
  );
}
