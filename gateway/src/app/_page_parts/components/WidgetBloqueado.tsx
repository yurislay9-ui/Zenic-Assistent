import { Lock, Crown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { TIER_DISPLAY_NAMES } from "@/lib/pricing-engine/types";
import type { SubscriptionTierName } from "@/lib/pricing-engine/types";

export function WidgetBloqueado({
  etiqueta,
  descripcion,
  tierRequerido,
}: {
  etiqueta: string;
  descripcion: string;
  tierRequerido: string;
}) {
  const nombreTier =
    TIER_DISPLAY_NAMES[tierRequerido as SubscriptionTierName] ?? tierRequerido;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="rounded-xl border-2 border-dashed border-gray-200 bg-gray-50/50 p-5 opacity-60 cursor-not-allowed relative overflow-hidden">
            <div className="flex items-center gap-2 mb-2">
              <Lock className="h-4 w-4 text-gray-400" />
              <span className="text-xs font-bold text-gray-500 truncate">
                {etiqueta}
              </span>
            </div>
            <p className="text-[10px] text-gray-400">{descripcion}</p>
            <Badge className="mt-2 bg-gray-200 text-gray-500 text-[8px] px-1.5 py-0 border-0 font-bold shrink-0">
              <Crown className="h-3 w-3 mr-1" />
              Requiere {nombreTier}
            </Badge>
          </div>
        </TooltipTrigger>
        <TooltipContent>
          <p className="text-xs">
            Actualiza a <strong>{nombreTier}</strong> para desbloquear esta
            función
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
