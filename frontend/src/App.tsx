import { useState } from 'react'
import AdminApp from '@/AdminApp'
import TenantApp from '@/TenantApp'
import { useAuth } from '@/lib/auth-context'
import { activationToken, navigate, usePathname } from '@/lib/router'
import ActivateAccount from '@/pages/ActivateAccount'
import Login from '@/pages/Login'

const ACTIVATED_NOTICE = 'Tu cuenta está activada. Ya puedes iniciar sesión con tu nueva contraseña.'

/**
 * Entry point: the activation page (reachable from the e-mail link) is public; everything
 * else needs a session, and the shell depends on the role of the logged-in user.
 */
export default function App() {
  const { user } = useAuth()
  const pathname = usePathname()
  const [notice, setNotice] = useState<string | null>(null)

  const token = activationToken(pathname)
  if (token) {
    return (
      <ActivateAccount
        token={token}
        onActivated={() => {
          setNotice(ACTIVATED_NOTICE)
          navigate('/')
        }}
      />
    )
  }

  if (user === undefined) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-sm text-slate-400">
        Cargando…
      </div>
    )
  }

  if (user === null) return <Login notice={notice} />

  return user.role === 'SUPER_ADMIN' ? <AdminApp /> : <TenantApp />
}
