import { useEffect, useRef, useState } from 'react'
import ChangePasswordDialog from '@/components/ChangePasswordDialog'
import { useAuth } from '@/lib/auth-context'

export interface NavItem<Id extends string> {
  id: Id
  label: string
}

interface TopNavProps<Id extends string> {
  items: NavItem<Id>[]
  activeId: Id
  onNavigate: (id: Id) => void
}

export default function TopNav<Id extends string>({ items, activeId, onNavigate }: TopNavProps<Id>) {
  const { user, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const [changingPassword, setChangingPassword] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  // Close the user menu when clicking elsewhere or pressing Escape
  useEffect(() => {
    if (!menuOpen) return
    const onPointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [menuOpen])

  async function handleLogout() {
    setMenuOpen(false)
    setLeaving(true)
    try {
      await logout()
    } finally {
      setLeaving(false)
    }
  }

  return (
    <header className="bg-white border-b border-slate-200 flex-shrink-0">
      <div className="max-w-screen-xl mx-auto px-6 h-14 flex items-center gap-8">
        {/* Logo */}
        <div className="flex items-center gap-2.5 flex-shrink-0">
          <div className="w-7 h-7 bg-indigo-600 rounded-md flex items-center justify-center">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <span className="font-bold text-slate-800 text-base tracking-tight">Isofactu</span>
        </div>

        {/* Nav links — centered */}
        <nav className="flex-1 flex justify-center">
          <ul className="flex items-center gap-1">
            {items.map((item) => {
              const isActive = activeId === item.id
              return (
                <li key={item.id}>
                  <button
                    onClick={() => onNavigate(item.id)}
                    className={`relative px-4 py-4 text-sm font-medium transition-colors ${
                      isActive ? 'text-indigo-600' : 'text-slate-500 hover:text-slate-800'
                    }`}
                  >
                    {item.label}
                    {isActive && (
                      <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-t-full" />
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        </nav>

        {/* Right: current user menu (change password, log out) */}
        {user && (
          <div ref={menuRef} className="relative flex-shrink-0">
            <button
              onClick={() => setMenuOpen((open) => !open)}
              disabled={leaving}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 hover:bg-slate-100 transition-colors disabled:opacity-50"
            >
              <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-sm font-semibold uppercase">
                {(user.name || user.email).charAt(0)}
              </div>
              <div className="hidden sm:block leading-tight text-left">
                <p className="text-sm font-medium text-slate-700 max-w-[12rem] truncate">{user.name || user.email}</p>
                <p className="text-[11px] text-slate-400 max-w-[12rem] truncate">
                  {user.name ? user.email : user.role === 'SUPER_ADMIN' ? 'Superadministrador' : 'Administrador'}
                </p>
              </div>
              <svg className={`w-4 h-4 text-slate-400 transition-transform ${menuOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {menuOpen && (
              <div
                role="menu"
                className="absolute right-0 mt-1 w-56 rounded-lg border border-slate-200 bg-white shadow-lg py-1 text-sm z-20"
              >
                <div className="px-4 py-2 border-b border-slate-100 sm:hidden">
                  <p className="font-medium text-slate-700 truncate">{user.name || user.email}</p>
                  <p className="text-xs text-slate-400 truncate">{user.email}</p>
                </div>
                <button
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false)
                    setChangingPassword(true)
                  }}
                  className="w-full text-left px-4 py-2 text-slate-700 hover:bg-slate-50"
                >
                  Cambiar contraseña
                </button>
                <button
                  role="menuitem"
                  onClick={handleLogout}
                  className="w-full text-left px-4 py-2 text-slate-700 hover:bg-slate-50"
                >
                  {leaving ? 'Saliendo…' : 'Cerrar sesión'}
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {changingPassword && <ChangePasswordDialog onClose={() => setChangingPassword(false)} />}
    </header>
  )
}
