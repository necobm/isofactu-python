import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { api, ApiError, type AiProviderId, type AiSettings, type AiSettingsInput } from '@/api'
import ConfirmDialog from '@/components/ConfirmDialog'
import { Field, FormMessage, INPUT_CLASS, PRIMARY_BUTTON_CLASS } from '@/components/form'
import SearchSelect, { type SelectOption } from '@/components/SearchSelect'
import { useApi } from '@/lib/useApi'

/** Where each vendor hands out the key, shown under the field. */
const API_KEY_HINTS: Record<AiProviderId, string> = {
  gemini: 'Créala en Google AI Studio (aistudio.google.com).',
  anthropic: 'Créala en la consola de Anthropic (console.anthropic.com).',
  openai: 'Créala en la plataforma de OpenAI (platform.openai.com).',
  azure: 'Una de las claves del recurso de Azure OpenAI (Claves y punto de conexión).',
  bedrock: 'Una API key de Amazon Bedrock (consola de Bedrock › API keys).',
}

/** Suggestions for Bedrock (any other region can be typed in). */
const AWS_REGIONS = ['eu-south-2', 'eu-west-1', 'eu-west-3', 'eu-central-1', 'eu-north-1', 'us-east-1', 'us-west-2']

interface FormState {
  provider: AiProviderId | ''
  model: string
  apiKey: string
  endpoint: string
  apiVersion: string
  deployment: string
  region: string
}

const EMPTY: FormState = {
  provider: '',
  model: '',
  apiKey: '',
  endpoint: '',
  apiVersion: '',
  deployment: '',
  region: '',
}

function fromSettings(settings: AiSettings): FormState {
  const { provider, model, endpoint, apiVersion, deployment, region } = settings
  return { provider, model, apiKey: '', endpoint, apiVersion, deployment, region }
}

/** Hosts of Azure OpenAI / AI Foundry resources (the server refuses any other endpoint). */
const AZURE_HOST = /^https:\/\/[a-z0-9-]+(\.[a-z0-9-]+)*\.(openai\.azure\.com|cognitiveservices\.azure\.com|services\.ai\.azure\.com)\/?$/i

/** `https://ACME.openai.azure.com/` and `https://acme.openai.azure.com` are the same resource. */
function sameEndpoint(a: string, b: string): boolean {
  const normalise = (url: string) => url.trim().toLowerCase().replace(/\/+$/, '')
  return normalise(a) === normalise(b)
}

interface AiVendorSettingsProps {
  /** Called after a successful save (e.g. to go back to the invoice being recorded). */
  onSaved?: () => void
}

/**
 * Settings: the AI vendor, model and API key the account reads received invoices with. The
 * key is write-only: the server stores it encrypted and only tells its last characters.
 */
