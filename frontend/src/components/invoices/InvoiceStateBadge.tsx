import type { InvoiceState } from '@/api'

const INVOICE_STATE_LABELS: Record<InvoiceState, string> = {
  DRAFT: 'Borrador',
  ISSUED: 'Emitida',
}

const STYLES: Record<InvoiceState, string> = {
  DRAFT: 'bg-amber-50 text-amber-700 border-amber-200',
  ISSUED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
}

export default function InvoiceStateBadge({ state }: { state: InvoiceState }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${STYLES[state]}`}
    >
      {INVOICE_STATE_LABELS[state]}
    </span>
  )
}
