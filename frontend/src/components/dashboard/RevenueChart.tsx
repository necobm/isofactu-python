import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'

interface MonthlyPoint {
  mes: string
  ingresos: number
  gastos: number
}

const data: MonthlyPoint[] = [
  { mes: 'Ene', ingresos: 8400, gastos: 3200 },
  { mes: 'Feb', ingresos: 9200, gastos: 3800 },
  { mes: 'Mar', ingresos: 7800, gastos: 2900 },
  { mes: 'Abr', ingresos: 11200, gastos: 4100 },
  { mes: 'May', ingresos: 10500, gastos: 3600 },
  { mes: 'Jun', ingresos: 12450, gastos: 4200 },
]

const formatEuro = (v: number) => `€${(v / 1000).toFixed(1)}k`

interface TooltipPayloadEntry {
  name?: string | number
  value?: string | number
  color?: string
}

interface CustomTooltipProps {
  active?: boolean
  payload?: TooltipPayloadEntry[]
  label?: string | number
}

const CustomTooltip = ({ active, payload, label }: CustomTooltipProps) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2.5 text-xs">
      <p className="font-semibold text-slate-700 mb-1">{label}</p>
      {payload.map((p) => (
        <p key={String(p.name)} style={{ color: p.color }}>
          {p.name === 'ingresos' ? 'Ingresos' : 'Gastos'}: €{Number(p.value).toLocaleString('es-ES')}
        </p>
      ))}
    </div>
  )
}

export default function RevenueChart() {
  return (
    <div className="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
      <div className="flex items-center justify-between mb-5">
        <div>
          <p className="text-sm font-semibold text-slate-800">Evolución de Ingresos</p>
          <p className="text-xs text-slate-400 mt-0.5">Últimos 6 meses</p>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-1.5 rounded-full bg-indigo-500 inline-block" />
            Ingresos
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-1.5 rounded-full bg-rose-400 inline-block" />
            Gastos
          </span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
          <defs>
            <linearGradient id="gradIngresos" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="gradGastos" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#fb7185" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#fb7185" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="mes" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
          <YAxis tickFormatter={formatEuro} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
          <Tooltip content={<CustomTooltip />} />
          <Area type="monotone" dataKey="ingresos" stroke="#6366f1" strokeWidth={2} fill="url(#gradIngresos)" dot={false} activeDot={{ r: 4 }} />
          <Area type="monotone" dataKey="gastos" stroke="#fb7185" strokeWidth={2} fill="url(#gradGastos)" dot={false} activeDot={{ r: 4 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