export default function AiVendorSettings({ onSaved }: AiVendorSettingsProps) {
  const current = useApi((signal) => api.getAiSettings(signal), [])
  const providers = useApi((signal) => api.listAiProviders(signal), [])
  const [saved, setSaved] = useState<AiSettings | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY)
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    if (current.status === 'success' && !loaded) {
      setSaved(current.data)
      setForm(current.data ? fromSettings(current.data) : EMPTY)
      setLoaded(true)
    }
  }, [current, loaded])

  const provider = providers.data?.find((p) => p.id === form.provider) ?? null
  // The model list follows the chosen provider: reloaded whenever it changes
  const models = useApi(
    (signal) => (form.provider ? api.listAiModels(form.provider, signal) : Promise.resolve([])),
    [form.provider],
  )
  const modelOptions = useMemo<SelectOption[]>(() => {
    const options = (models.data ?? []).map((m) => ({
      value: m.id,
      label: m.readsPdf ? m.id : `${m.id} · solo PDF con texto`,
    }))
    // A stored model the installed catalogue no longer lists stays visible
    if (saved && saved.provider === form.provider && !options.some((o) => o.value === saved.model)) {
      options.unshift({ value: saved.model, label: `${saved.model} (ya no aparece en el catálogo)` })
    }
    return options
  }, [models.data, saved, form.provider])
  const chosenModel = models.data?.find((m) => m.id === form.model) ?? null

  // The stored key applies to the same provider (and, on Azure, the same resource) only
  const keyRequired =
    !saved ||
    !saved.apiKeyReadable ||
    saved.provider !== form.provider ||
    (provider?.needsEndpoint === true && !sameEndpoint(saved.endpoint, form.endpoint))

  function set<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [field]: value }))
    setMessage(null)
  }

  function chooseProvider(id: AiProviderId | '') {
    setMessage(null)
    setForm((prev) => {
      if (saved && id === saved.provider) return { ...fromSettings(saved), apiKey: prev.apiKey }
      return { ...EMPTY, provider: id, apiKey: prev.apiKey }
    })
  }

  function validate(): string | null {
    if (!form.provider || !provider) return 'Elige un proveedor.'
    if (!form.model) return 'Elige un modelo.'
    if (keyRequired && !form.apiKey.trim()) return 'Introduce la API key del proveedor.'
    if (/\s/.test(form.apiKey.trim())) return 'La API key no puede contener espacios.'
    if (provider.needsEndpoint && !AZURE_HOST.test(form.endpoint.trim()))
      return 'Indica el punto de conexión del recurso de Azure, p. ej. https://mi-recurso.openai.azure.com.'
    if (provider.needsRegion && !form.region.trim()) return 'Indica la región de AWS.'
    return null
  }

  function toInput(): AiSettingsInput {
    const input: AiSettingsInput = { provider: form.provider as AiProviderId, model: form.model }
    if (form.apiKey.trim()) input.apiKey = form.apiKey.trim()
    if (provider?.needsEndpoint) {
      input.endpoint = form.endpoint.trim()
      input.apiVersion = form.apiVersion.trim()
      input.deployment = form.deployment.trim()
    }
    if (provider?.needsRegion) input.region = form.region.trim()
    return input
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const problem = validate()
    if (problem) {
      setMessage({ tone: 'error', text: problem })
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      const result = await api.saveAiSettings(toInput())
      setSaved(result)
      setForm(fromSettings(result))
      setMessage({ tone: 'success', text: 'Configuración de IA guardada. Ya puedes importar facturas recibidas desde PDF.' })
      onSaved?.()
    } catch (err) {
      setMessage({ tone: 'error', text: describe(err) })
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    try {
      await api.deleteAiSettings()
      setSaved(null)
      setForm(EMPTY)
      setMessage({ tone: 'success', text: 'Configuración de IA eliminada. La importación desde PDF queda desactivada.' })
    } catch (err) {
      setMessage({ tone: 'error', text: describe(err) })
    } finally {
      setBusy(false)
      setConfirmingDelete(false)
    }
  }

  const disabled = busy || !loaded || providers.status !== 'success'

  return (
    <section className="bg-white rounded-xl border border-slate-100 shadow-sm" aria-label="Inteligencia artificial">
      <div className="px-5 py-4 border-b border-slate-100">
        <h2 className="text-sm font-semibold text-slate-800">Inteligencia artificial</h2>
        <p className="text-xs text-slate-400 mt-0.5">
          El proveedor y el modelo con los que se leen las facturas recibidas que importas desde PDF. Los PDF se envían a
          este proveedor con tu API key, que se guarda cifrada y nunca se vuelve a mostrar.
        </p>
      </div>
      <form onSubmit={handleSubmit} className="px-5 py-5 space-y-5" noValidate>
        {(current.status === 'error' || providers.status === 'error') && (
          <FormMessage tone="error">
            No se pudo cargar la configuración de IA:{' '}
            {current.status === 'error' ? current.error.message : providers.status === 'error' ? providers.error.message : ''}
          </FormMessage>
        )}
        {loaded && !saved && !message && (
          <FormMessage tone="info">
            Todavía no has configurado un proveedor de IA: la importación de facturas desde PDF no está disponible.
          </FormMessage>
        )}
        {saved && !saved.apiKeyReadable && !message && (
          <FormMessage tone="error">
            La API key guardada ya no se puede descifrar (han cambiado las claves de cifrado del servidor). Vuelve a
            introducirla.
          </FormMessage>
        )}
        {message && <FormMessage tone={message.tone}>{message.text}</FormMessage>}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label htmlFor="ai-provider" className="block text-xs font-medium text-slate-600 mb-1.5">
              Proveedor
            </label>
            <select
              id="ai-provider"
              value={form.provider}
              onChange={(e) => chooseProvider(e.target.value as AiProviderId | '')}
              disabled={disabled}
              className={`${INPUT_CLASS} bg-white`}
            >
              <option value="">Elige un proveedor…</option>
              {(providers.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          <div className="sm:col-span-2">
            <SearchSelect
              // A fresh select per provider: its options are a different list
              key={form.provider || 'none'}
              id="ai-model"
              label="Modelo"
              options={modelOptions}
              value={form.model || null}
              onChange={(value) => set('model', value ?? '')}
              placeholder={form.provider ? 'Busca un modelo…' : 'Elige antes un proveedor'}
              disabled={disabled || !form.provider}
              loading={models.status === 'loading' && !!form.provider}
              required
              noOptionsMessage="Ningún modelo coincide"
              hint={
                models.status === 'error'
                  ? `No se pudieron cargar los modelos: ${models.error.message}`
                  : chosenModel
                    ? chosenModel.readsPdf
                      ? 'Lee el PDF completo: también facturas escaneadas.'
                      : 'Solo recibe el texto del PDF: no podrá leer facturas escaneadas.'
                    : 'Los primeros de la lista leen el PDF completo, también facturas escaneadas.'
              }
            />
          </div>
        </div>

        {provider?.needsEndpoint && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="sm:col-span-3">
              <Field
                id="ai-endpoint"
                label="Punto de conexión del recurso"
                type="url"
                placeholder="https://mi-recurso.openai.azure.com"
                maxLength={255}
                required
                value={form.endpoint}
                onChange={(e) => set('endpoint', e.target.value)}
                disabled={disabled}
              />
            </div>
            <div className="sm:col-span-2">
              <Field
                id="ai-deployment"
                label="Nombre de la implementación"
                type="text"
                placeholder={form.model || 'El nombre del modelo'}
                maxLength={100}
                value={form.deployment}
                onChange={(e) => set('deployment', e.target.value)}
                disabled={disabled}
                hint="Déjalo vacío si la implementación se llama como el modelo."
              />
            </div>
            <Field
              id="ai-api-version"
              label="Versión de la API"
              type="text"
              placeholder="Por defecto"
              maxLength={50}
              value={form.apiVersion}
              onChange={(e) => set('apiVersion', e.target.value)}
              disabled={disabled}
              hint="Opcional, p. ej. 2024-10-21."
            />
          </div>
        )}

        {provider?.needsRegion && (
          <div className="sm:w-1/3">
            <SearchSelect
              id="ai-region"
              label="Región de AWS"
              options={AWS_REGIONS.map((region) => ({ value: region, label: region }))}
              value={form.region || null}
              onChange={(value) => set('region', value ?? '')}
              placeholder="eu-south-2"
              disabled={disabled}
              required
              creatable
              hint="Donde tienes acceso al modelo (eu-south-2 es España)."
            />
          </div>
        )}

        {form.provider && (
          <Field
            id="ai-api-key"
            label="API key"
            type="password"
            autoComplete="off"
            spellCheck={false}
            maxLength={4096}
            required={keyRequired}
            placeholder={
              keyRequired
                ? 'Pega aquí tu API key'
                : `Guardada${saved?.apiKeyHint ? ` (${saved.apiKeyHint})` : ''}. Déjala vacía para mantenerla`
            }
            value={form.apiKey}
            onChange={(e) => set('apiKey', e.target.value)}
            disabled={disabled}
            hint={API_KEY_HINTS[form.provider]}
          />
        )}

        <div className="flex items-center justify-between gap-3 pt-1">
          <button type="submit" disabled={disabled} className={PRIMARY_BUTTON_CLASS}>
            {busy ? 'Guardando…' : 'Guardar configuración de IA'}
          </button>
          {saved && (
            <button
              type="button"
              onClick={() => setConfirmingDelete(true)}
              disabled={disabled}
              className="text-sm font-medium text-rose-600 hover:text-rose-700 px-4 py-2 rounded-lg hover:bg-rose-50 transition-colors disabled:opacity-50"
            >
              Eliminar configuración
            </button>
          )}
        </div>
      </form>

      {confirmingDelete && (
        <ConfirmDialog
          title="Eliminar configuración de IA"
          message="Se borrarán el proveedor, el modelo y la API key guardada. La importación de facturas desde PDF dejará de estar disponible hasta que configures otro proveedor."
          confirmLabel="Eliminar configuración"
          busyLabel="Eliminando…"
          tone="danger"
          busy={busy}
          onConfirm={remove}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}
    </section>
  )
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422) return `Revisa los datos: ${error.message}`
    return error.message
  }
  return 'No se pudo guardar la configuración de IA. Inténtalo de nuevo.'
}
