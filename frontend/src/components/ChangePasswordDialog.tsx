import { useEffect, useState, type FormEvent } from 'react'
import { ApiError, auth } from '@/api'
import { Field, FormMessage, PRIMARY_BUTTON_CLASS, SECONDARY_BUTTON_CLASS } from '@/components/form'

const MIN_PASSWORD_LENGTH = 8

interface ChangePasswordDialogProps {
  onClose: () => void
}

/** Lets the logged-in user (any role) replace their own password. */
export default function ChangePasswordDialog({ onClose }: ChangePasswordDialogProps) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose, busy])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (next.length < MIN_PASSWORD_LENGTH) {
      setError(`La nueva contraseña debe tener al menos ${MIN_PASSWORD_LENGTH} caracteres.`)
      return
    }
    if (next !== confirmation) {
      setError('Las contraseñas nuevas no coinciden.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await auth.changePassword({ currentPassword: current, newPassword: next })
      setDone(true)
    } catch (err) {
      setError(describe(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onClose()
      }}
    >
      <form
        onSubmit={handleSubmit}
        role="dialog"
        aria-modal="true"
        aria-labelledby="change-password-title"
        className="w-full max-w-md rounded-xl bg-white shadow-xl"
        noValidate
      >
        <div className="px-6 pt-5 pb-4 space-y-4">
          <h2 id="change-password-title" className="text-base font-semibold text-slate-800">
            Cambiar contraseña
          </h2>
          {done ? (
            <FormMessage tone="success">Contraseña actualizada. Úsala la próxima vez que inicies sesión.</FormMessage>
          ) : (
            <>
              {error && <FormMessage tone="error">{error}</FormMessage>}
              <Field
                id="password-current"
                label="Contraseña actual"
                type="password"
                autoComplete="current-password"
                autoFocus
                required
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                disabled={busy}
              />
              <Field
                id="password-new"
                label="Nueva contraseña"
                type="password"
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                value={next}
                onChange={(e) => setNext(e.target.value)}
                disabled={busy}
                hint={`Al menos ${MIN_PASSWORD_LENGTH} caracteres.`}
              />
              <Field
                id="password-confirmation"
                label="Repite la nueva contraseña"
                type="password"
                autoComplete="new-password"
                required
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                disabled={busy}
              />
            </>
          )}
        </div>
        <div className="flex justify-end gap-3 border-t border-slate-100 px-6 py-4">
          {done ? (
            <button type="button" onClick={onClose} className={PRIMARY_BUTTON_CLASS}>
              Cerrar
            </button>
          ) : (
            <>
              <button type="button" onClick={onClose} disabled={busy} className={SECONDARY_BUTTON_CLASS}>
                Cancelar
              </button>
              <button
                type="submit"
                disabled={busy || !current || !next || !confirmation}
                className={PRIMARY_BUTTON_CLASS}
              >
                {busy ? 'Guardando…' : 'Cambiar contraseña'}
              </button>
            </>
          )}
        </div>
      </form>
    </div>
  )
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 400) return 'La contraseña actual no es correcta.'
    if (error.status === 422) return `La nueva contraseña debe tener entre ${MIN_PASSWORD_LENGTH} y 72 caracteres.`
    return error.message
  }
  return 'No se pudo cambiar la contraseña. Inténtalo de nuevo.'
}
