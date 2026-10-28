import { formatAmount } from '@/lib/format'
import { lineAmounts } from '@/lib/money'
import { VAT_RATE_OPTIONS, type LineDraft } from './taxes'

interface ConceptsTableProps {
  lines: LineDraft[]
  onLineChange: <K extends keyof LineDraft>(id: number, field: K, value: LineDraft[K]) => void
  onAddLine: () => void
  onRemoveLine: (id: number) => void
}

export default function ConceptsTable({ lines, onLineChange, onAddLine, onRemoveLine }: ConceptsTableProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200">
      <div className="px-5 py-4 border-b border-slate-100">
        <h2 className="text-sm font-semibold text-slate-700">Conceptos</h2>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100">
              <th className="text-left px-5 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider w-auto">
                Descripción
              </th>
              <th className="text-right px-3 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider w-24">
                Cant.
              </th>
              <th className="text-right px-3 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider w-32">
                Precio U.
              </th>
              <th className="text-right px-3 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider w-36">
                Impuestos
              </th>
              <th className="text-right px-5 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider w-28">
                Importe
              </th>
              <th className="text-right px-5 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider w-28">
                Total
              </th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {lines.map((line) => {
              const amounts = lineAmounts(
                parseFloat(String(line.quantity)) || 0,
                parseFloat(String(line.unitPrice)) || 0,
                line.taxRate,
              )
              return (
                <tr key={line.id} className="group">
                  <td className="px-5 py-3">
                    <textarea
                      rows={1}
                      value={line.description}
                      onChange={(e) => onLineChange(line.id, 'description', e.target.value)}
                      placeholder="Descripción del servicio o producto..."
                      className="w-full resize-none text-sm text-slate-700 placeholder-slate-300 border-0 outline-none focus:ring-0 bg-transparent leading-5"
                    />
                  </td>
                  <td className="px-3 py-3">
                    <input
                      type="number"
                      min="0"
                      step="1"
                      value={line.quantity}
                      onChange={(e) => onLineChange(line.id, 'quantity', e.target.value)}
                      className="w-full text-right text-sm text-slate-700 border border-slate-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    />
                  </td>
                  <td className="px-3 py-3">
                    <div className="relative">
                      <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm">€</span>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={line.unitPrice}
                        onChange={(e) => onLineChange(line.id, 'unitPrice', e.target.value)}
                        className="w-full text-right text-sm text-slate-700 border border-slate-200 rounded-lg pl-6 pr-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                      />
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <select
                      value={line.taxRate}
                      onChange={(e) => onLineChange(line.id, 'taxRate', Number(e.target.value))}
                      className="w-full text-sm text-slate-700 border border-slate-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white"
                    >
                      {VAT_RATE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-5 py-3 text-right text-slate-600 whitespace-nowrap">
                    {formatAmount(amounts.subtotal)} €
                  </td>
                  {/* Line total: base + IVA */}
                  <td className="px-5 py-3 text-right font-medium text-slate-700 whitespace-nowrap">
                    {formatAmount(amounts.total)} €
                  </td>
                  <td className="pr-3 py-3">
                    <button
                      onClick={() => onRemoveLine(line.id)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 text-slate-300 hover:text-red-400 rounded"
                      aria-label="Eliminar concepto"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="px-5 py-3 border-t border-slate-100">
        <button
          onClick={onAddLine}
          className="flex items-center gap-2 text-sm text-indigo-600 hover:text-indigo-700 font-medium transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Añadir concepto
        </button>
      </div>
    </div>
  )
}
