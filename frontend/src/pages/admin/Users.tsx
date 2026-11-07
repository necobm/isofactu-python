import { useEffect, useState, type ReactNode } from 'react'
import { admin, ApiError, type User, type UserInput } from '@/api'
import ConfirmDialog from '@/components/ConfirmDialog'
import AccountStatusBadge from '@/components/admin/AccountStatusBadge'
import UserFormDialog from '@/components/admin/UserFormDialog'
import { FormMessage } from '@/components/form'
import { useAuth } from '@/lib/auth-context'
import { formatDateTime } from '@/lib/format'
import { useApi } from '@/lib/useApi'

const PAGE_SIZE = 25
const HEADER_CELL = 'px-5 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide'
const ACTION_BUTTON =
  'text-xs font-medium px-2.5 py-1.5 rounded-lg border border-transparent transition-colors disabled:opacity-40 disabled:cursor-not-allowed'

type Dialog =
  | { kind: 'create' }
  | { kind: 'edit'; user: User }
  | { kind: 'delete'; user: User }
  | { kind: 'resend'; user: User }

interface Notice {
  tone: 'success' | 'error'
  text: string
}

interface UsersProps {
  /** Set by the parent when the "Nueva cuenta" header button is pressed. */
  creating: boolean
  onCreatingHandled: () => void
}

