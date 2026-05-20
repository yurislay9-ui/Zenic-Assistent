"use client";

import {
  Link2,
  Plus,
  Eye,
  EyeOff,
  Trash2,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import type { ServiceCred } from "./_types";
import { EXTERNAL_SERVICES } from "./_constants";

export interface ServiceConnectionsSectionProps {
  serviceCreds: ServiceCred[];
  addServiceDialogOpen: boolean;
  selectedService: string;
  serviceFields: Record<string, string>;
  showServiceFields: Record<string, boolean>;
  setAddServiceDialogOpen: (open: boolean) => void;
  setSelectedService: (v: string) => void;
  setServiceFields: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setShowServiceFields: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  guardarCredServicio: () => Promise<void>;
  eliminarCredServicio: (id: string) => Promise<void>;
}

export function ServiceConnectionsSection(props: ServiceConnectionsSectionProps) {
  const {
    serviceCreds,
    addServiceDialogOpen,
    selectedService,
    serviceFields,
    showServiceFields,
    setAddServiceDialogOpen,
    setSelectedService,
    setServiceFields,
    setShowServiceFields,
    guardarCredServicio,
    eliminarCredServicio,
  } = props;

  return (
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
  );
}
