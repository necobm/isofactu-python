import { request } from './client'
import type {
  ActivationInfo,
  LoginInput,
  PasswordChangeInput,
  SystemSettings,
  User,
  UserCollection,
  UserInput,
} from './types'
import type { PageParams } from './invoices'

/** Session management and the public account activation flow. */
export const auth = {
  /** Starts a session (cookie). `401` bad credentials, `403` paused account. */
  login: (input: LoginInput) => request<User>('/api/auth/login', { method: 'POST', body: input }),

  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),

  /** The logged-in user, or `401`. */
  me: (signal?: AbortSignal) => request<User>('/api/auth/me', { signal }),

  /** Replaces the password of the logged-in user; `400` when the current one is wrong. */
  changePassword: (input: PasswordChangeInput) =>
    request<void>('/api/auth/password', { method: 'POST', body: input }),

  /** Who an activation link is for; `404` when it is unknown, used or expired. */
  activationInfo: (token: string, signal?: AbortSignal) =>
    request<ActivationInfo>(`/api/auth/activate/${encodeURIComponent(token)}`, { signal }),

  /** Sets the password, activates the account and consumes the link. */
  activate: (token: string, password: string) =>
    request<User>(`/api/auth/activate/${encodeURIComponent(token)}`, {
      method: 'POST',
      body: { password },
    }),
}

/** Account management (SUPER_ADMIN only). */
export const admin = {
  listUsers: (params: PageParams = {}, signal?: AbortSignal) =>
    request<UserCollection>('/api/admin/user', { query: params, signal }),

  /** Creates a paused account and e-mails it an activation link. */
  createUser: (input: UserInput) => request<User>('/api/admin/user', { method: 'POST', body: input }),

  updateUser: (id: number, input: UserInput) =>
    request<User>(`/api/admin/user/${id}`, { method: 'PUT', body: input }),

  /** Removes the account and everything it owns. */
  deleteUser: (id: number) => request<void>(`/api/admin/user/${id}`, { method: 'DELETE' }),

  pauseUser: (id: number) => request<User>(`/api/admin/user/${id}/pause`, { method: 'POST' }),

  activateUser: (id: number) => request<User>(`/api/admin/user/${id}/activate`, { method: 'POST' }),

  /** Issues a fresh activation link (the previous one stops working) and e-mails it. */
  sendActivation: (id: number) =>
    request<User>(`/api/admin/user/${id}/send-activation`, { method: 'POST' }),

  getSettings: (signal?: AbortSignal) => request<SystemSettings>('/api/admin/settings', { signal }),

  updateSettings: (input: SystemSettings) =>
    request<SystemSettings>('/api/admin/settings', { method: 'PUT', body: input }),
}
