import type { Invoice } from '@/api'
import { formatCurrency, formatDate } from '@/lib/format'
import { isoDate } from '@/lib/periods'
import CollectionBadge from './CollectionBadge'
import { collectionStatus } from './collection'
import InvoiceDetails from './InvoiceDetails'

/** Number of columns of the invoice table (the details row spans all of them). */
export const INVOICE_TABLE_COLUMNS = 7

interface InvoiceRowProps {
  invoice: Invoice
  /** Clicking the row expands the details; when false it just triggers `onActivate`. */
  expandable: boolean
  expanded: boolean
  onActivate: () => void
  /** The invoice changed from its details (e.g. marked as collected): reload the list. */
  onChanged?: () => void
  /** Offers to delete the invoice (drafts and received invoices only). */
  onDelete?: () => void
}

export default function InvoiceRow({ invoice, expandable, expanded, onActivate, onChanged, onDelete }: InvoiceRowProps) {
  const collection = collectionStatus(invoice, isoDate(new Date()))
  // The other party: the client of an issued invoice, the supplier of a received one
  const counterpart = invoice.kind === 'RECEIVED' ? invoice.issuer : invoice.recipient
  return (
    <>
      <tr
        onClick={onActivate}
        className={`cursor-pointer transition-colors ${expanded ? 'bg-indigo-50/40' : 'hover:bg-slate-50/50'}`}
        {...(expandable ? { 'aria-expanded': expanded } : {})}
      >
        <td className="px-5 py-3.5 text-slate-500 text-xs whitespace-nowrap">{formatDate(invoice.issueDate)}</td>
        <td className="px-5 py-3.5 font-mono text-xs text-slate-500">
          {invoice.invoiceNumber ? invoice.invoiceNumber.formatted : <span className="italic text-slate-400">Sin número</span>}
          {collection && (
            <span className="block mt-1 font-sans">
              <CollectionBadge status={collection} />
            </span>
          )}
        </td>
        <td className="px-5 py-3.5">
          <p className="font-medium text-slate-700">{counterpart.fullName}</p>
          <p className="text-xs text-slate-400">
            {counterpart.document.type} {counterpart.document.number}
          </p>
        </td>
        <td className="px-5 py-3.5 text-right text-slate-600 whitespace-nowrap">{formatCurrency(invoice.subtotal)}</td>
        <td className="px-5 py-3.5 text-right text-slate-600 whitespace-nowrap">{formatCurrency(invoice.taxAmount)}</td>
        <td className="px-5 py-3.5 text-right font-semibold text-slate-800 whitespace-nowrap">
          {formatCurrency(invoice.total)}
        </td>
        <td className="px-5 py-3.5 text-right whitespace-nowrap">
          {onDelete && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation() // the row itself opens the invoice
                onDelete()
              }}
              title="Eliminar"
              aria-label={`Eliminar factura de ${counterpart.fullName}`}
              className="mr-2 p-1.5 align-middle rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          )}
          <svg
            className={`w-4 h-4 inline-block text-slate-400 transition-transform ${expanded ? 'rotate-90 text-indigo-600' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </td>
      </tr>

      {expandable && expanded && (
        <tr className="bg-slate-50/70">
          <td colSpan={INVOICE_TABLE_COLUMNS} className="px-5 pb-5 pt-2">
            <InvoiceDetails invoice={invoice} onChanged={collection ? onChanged : undefined} />
          </td>
        </tr>
      )}
    </>
  )
}
