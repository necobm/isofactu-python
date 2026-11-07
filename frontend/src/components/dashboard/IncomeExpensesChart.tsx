import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { MonthlyBalance } from '@/api'
import { formatCurrency } from '@/lib/format'
import { longMonthLabel, monthLabel } from '@/lib/periods'

const INCOME_COLOR = '#6366f1'
const EXPENSES_COLOR = '#fb7185'

/** 12500 -> "12,5 k€", 800 -> "800 €" */
function compactEuro(value: number): string {
  if (Math.abs(value) >= 1000) return `${(value / 1000).toLocaleString('es-ES', { maximumFractionDigits: 1 })} k€`
  return `${value.toLocaleString('es-ES', { maximumFractionDigits: 0 })} €`
}

interface ChartPoint extends MonthlyBalance {
  label: string
}

interface TooltipProps {
  active?: boolean
  payload?: { payload?: ChartPoint }[]
}

function MonthTooltip({ active, payload }: TooltipProps) {
  const point = payload?.[0]?.payload
  if (!active || !point) return null
  const balance = point.income - point.expenses
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2.5 text-xs space-y-0.5">
      <p className="font-semibold text-slate-700 mb-1 first-letter:uppercase">{longMonthLabel(point.month)}</p>
      <p style={{ color: INCOME_COLOR }}>Ingresos: {formatCurrency(point.income)}</p>
      <p style={{ color: EXPENSES_COLOR }}>Gastos: {formatCurrency(point.expenses)}</p>
      <p className={`pt-1 border-t border-slate-100 font-medium ${balance < 0 ? 'text-rose-600' : 'text-slate-700'}`}>
        Resultado: {formatCurrency(balance)}
      </p>
    </div>
  )
}

interface IncomeExpensesChartProps {
  /** One entry per month of the period; `null` while loading. */
  monthly: MonthlyBalance[] | null
  /** What the period is, for the subtitle ("Este año"...). */
  periodLabel: string
}

/** Month by month taxable base of the invoices issued (income) and received (expenses). */
export default function IncomeExpensesChart({ monthly, periodLabel }: IncomeExpensesChartProps) {
  const spansYears = monthly !== null && new Set(monthly.map((point) => point.month.slice(0, 4))).size > 1
  const data: ChartPoint[] = (monthly ?? []).map((point) => ({ ...point, label: monthLabel(point.month, spansYears) }))
  const empty = monthly !== null && monthly.every((point) => point.income === 0 && point.expenses === 0)

  return (
    <section className="bg-white rounded-xl p-5 border border-slate-100 shadow-sm" aria-label="Ingresos vs Gastos">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">Ingresos vs Gastos</h2>
          <p className="text-xs text-slate-400 mt-0.5">Base imponible por mes, sin IVA · {periodLabel}</p>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm inline-block" style={{ background: INCOME_COLOR }} />
            Ingresos
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm inline-block" style={{ background: EXPENSES_COLOR }} />
            Gastos
          </span>
        </div>
      </div>
      {monthly === null ? (
        <div className="h-[260px] rounded-lg bg-slate-50 animate-pulse" />
      ) : empty ? (
        <div className="h-[260px] flex items-center justify-center text-sm text-slate-400">
          No hay facturas en este periodo.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 4 }} barGap={2}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
            <YAxis tickFormatter={compactEuro} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={64} />
            <Tooltip content={<MonthTooltip />} cursor={{ fill: '#f8fafc' }} />
            <Bar dataKey="income" name="Ingresos" fill={INCOME_COLOR} radius={[4, 4, 0, 0]} maxBarSize={32} />
            <Bar dataKey="expenses" name="Gastos" fill={EXPENSES_COLOR} radius={[4, 4, 0, 0]} maxBarSize={32} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </section>
  )
}
