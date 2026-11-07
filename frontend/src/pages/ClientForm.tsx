import { useEffect, useState } from 'react'
import { api, ApiError, type Client } from '@/api'
import { PartyAddressFields, PartyIdentityFields } from '@/components/party/PartyFields'
import {
  EMPTY_PARTY,
  partyFormFrom,
  toPartyInput,
  usePartyGeo,
  validateParty,
  type PartyFormState,
} from '@/lib/party'
import { useApi } from '@/lib/useApi'

interface ClientFormProps {
  /** When given, the form edits that client instead of creating a new one. */
  clientId?: number
  /** Leave without saving. */
  onBack: () => void
  /** The client was stored. */
  onSaved: (client: Client) => void
}

/** Full-page form to create or edit a client, laid out like the invoice form. */
export default function ClientForm({ clientId, onBack, onSaved }: ClientFormProps) {
  const editing = clientId !== undefined
  const [form, setForm] = useState<PartyFormState>(EMPTY_PARTY)
  const [loaded, setLoaded] = useState<Client | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // -- editing: load the client and pre-fill the form ------------------------------------
  const existing = useApi(
    (signal) => (clientId === undefined ? Promise.resolve(null) : api.getClient(clientId, signal)),
    [clientId],
  )
  useEffect(() => {
    const client = existing.status === 'success' ? existing.data : null
    if (!client || loaded?.id === client.id) return
    setLoaded(client)
    setForm(partyFormFrom(client))
  }, [existing, loaded])

  function update(patch: Partial<PartyFormState>) {
    setForm((prev) => ({ ...prev, ...patch }))
    setError(null)
  }

  // -- reference data: provinces depend on the country, cities on the province -------------
  const partyGeo = usePartyGeo(form)

  async function save() {
    const input = toPartyInput(form)
    const problem = validateParty(input, partyGeo, 'del cliente')
    if (problem) {
      setError(problem)
      return
    }
    setError(null)
    setSaving(true)
    try {
      const client = clientId === undefined ? await api.createClient(input) : await api.updateClient(clientId, input)
      onSaved(client)
    } catch (err) {
      setError(err instanceof ApiError && err.status === 422 ? `Revisa los datos: ${err.message}` : err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  const title = editing ? 'Editar Cliente' : 'Nuevo Cliente'
  const disabled = saving || (editing && !loaded)

  if (editing && existing.status === 'loading' && !loaded) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-sm text-slate-400">
        Cargando cliente…
      </div>
    )
  }
  if (editing && existing.status === 'error') {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center gap-3">
        <p className="text-sm text-rose-600">No se pudo cargar el cliente: {existing.error.message}</p>
        <button onClick={onBack} className="text-sm font-medium text-indigo-600 hover:text-indigo-700">
          Volver a los clientes
        </button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Page header */}
      <div className="bg-white border-b border-slate-200 flex-shrink-0">
        <div className="max-w-screen-xl mx-auto px-6 h-14 flex items-center gap-4">
          <button
            onClick={onBack}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
            aria-label="Volver"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <h1 className="text-base font-bold text-slate-800 flex-1">{title}</h1>
        </div>
      </div>

      {/* Main content */}
      <main className="flex-1 max-w-screen-xl mx-auto w-full px-6 py-6 pb-24">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            save()
          }}
          noValidate
          className="grid grid-cols-12 gap-6"
        >
          {/* Identity */}
          <div className="col-span-12 lg:col-span-7 space-y-5">
            <div className="bg-white rounded-xl border border-slate-200 px-5 py-4 space-y-4">
              <h2 className="text-sm font-semibold text-slate-700">Datos del cliente</h2>
              <PartyIdentityFields
                idPrefix="client"
                form={form}
                onChange={update}
                disabled={disabled}
                autoFocus={!editing}
              />
            </div>
          </div>

          {/* Address: street, postal code, country, province (by country), city (by province) */}
          <div className="col-span-12 lg:col-span-5">
            <div className="bg-white rounded-xl border border-slate-200 px-5 py-4 space-y-4">
              <h2 className="text-sm font-semibold text-slate-700">Dirección</h2>
              <PartyAddressFields idPrefix="client" form={form} onChange={update} disabled={disabled} geo={partyGeo} />
            </div>
          </div>
        </form>
      </main>

      {/* Sticky footer */}
      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-slate-200 z-10">
        <div className="max-w-screen-xl mx-auto px-6 h-16 flex items-center justify-between gap-6">
          <p role={error ? 'alert' : undefined} className={`text-xs truncate ${error ? 'text-rose-600 font-medium' : 'text-slate-400'}`}>
            {error ??
              (editing
                ? 'Los cambios no afectan a las facturas ya creadas con este cliente.'
                : 'El cliente quedará disponible al crear facturas.')}
          </p>
          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={onBack}
              disabled={saving}
              className="text-sm font-medium text-slate-500 hover:text-slate-700 px-4 py-2 rounded-lg hover:bg-slate-100 transition-colors disabled:opacity-50"
            >
              Cancelar
            </button>
            <button
              onClick={save}
              disabled={disabled}
              className="text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 px-4 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? 'Guardando…' : editing ? 'Guardar Cambios' : 'Guardar Cliente'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
