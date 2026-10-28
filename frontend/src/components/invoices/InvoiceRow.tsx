import type { Invoice } from '@/api'
import { formatCurrency, formatDate } from '@/lib/format'
import InvoiceDetails from './InvoiceDetails'

/** Number of columns of the invoice table (the details row spans all of them). */
export const INVOICE_TABLE_COLUMNS = 7

interface InvoiceRowProps {
  invoice: Invoice
  /** Clicking the row expands the details; when false it just triggers `onActivate`. */
  expandable: boolean
  expanded: boolean
  onActivate: () => void
}

export default function InvoiceRow({ invoice, expandable, expanded, onActivate }: InvoiceRowProps) {
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
        </td>
        <td className="px-5 py-3.5">
          <p className="font-medium text-slate-700">{invoice.recipient.fullName}</p>
          <p className="text-xs text-slate-400">
            {invoice.recipient.document.type} {invoice.recipient.document.number}
          </p>
        </td>
        <td className="px-5 py-3.5 text-right text-slate-600 whitespace-nowrap">{formatCurrency(invoice.subtotal)}</td>
        <td className="px-5 py-3.5 text-right text-slate-600 whitespace-nowrap">{formatCurrency(invoice.taxAmount)}</td>
        <td className="px-5 py-3.5 text-right font-semibold text-slate-800 whitespace-nowrap">
          {formatCurrency(invoice.total)}
        </td>
        <td className="px-5 py-3.5 text-right">
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
            <InvoiceDetails invoice={invoice} />
          </td>
        </tr>
      )}
    </>
  )
}
