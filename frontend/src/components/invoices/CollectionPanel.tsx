import { useState } from 'react'
import { api, type Invoice } from '@/api'
import { formatDate } from '@/lib/format'
import { isoDate } from '@/lib/periods'
import CollectionBadge from './CollectionBadge'
import { collectionStatus } from './collection'

interface CollectionPanelProps {
  /** An issued (final) invoice. */
  invoice: Invoice
  /** The invoice was marked as collected or pending: reload it. */
  onChanged: () => void
}

/** Whether the client has paid an issued invoice, and the controls to record it. */
export default function CollectionPanel({ invoice, onChanged }: CollectionPanelProps) {
  const today = isoDate(new Date())
  const status = collectionStatus(invoice, today)
  const [collectedOn, setCollectedOn] = useState(today < invoice.issueDate ? invoice.issueDate : today)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (status === null) return null

  async function save(value: string | null) {
    if (value !== null && (!value || value < invoice.issueDate || value > today)) {
      setError('La fecha de cobro debe estar entre la fecha de emisión y hoy.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api.setInvoiceCollection(invoice.id, value)
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3">
      <div className="flex items-center gap-3">
        <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Cobro</p>
        <CollectionBadge status={status} />
        <p className="text-xs text-slate-600">
          {status === 'collected'
            ? `Cobrada el ${formatDate(invoice.collectedOn!)}`
            : status === 'overdue'
              ? `Venció el ${formatDate(invoice.dueDate!)}`
              : invoice.dueDate
                ? `Vence el ${formatDate(invoice.dueDate)}`
                : 'Sin fecha de vencimiento'}
        </p>
      </div>
      <div className="flex items-center gap-2">
        {status === 'collected' ? (
          <button
            type="button"
            onClick={() => save(null)}
            disabled={busy}
            className="text-xs font-medium text-slate-600 border border-slate-200 hover:bg-slate-50 px-3 py-1.5 rounded-lg disabled:opacity-50"
          >
            {busy ? 'Guardando…' : 'Marcar como pendiente'}
          </button>
        ) : (
          <>
            <label className="flex items-center gap-2 text-xs text-slate-500">
              Fecha de cobro
              <input
                type="date"
                value={collectedOn}
                min={invoice.issueDate}
                max={today}
                onChange={(e) => setCollectedOn(e.target.value)}
                disabled={busy}
                className="text-xs text-slate-700 border border-slate-200 rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </label>
            <button
              type="button"
              onClick={() => save(collectedOn)}
              disabled={busy}
              className="text-xs font-medium text-white bg-emerald-600 hover:bg-emerald-700 px-3 py-1.5 rounded-lg disabled:opacity-50"
            >
              {busy ? 'Guardando…' : 'Marcar como cobrada'}
            </button>
          </>
        )}
      </div>
      {error && (
        <p role="alert" className="w-full text-xs text-rose-600">
          {error}
        </p>
      )}
    </div>
  )
}
