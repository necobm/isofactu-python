import { useState, type FormEvent } from 'react'
import { ApiError } from '@/api'
import AuthLayout from '@/components/AuthLayout'
import { Field, FormMessage, PRIMARY_BUTTON_CLASS } from '@/components/form'
import { useAuth } from '@/lib/auth-context'

interface LoginProps {
  /** Shown above the form, e.g. after activating an account. */
  notice?: string | null
}

export default function Login({ notice }: LoginProps) {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login({ email: email.trim(), password })
    } catch (err) {
      setError(describe(err))
      setBusy(false)
    }
  }

  return (
    <AuthLayout title="Iniciar sesión" subtitle="Accede con el correo y la contraseña de tu cuenta.">
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {notice && !error && <FormMessage tone="success">{notice}</FormMessage>}
        {error && <FormMessage tone="error">{error}</FormMessage>}
        <Field
          id="login-email"
          label="Correo electrónico"
          type="email"
          autoComplete="email"
          autoFocus
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={busy}
        />
        <Field
          id="login-password"
          label="Contraseña"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !email || !password} className={`${PRIMARY_BUTTON_CLASS} w-full`}>
          {busy ? 'Entrando…' : 'Entrar'}
        </button>
        <p className="text-xs text-slate-400 text-center">
          ¿No tienes cuenta? Las cuentas las crea el administrador del sistema.
        </p>
      </form>
    </AuthLayout>
  )
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'El correo o la contraseña no son correctos.'
    if (error.status === 403) return 'Tu cuenta está pausada. Ponte en contacto con el administrador.'
    if (error.status === 422) return 'Introduce un correo electrónico válido y tu contraseña.'
    return error.message
  }
  return 'No se pudo iniciar sesión. Inténtalo de nuevo.'
}
