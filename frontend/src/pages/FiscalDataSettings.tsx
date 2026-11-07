import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, type DocumentType, type FiscalData, type FiscalDataInput } from '@/api'
import { Field, FormMessage, INPUT_CLASS, PRIMARY_BUTTON_CLASS } from '@/components/form'
import { useApi } from '@/lib/useApi'

const DOCUMENT_TYPES: { value: DocumentType; label: string }[] = [
  { value: 'NIF', label: 'NIF' },
  { value: 'CIF', label: 'CIF' },
  { value: 'OTHER', label: 'Otro' },
]

interface FormState {
  companyName: string
  documentType: DocumentType
  documentNumber: string
  street: string
  zipCode: string
  city: string
  province: string
  countryIsoCode: string
}

const EMPTY: FormState = {
  companyName: '',
  documentType: 'NIF',
  documentNumber: '',
  street: '',
  zipCode: '',
  city: '',
  province: '',
  countryIsoCode: 'ES',
}

function fromFiscalData(data: FiscalData): FormState {
  return {
    companyName: data.companyName,
    documentType: data.document.type,
    documentNumber: data.document.number,
    ...data.address,
  }
}

function toInput(form: FormState): FiscalDataInput {
  return {
    companyName: form.companyName.trim(),
    document: { type: form.documentType, number: form.documentNumber.trim().toUpperCase() },
    address: {
      street: form.street.trim(),
      zipCode: form.zipCode.trim(),
      city: form.city.trim(),
      province: form.province.trim(),
      countryIsoCode: form.countryIsoCode.trim().toUpperCase(),
    },
  }
}

interface FiscalDataSettingsProps {
  /** Called after a successful save (e.g. to go back to the invoice being created). */
  onSaved?: (data: FiscalData) => void
}

/** Settings page: the tenant's fiscal data, used as issuer on every invoice it saves. */
export default function FiscalDataSettings({ onSaved }: FiscalDataSettingsProps) {
  const current = useApi((signal) => api.getFiscalData(signal), [])
  const [form, setForm] = useState<FormState>(EMPTY)
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    if (current.status === 'success' && !loaded) {
      setForm(current.data ? fromFiscalData(current.data) : EMPTY)
      setLoaded(true)
    }
  }, [current, loaded])

  function set<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [field]: value }))
    setMessage(null)
  }

  function validate(input: FiscalDataInput): string | null {
    if (!input.companyName) return 'Indica el nombre o razón social.'
    if (!input.document.number) return 'Indica el NIF / CIF.'
    if (!input.address.street) return 'Indica la dirección.'
    if (!input.address.zipCode) return 'Indica el código postal.'
    if (!input.address.city) return 'Indica la ciudad.'
    if (!/^[A-Z]{2}$/.test(input.address.countryIsoCode)) return 'El país es un código de dos letras (ES, PT, FR…).'
    return null
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const input = toInput(form)
    const problem = validate(input)
    if (problem) {
      setMessage({ tone: 'error', text: problem })
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      const saved = await api.saveFiscalData(input)
      setForm(fromFiscalData(saved))
      setMessage({ tone: 'success', text: 'Datos fiscales guardados. Se usarán como emisor en las facturas que guardes a partir de ahora.' })
      onSaved?.(saved)
    } catch (err) {
      setMessage({ tone: 'error', text: describe(err) })
    } finally {
      setBusy(false)
    }
  }

  const disabled = busy || !loaded

  return (
    <section className="bg-white rounded-xl border border-slate-100 shadow-sm" aria-label="Datos fiscales">
      <div className="px-5 py-4 border-b border-slate-100">
        <h2 className="text-sm font-semibold text-slate-800">Datos fiscales</h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Aparecen como emisor en tus facturas. Las facturas ya emitidas conservan los datos con los que se emitieron.
        </p>
      </div>
      <form onSubmit={handleSubmit} className="px-5 py-5 space-y-5" noValidate>
        {current.status === 'error' && (
          <FormMessage tone="error">No se pudieron cargar los datos fiscales: {current.error.message}</FormMessage>
        )}
        {current.status === 'success' && current.data === null && !message && (
          <FormMessage tone="info">
            Todavía no has configurado tus datos fiscales. Son necesarios para crear facturas.
          </FormMessage>
        )}
        {message && <FormMessage tone={message.tone}>{message.text}</FormMessage>}

        <Field
          id="fiscal-company"
          label="Nombre o razón social"
          type="text"
          autoComplete="organization"
          maxLength={255}
          required
          value={form.companyName}
          onChange={(e) => set('companyName', e.target.value)}
          disabled={disabled}
        />

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label htmlFor="fiscal-document-type" className="block text-xs font-medium text-slate-600 mb-1.5">
              Tipo de identificación
            </label>
            <select
              id="fiscal-document-type"
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
              id="fiscal-document-number"
              label="NIF / CIF"
              type="text"
              autoComplete="off"
              maxLength={100}
              required
              value={form.documentNumber}
              onChange={(e) => set('documentNumber', e.target.value)}
              disabled={disabled}
              className="font-mono uppercase"
            />
          </div>
        </div>

        <Field
          id="fiscal-street"
          label="Dirección"
          type="text"
          autoComplete="street-address"
          maxLength={255}
          required
          value={form.street}
          onChange={(e) => set('street', e.target.value)}
          disabled={disabled}
        />

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Field
            id="fiscal-zip"
            label="Código postal"
            type="text"
            autoComplete="postal-code"
            maxLength={50}
            required
            value={form.zipCode}
            onChange={(e) => set('zipCode', e.target.value)}
            disabled={disabled}
          />
          <div className="sm:col-span-2">
            <Field
              id="fiscal-city"
              label="Ciudad"
              type="text"
              autoComplete="address-level2"
              maxLength={100}
              required
              value={form.city}
              onChange={(e) => set('city', e.target.value)}
              disabled={disabled}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="sm:col-span-2">
            <Field
              id="fiscal-province"
              label="Provincia"
              type="text"
              autoComplete="address-level1"
              maxLength={100}
              value={form.province}
              onChange={(e) => set('province', e.target.value)}
              disabled={disabled}
              hint="Opcional."
            />
          </div>
          <Field
            id="fiscal-country"
            label="País"
            type="text"
            autoComplete="country"
            maxLength={2}
            required
            value={form.countryIsoCode}
            onChange={(e) => set('countryIsoCode', e.target.value)}
            disabled={disabled}
            className="uppercase"
            hint="Código de dos letras (ES, PT, FR…)."
          />
        </div>

        <div className="pt-1">
          <button type="submit" disabled={disabled} className={PRIMARY_BUTTON_CLASS}>
            {busy ? 'Guardando…' : 'Guardar datos fiscales'}
          </button>
        </div>
      </form>
    </section>
  )
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422) return `Revisa los datos: ${error.message}`
    return error.message
  }
  return 'No se pudieron guardar los datos fiscales. Inténtalo de nuevo.'
}
