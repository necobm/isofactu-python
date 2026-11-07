import { useEffect, useState, type FormEvent } from 'react'
import { admin } from '@/api'
import { Field, FormMessage, PRIMARY_BUTTON_CLASS } from '@/components/form'
import { useApi } from '@/lib/useApi'

const MIN_HOURS = 1
const MAX_HOURS = 24 * 30

/** SUPER_ADMIN panel: system-wide settings. */
export default function Settings() {
  const settings = useApi((signal) => admin.getSettings(signal), [])
  const [hours, setHours] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    if (settings.status === 'success') setHours(String(settings.data.activationLinkTtlHours))
  }, [settings])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const value = Number(hours)
    if (!Number.isInteger(value) || value < MIN_HOURS || value > MAX_HOURS) {
      setMessage({ tone: 'error', text: `Indica un número entero de horas entre ${MIN_HOURS} y ${MAX_HOURS}.` })
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      const saved = await admin.updateSettings({ activationLinkTtlHours: value })
      setHours(String(saved.activationLinkTtlHours))
      setMessage({ tone: 'success', text: 'Ajustes guardados.' })
    } catch (err) {
      setMessage({ tone: 'error', text: err instanceof Error ? err.message : String(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="bg-white rounded-xl border border-slate-100 shadow-sm max-w-2xl" aria-label="Ajustes">
      <div className="px-5 py-4 border-b border-slate-100">
        <h2 className="text-sm font-semibold text-slate-800">Enlaces de activación</h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Los enlaces que reciben los usuarios por correo para elegir su contraseña y activar la cuenta.
        </p>
      </div>
      <form onSubmit={handleSubmit} className="px-5 py-5 space-y-4" noValidate>
        {message && <FormMessage tone={message.tone}>{message.text}</FormMessage>}
        {settings.status === 'error' && (
          <FormMessage tone="error">No se pudieron cargar los ajustes: {settings.error.message}</FormMessage>
        )}
        <div className="max-w-xs">
          <Field
            id="settings-ttl"
            label="Caducidad de los enlaces (horas)"
            type="number"
            inputMode="numeric"
            min={MIN_HOURS}
            max={MAX_HOURS}
            step={1}
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            disabled={busy || settings.status !== 'success'}
            hint={`Entre ${MIN_HOURS} y ${MAX_HOURS} horas (${MAX_HOURS / 24} días). Se aplica a los enlaces que se envíen a partir de ahora; los ya enviados conservan su caducidad.`}
          />
        </div>
        <div>
          <button type="submit" disabled={busy || settings.status !== 'success'} className={PRIMARY_BUTTON_CLASS}>
            {busy ? 'Guardando…' : 'Guardar'}
          </button>
        </div>
      </form>
    </section>
  )
}
