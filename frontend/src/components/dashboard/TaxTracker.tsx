interface TaxTrackerProps {
  percent?: number
  dueDate?: string
  quarter?: string
}

const steps = [
  { label: 'Ingresos', done: true },
  { label: 'Gastos', done: true },
  { label: 'IVA / IRPF', done: false },
]

export default function TaxTracker({ percent = 70, dueDate = '20 Jul 2026', quarter = '2T 2026' }: TaxTrackerProps) {
  return (
    <div className="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-sm font-semibold text-slate-800">Declaración Trimestral</p>
          <p className="text-xs text-slate-400 mt-0.5">{quarter} · Vence {dueDate}</p>
        </div>
        <span className="text-xs font-medium bg-amber-50 text-amber-600 border border-amber-200 px-2.5 py-1 rounded-full">
          En progreso
        </span>
      </div>

      <div className="space-y-2">
        <div className="flex justify-between text-xs">
          <span className="text-slate-500">Completado</span>
          <span className="font-semibold text-slate-700">{percent}%</span>
        </div>
        <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
          <div className="h-full bg-indigo-500 rounded-full transition-all duration-500" style={{ width: `${percent}%` }} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 mt-4">
        {steps.map((step) => (
          <div key={step.label} className="flex items-center gap-1.5">
            <span
              className={`w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0 ${
                step.done ? 'bg-emerald-500' : 'bg-slate-200'
              }`}
            >
              {step.done && (
                <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                </svg>
              )}
            </span>
            <span className="text-xs text-slate-500">{step.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
