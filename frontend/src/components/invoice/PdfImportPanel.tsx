import { useRef } from 'react'
import { formatCurrency } from '@/lib/format'

export interface PdfImportResult {
  fileName: string
  /** Whether the invoice is addressed to the account; `null` when it cannot be told. */
  addressedToAccount: boolean | null
  customerName: string | null
  /** The total printed on the invoice. */
  printedTotal: number | null
}

interface PdfImportPanelProps {
  /** The PDF is being read: the button shows a spinner and cannot be used. */
  importing: boolean
  disabled?: boolean
  onImport: (file: File) => void
  result: PdfImportResult | null
  error: string | null
  /** The total computed from the form's lines, checked against the printed one. */
  computedTotal: number
}

/** Reads a supplier's invoice from a PDF to fill in the received invoice form. */
export default function PdfImportPanel({
  importing,
  disabled,
  onImport,
  result,
  error,
  computedTotal,
}: PdfImportPanelProps) {
  const input = useRef<HTMLInputElement>(null)
  const totalMismatch =
    result?.printedTotal != null && Math.abs(result.printedTotal - computedTotal) >= 0.01

  return (
    <div className="bg-white rounded-xl border border-slate-200 px-5 py-4 space-y-3" aria-busy={importing}>
      <div>
        <h2 className="text-sm font-semibold text-slate-700">Importar desde PDF</h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Sube la factura del proveedor y rellenaremos el formulario con sus datos. Revísalos antes de guardar.
        </p>
      </div>

      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        aria-label="PDF de la factura"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = '' // choosing the same file again must trigger a new import
          if (file) onImport(file)
        }}
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={importing || disabled}
        className="w-full flex items-center justify-center gap-2 text-sm font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 px-4 py-2 rounded-lg transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {importing ? (
          <>
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" role="status" aria-label="Procesando">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            Leyendo PDF…
          </>
        ) : (
          <>
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            Importar desde PDF
          </>
        )}
      </button>

      {importing && <p className="text-xs text-slate-400">Puede tardar unos segundos…</p>}
      {error && (
        <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {error}
        </p>
      )}
      {result && !importing && (
        <div className="space-y-2 text-xs">
          <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-700">
            Datos importados de <strong className="break-all">{result.fileName}</strong>. Revísalos antes de guardar.
          </p>
          {result.addressedToAccount === false && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-700">
              La factura está a nombre de {result.customerName ? <strong>{result.customerName}</strong> : 'otra persona'}, no
              de tus datos fiscales: comprueba que es un gasto tuyo.
            </p>
          )}
          {totalMismatch && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-700">
              El total de la factura es {formatCurrency(result.printedTotal!)}, pero los conceptos suman{' '}
              {formatCurrency(computedTotal)}: revisa los conceptos, el IVA y la retención.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
