import { useCallback, useState } from 'react'
import TopNav, { type NavItem } from '@/components/TopNav'
import Settings from '@/pages/admin/Settings'
import Users from '@/pages/admin/Users'

type AdminPage = 'usuarios' | 'ajustes'

const NAV_ITEMS: NavItem<AdminPage>[] = [
  { id: 'usuarios', label: 'Cuentas' },
  { id: 'ajustes', label: 'Ajustes' },
]

const PAGE_TITLES: Record<AdminPage, { title: string; subtitle: string }> = {
  usuarios: { title: 'Gestión de cuentas', subtitle: 'Crea, activa, pausa o elimina las cuentas del sistema.' },
  ajustes: { title: 'Ajustes del sistema', subtitle: 'Configuración que afecta a todas las cuentas.' },
}

/** Shell for SUPER_ADMIN users: account management only, no invoicing. */
export default function AdminApp() {
  const [activePage, setActivePage] = useState<AdminPage>('usuarios')
  const [creating, setCreating] = useState(false)
  const { title, subtitle } = PAGE_TITLES[activePage]
  const onCreatingHandled = useCallback(() => setCreating(false), [])

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <TopNav items={NAV_ITEMS} activeId={activePage} onNavigate={setActivePage} />

      <div className="bg-white border-b border-slate-200">
        <div className="max-w-screen-xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-800">{title}</h1>
            <p className="text-sm text-slate-400 mt-0.5">{subtitle}</p>
          </div>
          {activePage === 'usuarios' && (
            <button
              onClick={() => setCreating(true)}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Nueva cuenta
            </button>
          )}
        </div>
      </div>

      <main className="flex-1 max-w-screen-xl mx-auto w-full px-6 py-6">
        {activePage === 'usuarios' && <Users creating={creating} onCreatingHandled={onCreatingHandled} />}
        {activePage === 'ajustes' && <Settings />}
      </main>
    </div>
  )
}
