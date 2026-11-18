import { useState } from 'react'
import { api, type Invoice } from '@/api'
import { saveFile } from '@/lib/download'

/** Downloads an issued invoice as PDF (`Factura-<number>.pdf`). */
export default function PdfDownloadButton({ invoice }: { invoice: Invoice }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function downloadPdf() {
    setBusy(true)
    setError(null)
    try {
      const { blob, filename } = await api.downloadInvoicePdf(invoice.id)
      saveFile(blob, filename ?? `Factura-${invoice.invoiceNumber?.formatted ?? invoice.id}.pdf`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={downloadPdf}
        disabled={busy}
        className="flex items-center gap-1.5 text-xs font-medium text-indigo-600 border border-indigo-200 bg-white hover:bg-indigo-50 px-3 py-1.5 rounded-lg disabled:opacity-50 transition-colors"
      >
        <svg className={`w-3.5 h-3.5 ${busy ? 'animate-pulse' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 10v6m0 0l-3-3m3 3l3-3M6 20h12a2 2 0 002-2V8.414a1 1 0 00-.293-.707l-4.414-4.414A1 1 0 0014.586 3H6a2 2 0 00-2 2v13a2 2 0 002 2z" />
        </svg>
        {busy ? 'Generando PDF…' : 'Descargar PDF'}
      </button>
      {error && (
        <p role="alert" className="text-xs text-rose-600">
          No se pudo descargar el PDF: {error}
        </p>
      )}
    </div>
  )
}
