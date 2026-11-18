import { useState } from 'react'
import { api, ApiError, type Invoice } from '@/api'
import ConfirmDialog from '@/components/ConfirmDialog'
import { formatCurrency, formatDate } from '@/lib/format'

function describe(invoice: Invoice): string {
  const amount = formatCurrency(invoice.total)
  if (invoice.kind === 'RECEIVED') {
    const number = invoice.invoiceNumber ? ` ${invoice.invoiceNumber.formatted}` : ''
    return (
      `Se eliminará la factura${number} de ${invoice.issuer.fullName} (${amount}) y dejará de contar ` +
      'como gasto. Esta acción no se puede deshacer.'
    )
  }
  return (
    `Se eliminará el borrador para ${invoice.recipient.fullName} del ${formatDate(invoice.issueDate)} ` +
    `(${amount}). Esta acción no se puede deshacer.`
  )
}

interface DeleteInvoiceDialogProps {
  /** A draft or a received invoice (see `isDeletable` in `./deletion`). */
  invoice: Invoice
  onDeleted: () => void
  onCancel: () => void
}

/** Asks for confirmation, then deletes a draft or a received invoice. */
export default function DeleteInvoiceDialog({ invoice, onDeleted, onCancel }: DeleteInvoiceDialogProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const received = invoice.kind === 'RECEIVED'

  async function remove() {
    setBusy(true)
    setError(null)
    try {
      if (received) await api.deleteReceivedInvoice(invoice.id)
      else await api.deleteInvoice(invoice.id)
      onDeleted()
    } catch (err) {
      setBusy(false)
      setError(
        err instanceof ApiError && err.status === 409
          ? 'La factura ya ha sido emitida y no se puede eliminar.'
          : `No se pudo eliminar la factura: ${err instanceof Error ? err.message : String(err)}`,
      )
    }
  }

  return (
    <ConfirmDialog
      title={received ? 'Eliminar factura recibida' : 'Eliminar borrador'}
      message={describe(invoice)}
      confirmLabel={received ? 'Eliminar factura' : 'Eliminar borrador'}
      busyLabel="Eliminando…"
      tone="danger"
      busy={busy}
      error={error}
      onConfirm={remove}
      onCancel={onCancel}
    />
  )
}
