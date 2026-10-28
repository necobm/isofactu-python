import type { PaymentMethod } from '@/api'
import { formatAmount } from '@/lib/format'
import { PAYMENT_METHOD_LABELS, PAYMENT_METHODS } from './paymentMethods'
import { RETENTION_OPTIONS } from './retention'

export interface TaxBreakdownEntry {
  rate: number
  base: number
  amount: number
}

interface TotalsPanelProps {
  subtotal: number
  /** One entry per distinct VAT rate used across the invoice lines. */
  taxBreakdown: TaxBreakdownEntry[]
  retentionRate: number | null
  retentionAmount: number
  total: number
  paymentMethod: PaymentMethod
  issueDate: string
  dueDate: string
  /** Today, as YYYY-MM-DD: invoices cannot be issued with a future date. */
  today: string
  onRetentionRateChange: (rate: number | null) => void
  onPaymentMethodChange: (method: PaymentMethod) => void
  onIssueDateChange: (date: string) => void
  onDueDateChange: (date: string) => void
}

const FIELD_CLASS =
  'w-full text-sm text-slate-700 border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white'

export default function TotalsPanel({
  subtotal,
  taxBreakdown,
  retentionRate,
  retentionAmount,
  total,
  paymentMethod,
  issueDate,
  dueDate,
  today,
  onRetentionRateChange,
  onPaymentMethodChange,
  onIssueDateChange,
  onDueDateChange,
}: TotalsPanelProps) {
  return (
    <div className="sticky top-24">
      {/* Totals — dark header */}
      <div className="rounded-xl overflow-hidden border border-slate-200">
        <div className="bg-slate-900 px-5 py-4 space-y-3">
          <div className="flex justify-between text-sm text-slate-300">
            <span>Subtotal</span>
            <span>{formatAmount(subtotal)} €</span>
          </div>
          {/* One row per tax type used in the lines */}
          {taxBreakdown.length === 0 && (
            <div className="flex justify-between text-sm text-slate-300">
              <span>Cuota IVA</span>
              <span>+{formatAmount(0)} €</span>
            </div>
          )}
          {taxBreakdown.map((tax) => (
            <div key={tax.rate} className="flex justify-between text-sm text-slate-300">
              <span>
                {tax.rate === 0 ? 'Exento' : `Cuota IVA (${tax.rate} %)`}
                <span className="text-slate-500"> · base {formatAmount(tax.base)} €</span>
              </span>
              <span>+{formatAmount(tax.amount)} €</span>
            </div>
          ))}
          {retentionRate !== null && (
            <div className="flex justify-between text-sm text-slate-300">
              <span>Retención IRPF ({retentionRate} %)</span>
              <span>−{formatAmount(retentionAmount)} €</span>
            </div>
          )}
          <div className="border-t border-slate-700 pt-3 flex justify-between items-baseline">
            <span className="text-white font-semibold text-sm">Total Final</span>
            <span className="text-white font-bold text-xl">{formatAmount(total)} €</span>
          </div>
        </div>

        {/* Payment details — light body */}
        <div className="bg-white px-5 py-4 space-y-4">
          <div>
            <label htmlFor="invoice-retention" className="block text-xs font-medium text-slate-500 mb-1.5">
              Retención IRPF
            </label>
            <select
              id="invoice-retention"
              value={retentionRate ?? ''}
              onChange={(e) => onRetentionRateChange(e.target.value === '' ? null : Number(e.target.value))}
              className={FIELD_CLASS}
            >
              {RETENTION_OPTIONS.map((option) => (
                <option key={option.label} value={option.value ?? ''}>{option.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="invoice-payment-method" className="block text-xs font-medium text-slate-500 mb-1.5">
              Método de Pago
            </label>
            <select
              id="invoice-payment-method"
              value={paymentMethod}
              onChange={(e) => onPaymentMethodChange(e.target.value as PaymentMethod)}
              className={FIELD_CLASS}
            >
              {PAYMENT_METHODS.map((method) => (
                <option key={method} value={method}>{PAYMENT_METHOD_LABELS[method]}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="invoice-issue-date" className="block text-xs font-medium text-slate-500 mb-1.5">
              Fecha de Emisión
            </label>
            <input
              id="invoice-issue-date"
              type="date"
              value={issueDate}
              max={today}
              onChange={(e) => onIssueDateChange(e.target.value)}
              className={FIELD_CLASS}
            />
          </div>

          <div>
            <label htmlFor="invoice-due-date" className="block text-xs font-medium text-slate-500 mb-1.5">
              Fecha de Vencimiento
            </label>
            <input
              id="invoice-due-date"
              type="date"
              value={dueDate}
              min={issueDate || undefined}
              onChange={(e) => onDueDateChange(e.target.value)}
              className={FIELD_CLASS}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
