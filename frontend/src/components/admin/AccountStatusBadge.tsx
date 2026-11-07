import type { User } from '@/api'

const STYLES = {
  active: 'bg-emerald-50 text-emerald-700 border-emerald-100',
  pending: 'bg-amber-50 text-amber-700 border-amber-100',
  paused: 'bg-slate-100 text-slate-600 border-slate-200',
}

/** Account state at a glance: active, paused, or created but still without a password. */
export default function AccountStatusBadge({ user }: { user: User }) {
  const kind = user.status === 'ACTIVE' ? 'active' : user.hasPassword ? 'paused' : 'pending'
  const label = { active: 'Activa', paused: 'Pausada', pending: 'Pendiente de activar' }[kind]
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${STYLES[kind]}`}>
      {label}
    </span>
  )
}
