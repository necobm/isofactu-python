import { useState } from 'react'
import { api } from '@/api'
import IncomeExpensesChart from '@/components/dashboard/IncomeExpensesChart'
import StatCard from '@/components/dashboard/StatCard'
import { formatCurrency, formatDate } from '@/lib/format'
import { PERIODS, periodRange, type PeriodId } from '@/lib/periods'
import { useApi } from '@/lib/useApi'

const IncomeIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
  </svg>
)

const ExpensesIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2z" />
  </svg>
)

const PendingIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
)

/** "1 factura emitida", "3 facturas emitidas" */
function count(n: number, singular: string, plural: string): string {
  return `${n} ${n === 1 ? singular : plural}`
}

interface DashboardProps {
  /** Opens the list of issued invoices (to collect the pending ones). */
  onViewInvoices: () => void
}

/** The tenant's activity from its invoices: income, expenses, what is pending collection. */
export default function Dashboard({ onViewInvoices }: DashboardProps) {
  const [periodId, setPeriodId] = useState<PeriodId>('year')
  const range = periodRange(periodId)
  const dashboard = useApi((signal) => api.getDashboard(range, signal), [range.from, range.to])
  // While another period loads, the previous figures stay on screen
  const data = dashboard.data ?? null
  const periodLabel = PERIODS.find((period) => period.id === periodId)!.label
  const pending = data?.pendingCollection

  return (
    <div className="space-y-6 max-w-screen-xl mx-auto">
      {/* Period */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-500">
          {data ? (
            <>
              Del <strong className="font-medium text-slate-700">{formatDate(data.periodStart)}</strong> al{' '}
              <strong className="font-medium text-slate-700">{formatDate(data.periodEnd)}</strong>
            </>
          ) : (
            ' '
          )}
        </p>
        <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
          Periodo
          <select
            value={periodId}
            onChange={(e) => setPeriodId(e.target.value as PeriodId)}
            className="text-sm text-slate-700 border border-slate-200 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          >
            {PERIODS.map((period) => (
              <option key={period.id} value={period.id}>
                {period.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {dashboard.status === 'error' && (
        <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <span>No se pudieron cargar los datos del panel: {dashboard.error.message}</span>
          <button onClick={dashboard.reload} className="shrink-0 font-medium text-rose-700 hover:text-rose-800">
            Reintentar
          </button>
        </div>
      )}

      {/* Figures */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        <StatCard
          title="Ingresos"
          value={data ? formatCurrency(data.income.base) : null}
          subtitle={data && `${count(data.income.count, 'factura emitida', 'facturas emitidas')} · sin IVA`}
          icon={<IncomeIcon />}
          iconBg="bg-indigo-50"
          iconColor="text-indigo-600"
        />
        <StatCard
          title="Gastos"
          value={data ? formatCurrency(data.expenses.base) : null}
          subtitle={data && `${count(data.expenses.count, 'factura recibida', 'facturas recibidas')} · sin IVA`}
          icon={<ExpensesIcon />}
          iconBg="bg-rose-50"
          iconColor="text-rose-500"
        />
        <StatCard
          title="Pendiente de cobro"
          value={pending ? formatCurrency(pending.total) : null}
          subtitle={
            pending && (
              <>
                {pending.count === 0 ? 'Todas las facturas emitidas están cobradas' : count(pending.count, 'factura sin cobrar', 'facturas sin cobrar')}
                {pending.overdueCount > 0 && (
                  <span className="block text-rose-600 font-medium">
                    {count(pending.overdueCount, 'vencida', 'vencidas')} · {formatCurrency(pending.overdueTotal)}
                  </span>
                )}
              </>
            )
          }
          icon={<PendingIcon />}
          iconBg="bg-amber-50"
          iconColor="text-amber-500"
          footer={
            <div className="flex items-center justify-between gap-2">
              <span className="text-slate-400">De cualquier fecha</span>
              <button onClick={onViewInvoices} className="font-medium text-indigo-600 hover:text-indigo-700">
                Ver facturas emitidas →
              </button>
            </div>
          }
        />
      </div>

      <IncomeExpensesChart monthly={data?.monthly ?? null} periodLabel={periodLabel} />
    </div>
  )
}
