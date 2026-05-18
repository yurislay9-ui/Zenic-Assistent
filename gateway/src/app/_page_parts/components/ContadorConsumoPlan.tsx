import { Progress } from "@/components/ui/progress";

export function ContadorConsumoPlan({
  etiqueta,
  actual,
  maximo,
  unlimited,
}: {
  etiqueta: string;
  actual: number;
  maximo: number;
  unlimited: boolean;
}) {
  if (unlimited) {
    return (
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-gray-500 font-medium truncate">
            {etiqueta}
          </span>
          <span className="text-[10px] text-emerald-600 font-bold shrink-0">
            {actual} / ∞
          </span>
        </div>
        <Progress value={0} className="h-1.5" />
      </div>
    );
  }

  const porcentaje = maximo > 0 ? Math.min((actual / maximo) * 100, 100) : 0;
  const cercano = porcentaje >= 80;
  const excedido = actual >= maximo;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-gray-500 font-medium truncate">
          {etiqueta}
        </span>
        <span
          className={`text-[10px] font-bold shrink-0 ${excedido ? "text-red-600" : cercano ? "text-amber-600" : "text-gray-700"}`}
        >
          {actual} / {maximo}
        </span>
      </div>
      <Progress
        value={porcentaje}
        className={`h-1.5 ${cercano ? "[&>div]:bg-amber-500" : ""} ${excedido ? "[&>div]:bg-red-500" : ""}`}
      />
    </div>
  );
}
