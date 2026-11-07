import { useEffect, useState, type FormEvent } from 'react'
import { ApiError, type Role, type User, type UserInput } from '@/api'
import { Field, FormMessage, INPUT_CLASS, PRIMARY_BUTTON_CLASS, SECONDARY_BUTTON_CLASS } from '@/components/form'

const ROLE_OPTIONS: { value: Role; label: string; description: string }[] = [
  { value: 'ADMIN', label: 'Administrador (cuenta)', description: 'Gestiona sus propias facturas y datos.' },
  { value: 'SUPER_ADMIN', label: 'Superadministrador', description: 'Gestiona las cuentas del sistema.' },
]

interface UserFormDialogProps {
  /** The account being edited; omitted when creating a new one. */
  user?: User
  /** Whether the role can be changed (not for one's own account). */
  roleLocked?: boolean
  onSubmit: (input: UserInput) => Promise<void>
  onClose: () => void
}

/** Modal form to create an account (an activation e-mail is sent) or edit its details. */
export default function UserFormDialog({ user, roleLocked = false, onSubmit, onClose }: UserFormDialogProps) {
  const editing = user !== undefined
  const [email, setEmail] = useState(user?.email ?? '')
  const [name, setName] = useState(user?.name ?? '')
  const [role, setRole] = useState<Role>(user?.role ?? 'ADMIN')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose, busy])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onSubmit({ email: email.trim(), name: name.trim(), role })
    } catch (err) {
      setError(describe(err))
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
        aria-labelledby="user-form-title"
        className="w-full max-w-md rounded-xl bg-white shadow-xl"
        noValidate
      >
        <div className="px-6 pt-5 pb-4 space-y-4">
          <div>
            <h2 id="user-form-title" className="text-base font-semibold text-slate-800">
              {editing ? 'Editar cuenta' : 'Nueva cuenta'}
            </h2>
            {!editing && (
              <p className="mt-1 text-sm text-slate-500">
                La cuenta se crea pausada y sin contraseña: el usuario recibirá por correo un enlace para elegirla y
                activarla.
              </p>
            )}
          </div>
          {error && <FormMessage tone="error">{error}</FormMessage>}
          <Field
            id="user-email"
            label="Correo electrónico"
            type="email"
            autoComplete="off"
            autoFocus
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy}
          />
          <Field
            id="user-name"
            label="Nombre"
            type="text"
            autoComplete="off"
            maxLength={255}
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy}
            hint="Opcional. Cómo se muestra al usuario en la aplicación."
          />
          <div>
            <label htmlFor="user-role" className="block text-xs font-medium text-slate-600 mb-1.5">
              Rol
            </label>
            <select
              id="user-role"
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              disabled={busy || roleLocked}
              className={`${INPUT_CLASS} bg-white`}
            >
              {ROLE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-slate-400">
              {roleLocked ? 'No puedes cambiar tu propio rol.' : ROLE_OPTIONS.find((o) => o.value === role)?.description}
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-3 border-t border-slate-100 px-6 py-4">
          <button type="button" onClick={onClose} disabled={busy} className={SECONDARY_BUTTON_CLASS}>
            Cancelar
          </button>
          <button type="submit" disabled={busy || !email.trim()} className={PRIMARY_BUTTON_CLASS}>
            {busy ? (editing ? 'Guardando…' : 'Creando…') : editing ? 'Guardar' : 'Crear y enviar enlace'}
          </button>
        </div>
      </form>
    </div>
  )
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return 'Ya existe una cuenta con ese correo electrónico.'
    if (error.status === 422) return 'Introduce un correo electrónico válido.'
    if (error.status === 503) return 'No se pudo enviar el correo de activación. Comprueba el servidor de correo e inténtalo de nuevo.'
    return error.message
  }
  return 'No se pudo guardar la cuenta. Inténtalo de nuevo.'
}
