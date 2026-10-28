import InvoiceSection from '@/components/invoices/InvoiceSection'

interface InvoicesProps {
  /** Opens the edit view of a draft invoice. */
  onEditDraft: (invoiceId: number) => void
}

const PAGE_SIZE = 10
/** Drafts are listed in full: the API caps a page at 200, which only kicks in as a safety net. */
const DRAFTS_PAGE_SIZE = 200

export default function Invoices({ onEditDraft }: InvoicesProps) {
  return (
    <div className="space-y-6">
      <InvoiceSection
        state="DRAFT"
        title="Facturas en borrador"
        countLabel={{ singular: 'factura en borrador', plural: 'facturas en borrador' }}
        emptyMessage="No hay facturas en borrador."
        pageSize={DRAFTS_PAGE_SIZE}
        alwaysShowPagination={false}
        onSelect={(invoice) => onEditDraft(invoice.id)}
      />
      <InvoiceSection
        state="ISSUED"
        title="Facturas emitidas"
        countLabel={{ singular: 'factura emitida', plural: 'facturas emitidas' }}
        emptyMessage="Todavía no hay facturas emitidas. Crea la primera con «Nueva Factura»."
        pageSize={PAGE_SIZE}
      />
    </div>
  )
}
