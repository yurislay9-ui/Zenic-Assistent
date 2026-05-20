"use client";

import {
  Key,
  Plus,
  Eye,
  EyeOff,
  Activity,
  RefreshCw,
  Zap,
  Globe,
  Trash2,
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
import type { ApiCredentialData } from "./_types";
import { ZENIC_API_GROUPS, CREDENTIAL_TYPES } from "./_constants";
import { getStatusBadge, getApiGroupColor } from "./_helpers";

export interface NewCredData {
  name: string;
  platform: string;
  type: string;
  apiKey: string;
  apiSecret: string;
  endpoint: string;
  username: string;
  password: string;
}

export interface AddCredentialDialogProps {
  credentials: ApiCredentialData[];
  testingId: string | null;
  addDialogOpen: boolean;
  showApiKey: boolean;
  showSecret: boolean;
  showPassword: boolean;
  newCred: NewCredData;
  setAddDialogOpen: (open: boolean) => void;
  setShowApiKey: (v: boolean) => void;
  setShowSecret: (v: boolean) => void;
  setShowPassword: (v: boolean) => void;
  setNewCred: React.Dispatch<React.SetStateAction<NewCredData>>;
  crearCredencial: () => Promise<void>;
  eliminarCredencial: (id: string) => Promise<void>;
  testearCredencial: (id: string) => Promise<void>;
}

export function AddCredentialDialog(props: AddCredentialDialogProps) {
  const {
    credentials,
    testingId,
    addDialogOpen,
    showApiKey,
    showSecret,
    showPassword,
    newCred,
    setAddDialogOpen,
    setShowApiKey,
    setShowSecret,
    setShowPassword,
    setNewCred,
    crearCredencial,
    eliminarCredencial,
    testearCredencial,
  } = props;

  return (
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
  );
}
