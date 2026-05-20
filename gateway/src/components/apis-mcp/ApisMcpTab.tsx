"use client";

import { useEffect, useState, useRef } from "react";
import {
  Globe,
  Server,
  Shield,
  Lock,
  RefreshCw,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ZENIC_API_GROUPS } from "./ApisMcpTab_parts/_constants";
import { ApiGroupCard } from "./ApisMcpTab_parts/ApiGroupCard";
import { useApiCredentials } from "./ApisMcpTab_parts/useApiCredentials";
import { useMcpServers } from "./ApisMcpTab_parts/useMcpServers";
import { useServiceCreds } from "./ApisMcpTab_parts/useServiceCreds";
import { AddCredentialDialog } from "./ApisMcpTab_parts/AddCredentialDialog";
import { AddServerDialog } from "./ApisMcpTab_parts/AddServerDialog";
import { ServiceConnectionsSection } from "./ApisMcpTab_parts/ServiceConnectionsSection";

export default function ApisMcpTab() {
  const cred = useApiCredentials();
  const mcp = useMcpServers();
  const svc = useServiceCreds();
  const [loading, setLoading] = useState(true);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;

    const loadAll = async () => {
      setLoading(true);
      await Promise.all([
        cred.loadCredentials(controller.signal),
        mcp.loadMcpServers(controller.signal),
        svc.loadServiceCreds(controller.signal),
      ]);
      setLoading(false);
    };
    loadAll();

    return () => {
      controller.abort();
    };
  }, [cred.loadCredentials, mcp.loadMcpServers, svc.loadServiceCreds]);

  // ─── Contadores resumen ──────────────────────────────────────────────
  const totalEndpoints = ZENIC_API_GROUPS.reduce((sum, g) => sum + g.endpoints, 0);
  const activeCreds = cred.credentials.filter((c) => c.isActive).length;

  // ─── Loading state ─────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center space-y-3">
          <RefreshCw className="h-8 w-8 text-emerald-500 mx-auto animate-spin" />
          <p className="text-xs text-gray-500 tracking-wider uppercase">Cargando APIs & MCP...</p>
        </div>
      </div>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════════════════════

  return (
    <ScrollArea className="h-full">
      <div className="space-y-8 pr-2">
        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* RESUMEN SUPERIOR                                               */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card className="border-0 shadow-sm overflow-hidden">
            <CardContent className="p-3 text-center">
              <p className="text-2xl font-bold text-gray-900">{ZENIC_API_GROUPS.length}</p>
              <p className="text-[9px] text-gray-400 uppercase tracking-wider font-semibold">Grupos API</p>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-sm overflow-hidden">
            <CardContent className="p-3 text-center">
              <p className="text-2xl font-bold text-emerald-600">{totalEndpoints}</p>
              <p className="text-[9px] text-gray-400 uppercase tracking-wider font-semibold">Endpoints</p>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-sm overflow-hidden">
            <CardContent className="p-3 text-center">
              <p className="text-2xl font-bold text-amber-600">{activeCreds}</p>
              <p className="text-[9px] text-gray-400 uppercase tracking-wider font-semibold">Credenciales Activas</p>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-sm overflow-hidden">
            <CardContent className="p-3 text-center">
              <p className="text-2xl font-bold text-violet-600">{mcp.mcpServers.length}</p>
              <p className="text-[9px] text-gray-400 uppercase tracking-wider font-semibold">Servidores MCP</p>
            </CardContent>
          </Card>
        </div>

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* SECCIÓN A: APIs de Zenic-Agents                                 */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Globe className="h-5 w-5 text-emerald-600 shrink-0" />
              <h2 className="text-sm font-bold text-gray-900 uppercase tracking-wider">
                APIs de Zenic-Agents
              </h2>
              <Badge className="text-[8px] px-1.5 py-0 border-0 font-bold bg-emerald-100 text-emerald-700 shrink-0">
                {ZENIC_API_GROUPS.length} grupos · {totalEndpoints} endpoints
              </Badge>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {ZENIC_API_GROUPS.map((group) => (
              <ApiGroupCard key={group.id} group={group} />
            ))}
          </div>
        </section>

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* SECCIÓN B: Credenciales API del Proyecto                        */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <AddCredentialDialog
          credentials={cred.credentials}
          testingId={cred.testingId}
          addDialogOpen={cred.addDialogOpen}
          showApiKey={cred.showApiKey}
          showSecret={cred.showSecret}
          showPassword={cred.showPassword}
          newCred={cred.newCred}
          setAddDialogOpen={cred.setAddDialogOpen}
          setShowApiKey={cred.setShowApiKey}
          setShowSecret={cred.setShowSecret}
          setShowPassword={cred.setShowPassword}
          setNewCred={cred.setNewCred}
          crearCredencial={cred.crearCredencial}
          eliminarCredencial={cred.eliminarCredencial}
          testearCredencial={cred.testearCredencial}
        />

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* SECCIÓN C: Conexiones de Agentes (Servicios Externos)           */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <ServiceConnectionsSection
          serviceCreds={svc.serviceCreds}
          addServiceDialogOpen={svc.addServiceDialogOpen}
          selectedService={svc.selectedService}
          serviceFields={svc.serviceFields}
          showServiceFields={svc.showServiceFields}
          setAddServiceDialogOpen={svc.setAddServiceDialogOpen}
          setSelectedService={svc.setSelectedService}
          setServiceFields={svc.setServiceFields}
          setShowServiceFields={svc.setShowServiceFields}
          guardarCredServicio={svc.guardarCredServicio}
          eliminarCredServicio={svc.eliminarCredServicio}
        />

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* SECCIÓN D: Servidores MCP                                       */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <AddServerDialog
          mcpServers={mcp.mcpServers}
          testingServerId={mcp.testingServerId}
          addServerDialogOpen={mcp.addServerDialogOpen}
          newServer={mcp.newServer}
          setAddServerDialogOpen={mcp.setAddServerDialogOpen}
          setNewServer={mcp.setNewServer}
          crearServidorMcp={mcp.crearServidorMcp}
          testearServidorMcp={mcp.testearServidorMcp}
        />

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* SECCIÓN E: Autenticación del Gateway                            */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <section>
          <div className="flex items-center gap-2 mb-4">
            <Shield className="h-5 w-5 text-slate-600 shrink-0" />
            <h2 className="text-sm font-bold text-gray-900 uppercase tracking-wider">
              Autenticación del Gateway
            </h2>
          </div>

          <Card className="border-0 shadow-sm overflow-hidden">
            <CardContent className="p-5 space-y-4">
              <div className="flex items-center gap-3 bg-slate-50 rounded-lg px-4 py-3">
                <Lock className="h-5 w-5 text-slate-500 shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-gray-800">Pipeline de Autenticación MCP</p>
                  <p className="text-[10px] text-gray-400">
                    7 pasos: Resolución → Auth → Rate Limit → RBAC → Política → Ejecución → Auditoría Merkle
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-emerald-500" />
                    <span className="text-[10px] font-semibold text-gray-700">API Key</span>
                  </div>
                  <p className="text-[9px] text-gray-400 pl-4">
                    Clave de acceso para las APIs de Zenic-Agents. Prefijo zk-
                  </p>
                </div>
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-amber-500" />
                    <span className="text-[10px] font-semibold text-gray-700">Bearer Token</span>
                  </div>
                  <p className="text-[9px] text-gray-400 pl-4">
                    Token JWT para sesiones autenticadas con RBAC
                  </p>
                </div>
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-violet-500" />
                    <span className="text-[10px] font-semibold text-gray-700">mTLS</span>
                  </div>
                  <p className="text-[9px] text-gray-400 pl-4">
                    Certificados mutuos para servidores MCP en producción
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>
      </div>
    </ScrollArea>
  );
}
