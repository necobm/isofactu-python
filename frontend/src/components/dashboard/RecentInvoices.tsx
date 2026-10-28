import { api } from '@/api'
import { formatCurrency, formatDate } from '@/lib/format'
import { useApi } from '@/lib/useApi'

interface RecentInvoicesProps {
  onViewAll?: () => void
}

export default function RecentInvoices({ onViewAll }: RecentInvoicesProps) {
  const invoices = useApi((signal) => api.listInvoices({ state: 'ISSUED', limit: 5 }, signal), [])
  const items = invoices.data?.items ?? []

  return (
    <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
        <div>
          <p className="text-sm font-semibold text-slate-800">Facturas Recientes</p>
          <p className="text-xs text-slate-400 mt-0.5">Últimas 5 facturas emitidas</p>
        </div>
        <button onClick={onViewAll} className="text-xs text-indigo-600 hover:text-indigo-700 font-medium">
          Ver todas →
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              <th className="text-left px-5 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Nº Factura</th>
              <th className="text-left px-5 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Cliente</th>
              <th className="text-left px-5 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Fecha</th>
              <th className="text-right px-5 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Base</th>
              <th className="text-right px-5 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Total</th>
              <th className="px-5 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {invoices.status === 'loading' && items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-slate-400 text-xs">Cargando facturas…</td>
              </tr>
            )}
            {invoices.status === 'error' && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-rose-500 text-xs">
                  No se pudieron cargar las facturas: {invoices.error.message}
                </td>
              </tr>
            )}
            {invoices.status === 'success' && items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-slate-400 text-xs">Todavía no hay facturas.</td>
              </tr>
            )}
            {items.map((inv) => (
              <tr key={inv.id} className="hover:bg-slate-50/50 transition-colors">
                <td className="px-5 py-3.5 font-mono text-xs text-slate-500">{inv.invoiceNumber?.formatted ?? '—'}</td>
                <td className="px-5 py-3.5 font-medium text-slate-700">{inv.recipient.fullName}</td>
                <td className="px-5 py-3.5 text-slate-500 text-xs">{formatDate(inv.issueDate)}</td>
                <td className="px-5 py-3.5 text-right text-slate-600">{formatCurrency(inv.subtotal)}</td>
                <td className="px-5 py-3.5 text-right font-semibold text-slate-800">{formatCurrency(inv.total)}</td>
                <td className="px-5 py-3.5 text-right">
                  <button onClick={onViewAll} className="text-slate-400 hover:text-indigo-600 transition-colors" aria-label="Ver factura">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
