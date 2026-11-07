import { useEffect, useMemo, useState } from 'react'
import { api, ApiError, geo, type Client, type ClientInput, type DocumentType } from '@/api'
import { Field, INPUT_CLASS } from '@/components/form'
import SearchSelect from '@/components/SearchSelect'
import { isValidCif, isValidNif, normaliseId } from '@/lib/spanishIds'
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
    document: {
      type: form.documentType,
      number: form.documentType === 'OTHER' ? form.documentNumber.trim() : normaliseId(form.documentNumber),
    },
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

  // -- reference data: provinces depend on the country, cities on the province -------------
  const countries = useApi((signal) => geo.countries(signal), [])
  const country = useMemo(
    () => countries.data?.find((c) => c.code === form.countryIsoCode) ?? null,
    [countries.data, form.countryIsoCode],
  )
  const provinces = useApi(
    (signal) => (form.countryIsoCode ? geo.provinces(form.countryIsoCode, signal) : Promise.resolve([])),
    [form.countryIsoCode],
  )
  const provinceOptions = useMemo(
    () => (provinces.data ?? []).map((p) => ({ value: p.name, label: p.name })),
    [provinces.data],
  )
  /** Countries without ISO provinces take a free-text province. */
  const freeTextProvince =
    form.countryIsoCode !== '' && provinces.status === 'success' && provinces.data.length === 0
  const province = provinces.data?.find((p) => p.name === form.province) ?? null
  const provinceCode = province?.code ?? null
  const cities = useApi(
    (signal) =>
      provinceCode ? geo.cities(form.countryIsoCode, provinceCode, signal) : Promise.resolve([] as string[]),
    [form.countryIsoCode, provinceCode],
  )
  const cityOptions = useMemo(() => (cities.data ?? []).map((c) => ({ value: c, label: c })), [cities.data])

  function changeCountry(code: string | null) {
    // A new country means a new set of provinces and cities
    setForm((prev) => ({ ...prev, countryIsoCode: code ?? '', province: '', city: '' }))
    setError(null)
  }

  function changeProvince(name: string | null) {
    setForm((prev) => ({ ...prev, province: name ?? '', city: '' }))
    setError(null)
  }

  function validate(input: ClientInput): string | null {
    if (input.fullName.length < 2) return 'Indica el nombre o razón social del cliente.'
    if (!input.document.number) return 'Indica el NIF / CIF del cliente.'
    if (input.document.type === 'NIF' && !isValidNif(input.document.number)) {
      return 'El NIF no es válido: comprueba los dígitos y la letra (DNI: 8 dígitos y letra; NIE: X/Y/Z, 7 dígitos y letra).'
    }
    if (input.document.type === 'CIF' && !isValidCif(input.document.number)) {
      return 'El CIF no es válido: comprueba la letra, los 7 dígitos y el carácter de control.'
    }
    if (input.address.street.length < 3) return 'Indica la dirección del cliente.'
    if (!input.address.zipCode) return 'Indica el código postal.'
    if (!input.address.countryIsoCode) return 'Selecciona el país.'
    if (country?.postalCodePattern && !new RegExp(country.postalCodePattern).test(input.address.zipCode)) {
      return `El código postal no tiene el formato de ${country.name}.`
    }
    if (!input.address.province) return freeTextProvince ? 'Indica la provincia.' : 'Selecciona la provincia.'
    if (!freeTextProvince && !province) return 'Selecciona una provincia de la lista.'
    if (!input.address.city) return cityOptions.length ? 'Selecciona o escribe la ciudad.' : 'Indica la ciudad.'
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
                    hint={
                      form.documentType === 'NIF'
                        ? 'DNI (8 dígitos y letra) o NIE (X/Y/Z, 7 dígitos y letra).'
                        : form.documentType === 'CIF'
                          ? 'Letra, 7 dígitos y carácter de control (p. ej. B12345674).'
                          : 'Identificador fiscal extranjero u otro documento.'
                    }
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Address: street, postal code, country, province (by country), city (by province) */}
          <div className="col-span-12 lg:col-span-5">
            <div className="bg-white rounded-xl border border-slate-200 px-5 py-4 space-y-4">
              <h2 className="text-sm font-semibold text-slate-700">Dirección</h2>
              <Field
                id="client-street"
                label="Dirección"
                type="text"
                autoComplete="street-address"
                maxLength={255}
                required
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
                  required
                  value={form.zipCode}
                  onChange={(e) => set('zipCode', e.target.value)}
                  disabled={disabled}
                />
                <div className="col-span-2">
                  <SearchSelect
                    id="client-country"
                    label="País"
                    options={(countries.data ?? []).map((c) => ({ value: c.code, label: c.name }))}
                    value={form.countryIsoCode || null}
                    onChange={changeCountry}
                    placeholder="Buscar país…"
                    loading={countries.status === 'loading'}
                    disabled={disabled}
                    required
                    noOptionsMessage="Ningún país coincide"
                  />
                </div>
              </div>
              {freeTextProvince ? (
                <Field
                  id="client-province"
                  label="Provincia"
                  type="text"
                  autoComplete="address-level1"
                  maxLength={100}
                  required
                  value={form.province}
                  onChange={(e) => set('province', e.target.value)}
                  disabled={disabled}
                  hint="Este país no tiene provincias definidas: escríbela."
                />
              ) : (
                <SearchSelect
                  id="client-province"
                  label="Provincia"
                  options={provinceOptions}
                  value={form.province || null}
                  onChange={changeProvince}
                  placeholder={form.countryIsoCode ? 'Buscar provincia…' : 'Selecciona primero el país'}
                  loading={provinces.status === 'loading'}
                  disabled={disabled || !form.countryIsoCode}
                  required
                  noOptionsMessage="Ninguna provincia coincide"
                />
              )}
              {freeTextProvince || cityOptions.length === 0 ? (
                <Field
                  id="client-city"
                  label="Ciudad"
                  type="text"
                  autoComplete="address-level2"
                  maxLength={100}
                  required
                  value={form.city}
                  onChange={(e) => set('city', e.target.value)}
                  disabled={disabled || !form.province}
                  hint={
                    !form.province
                      ? 'Selecciona primero la provincia.'
                      : cities.status === 'loading'
                        ? 'Cargando ciudades…'
                        : 'No hay lista de ciudades para esta provincia: escríbela.'
                  }
                />
              ) : (
                <SearchSelect
                  id="client-city"
                  label="Ciudad"
                  options={cityOptions}
                  value={form.city || null}
                  onChange={(city) => set('city', city ?? '')}
                  placeholder="Buscar ciudad…"
                  loading={cities.status === 'loading'}
                  disabled={disabled}
                  required
                  creatable
                  noOptionsMessage="Ninguna ciudad coincide: escríbela para usarla"
                  hint="Si no aparece en la lista, escríbela y pulsa Intro."
                />
              )}
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
