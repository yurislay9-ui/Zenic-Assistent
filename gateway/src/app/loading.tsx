// Zenic-Agents v3.0 — Loading State
// Suspense boundary para la ruta raíz del dashboard.

export default function Loading() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0F1225]">
      <div className="text-center space-y-4">
        <div className="relative">
          <svg
            className="h-12 w-12 mx-auto animate-spin text-emerald-400"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        </div>
        <p className="text-white/60 text-sm tracking-widest uppercase">
          Iniciando Motor Zenic...
        </p>
        <div className="flex items-center justify-center gap-2">
          <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
          <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
          <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce" />
        </div>
      </div>
    </div>
  );
}
