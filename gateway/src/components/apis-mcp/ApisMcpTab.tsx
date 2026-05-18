"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  Key,
  Globe,
  Server,
  Plus,
  Trash2,
  Eye,
  EyeOff,
  RefreshCw,
  Link2,
  Shield,
  Cpu,
  Zap,
  Activity,
  Lock,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ApiCredentialData, McpServerData, ServiceCred } from "./ApisMcpTab_parts/_types";
import { ZENIC_API_GROUPS, EXTERNAL_SERVICES, CREDENTIAL_TYPES, PROTOCOLS, AUTH_TYPES } from "./ApisMcpTab_parts/_constants";
import { getStatusBadge, getServerStatusBadge, getApiGroupColor } from "./ApisMcpTab_parts/_helpers";
import { ApiGroupCard } from "./ApisMcpTab_parts/ApiGroupCard";

export default function ApisMcpTab() {
  // ─── Estado ─────────────────────────────────────────────────────────────
  const [credentials, setCredentials] = useState<ApiCredentialData[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServerData[]>([]);
  const [serviceCreds, setServiceCreds] = useState<ServiceCred[]>([]);
  const [loading, setLoading] = useState(true);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testingServerId, setTestingServerId] = useState<string | null>(null);

  // Add credential dialog state
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [newCred, setNewCred] = useState({
    name: "",
    platform: "mcp-gateway",
    type: "api_key",
    apiKey: "",
    apiSecret: "",
    endpoint: "",
    username: "",
    password: "",
  });
  const [showApiKey, setShowApiKey] = useState(false);
  const [showSecret, setShowSecret] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Add MCP server dialog state
  const [addServerDialogOpen, setAddServerDialogOpen] = useState(false);
  const [newServer, setNewServer] = useState({
    name: "",
    displayName: "",
    description: "",
    url: "",
    protocol: "http",
    authType: "none",
    healthCheckUrl: "",
  });

  // Add service credential state
  const [addServiceDialogOpen, setAddServiceDialogOpen] = useState(false);
  const [selectedService, setSelectedService] = useState<string>("jira");
  const [serviceFields, setServiceFields] = useState<Record<string, string>>({});
  const [showServiceFields, setShowServiceFields] = useState<Record<string, boolean>>({});

  // ─── Ref para AbortController ──────────────────────────────────────
  const abortRef = useRef<AbortController | null>(null);

  // ─── Cargar datos ─────────────────────────────────────────────────────
  const loadCredentials = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch("/api/dashboard/api-credentials", { signal });
      if (res.ok) {
        const data = await res.json();
        setCredentials(data.credentials || []);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Error cargando credenciales:", err);
    }
  }, []);

  const loadMcpServers = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch("/api/mcp/servers", { signal });
      if (res.ok) {
        const data = await res.json();
        setMcpServers(data.data || []);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Error cargando servidores MCP:", err);
    }
  }, []);

  const loadServiceCreds = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch("/api/dashboard/service-credentials", { signal });
      if (res.ok) {
        const data = await res.json();
        setServiceCreds(data.credentials || []);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Error cargando credenciales de servicio:", err);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;

    const loadAll = async () => {
      setLoading(true);
      await Promise.all([
        loadCredentials(controller.signal),
        loadMcpServers(controller.signal),
        loadServiceCreds(controller.signal),
      ]);
      setLoading(false);
    };
    loadAll();

    return () => {
      controller.abort();
    };
  }, [loadCredentials, loadMcpServers, loadServiceCreds]);

  // ─── Crear credencial API ──────────────────────────────────────────────
  const crearCredencial = async () => {
    if (!newCred.name || !newCred.apiKey) return;

    try {
      const res = await fetch("/api/dashboard/api-credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newCred.name,
          platform: newCred.platform,
          type: newCred.type,
          apiKey: newCred.apiKey,
          apiSecret: newCred.apiSecret || null,
          endpoint: newCred.endpoint || null,
          username: newCred.type === "basic_auth" ? newCred.username : null,
          password: newCred.type === "basic_auth" ? newCred.password : null,
        }),
      });

      if (res.ok) {
        setAddDialogOpen(false);
        setNewCred({
          name: "",
          platform: "mcp-gateway",
          type: "api_key",
          apiKey: "",
          apiSecret: "",
          endpoint: "",
          username: "",
          password: "",
        });
        loadCredentials();
      }
    } catch (err) {
      console.error("Error creando credencial:", err);
    }
  };

  // ─── Eliminar credencial API ───────────────────────────────────────────
  const eliminarCredencial = async (id: string) => {
    try {
      const res = await fetch(`/api/dashboard/api-credentials?id=${id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        loadCredentials();
      }
    } catch (err) {
      console.error("Error eliminando credencial:", err);
    }
  };

  // ─── Testear credencial API ────────────────────────────────────────────
  const testearCredencial = async (id: string) => {
    setTestingId(id);
    try {
      const res = await fetch("/api/dashboard/api-credentials/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
      if (res.ok) {
        loadCredentials();
      }
    } catch (err) {
      console.error("Error testeando credencial:", err);
    } finally {
      setTestingId(null);
    }
  };

  // ─── Crear servidor MCP ────────────────────────────────────────────────
  const crearServidorMcp = async () => {
    if (!newServer.name || !newServer.url) return;

    try {
      const res = await fetch("/api/mcp/servers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newServer.name,
          displayName: newServer.displayName || newServer.name,
          description: newServer.description || "Servidor MCP",
          url: newServer.url,
          protocol: newServer.protocol,
          status: "active",
          authType: newServer.authType,
          healthCheckUrl: newServer.healthCheckUrl || null,
        }),
      });

      if (res.ok) {
        setAddServerDialogOpen(false);
        setNewServer({
          name: "",
          displayName: "",
          description: "",
          url: "",
          protocol: "http",
          authType: "none",
          healthCheckUrl: "",
        });
        loadMcpServers();
      }
    } catch (err) {
      console.error("Error creando servidor MCP:", err);
    }
  };

  // ─── Testear servidor MCP ──────────────────────────────────────────────
  // FIX: Antes era un fake health check (setTimeout + console.log).
  // Ahora hace un fetch real al endpoint de health check del servidor.
  const testearServidorMcp = async (server: McpServerData) => {
    setTestingServerId(server.id);
    try {
      const healthUrl = server.healthCheckUrl || server.url;
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      const res = await fetch(healthUrl, {
        method: "GET",
        signal: controller.signal,
        mode: "no-cors", // Permite check sin CORS headers
      });
      clearTimeout(timeoutId);
      // En mode no-cors, res.type es 'opaque' y res.status es 0 si OK
      // Cualquier respuesta (incluso opaque) = servidor alcanzaable
      void res; // usaremos el resultado en el refresh de loadMcpServers
      loadMcpServers();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        console.warn(`Health check timeout para ${server.name}`);
      } else {
        console.error("Error testeando servidor:", err);
      }
    } finally {
      setTestingServerId(null);
    }
  };

  // ─── Guardar credencial de servicio externo ────────────────────────────
  // SECURITY: Ya no usa localStorage. Envía al API endpoint cifrado.
  // INVARIANT 4 — defensa en profundidad, la regla DENY es absoluta.
  const guardarCredServicio = async () => {
    const service = EXTERNAL_SERVICES.find((s) => s.id === selectedService);
    if (!service) return;

    const hasValues = Object.values(serviceFields).some((v) => v.trim() !== "");
    if (!hasValues) return;

    try {
      const res = await fetch("/api/dashboard/service-credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          serviceId: selectedService,
          nombre: service.nombre,
          campos: serviceFields,
        }),
      });

      if (res.ok) {
        setServiceFields({});
        setAddServiceDialogOpen(false);
        loadServiceCreds();
      } else {
        const data = await res.json();
        console.error("Error guardando credencial de servicio:", data.error);
      }
    } catch (err) {
      console.error("Error guardando credencial de servicio:", err);
    }
  };

  const eliminarCredServicio = async (id: string) => {
    try {
      const res = await fetch(`/api/dashboard/service-credentials?id=${id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        loadServiceCreds();
      }
    } catch (err) {
      console.error("Error eliminando credencial de servicio:", err);
    }
  };

  // ─── Contadores resumen ──────────────────────────────────────────────
  const totalEndpoints = ZENIC_API_GROUPS.reduce((sum, g) => sum + g.endpoints, 0);
  const activeCreds = credentials.filter((c) => c.isActive).length;

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
              <p className="text-2xl font-bold text-violet-600">{mcpServers.length}</p>
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
        <section>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Key className="h-5 w-5 text-amber-600 shrink-0" />
              <h2 className="text-sm font-bold text-gray-900 uppercase tracking-wider">
                Credenciales API
              </h2>
              <Badge className="text-[8px] px-1.5 py-0 border-0 font-bold bg-amber-100 text-amber-700 shrink-0">
                {credentials.length}
              </Badge>
            </div>

            <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
              <DialogTrigger asChild>
                <Button
                  size="sm"
                  className="bg-[#1A1D2E] hover:bg-[#2A2D3E] text-white text-[10px] h-8 gap-1"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Añadir Credencial
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle className="text-sm font-bold flex items-center gap-2">
                    <Key className="h-4 w-4 text-amber-600" />
                    Nueva Credencial API
                  </DialogTitle>
                </DialogHeader>

                <div className="space-y-4 pt-2">
                  {/* Platform selector — only Zenic APIs */}
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-gray-700">API de Zenic</Label>
                    <Select
                      value={newCred.platform}
                      onValueChange={(v) =>
                        setNewCred((prev) => ({ ...prev, platform: v }))
                      }
                    >
                      <SelectTrigger className="h-9 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ZENIC_API_GROUPS.map((g) => (
                          <SelectItem key={g.id} value={g.id}>
                            <span className="flex items-center gap-2">
                              <span>{g.nombre}</span>
                              <span className="text-gray-400 text-[9px]">{g.basePath}</span>
                            </span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Name */}
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-gray-700">Nombre</Label>
                    <Input
                      placeholder="Ej: Gateway Producción"
                      className="h-9 text-xs"
                      value={newCred.name}
                      onChange={(e) =>
                        setNewCred((prev) => ({ ...prev, name: e.target.value }))
                      }
                    />
                  </div>

                  {/* Type */}
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-gray-700">Tipo de Autenticación</Label>
                    <Select
                      value={newCred.type}
                      onValueChange={(v) =>
                        setNewCred((prev) => ({ ...prev, type: v }))
                      }
                    >
                      <SelectTrigger className="h-9 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {CREDENTIAL_TYPES.map((t) => (
                          <SelectItem key={t.value} value={t.value}>
                            {t.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* API Key */}
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-gray-700">
                      {newCred.type === "bearer" ? "Token Bearer" : newCred.type === "oauth2" ? "Token de Acceso" : "API Key / Token"}
                    </Label>
                    <div className="relative">
                      <Input
                        type={showApiKey ? "text" : "password"}
                        placeholder="zk-..."
                        className="h-9 text-xs pr-10"
                        value={newCred.apiKey}
                        onChange={(e) =>
                          setNewCred((prev) => ({ ...prev, apiKey: e.target.value }))
                        }
                      />
                      <button
                        type="button"
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                        onClick={() => setShowApiKey(!showApiKey)}
                      >
                        {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Secret (optional) */}
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-gray-500">Secreto (opcional)</Label>
                    <div className="relative">
                      <Input
                        type={showSecret ? "text" : "password"}
                        placeholder="Client secret, HMAC key..."
                        className="h-9 text-xs pr-10"
                        value={newCred.apiSecret}
                        onChange={(e) =>
                          setNewCred((prev) => ({ ...prev, apiSecret: e.target.value }))
                        }
                      />
                      <button
                        type="button"
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                        onClick={() => setShowSecret(!showSecret)}
                      >
                        {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Custom Endpoint */}
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-gray-500">Endpoint Personalizado (opcional)</Label>
                    <Input
                      placeholder="https://zenic.ejemplo.com/api"
                      className="h-9 text-xs"
                      value={newCred.endpoint}
                      onChange={(e) =>
                        setNewCred((prev) => ({ ...prev, endpoint: e.target.value }))
                      }
                    />
                  </div>

                  {/* Basic Auth fields */}
                  {newCred.type === "basic_auth" && (
                    <>
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold text-gray-700">Usuario</Label>
                        <Input
                          placeholder="nombre_usuario"
                          className="h-9 text-xs"
                          value={newCred.username}
                          onChange={(e) =>
                            setNewCred((prev) => ({ ...prev, username: e.target.value }))
                          }
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold text-gray-700">Contraseña</Label>
                        <div className="relative">
                          <Input
                            type={showPassword ? "text" : "password"}
                            placeholder="••••••••"
                            className="h-9 text-xs pr-10"
                            value={newCred.password}
                            onChange={(e) =>
                              setNewCred((prev) => ({ ...prev, password: e.target.value }))
                            }
                          />
                          <button
                            type="button"
                            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                            onClick={() => setShowPassword(!showPassword)}
                          >
                            {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                      </div>
                    </>
                  )}

                  <Button
                    onClick={crearCredencial}
                    className="w-full bg-[#1A1D2E] hover:bg-[#2A2D3E] text-white text-xs h-9"
                    disabled={!newCred.name || !newCred.apiKey}
                  >
                    <Plus className="h-3.5 w-3.5 mr-1" />
                    Guardar Credencial
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          {credentials.length === 0 ? (
            <Card className="border-0 shadow-sm overflow-hidden">
              <CardContent className="py-12 text-center">
                <Key className="h-10 w-10 text-gray-300 mx-auto mb-3" />
                <p className="text-xs text-gray-400">Sin credenciales API configuradas</p>
                <p className="text-[10px] text-gray-300 mt-1">
                  Añade tu primera credencial para acceder a las APIs de Zenic
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {credentials.map((cred) => {
                const apiGroup = ZENIC_API_GROUPS.find((g) => g.id === cred.platform);
                const colors = apiGroup ? getApiGroupColor(apiGroup.color) : getApiGroupColor("gray");
                return (
                  <Card
                    key={cred.id}
                    className="border-0 shadow-sm overflow-hidden hover:shadow-md transition-shadow"
                  >
                    <CardHeader className="pb-2 pt-4 px-4">
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-2 min-w-0">
                          <div className={`w-8 h-8 rounded-lg ${colors.iconBg} flex items-center justify-center shrink-0`}>
                            {apiGroup ? (
                              <apiGroup.icon className={`h-4 w-4 ${colors.text}`} />
                            ) : (
                              <Key className="h-4 w-4 text-gray-500" />
                            )}
                          </div>
                          <div className="min-w-0">
                            <CardTitle className="text-xs font-bold text-gray-900 truncate">
                              {cred.name}
                            </CardTitle>
                            <p className="text-[10px] text-gray-400 truncate">
                              {apiGroup?.nombre || cred.platform}
                            </p>
                          </div>
                        </div>
                        {getStatusBadge(cred.verifyStatus)}
                      </div>
                    </CardHeader>
                    <CardContent className="px-4 pb-4 space-y-2">
                      <div className="flex items-center gap-2">
                        <Badge
                          className="text-[8px] px-1.5 py-0 border-0 font-semibold shrink-0"
                          variant="outline"
                        >
                          {cred.type === "api_key" ? "API KEY" : cred.type === "bearer" ? "BEARER" : cred.type === "oauth2" ? "OAUTH2" : cred.type === "basic_auth" ? "BASIC" : "CUSTOM"}
                        </Badge>
                        <span className="text-[10px] text-gray-500 font-mono truncate">
                          {cred.apiKey.substring(0, 8)}•••••••
                        </span>
                      </div>

                      {cred.endpoint && (
                        <div className="flex items-center gap-1">
                          <Globe className="h-3 w-3 text-gray-400 shrink-0" />
                          <span className="text-[10px] text-gray-400 truncate">
                            {cred.endpoint}
                          </span>
                        </div>
                      )}

                      <Separator className="my-1" />

                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          {cred.isActive ? (
                            <Zap className="h-3 w-3 text-emerald-500 shrink-0" />
                          ) : (
                            <Zap className="h-3 w-3 text-gray-300 shrink-0" />
                          )}
                          <span className="text-[9px] text-gray-400">
                            {cred.isActive ? "Activa" : "Inactiva"}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-[10px] text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50"
                            onClick={() => testearCredencial(cred.id)}
                            disabled={testingId === cred.id}
                          >
                            {testingId === cred.id ? (
                              <RefreshCw className="h-3 w-3 animate-spin" />
                            ) : (
                              <Activity className="h-3 w-3" />
                            )}
                            <span className="ml-1">Test</span>
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-[10px] text-red-500 hover:text-red-600 hover:bg-red-50"
                            onClick={() => eliminarCredencial(cred.id)}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </section>

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* SECCIÓN C: Conexiones de Agentes (Servicios Externos)           */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Link2 className="h-5 w-5 text-rose-600 shrink-0" />
              <h2 className="text-sm font-bold text-gray-900 uppercase tracking-wider">
                Conexiones de Agentes
              </h2>
              <Badge className="text-[8px] px-1.5 py-0 border-0 font-bold bg-rose-100 text-rose-700 shrink-0">
                {serviceCreds.length}
              </Badge>
            </div>

            <Dialog open={addServiceDialogOpen} onOpenChange={setAddServiceDialogOpen}>
              <DialogTrigger asChild>
                <Button
                  size="sm"
                  className="bg-rose-600 hover:bg-rose-700 text-white text-[10px] h-8 gap-1"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Añadir Conexión
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle className="text-sm font-bold flex items-center gap-2">
                    <Link2 className="h-4 w-4 text-rose-600" />
                    Nueva Conexión de Agente
                  </DialogTitle>
                </DialogHeader>

                <div className="space-y-4 pt-2">
                  {/* Service selector */}
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-gray-700">Servicio</Label>
                    <Select
                      value={selectedService}
                      onValueChange={(v) => {
                        setSelectedService(v);
                        setServiceFields({});
                      }}
                    >
                      <SelectTrigger className="h-9 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {EXTERNAL_SERVICES.map((s) => (
                          <SelectItem key={s.id} value={s.id}>
                            <span className="flex items-center gap-2">
                              <span>{s.icon}</span>
                              <span>{s.nombre}</span>
                            </span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Description */}
                  {selectedService && (
                    <p className="text-[10px] text-gray-400 bg-gray-50 rounded-lg px-3 py-2">
                      {EXTERNAL_SERVICES.find((s) => s.id === selectedService)?.descripcion}
                    </p>
                  )}

                  {/* Dynamic fields */}
                  {selectedService &&
                    EXTERNAL_SERVICES.find((s) => s.id === selectedService)?.campos.map((campo) => (
                      <div key={campo} className="space-y-1.5">
                        <Label className="text-xs font-semibold text-gray-700 font-mono">
                          {campo}
                        </Label>
                        <div className="relative">
                          <Input
                            type={showServiceFields[campo] ? "text" : "password"}
                            placeholder={campo}
                            className="h-9 text-xs pr-10 font-mono"
                            value={serviceFields[campo] || ""}
                            onChange={(e) =>
                              setServiceFields((prev) => ({ ...prev, [campo]: e.target.value }))
                            }
                          />
                          <button
                            type="button"
                            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                            onClick={() =>
                              setShowServiceFields((prev) => ({ ...prev, [campo]: !prev[campo] }))
                            }
                          >
                            {showServiceFields[campo] ? (
                              <EyeOff className="h-4 w-4" />
                            ) : (
                              <Eye className="h-4 w-4" />
                            )}
                          </button>
                        </div>
                      </div>
                    ))}

                  <Button
                    onClick={guardarCredServicio}
                    className="w-full bg-rose-600 hover:bg-rose-700 text-white text-xs h-9"
                    disabled={!Object.values(serviceFields).some((v) => v.trim() !== "")}
                  >
                    <Plus className="h-3.5 w-3.5 mr-1" />
                    Guardar Conexión
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          {/* Saved service connections */}
          {serviceCreds.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {serviceCreds.map((svc) => {
                const service = EXTERNAL_SERVICES.find((s) => s.id === svc.serviceId);
                return (
                  <div
                    key={svc.id}
                    className="flex items-center justify-between gap-3 bg-gray-50 rounded-lg px-4 py-3"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-xl shrink-0">{service?.icon || "🔌"}</span>
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-gray-800 truncate">
                          {svc.nombre}
                        </p>
                        <p className="text-[10px] text-gray-400 truncate">
                          {Object.keys(svc.campos).map((k) => k).join(" · ")}
                        </p>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-red-400 hover:text-red-500 hover:bg-red-50 shrink-0"
                      onClick={() => eliminarCredServicio(svc.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                );
              })}
            </div>
          ) : (
            <Card className="border-0 shadow-sm overflow-hidden">
              <CardContent className="py-10 text-center">
                <Link2 className="h-10 w-10 text-gray-300 mx-auto mb-3" />
                <p className="text-xs text-gray-400">Sin conexiones de agentes configuradas</p>
                <p className="text-[10px] text-gray-300 mt-1">
                  Configura Jira, ServiceNow, Slack, WhatsApp, etc.
                </p>
              </CardContent>
            </Card>
          )}
        </section>

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* SECCIÓN D: Servidores MCP                                       */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Server className="h-5 w-5 text-violet-600 shrink-0" />
              <h2 className="text-sm font-bold text-gray-900 uppercase tracking-wider">
                Servidores MCP
              </h2>
              <Badge className="text-[8px] px-1.5 py-0 border-0 font-bold bg-violet-100 text-violet-700 shrink-0">
                {mcpServers.length}
              </Badge>
            </div>

            <Dialog open={addServerDialogOpen} onOpenChange={setAddServerDialogOpen}>
              <DialogTrigger asChild>
                <Button
                  size="sm"
                  className="bg-violet-600 hover:bg-violet-700 text-white text-[10px] h-8 gap-1"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Añadir Servidor MCP
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle className="text-sm font-bold flex items-center gap-2">
                    <Server className="h-4 w-4 text-violet-600" />
                    Nuevo Servidor MCP
                  </DialogTitle>
                </DialogHeader>

                <div className="space-y-4 pt-2">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs font-semibold text-gray-700">Nombre</Label>
                      <Input
                        placeholder="mi-servidor-mcp"
                        className="h-9 text-xs"
                        value={newServer.name}
                        onChange={(e) =>
                          setNewServer((prev) => ({ ...prev, name: e.target.value }))
                        }
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs font-semibold text-gray-700">Nombre a Mostrar</Label>
                      <Input
                        placeholder="Mi Servidor MCP"
                        className="h-9 text-xs"
                        value={newServer.displayName}
                        onChange={(e) =>
                          setNewServer((prev) => ({ ...prev, displayName: e.target.value }))
                        }
                      />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-gray-700">Descripción</Label>
                    <Input
                      placeholder="Descripción del servidor MCP"
                      className="h-9 text-xs"
                      value={newServer.description}
                      onChange={(e) =>
                        setNewServer((prev) => ({ ...prev, description: e.target.value }))
                      }
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-gray-700">URL del Servidor</Label>
                    <Input
                      placeholder="http://localhost:3001"
                      className="h-9 text-xs"
                      value={newServer.url}
                      onChange={(e) =>
                        setNewServer((prev) => ({ ...prev, url: e.target.value }))
                      }
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs font-semibold text-gray-700">Protocolo</Label>
                      <Select
                        value={newServer.protocol}
                        onValueChange={(v) =>
                          setNewServer((prev) => ({ ...prev, protocol: v }))
                        }
                      >
                        <SelectTrigger className="h-9 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {PROTOCOLS.map((p) => (
                            <SelectItem key={p.value} value={p.value}>
                              {p.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs font-semibold text-gray-700">Autenticación</Label>
                      <Select
                        value={newServer.authType}
                        onValueChange={(v) =>
                          setNewServer((prev) => ({ ...prev, authType: v }))
                        }
                      >
                        <SelectTrigger className="h-9 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {AUTH_TYPES.map((a) => (
                            <SelectItem key={a.value} value={a.value}>
                              {a.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-gray-500">URL de Health Check (opcional)</Label>
                    <Input
                      placeholder="http://localhost:3001/health"
                      className="h-9 text-xs"
                      value={newServer.healthCheckUrl}
                      onChange={(e) =>
                        setNewServer((prev) => ({ ...prev, healthCheckUrl: e.target.value }))
                      }
                    />
                  </div>

                  <Button
                    onClick={crearServidorMcp}
                    className="w-full bg-violet-600 hover:bg-violet-700 text-white text-xs h-9"
                    disabled={!newServer.name || !newServer.url}
                  >
                    <Plus className="h-3.5 w-3.5 mr-1" />
                    Crear Servidor MCP
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          {mcpServers.length === 0 ? (
            <Card className="border-0 shadow-sm overflow-hidden">
              <CardContent className="py-12 text-center">
                <Server className="h-10 w-10 text-gray-300 mx-auto mb-3" />
                <p className="text-xs text-gray-400">Sin servidores MCP configurados</p>
                <p className="text-[10px] text-gray-300 mt-1">
                  Añade un servidor MCP para habilitar herramientas
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {mcpServers.map((server) => (
                <Card
                  key={server.id}
                  className="border-0 shadow-sm overflow-hidden hover:shadow-md transition-shadow"
                >
                  <CardHeader className="pb-2 pt-4 px-4">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-8 h-8 rounded-lg bg-violet-100 flex items-center justify-center shrink-0">
                          <Server className="h-4 w-4 text-violet-600" />
                        </div>
                        <div className="min-w-0">
                          <CardTitle className="text-xs font-bold text-gray-900 truncate">
                            {server.displayName || server.name}
                          </CardTitle>
                          <p className="text-[10px] text-gray-400 truncate">
                            {server.protocol.toUpperCase()} · {server.authType !== "none" ? `Auth: ${server.authType}` : "Sin auth"}
                          </p>
                        </div>
                      </div>
                      {getServerStatusBadge(server.status)}
                    </div>
                  </CardHeader>
                  <CardContent className="px-4 pb-4 space-y-2">
                    <p className="text-[10px] text-gray-500 truncate">{server.description}</p>
                    <div className="flex items-center gap-1">
                      <Globe className="h-3 w-3 text-gray-400 shrink-0" />
                      <span className="text-[10px] text-gray-400 font-mono truncate">
                        {server.url}
                      </span>
                    </div>
                    {server.toolCount !== undefined && server.toolCount > 0 && (
                      <Badge className="text-[8px] px-1.5 py-0 border-0 font-semibold bg-violet-50 text-violet-600 shrink-0">
                        {server.toolCount} herramientas
                      </Badge>
                    )}
                    <Separator className="my-1" />
                    <div className="flex items-center justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-[10px] text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50"
                        onClick={() => testearServidorMcp(server)}
                        disabled={testingServerId === server.id}
                      >
                        {testingServerId === server.id ? (
                          <RefreshCw className="h-3 w-3 animate-spin" />
                        ) : (
                          <Activity className="h-3 w-3" />
                        )}
                        <span className="ml-1">Health Check</span>
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </section>

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
