import { useEffect, useState } from 'react'
import { api, type Client } from '@/api'
import ConfirmDialog from '@/components/ConfirmDialog'
import { FormMessage } from '@/components/form'
import { useApi } from '@/lib/useApi'

const PAGE_SIZE = 10
const DEBOUNCE_MS = 250
const HEADER_CELL = 'px-5 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide'
const COLUMNS = 5

interface ClientsProps {
  /** Opens the edit form of a client. */
  onEdit: (clientId: number) => void
}

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

/** Where a client is, on one line ("Calle Mayor 1 · 28001 Madrid"). */
function describeAddress(client: Client): string {
  const { street, zipCode, city } = client.address
  return [street, [zipCode, city].filter(Boolean).join(' ')].filter(Boolean).join(' · ')
}

/** The client directory: searchable, paginated list with edit / delete actions per row. */
export default function Clients({ onEdit }: ClientsProps) {
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const [deleting, setDeleting] = useState<Client | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)
  const q = useDebounced(query.trim(), DEBOUNCE_MS)

  useEffect(() => setPage(0), [q])

  const clients = useApi(
    (signal) => api.listClients({ q: q || undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE }, signal),
    [q, page],
  )

  const items = clients.data?.items ?? []
  const total = clients.data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const from = total === 0 ? 0 : page * PAGE_SIZE + 1
  const to = Math.min(total, (page + 1) * PAGE_SIZE)

  async function remove(client: Client) {
    setBusy(true)
    try {
      await api.deleteClient(client.id)
      setNotice({ tone: 'success', text: `Cliente ${client.fullName} eliminado. Sus facturas conservan sus datos.` })
      if (items.length === 1 && page > 0) setPage((p) => p - 1)
      else clients.reload()
    } catch (err) {
      setNotice({ tone: 'error', text: err instanceof Error ? err.message : String(err) })
    } finally {
      setBusy(false)
      setDeleting(null)
    }
  }

  return (
    <div className="space-y-4">
      {notice && <FormMessage tone={notice.tone}>{notice.text}</FormMessage>}

      <section className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden" aria-label="Clientes">
        <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">Clientes</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {clients.data ? `${total} ${total === 1 ? 'cliente' : 'clientes'}` : ' '}
            </p>
          </div>
          <div className="relative w-full sm:w-72">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11A6 6 0 105 11a6 6 0 0012 0z" />
            </svg>
            <input
              type="search"
              aria-label="Buscar cliente"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar por nombre o CIF / NIF…"
              className="w-full pl-9 pr-3 py-2 text-sm text-slate-700 border border-slate-200 rounded-lg placeholder-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className={`text-left ${HEADER_CELL}`}>Cliente</th>
                <th className={`text-left ${HEADER_CELL}`}>NIF / CIF</th>
                <th className={`text-left ${HEADER_CELL}`}>Dirección</th>
                <th className={`text-left ${HEADER_CELL}`}>Provincia</th>
                <th className={`text-right ${HEADER_CELL}`}>Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {clients.status === 'loading' && items.length === 0 && (
                <tr>
                  <td colSpan={COLUMNS} className="px-5 py-12 text-center text-slate-400">Cargando clientes…</td>
                </tr>
              )}
              {clients.status === 'error' && (
                <tr>
                  <td colSpan={COLUMNS} className="px-5 py-12 text-center">
                    <p className="text-rose-500 font-medium">No se pudieron cargar los clientes</p>
                    <p className="text-slate-400 text-xs mt-1">{clients.error.message}</p>
                    <button onClick={clients.reload} className="mt-3 text-xs text-indigo-600 hover:text-indigo-700 font-medium">
                      Reintentar
                    </button>
                  </td>
                </tr>
              )}
              {clients.status === 'success' && items.length === 0 && (
                <tr>
                  <td colSpan={COLUMNS} className="px-5 py-10 text-center text-slate-400">
                    {q ? 'Ningún cliente coincide con la búsqueda.' : 'Todavía no hay clientes. Crea el primero con «Nuevo Cliente».'}
                  </td>
                </tr>
              )}
              {items.map((client) => (
                <tr key={client.id} className="hover:bg-slate-50/50">
                  <td className="px-5 py-3.5 font-medium text-slate-700">{client.fullName}</td>
                  <td className="px-5 py-3.5 text-xs text-slate-500 whitespace-nowrap">
                    {client.document.number ? `${client.document.type} ${client.document.number}` : <span className="italic text-slate-300">—</span>}
                  </td>
                  <td className="px-5 py-3.5 text-xs text-slate-500">{describeAddress(client) || <span className="italic text-slate-300">—</span>}</td>
                  <td className="px-5 py-3.5 text-xs text-slate-500">{client.address.province || <span className="italic text-slate-300">—</span>}</td>
                  <td className="px-5 py-3.5">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => onEdit(client.id)}
                        title="Editar"
                        aria-label={`Editar ${client.fullName}`}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                            d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                        </svg>
                      </button>
                      <button
                        onClick={() => setDeleting(client)}
                        title="Eliminar"
                        aria-label={`Eliminar ${client.fullName}`}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 text-xs text-slate-500">
          <span>
            Mostrando {from}–{to} de {total}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Anterior
            </button>
            <span className="px-2">
              {page + 1} / {pageCount}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              disabled={page + 1 >= pageCount}
              className="px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Siguiente
            </button>
          </div>
        </div>
      </section>

      {deleting && (
        <ConfirmDialog
          title="Eliminar cliente"
          message={
            `Se eliminará ${deleting.fullName} del directorio de clientes. ` +
            'Las facturas ya creadas con este cliente conservan sus datos. Esta acción no se puede deshacer.'
          }
          confirmLabel="Eliminar cliente"
          busyLabel="Eliminando…"
          tone="danger"
          busy={busy}
          onConfirm={() => remove(deleting)}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  )
}
