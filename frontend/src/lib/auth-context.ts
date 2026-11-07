import { createContext, useContext } from 'react'
import type { LoginInput, User } from '@/api'

export interface AuthState {
  /** `undefined` while the session is being checked, `null` when nobody is logged in. */
  user: User | null | undefined
  login: (input: LoginInput) => Promise<User>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const state = useContext(AuthContext)
  if (!state) throw new Error('useAuth must be used inside <AuthProvider>')
  return state
}