/** SUPER_ADMIN panel: every account of the system and what can be done with it. */
export default function Users({ creating, onCreatingHandled }: UsersProps) {
  const { user: me } = useAuth()
  const [page, setPage] = useState(0)
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)

  const users = useApi((signal) => admin.listUsers({ limit: PAGE_SIZE, offset: page * PAGE_SIZE }, signal), [page])

  useEffect(() => {
    if (creating) {
      setDialog({ kind: 'create' })
      onCreatingHandled()
    }
  }, [creating, onCreatingHandled])

  const items = users.data?.items ?? []
  const total = users.data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  /** Runs an action on an account, reloads the list and reports the outcome. */
  async function perform(user: User, action: () => Promise<unknown>, done: string) {
    setBusyId(user.id)
    setNotice(null)
    try {
      await action()
      setNotice({ tone: 'success', text: done })
      users.reload()
    } catch (err) {
      setNotice({ tone: 'error', text: describe(err) })
    } finally {
      setBusyId(null)
    }
  }

  async function create(input: UserInput) {
    await admin.createUser(input)
    setDialog(null)
    setNotice({ tone: 'success', text: `Cuenta creada. Se ha enviado el enlace de activación a ${input.email}.` })
    users.reload()
  }

  async function update(user: User, input: UserInput) {
    await admin.updateUser(user.id, input)
    setDialog(null)
    setNotice({ tone: 'success', text: `Cuenta ${input.email} actualizada.` })
    users.reload()
  }

  return (
    <div className="space-y-4">
      {notice && <FormMessage tone={notice.tone}>{notice.text}</FormMessage>}

      <section className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden" aria-label="Cuentas">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">Cuentas del sistema</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {users.data ? `${total} ${total === 1 ? 'cuenta' : 'cuentas'}` : ' '}
            </p>
          </div>
          <button
            onClick={users.reload}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-indigo-600 font-medium transition-colors"
          >
            <svg className={`w-3.5 h-3.5 ${users.status === 'loading' ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Actualizar
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className={`text-left ${HEADER_CELL}`}>Cuenta</th>
                <th className={`text-left ${HEADER_CELL}`}>Rol</th>
                <th className={`text-left ${HEADER_CELL}`}>Estado</th>
                <th className={`text-left ${HEADER_CELL}`}>Enlace de activación</th>
                <th className={`text-left ${HEADER_CELL}`}>Último acceso</th>
                <th className={`text-right ${HEADER_CELL}`}>Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {users.status === 'loading' && items.length === 0 && (
                <Placeholder>Cargando cuentas…</Placeholder>
              )}
              {users.status === 'error' && (
                <Placeholder>
                  <p className="text-rose-500 font-medium">No se pudieron cargar las cuentas</p>
                  <p className="text-slate-400 text-xs mt-1">{users.error.message}</p>
                </Placeholder>
              )}
              {users.status === 'success' && items.length === 0 && <Placeholder>No hay cuentas.</Placeholder>}
              {items.map((user) => {
                const self = user.id === me?.id
                const busy = busyId === user.id
                return (
                  <tr key={user.id} className="hover:bg-slate-50/50">
                    <td className="px-5 py-3.5">
                      <p className="font-medium text-slate-700">
                        {user.email}
                        {self && <span className="ml-2 text-[11px] font-normal text-indigo-500">(tú)</span>}
                      </p>
                      <p className="text-xs text-slate-400">{user.name || '—'}</p>
                    </td>
                    <td className="px-5 py-3.5 text-slate-600 whitespace-nowrap">
                      {user.role === 'SUPER_ADMIN' ? 'Superadministrador' : 'Administrador'}
                    </td>
                    <td className="px-5 py-3.5 whitespace-nowrap">
                      <AccountStatusBadge user={user} />
                      {user.status === 'ACTIVE' && !user.hasPassword && (
                        <p className="mt-1 text-[11px] text-amber-600">Sin contraseña: no puede entrar.</p>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-xs whitespace-nowrap">
                      <ActivationLinkCell user={user} />
                    </td>
                    <td className="px-5 py-3.5 text-xs text-slate-500 whitespace-nowrap">
                      {user.lastLoginAt ? formatDateTime(user.lastLoginAt) : 'Nunca'}
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => setDialog({ kind: 'edit', user })}
                          disabled={busy}
                          className={`${ACTION_BUTTON} text-slate-600 hover:bg-slate-100`}
                        >
                          Editar
                        </button>
                        <button
                          onClick={() => setDialog({ kind: 'resend', user })}
                          disabled={busy}
                          className={`${ACTION_BUTTON} text-slate-600 hover:bg-slate-100`}
                          title="Envía un nuevo enlace para elegir contraseña y activar la cuenta"
                        >
                          Reenviar enlace
                        </button>
                        {user.status === 'ACTIVE' ? (
                          <button
                            onClick={() => perform(user, () => admin.pauseUser(user.id), `Cuenta ${user.email} pausada.`)}
                            disabled={busy || self}
                            title={self ? 'No puedes pausar tu propia cuenta' : undefined}
                            className={`${ACTION_BUTTON} text-amber-700 hover:bg-amber-50`}
                          >
                            Pausar
                          </button>
                        ) : (
                          <button
                            onClick={() =>
                              perform(user, () => admin.activateUser(user.id), `Cuenta ${user.email} activada.`)
                            }
                            disabled={busy}
                            className={`${ACTION_BUTTON} text-emerald-700 hover:bg-emerald-50`}
                          >
                            Activar
                          </button>
                        )}
                        <button
                          onClick={() => setDialog({ kind: 'delete', user })}
                          disabled={busy || self}
                          title={self ? 'No puedes eliminar tu propia cuenta' : undefined}
                          className={`${ACTION_BUTTON} text-rose-600 hover:bg-rose-50`}
                        >
                          Eliminar
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {pageCount > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 text-xs text-slate-500">
            <span>
              Mostrando {page * PAGE_SIZE + 1}–{Math.min(total, (page + 1) * PAGE_SIZE)} de {total}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Anterior
              </button>
              <span className="px-2">
                {page + 1} / {pageCount}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                disabled={page + 1 >= pageCount}
                className="px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Siguiente
              </button>
            </div>
          </div>
        )}
      </section>

      {dialog?.kind === 'create' && <UserFormDialog onSubmit={create} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'edit' && (
        <UserFormDialog
          user={dialog.user}
          roleLocked={dialog.user.id === me?.id}
          onSubmit={(input) => update(dialog.user, input)}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === 'resend' && (
        <ConfirmDialog
          title="Reenviar enlace de activación"
          message={
            `Se enviará a ${dialog.user.email} un nuevo enlace para elegir contraseña y activar la cuenta. ` +
            (dialog.user.hasPassword
              ? 'Su contraseña actual seguirá funcionando hasta que use el enlace.'
              : 'El enlace anterior, si lo había, dejará de funcionar.')
          }
          confirmLabel="Enviar enlace"
          busyLabel="Enviando…"
          busy={busyId === dialog.user.id}
          onConfirm={async () => {
            const { user } = dialog
            await perform(user, () => admin.sendActivation(user.id), `Enlace de activación enviado a ${user.email}.`)
            setDialog(null)
          }}
          onCancel={() => setDialog(null)}
        />
      )}
      {dialog?.kind === 'delete' && (
        <ConfirmDialog
          title="Eliminar cuenta"
          message={
            `Se eliminará la cuenta ${dialog.user.email} junto con todos sus datos (clientes y facturas). ` +
            'Esta acción no se puede deshacer.'
          }
          confirmLabel="Eliminar cuenta"
          busyLabel="Eliminando…"
          tone="danger"
          busy={busyId === dialog.user.id}
          onConfirm={async () => {
            const { user } = dialog
            await perform(user, () => admin.deleteUser(user.id), `Cuenta ${user.email} eliminada.`)
            setDialog(null)
          }}
          onCancel={() => setDialog(null)}
        />
      )}
    </div>
  )
}

function ActivationLinkCell({ user }: { user: User }) {
  if (!user.activationExpiresAt) return <span className="text-slate-400">—</span>
  const expired = new Date(user.activationExpiresAt).getTime() < Date.now()
  return expired ? (
    <span className="text-rose-600">Caducado el {formatDateTime(user.activationExpiresAt)}</span>
  ) : (
    <span className="text-slate-600">Válido hasta el {formatDateTime(user.activationExpiresAt)}</span>
  )
}

function Placeholder({ children }: { children: ReactNode }) {
  return (
    <tr>
      <td colSpan={6} className="px-5 py-12 text-center text-slate-400 text-sm">
        {children}
      </td>
    </tr>
  )
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 503) return 'No se pudo enviar el correo. Comprueba el servidor de correo e inténtalo de nuevo.'
    return error.message
  }
  return 'La operación no se pudo completar. Inténtalo de nuevo.'
}
