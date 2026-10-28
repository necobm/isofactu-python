import { useState } from 'react'
import { api, type Invoice, type InvoiceState } from '@/api'
import { useApi } from '@/lib/useApi'
import InvoiceRow, { INVOICE_TABLE_COLUMNS } from './InvoiceRow'

interface InvoiceSectionProps {
  /** Which invoices the section lists. */
  state: InvoiceState
  title: string
  /** Shown when the section has no invoices. */
  emptyMessage: string
  /** "factura emitida" → "3 facturas emitidas" in the subtitle. */
  countLabel: { singular: string; plural: string }
  pageSize: number
  /**
   * Whether to render the pagination footer when everything fits in one page.
   * Defaults to `true`; the draft section turns it off since it lists every draft.
   */
  alwaysShowPagination?: boolean
  /**
   * What clicking a row does: without a handler it toggles the invoice details (issued
   * invoices); with one, the invoice is handed over instead (drafts open the edit view).
   */
  onSelect?: (invoice: Invoice) => void
}

const HEADER_CELL = 'px-5 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide'

export default function InvoiceSection({
  state,
  title,
  emptyMessage,
  countLabel,
  pageSize,
  alwaysShowPagination = true,
  onSelect,
}: InvoiceSectionProps) {
  const [page, setPage] = useState(0)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const invoices = useApi(
    (signal) => api.listInvoices({ state, limit: pageSize, offset: page * pageSize }, signal),
    [state, page, pageSize],
  )

  const collection = invoices.data
  const items = collection?.items ?? []
  const total = collection?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : page * pageSize + 1
  const to = Math.min(total, (page + 1) * pageSize)
  const showPagination = alwaysShowPagination || pageCount > 1

  return (
    <section
      className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden"
      aria-label={title}
      data-invoice-state={state}
    >
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {invoices.status === 'success' || collection
              ? `${total} ${total === 1 ? countLabel.singular : countLabel.plural}`
              : ' '}
          </p>
        </div>
        <button
          onClick={invoices.reload}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-indigo-600 font-medium transition-colors"
        >
          <svg className={`w-3.5 h-3.5 ${invoices.status === 'loading' ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Actualizar
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              <th className={`text-left ${HEADER_CELL}`}>Fecha</th>
              <th className={`text-left ${HEADER_CELL}`}>Nº Factura</th>
              <th className={`text-left ${HEADER_CELL}`}>Cliente</th>
              <th className={`text-right ${HEADER_CELL}`}>Base</th>
              <th className={`text-right ${HEADER_CELL}`}>IVA</th>
              <th className={`text-right ${HEADER_CELL}`}>Total</th>
              <th className="px-5 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {invoices.status === 'loading' && items.length === 0 && (
              <tr>
                <td colSpan={INVOICE_TABLE_COLUMNS} className="px-5 py-12 text-center text-slate-400 text-sm">
                  Cargando facturas…
                </td>
              </tr>
            )}
            {invoices.status === 'error' && (
              <tr>
                <td colSpan={INVOICE_TABLE_COLUMNS} className="px-5 py-12 text-center text-sm">
                  <p className="text-rose-500 font-medium">No se pudieron cargar las facturas</p>
                  <p className="text-slate-400 text-xs mt-1">{invoices.error.message}</p>
                  <button onClick={invoices.reload} className="mt-3 text-xs text-indigo-600 hover:text-indigo-700 font-medium">
                    Reintentar
                  </button>
                </td>
              </tr>
            )}
            {invoices.status === 'success' && items.length === 0 && (
              <tr>
                <td colSpan={INVOICE_TABLE_COLUMNS} className="px-5 py-10 text-center text-slate-400 text-sm">
                  {emptyMessage}
                </td>
              </tr>
            )}
            {items.map((invoice) => (
              <InvoiceRow
                key={invoice.id}
                invoice={invoice}
                expandable={onSelect === undefined}
                expanded={expandedId === invoice.id}
                onActivate={() =>
                  onSelect
                    ? onSelect(invoice)
                    : setExpandedId((current) => (current === invoice.id ? null : invoice.id))
                }
              />
            ))}
          </tbody>
        </table>
      </div>

      {showPagination && (
        <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 text-xs text-slate-500">
          <span>
            Mostrando {from}–{to} de {total}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Anterior
            </button>
            <span className="px-2">
              {page + 1} / {pageCount}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              disabled={page + 1 >= pageCount}
              className="px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
