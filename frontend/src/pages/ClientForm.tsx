import { useEffect, useState } from 'react'
import { api, ApiError, type Client, type ClientInput, type DocumentType } from '@/api'
import { Field, INPUT_CLASS } from '@/components/form'
import { useApi } from '@/lib/useApi'

const DOCUMENT_TYPES: { value: DocumentType; label: string }[] = [
  { value: 'NIF', label: 'NIF' },
  { value: 'CIF', label: 'CIF' },
  { value: 'OTHER', label: 'Otro' },
]

interface FormState {
  fullName: string
  documentType: DocumentType
  documentNumber: string
  street: string
  zipCode: string
  city: string
  province: string
  countryIsoCode: string
}

const EMPTY: FormState = {
  fullName: '',
  documentType: 'NIF',
  documentNumber: '',
  street: '',
  zipCode: '',
  city: '',
  province: '',
  countryIsoCode: 'ES',
}

function fromClient(client: Client): FormState {
  return {
    fullName: client.fullName,
    documentType: client.document.type,
    documentNumber: client.document.number,
    ...client.address,
  }
}

function toInput(form: FormState): ClientInput {
  return {
    fullName: form.fullName.trim(),
    document: { type: form.documentType, number: form.documentNumber.trim().toUpperCase() },
    address: {
      street: form.street.trim(),
      zipCode: form.zipCode.trim(),
      city: form.city.trim(),
      province: form.province.trim(),
      countryIsoCode: form.countryIsoCode.trim().toUpperCase() || 'ES',
    },
  }
}

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
  const [form, setForm] = useState<FormState>(EMPTY)
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
    setForm(fromClient(client))
  }, [existing, loaded])

  function set<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [field]: value }))
    setError(null)
  }

  function validate(input: ClientInput): string | null {
    if (!input.fullName) return 'Indica el nombre o razón social del cliente.'
    if (!/^[A-Z]{2}$/.test(input.address.countryIsoCode)) return 'El país es un código de dos letras (ES, PT, FR…).'
    return null
  }

  async function save() {
    const input = toInput(form)
    const problem = validate(input)
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
              <Field
                id="client-name"
                label="Nombre o razón social"
                type="text"
                autoComplete="organization"
                autoFocus={!editing}
                maxLength={255}
                required
                value={form.fullName}
                onChange={(e) => set('fullName', e.target.value)}
                disabled={disabled}
              />
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label htmlFor="client-document-type" className="block text-xs font-medium text-slate-600 mb-1.5">
                    Tipo de identificación
                  </label>
                  <select
                    id="client-document-type"
                    value={form.documentType}
                    onChange={(e) => set('documentType', e.target.value as DocumentType)}
                    disabled={disabled}
                    className={`${INPUT_CLASS} bg-white`}
                  >
                    {DOCUMENT_TYPES.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="sm:col-span-2">
                  <Field
                    id="client-document-number"
                    label="NIF / CIF"
                    type="text"
                    autoComplete="off"
                    maxLength={100}
                    value={form.documentNumber}
                    onChange={(e) => set('documentNumber', e.target.value)}
                    disabled={disabled}
                    className="font-mono uppercase"
                    hint="Necesario para facturar a empresas y profesionales."
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Address */}
          <div className="col-span-12 lg:col-span-5">
            <div className="bg-white rounded-xl border border-slate-200 px-5 py-4 space-y-4">
              <h2 className="text-sm font-semibold text-slate-700">Dirección</h2>
              <Field
                id="client-street"
                label="Dirección"
                type="text"
                autoComplete="street-address"
                maxLength={255}
                value={form.street}
                onChange={(e) => set('street', e.target.value)}
                disabled={disabled}
              />
              <div className="grid grid-cols-3 gap-4">
                <Field
                  id="client-zip"
                  label="Código postal"
                  type="text"
                  autoComplete="postal-code"
                  maxLength={50}
                  value={form.zipCode}
                  onChange={(e) => set('zipCode', e.target.value)}
                  disabled={disabled}
                />
                <div className="col-span-2">
                  <Field
                    id="client-city"
                    label="Ciudad"
                    type="text"
                    autoComplete="address-level2"
                    maxLength={100}
                    value={form.city}
                    onChange={(e) => set('city', e.target.value)}
                    disabled={disabled}
                  />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div className="col-span-2">
                  <Field
                    id="client-province"
                    label="Provincia"
                    type="text"
                    autoComplete="address-level1"
                    maxLength={100}
                    value={form.province}
                    onChange={(e) => set('province', e.target.value)}
                    disabled={disabled}
                  />
                </div>
                <Field
                  id="client-country"
                  label="País"
                  type="text"
                  autoComplete="country"
                  maxLength={2}
                  value={form.countryIsoCode}
                  onChange={(e) => set('countryIsoCode', e.target.value)}
                  disabled={disabled}
                  className="uppercase"
                  hint="Código ISO (ES…)"
                />
              </div>
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
