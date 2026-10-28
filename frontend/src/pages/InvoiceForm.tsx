import { useEffect, useMemo, useState } from 'react'
import { api, type Invoice, type InvoiceInput, type InvoiceState, type PaymentMethod, type Subject } from '@/api'
import ConfirmDialog from '@/components/ConfirmDialog'
import ClientPicker from '@/components/invoice/ClientPicker'
import ConceptsTable from '@/components/invoice/ConceptsTable'
import TotalsPanel, { type TaxBreakdownEntry } from '@/components/invoice/TotalsPanel'
import { type LineDraft } from '@/components/invoice/taxes'
import { resolveIssuer } from '@/lib/issuer'
import { invoiceAmounts, lineAmounts } from '@/lib/money'
import { useApi } from '@/lib/useApi'

const SERIES_OPTIONS = ['F-2024', 'F-2025', 'F-2026', 'PRO-2026', 'REC-2026']
const DEFAULT_SERIES = 'F-2026'
const DEFAULT_VAT_RATE = 21

const ISSUE_CONFIRMATION =
  'Si finalizas esta factura, constará como ingreso en tu contabilidad y no podrá ser modificada ' +
  'más adelante. ¿Deseas continuar con la emisión de la factura?'

let nextId = 1

function emptyLine(): LineDraft {
  return { id: nextId++, description: '', quantity: 1, unitPrice: 0, taxRate: DEFAULT_VAT_RATE }
}

function toNumber(value: string | number): number {
  return parseFloat(String(value)) || 0
}

/** Local date as YYYY-MM-DD (the `<input type="date">` format). */
function isoToday(): string {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}

interface InvoiceFormProps {
  /** When given, the form edits that (draft) invoice instead of creating a new one. */
  invoiceId?: number
  /** Leave without saving. */
  onBack: () => void
  /** The invoice was stored (as draft or issued). */
  onSaved: () => void
}

