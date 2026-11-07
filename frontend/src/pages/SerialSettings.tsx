import { useState } from 'react'
import { api, ApiError, type Serial, type SerialInput } from '@/api'
import ConfirmDialog from '@/components/ConfirmDialog'
import { FormMessage } from '@/components/form'
import SerialFormDialog from '@/components/settings/SerialFormDialog'
import { formatDate } from '@/lib/format'
import { isSerialAvailableOn } from '@/lib/serials'
import { useApi } from '@/lib/useApi'

const HEADER_CELL = 'px-5 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide'
const ACTION_BUTTON =
  'text-xs font-medium px-2.5 py-1.5 rounded-lg border border-transparent transition-colors disabled:opacity-40 disabled:cursor-not-allowed'

type Dialog = { kind: 'create' } | { kind: 'edit'; serial: Serial } | { kind: 'delete'; serial: Serial }

/** Local date as YYYY-MM-DD. */
function isoToday(): string {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}

/** Settings section: the numbering series invoices take their numbers from. */
export default function SerialSettings() {
  const serials = useApi((signal) => api.listSerials(signal), [])
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)
  const today = isoToday()
  const items = serials.data ?? []

  async function create(input: SerialInput) {
    const created = await api.createSerial(input)
    setDialog(null)
    setNotice({ tone: 'success', text: `Serie creada. La próxima factura será la ${created.nextNumberFormatted}.` })
    serials.reload()
  }

  async function update(serial: Serial, input: SerialInput) {
    await api.updateSerial(serial.id, input)
    setDialog(null)
    setNotice({ tone: 'success', text: 'Serie actualizada.' })
    serials.reload()
  }

  async function remove(serial: Serial) {
    setDeleting(true)
    try {
      await api.deleteSerial(serial.id)
      setNotice({ tone: 'success', text: 'Serie eliminada.' })
      serials.reload()
    } catch (err) {
      setNotice({
        tone: 'error',
        text:
          err instanceof ApiError && err.status === 409
            ? 'La serie tiene facturas emitidas y no puede eliminarse. Ponle una fecha de fin para dejar de usarla.'
            : err instanceof Error
              ? err.message
              : String(err),
      })
    } finally {
      setDeleting(false)
      setDialog(null)
    }
  }

  return (
    <section className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden max-w-3xl" aria-label="Series de facturación">
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">Series de facturación</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Cada factura emitida toma el siguiente número correlativo de la serie elegida.
          </p>
        </div>
        <button
          onClick={() => setDialog({ kind: 'create' })}
          className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium px-3 py-2 rounded-lg transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Nueva serie
        </button>
      </div>

      {notice && (
        <div className="px-5 pt-4">
          <FormMessage tone={notice.tone}>{notice.text}</FormMessage>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              <th className={`text-left ${HEADER_CELL}`}>Serie</th>
              <th className={`text-left ${HEADER_CELL}`}>Vigencia</th>
              <th className={`text-right ${HEADER_CELL}`}>Emitidas</th>
              <th className={`text-left ${HEADER_CELL}`}>Próximo número</th>
              <th className={`text-right ${HEADER_CELL}`}>Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {serials.status === 'loading' && items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-slate-400">Cargando series…</td>
              </tr>
            )}
            {serials.status === 'error' && (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-rose-500">
                  No se pudieron cargar las series: {serials.error.message}
                </td>
              </tr>
            )}
            {serials.status === 'success' && items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-slate-400">
                  Todavía no hay series. Crea una para poder emitir facturas.
                </td>
              </tr>
            )}
            {items.map((serial) => {
              const available = isSerialAvailableOn(serial, today)
              return (
                <tr key={serial.id} className="hover:bg-slate-50/50">
                  <td className="px-5 py-3.5">
                    <p className="font-mono text-slate-700">
                      {serial.prefix}
                      <span className="text-slate-300">‹nº›</span>
                      {serial.suffix}
                    </p>
                    {serial.locked && <p className="text-[11px] text-slate-400">En uso: prefijo, sufijo y número inicial bloqueados</p>}
                  </td>
                  <td className="px-5 py-3.5 text-xs whitespace-nowrap">
                    <Validity serial={serial} available={available} />
                  </td>
                  <td className="px-5 py-3.5 text-right text-slate-600">{serial.issuedCount}</td>
                  <td className="px-5 py-3.5 font-mono text-xs text-slate-600">{serial.nextNumberFormatted}</td>
                  <td className="px-5 py-3.5">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => setDialog({ kind: 'edit', serial })} className={`${ACTION_BUTTON} text-slate-600 hover:bg-slate-100`}>
                        Editar
                      </button>
                      <button
                        onClick={() => setDialog({ kind: 'delete', serial })}
                        disabled={serial.locked}
                        title={serial.locked ? 'Tiene facturas emitidas: ponle una fecha de fin en lugar de eliminarla' : undefined}
                        className={`${ACTION_BUTTON} text-rose-600 hover:bg-rose-50`}
                      >
                        Eliminar
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {dialog?.kind === 'create' && <SerialFormDialog onSubmit={create} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'edit' && (
        <SerialFormDialog serial={dialog.serial} onSubmit={(input) => update(dialog.serial, input)} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === 'delete' && (
        <ConfirmDialog
          title="Eliminar serie"
          message={`Se eliminará la serie ${dialog.serial.prefix}‹nº›${dialog.serial.suffix}. Los borradores que la tuvieran elegida quedarán sin serie.`}
          confirmLabel="Eliminar serie"
          busyLabel="Eliminando…"
          tone="danger"
          busy={deleting}
          onConfirm={() => remove(dialog.serial)}
          onCancel={() => setDialog(null)}
        />
      )}
    </section>
  )
}

function Validity({ serial, available }: { serial: Serial; available: boolean }) {
  const { startDate, endDate } = serial
  const range =
    !startDate && !endDate
      ? 'Sin límite'
      : [startDate ? `desde ${formatDate(startDate)}` : null, endDate ? `hasta ${formatDate(endDate)}` : null]
          .filter(Boolean)
          .join(' ')
  return (
    <>
      <span className={available ? 'text-slate-600' : 'text-slate-400'}>{range}</span>
      {!available && <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">No disponible hoy</span>}
    </>
  )
}
