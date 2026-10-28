import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

interface StatusSlice {
  name: string
  value: number
  color: string
}

const data: StatusSlice[] = [
  { name: 'Cobradas', value: 68, color: '#10b981' },
  { name: 'Pendientes', value: 22, color: '#f59e0b' },
  { name: 'Vencidas', value: 10, color: '#ef4444' },
]

interface CustomTooltipProps {
  active?: boolean
  payload?: { name?: string | number; value?: string | number; payload?: StatusSlice }[]
}

const CustomTooltip = ({ active, payload }: CustomTooltipProps) => {
  if (!active || !payload?.length) return null
  const [entry] = payload
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2 text-xs">
      <p style={{ color: entry.payload?.color }} className="font-medium">
        {entry.name}: {entry.value}%
      </p>
    </div>
  )
}

export default function InvoiceStatusChart() {
  return (
    <div className="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
      <p className="text-sm font-semibold text-slate-800 mb-1">Estado de Facturas</p>
      <p className="text-xs text-slate-400 mb-4">Distribución actual</p>

      <div className="flex items-center gap-4">
        <ResponsiveContainer width={120} height={120}>
          <PieChart>
            <Pie data={data} cx="50%" cy="50%" innerRadius={35} outerRadius={55} dataKey="value" strokeWidth={0}>
              {data.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
          </PieChart>
        </ResponsiveContainer>

        <div className="flex-1 space-y-2.5">
          {data.map((item) => (
            <div key={item.name} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: item.color }} />
                <span className="text-xs text-slate-600">{item.name}</span>
              </div>
              <span className="text-xs font-semibold text-slate-700">{item.value}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
