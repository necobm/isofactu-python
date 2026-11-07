import type { InvoiceKind } from '@/api'
import InvoiceSection from '@/components/invoices/InvoiceSection'

interface InvoicesProps {
  /** Which book to show: issued invoices (income) or received ones (expenses). */
  kind: InvoiceKind
  /** Opens the edit view of an invoice: a draft, or any received invoice. */
  onEdit: (invoiceId: number) => void
}

const PAGE_SIZE = 10
/** Drafts are listed in full: the API caps a page at 200, which only kicks in as a safety net. */
const DRAFTS_PAGE_SIZE = 200

export default function Invoices({ kind, onEdit }: InvoicesProps) {
  if (kind === 'RECEIVED') {
    // No drafts: one list, and every received invoice can be edited
    return (
      <InvoiceSection
        kind="RECEIVED"
        title="Facturas recibidas"
        countLabel={{ singular: 'factura recibida', plural: 'facturas recibidas' }}
        emptyMessage="Todavía no hay facturas recibidas. Registra la primera con «Registrar Factura Recibida»."
        pageSize={PAGE_SIZE}
        onSelect={(invoice) => onEdit(invoice.id)}
      />
    )
  }
  return (
    <div className="space-y-6">
      <InvoiceSection
        kind="ISSUED"
        state="DRAFT"
        title="Facturas en borrador"
        countLabel={{ singular: 'factura en borrador', plural: 'facturas en borrador' }}
        emptyMessage="No hay facturas en borrador."
        pageSize={DRAFTS_PAGE_SIZE}
        alwaysShowPagination={false}
        onSelect={(invoice) => onEdit(invoice.id)}
      />
      <InvoiceSection
        kind="ISSUED"
        state="ISSUED"
        title="Facturas emitidas"
        countLabel={{ singular: 'factura emitida', plural: 'facturas emitidas' }}
        emptyMessage="Todavía no hay facturas emitidas. Crea la primera con «Nueva Factura»."
        pageSize={PAGE_SIZE}
      />
    </div>
  )
}
