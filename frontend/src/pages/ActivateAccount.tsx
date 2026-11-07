import { useState, type FormEvent } from 'react'
import { ApiError, auth } from '@/api'
import AuthLayout from '@/components/AuthLayout'
import { Field, FormMessage, PRIMARY_BUTTON_CLASS } from '@/components/form'
import { formatDateTime } from '@/lib/format'
import { useApi } from '@/lib/useApi'

const MIN_PASSWORD_LENGTH = 8

interface ActivateAccountProps {
  token: string
  /** The account is active: go to the login page. */
  onActivated: () => void
}

/** Page behind the link of the activation e-mail: the user chooses a password. */
export default function ActivateAccount({ token, onActivated }: ActivateAccountProps) {
  const info = useApi((signal) => auth.activationInfo(token, signal), [token])
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`La contraseña debe tener al menos ${MIN_PASSWORD_LENGTH} caracteres.`)
      return
    }
    if (password !== confirmation) {
      setError('Las contraseñas no coinciden.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await auth.activate(token, password)
      onActivated()
    } catch (err) {
      setError(describe(err))
      setBusy(false)
    }
  }

  if (info.status === 'loading') {
    return (
      <AuthLayout title="Activar cuenta">
        <p className="text-sm text-slate-400">Comprobando el enlace…</p>
      </AuthLayout>
    )
  }

  if (info.status === 'error') {
    const invalid = info.error instanceof ApiError && info.error.status === 404
    return (
      <AuthLayout title="Activar cuenta">
        <FormMessage tone="error">
          {invalid
            ? 'Este enlace de activación no es válido o ha caducado. Pide a tu administrador que te envíe uno nuevo.'
            : `No se pudo comprobar el enlace: ${info.error.message}`}
        </FormMessage>
      </AuthLayout>
    )
  }

  const { email, name, expiresAt } = info.data
  return (
    <AuthLayout
      title={name ? `Hola, ${name}` : 'Activar cuenta'}
      subtitle={
        <>
          Elige la contraseña de la cuenta <span className="font-medium text-slate-700">{email}</span> para activarla.
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {error && <FormMessage tone="error">{error}</FormMessage>}
        <Field
          id="activate-password"
          label="Contraseña"
          type="password"
          autoComplete="new-password"
          autoFocus
          required
          minLength={MIN_PASSWORD_LENGTH}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={busy}
          hint={`Al menos ${MIN_PASSWORD_LENGTH} caracteres.`}
        />
        <Field
          id="activate-confirmation"
          label="Repite la contraseña"
          type="password"
          autoComplete="new-password"
          required
          value={confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !password || !confirmation} className={`${PRIMARY_BUTTON_CLASS} w-full`}>
          {busy ? 'Activando…' : 'Activar mi cuenta'}
        </button>
        <p className="text-xs text-slate-400 text-center">Este enlace caduca el {formatDateTime(expiresAt)}.</p>
      </form>
    </AuthLayout>
  )
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) return 'Este enlace ya no es válido. Pide a tu administrador que te envíe uno nuevo.'
    return error.message
  }
  return 'No se pudo activar la cuenta. Inténtalo de nuevo.'
}
