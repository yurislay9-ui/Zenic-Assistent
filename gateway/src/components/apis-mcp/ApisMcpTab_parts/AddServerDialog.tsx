"use client";

import {
  Server,
  Plus,
  Globe,
  Activity,
  RefreshCw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
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
import type { McpServerData } from "./_types";
import { PROTOCOLS, AUTH_TYPES } from "./_constants";
import { getServerStatusBadge } from "./_helpers";

export interface NewServerData {
  name: string;
  displayName: string;
  description: string;
  url: string;
  protocol: string;
  authType: string;
  healthCheckUrl: string;
}

export interface AddServerDialogProps {
  mcpServers: McpServerData[];
  testingServerId: string | null;
  addServerDialogOpen: boolean;
  newServer: NewServerData;
  setAddServerDialogOpen: (open: boolean) => void;
  setNewServer: React.Dispatch<React.SetStateAction<NewServerData>>;
  crearServidorMcp: () => Promise<void>;
  testearServidorMcp: (server: McpServerData) => Promise<void>;
}

export function AddServerDialog(props: AddServerDialogProps) {
  const {
    mcpServers,
    testingServerId,
    addServerDialogOpen,
    newServer,
    setAddServerDialogOpen,
    setNewServer,
    crearServidorMcp,
    testearServidorMcp,
  } = props;

  return (
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
  );
}
