import type { ReactNode } from 'react'
import { api } from '@/api'
import { formatCurrency, formatDate, formatRate } from '@/lib/format'
import { useApi } from '@/lib/useApi'

const QUARTER_NAMES = ['Primer', 'Segundo', 'Tercer', 'Cuarto']

/** "1 factura emitida", "3 facturas emitidas" */
function count(n: number, singular: string, plural: string): string {
  return `${n} ${n === 1 ? singular : plural}`
}

interface TaxLineProps {
  label: string
  hint?: ReactNode
  /** `null` while loading. */
  amount: number | null
  /** Shown as a deduction (−). */
  deducted?: boolean
}

function TaxLine({ label, hint, amount, deducted = false }: TaxLineProps) {
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <div className="min-w-0">
        <dt className="text-sm text-slate-600">{label}</dt>
        {hint && <p className="text-xs text-slate-400 mt-0.5">{hint}</p>}
      </div>
      <dd className="text-sm font-medium text-slate-700 whitespace-nowrap tabular-nums">
        {amount === null ? (
          <span className="inline-block h-4 w-20 rounded bg-slate-100 animate-pulse align-middle" />
        ) : (
          <>
            {deducted && amount !== 0 && '− '}
            {formatCurrency(amount)}
          </>
        )}
      </dd>
    </div>
  )
}

interface TaxCardProps {
  /** The tax name. */
  name: string
  /** The form it is filed with. */
  form: string
  children: ReactNode
  estimateLabel: string
  /** `null` while loading. */
  estimate: number | null
  /** What a negative estimate means. */
  negativeHint: string
}

function TaxCard({ name, form, children, estimateLabel, estimate, negativeHint }: TaxCardProps) {
  return (
    <section className="bg-white rounded-xl border border-slate-100 shadow-sm flex flex-col" aria-label={name}>
      <div className="flex items-baseline justify-between gap-3 px-5 py-4 border-b border-slate-100">
        <h2 className="text-base font-semibold text-slate-800">{name}</h2>
        <span className="text-xs text-slate-400">{form}</span>
      </div>
      <dl className="px-5 divide-y divide-slate-50 flex-1">{children}</dl>
      <div className="flex items-start justify-between gap-4 px-5 py-4 border-t border-slate-100 bg-slate-50/60 rounded-b-xl">
        <div>
          <p className="text-sm font-semibold text-slate-800">{estimateLabel}</p>
          {estimate !== null && estimate < 0 && <p className="text-xs text-slate-500 mt-0.5">{negativeHint}</p>}
        </div>
        {estimate === null ? (
          <span className="inline-block h-7 w-28 rounded bg-slate-100 animate-pulse" />
        ) : (
          <p
            className={`text-2xl font-bold tracking-tight tabular-nums ${estimate < 0 ? 'text-emerald-600' : 'text-slate-800'}`}
            data-testid={`${name.toLowerCase()}-estimate`}
          >
            {formatCurrency(estimate)}
          </p>
        )}
      </div>
    </section>
  )
}

/** Taxes: IVA and IRPF estimated from the invoices of the current quarter. */
export default function Taxes() {
  const taxes = useApi((signal) => api.getTaxes({}, signal), [])
  const data = taxes.data ?? null
  const vat = data?.vat
  const irpf = data?.irpf

  return (
    <div className="space-y-6 max-w-screen-xl mx-auto">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <p className="text-sm text-slate-500">
          {data ? (
            <>
              <strong className="font-semibold text-slate-700">
                {QUARTER_NAMES[data.quarter - 1]} trimestre de {data.year}
              </strong>{' '}
              · del {formatDate(data.periodStart)} al {formatDate(data.periodEnd)}
            </>
          ) : (
            ' '
          )}
        </p>
        <button
          onClick={taxes.reload}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-indigo-600 font-medium transition-colors"
        >
          <svg className={`w-3.5 h-3.5 ${taxes.status === 'loading' ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Actualizar
        </button>
      </div>

      {taxes.status === 'error' && (
        <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          No se pudieron calcular los impuestos: {taxes.error.message}{' '}
          <button onClick={taxes.reload} className="font-medium underline">
            Reintentar
          </button>
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TaxCard
          name="IVA"
          form="Modelo 303"
          estimateLabel="IVA estimado"
          estimate={vat?.estimated ?? null}
          negativeHint="Has pagado más IVA del que has cobrado: la diferencia se compensa en próximos trimestres."
        >
          <TaxLine
            label="IVA cobrado"
            hint={vat ? `Repercutido en ${count(vat.issuedCount, 'factura emitida', 'facturas emitidas')}` : undefined}
            amount={vat?.collected ?? null}
          />
          <TaxLine
            label="IVA pagado"
            hint={vat ? `Soportado en ${count(vat.receivedCount, 'factura recibida', 'facturas recibidas')}` : undefined}
            amount={vat?.paid ?? null}
            deducted
          />
        </TaxCard>

        <TaxCard
          name="IRPF"
          form="Modelo 130"
          estimateLabel="IRPF estimado"
          estimate={irpf?.estimated ?? null}
          negativeHint="Tus clientes ya han retenido más de lo estimado: no hay nada que pagar."
        >
          <TaxLine
            label="IRPF sobre ingresos"
            hint={
              irpf
                ? irpf.foreignInvoiceCount === 0
                  ? 'Ninguna factura a clientes fuera de España'
                  : `${formatRate(irpf.rate)} de ${formatCurrency(irpf.foreignIncome)} facturados a clientes fuera de España (${count(irpf.foreignInvoiceCount, 'factura', 'facturas')})`
                : undefined
            }
            amount={irpf?.fromIncome ?? null}
          />
          <TaxLine
            label="IRPF retenido por tus clientes"
            hint="Ya ingresado en tu nombre: se descuenta"
            amount={irpf?.withheld ?? null}
            deducted
          />
        </TaxCard>
      </div>

      <p className="text-xs text-slate-400">
        Estimaciones a partir de las facturas del trimestre (los borradores no cuentan). Te ayudan a prever lo que vas a
        pagar, pero no sustituyen a la declaración: no tienen en cuenta trimestres anteriores, gastos no deducibles ni otras
        situaciones particulares.
      </p>
    </div>
  )
}