export default function InvoiceForm({ invoiceId, onBack, onSaved }: InvoiceFormProps) {
  const editing = invoiceId !== undefined

  const [invoiceSeries, setInvoiceSeries] = useState(DEFAULT_SERIES)
  const [client, setClient] = useState<Subject | null>(null)
  const [lines, setLines] = useState<LineDraft[]>([emptyLine()])
  const [notes, setNotes] = useState('')
  const [retentionRate, setRetentionRate] = useState<number | null>(null)
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('TRANSFER')
  const [issueDate, setIssueDate] = useState(isoToday())
  const [dueDate, setDueDate] = useState('')
  const [saving, setSaving] = useState<InvoiceState | null>(null)
  const [confirmingIssue, setConfirmingIssue] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState<Invoice | null>(null)

  // -- editing: load the invoice and pre-fill the form with its data ---------------------
  const existing = useApi(
    (signal) => (invoiceId === undefined ? Promise.resolve(null) : api.getInvoice(invoiceId, signal)),
    [invoiceId],
  )
  useEffect(() => {
    const invoice = existing.status === 'success' ? existing.data : null
    if (!invoice || loaded?.id === invoice.id) return
    setLoaded(invoice)
    setClient(invoice.recipient)
    setInvoiceSeries(invoice.invoiceNumber?.serial ?? DEFAULT_SERIES)
    setLines(
      invoice.lines.length > 0
        ? invoice.lines.map((line) => ({
            id: nextId++,
            description: line.description,
            quantity: line.quantity,
            unitPrice: line.unitPrice,
            taxRate: line.taxRate,
          }))
        : [emptyLine()],
    )
    setNotes(invoice.notes)
    setRetentionRate(invoice.retentionRate > 0 ? invoice.retentionRate : null)
    setPaymentMethod(invoice.paymentMethod)
    setIssueDate(invoice.issueDate)
    setDueDate(invoice.dueDate ?? '')
  }, [existing, loaded])

  // A validation / server message only makes sense until the user edits the form again.
  useEffect(
    () => setError(null),
    [client, lines, notes, retentionRate, paymentMethod, issueDate, dueDate, invoiceSeries],
  )

  const amounts = useMemo(
    () =>
      lines.map((line) => ({
        taxRate: line.taxRate,
        ...lineAmounts(toNumber(line.quantity), toNumber(line.unitPrice), line.taxRate),
      })),
    [lines],
  )
  const totals = useMemo(() => invoiceAmounts(amounts, retentionRate ?? 0), [amounts, retentionRate])

  /** One entry per distinct VAT rate used in the lines, highest rate first. */
  const taxBreakdown = useMemo<TaxBreakdownEntry[]>(() => {
    const byRate = new Map<number, TaxBreakdownEntry>()
    for (const line of amounts) {
      const entry = byRate.get(line.taxRate) ?? { rate: line.taxRate, base: 0, amount: 0 }
      byRate.set(line.taxRate, {
        rate: line.taxRate,
        base: entry.base + line.subtotal,
        amount: entry.amount + line.taxAmount,
      })
    }
    return [...byRate.values()].sort((a, b) => b.rate - a.rate)
  }, [amounts])

  function handleLineChange<K extends keyof LineDraft>(id: number, field: K, value: LineDraft[K]) {
    setLines((prev) => prev.map((l) => (l.id === id ? { ...l, [field]: value } : l)))
  }

  function handleAddLine() {
    setLines((prev) => [...prev, emptyLine()])
  }

  function handleRemoveLine(id: number) {
    setLines((prev) => (prev.length > 1 ? prev.filter((l) => l.id !== id) : prev))
  }

  /**
   * Returns a message when the form cannot be saved. The same rules apply whether the
   * invoice is stored as a draft or issued: both end up as an invoice in the database.
   */
  function validate(): string | null {
    if (!client) return 'Selecciona un cliente.'
    if (!issueDate) return 'Indica la fecha de emisión.'
    if (issueDate > isoToday()) return 'La fecha de emisión no puede ser futura.'
    if (dueDate && dueDate < issueDate) return 'La fecha de vencimiento no puede ser anterior a la de emisión.'
    if (lines.some((line) => !line.description.trim())) return 'Todos los conceptos necesitan una descripción.'
    if (totals.subtotal <= 0) return 'La factura debe tener algún importe.'
    return null
  }

  function buildPayload(state: InvoiceState, issuerId: number): InvoiceInput {
    return {
      state,
      issueDate,
      // Drafts are numberless; when issuing, the server assigns the next number of the serial.
      ...(state === 'ISSUED' ? { invoiceNumber: { serial: invoiceSeries } } : {}),
      issuerId,
      recipientId: client!.id,
      notes: notes.trim(),
      dueDate: dueDate || null,
      paymentMethod,
      retentionRate: retentionRate ?? 0,
      lines: lines.map((line) => ({
        description: line.description.trim(),
        quantity: toNumber(line.quantity),
        unitPrice: toNumber(line.unitPrice),
        taxRate: line.taxRate,
      })),
    }
  }

  async function save(state: InvoiceState) {
    const problem = validate()
    if (problem) {
      setConfirmingIssue(false)
      setError(problem)
      return
    }
    setError(null)
    setSaving(state)
    try {
      const issuer = await resolveIssuer()
      const payload = buildPayload(state, issuer.id)
      if (invoiceId === undefined) await api.createInvoice(payload)
      else await api.updateInvoice(invoiceId, payload)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSaving(null)
      setConfirmingIssue(false)
    }
  }

  function requestIssue() {
    const problem = validate()
    if (problem) {
      setError(problem)
      return
    }
    setConfirmingIssue(true)
  }

  const busy = saving !== null
  const alreadyIssued = loaded?.state === 'ISSUED'
  const title = editing ? 'Editar Borrador' : 'Nueva Factura'

  if (editing && existing.status === 'loading' && !loaded) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-sm text-slate-400">
        Cargando factura…
      </div>
    )
  }
  if (editing && existing.status === 'error') {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center gap-3">
        <p className="text-sm text-rose-600">No se pudo cargar la factura: {existing.error.message}</p>
        <button onClick={onBack} className="text-sm font-medium text-indigo-600 hover:text-indigo-700">
          Volver a las facturas
        </button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Page header */}
      <div className="bg-white border-b border-slate-200 flex-shrink-0">
        <div className="max-w-screen-xl mx-auto px-6 h-14 flex items-center gap-4">
          <button
            onClick={onBack}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
            aria-label="Volver"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>

          <h1 className="text-base font-bold text-slate-800 flex-1">{title}</h1>

          <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
            Serie
            <select
              value={invoiceSeries}
              onChange={(e) => setInvoiceSeries(e.target.value)}
              className="text-sm text-slate-700 border border-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white font-medium"
            >
              {SERIES_OPTIONS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {/* Main content */}
      <main className="flex-1 max-w-screen-xl mx-auto w-full px-6 py-6 pb-24">
        {alreadyIssued && (
          <p className="mb-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            Esta factura ya está emitida, por lo que no puede modificarse.
          </p>
        )}
        <div className="grid grid-cols-12 gap-6">
          {/* Left column */}
          <div className="col-span-8 space-y-5">
            {/* Client section */}
            <div className="bg-white rounded-xl border border-slate-200 px-5 py-4">
              <h2 className="text-sm font-semibold text-slate-700 mb-4">Cliente</h2>
              <ClientPicker value={client} onChange={setClient} />
            </div>

            {/* Concepts table */}
            <ConceptsTable
              lines={lines}
              onLineChange={handleLineChange}
              onAddLine={handleAddLine}
              onRemoveLine={handleRemoveLine}
            />

            {/* Additional notes */}
            <div className="bg-white rounded-xl border border-slate-200 px-5 py-4">
              <label htmlFor="invoice-notes" className="block text-sm font-semibold text-slate-700 mb-3">
                Notas adicionales
              </label>
              <textarea
                id="invoice-notes"
                rows={4}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                maxLength={5000}
                placeholder="Condiciones de pago, referencias, observaciones… Aparecerán en la factura."
                className="w-full resize-y text-sm text-slate-700 border border-slate-200 rounded-lg px-3 py-2 placeholder-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>
          </div>

          {/* Right column */}
          <div className="col-span-4">
            <TotalsPanel
              subtotal={totals.subtotal}
              taxBreakdown={taxBreakdown}
              retentionRate={retentionRate}
              retentionAmount={totals.retentionAmount}
              total={totals.total}
              paymentMethod={paymentMethod}
              issueDate={issueDate}
              dueDate={dueDate}
              today={isoToday()}
              onRetentionRateChange={setRetentionRate}
              onPaymentMethodChange={setPaymentMethod}
              onIssueDateChange={setIssueDate}
              onDueDateChange={setDueDate}
            />
          </div>
        </div>
      </main>

      {/* Sticky footer */}
      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-slate-200 z-10">
        <div className="max-w-screen-xl mx-auto px-6 h-16 flex items-center justify-between gap-6">
          <p role={error ? 'alert' : undefined} className={`text-xs truncate ${error ? 'text-rose-600 font-medium' : 'text-slate-400'}`}>
            {error ??
              (editing
                ? 'Guarda los cambios del borrador o finaliza la factura para emitirla con número.'
                : 'Guarda un borrador para seguir más tarde o finaliza la factura para emitirla con número.')}
          </p>
          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={onBack}
              disabled={busy}
              className="text-sm font-medium text-slate-500 hover:text-slate-700 px-4 py-2 rounded-lg hover:bg-slate-100 transition-colors disabled:opacity-50"
            >
              Cancelar
            </button>
            <button
              onClick={() => save('DRAFT')}
              disabled={busy || alreadyIssued}
              className="text-sm font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 px-4 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving === 'DRAFT' ? 'Guardando…' : editing ? 'Guardar' : 'Guardar Borrador'}
            </button>
            <button
              onClick={requestIssue}
              disabled={busy || alreadyIssued}
              className="text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 px-4 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving === 'ISSUED' ? 'Emitiendo…' : 'Finalizar Factura'}
            </button>
          </div>
        </div>
      </div>

      {confirmingIssue && (
        <ConfirmDialog
          title="Finalizar factura"
          message={ISSUE_CONFIRMATION}
          confirmLabel="Emitir Factura"
          busy={saving === 'ISSUED'}
          onConfirm={() => save('ISSUED')}
          onCancel={() => setConfirmingIssue(false)}
        />
      )}
    </div>
  )
}
