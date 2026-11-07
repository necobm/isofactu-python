import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError, auth, onUnauthorized, type LoginInput, type User } from '@/api'
import { AuthContext } from './auth-context'

/**
 * Keeps track of the logged-in user. The session itself lives in an HttpOnly cookie set by
 * the backend: on mount we ask `/api/auth/me` who we are, and any `401` answered by the API
 * afterwards (expired session, paused account...) sends the user back to the login page.
 */
export default function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined)

  useEffect(() => {
    const controller = new AbortController()
    auth
      .me(controller.signal)
      .then(setUser)
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        // 401 = no session; anything else (server down...) is also "not logged in" for now
        setUser(null)
        if (!(error instanceof ApiError && error.status === 401)) console.error(error)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => onUnauthorized(() => setUser((current) => (current ? null : current))), [])

  const login = useCallback(async (input: LoginInput) => {
    const logged = await auth.login(input)
    setUser(logged)
    return logged
  }, [])

  const logout = useCallback(async () => {
    try {
      await auth.logout()
    } finally {
      setUser(null)
    }
  }, [])

  const value = useMemo(() => ({ user, login, logout }), [user, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
