import type { Invoice, Subject } from '@/api'
import { PAYMENT_METHOD_LABELS } from '@/components/invoice/paymentMethods'
import { formatAmount, formatCurrency, formatDate, formatRate } from '@/lib/format'
import InvoiceStateBadge from './InvoiceStateBadge'

/** Postal address as display lines, skipping the parts that are empty. */
function addressLines({ street, zipCode, city, province, countryIsoCode }: Subject['address']): string[] {
  const locality = [zipCode, city].filter(Boolean).join(' ')
  const region = [province, countryIsoCode].filter(Boolean).join(', ')
  return [street, locality, region].filter(Boolean)
}

function PartyCard({ title, subject }: { title: string; subject: Subject }) {
  const lines = addressLines(subject.address)
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">{title}</p>
      <p className="mt-1 text-sm font-semibold text-slate-800">{subject.fullName}</p>
      <p className="text-xs text-slate-500">
        {subject.document.type} {subject.document.number}
      </p>
      {lines.length > 0 && (
        <address className="mt-2 text-xs not-italic leading-relaxed text-slate-500">
          {lines.map((line) => (
            <span key={line} className="block">{line}</span>
          ))}
        </address>
      )}
    </div>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="inline text-slate-400">{label}: </dt>
      <dd className="inline font-medium text-slate-700">{value}</dd>
    </div>
  )
}

/** Full read-only view of an invoice: header, parties, concepts, notes and totals. */
export default function InvoiceDetails({ invoice }: { invoice: Invoice }) {
  const number = invoice.invoiceNumber
  const hasRetention = invoice.retentionRate > 0

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <div className="flex items-center gap-3">
          <p className="text-sm font-semibold text-slate-800">
            {number ? (
              <>
                Factura <span className="font-mono">{number.formatted}</span>
              </>
            ) : (
              <>
                Factura <span className="font-normal italic text-slate-400">sin número</span>
              </>
            )}
          </p>
          <InvoiceStateBadge state={invoice.state} />
        </div>
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs">
          <Fact label="Fecha" value={formatDate(invoice.issueDate)} />
          {number?.serial && <Fact label="Serie" value={number.serial} />}
          {number && <Fact label="Número" value={number.number} />}
          <Fact label="Pago" value={PAYMENT_METHOD_LABELS[invoice.paymentMethod]} />
          {invoice.dueDate && <Fact label="Vencimiento" value={formatDate(invoice.dueDate)} />}
        </dl>
      </div>

      {/* Parties */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <PartyCard title="Emisor" subject={invoice.issuer} />
        <PartyCard title="Cliente" subject={invoice.recipient} />
      </div>

      {/* Concepts */}
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-100 text-slate-400 uppercase tracking-wider">
              <th className="text-left px-4 py-2 font-medium">Concepto</th>
              <th className="text-right px-4 py-2 font-medium w-20">Cant.</th>
              <th className="text-right px-4 py-2 font-medium w-28">Precio U.</th>
              <th className="text-right px-4 py-2 font-medium w-20">IVA</th>
              <th className="text-right px-4 py-2 font-medium w-28">Base</th>
              <th className="text-right px-4 py-2 font-medium w-28">Cuota</th>
              <th className="text-right px-4 py-2 font-medium w-28">Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {invoice.lines.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-3 text-center text-slate-400">Sin conceptos</td>
              </tr>
            )}
            {invoice.lines.map((line) => (
              <tr key={line.id}>
                <td className="px-4 py-2 text-slate-700">{line.description || <span className="text-slate-300">—</span>}</td>
                <td className="px-4 py-2 text-right text-slate-600">{formatAmount(line.quantity)}</td>
                <td className="px-4 py-2 text-right text-slate-600">{formatAmount(line.unitPrice)} €</td>
                <td className="px-4 py-2 text-right text-slate-600">{formatRate(line.taxRate)}</td>
                <td className="px-4 py-2 text-right text-slate-600">{formatAmount(line.subtotal)} €</td>
                <td className="px-4 py-2 text-right text-slate-600">{formatAmount(line.taxAmount)} €</td>
                <td className="px-4 py-2 text-right font-medium text-slate-700">{formatAmount(line.total)} €</td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Totals */}
        <dl className="ml-auto w-full max-w-xs space-y-1 border-t border-slate-100 px-4 py-3 text-xs">
          <div className="flex justify-between">
            <dt className="text-slate-500">Base imponible</dt>
            <dd className="text-slate-700">{formatCurrency(invoice.subtotal)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">IVA</dt>
            <dd className="text-slate-700">{formatCurrency(invoice.taxAmount)}</dd>
          </div>
          {hasRetention && (
            <div className="flex justify-between">
              <dt className="text-slate-500">Retención IRPF ({formatRate(invoice.retentionRate)})</dt>
              <dd className="text-slate-700">−{formatCurrency(invoice.retentionAmount)}</dd>
            </div>
          )}
          <div className="flex justify-between border-t border-slate-100 pt-1.5 text-sm">
            <dt className="font-semibold text-slate-800">Total</dt>
            <dd className="font-semibold text-slate-800">{formatCurrency(invoice.total)}</dd>
          </div>
        </dl>
      </div>

      {/* Notes */}
      {invoice.notes && (
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
          <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Notas</p>
          <p className="mt-1 whitespace-pre-line text-xs leading-relaxed text-slate-600">{invoice.notes}</p>
        </div>
      )}
    </div>
  )
}
