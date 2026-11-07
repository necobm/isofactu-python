import { useEffect, useRef, useState } from 'react'
import ChangePasswordDialog from '@/components/ChangePasswordDialog'
import { useAuth } from '@/lib/auth-context'

export interface NavItem<Id extends string> {
  id: Id
  label: string
  /** Sub-sections: the item opens a menu with them instead of navigating itself. */
  children?: { id: Id; label: string; description?: string }[]
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
  // The nav item whose sub-section menu is open, if any
  const [openGroup, setOpenGroup] = useState<Id | null>(null)
  const groupRef = useRef<HTMLLIElement>(null)

  useEffect(() => {
    if (openGroup === null) return
    const onPointerDown = (event: MouseEvent) => {
      if (!groupRef.current?.contains(event.target as Node)) setOpenGroup(null)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpenGroup(null)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [openGroup])

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
              const isActive = activeId === item.id || (item.children ?? []).some((child) => child.id === activeId)
              if (item.children) {
                const open = openGroup === item.id
                const activeChild = item.children.find((child) => child.id === activeId)
                return (
                  <li key={item.id} ref={open ? groupRef : undefined} className="relative">
                    <button
                      onClick={() => setOpenGroup(open ? null : item.id)}
                      aria-haspopup="menu"
                      aria-expanded={open}
                      className={`relative flex items-center gap-1 px-4 py-4 text-sm font-medium transition-colors ${
                        isActive ? 'text-indigo-600' : 'text-slate-500 hover:text-slate-800'
                      }`}
                    >
                      {item.label}
                      {activeChild && <span className="font-normal text-indigo-400">· {activeChild.label}</span>}
                      <svg className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                      {isActive && (
                        <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-t-full" />
                      )}
                    </button>
                    {open && (
                      <div
                        role="menu"
                        aria-label={item.label}
                        className="absolute left-1/2 -translate-x-1/2 mt-1 w-64 rounded-lg border border-slate-200 bg-white shadow-lg py-1 text-sm z-20"
                      >
                        {item.children.map((child) => (
                          <button
                            key={child.id}
                            role="menuitem"
                            aria-current={child.id === activeId ? 'page' : undefined}
                            onClick={() => {
                              setOpenGroup(null)
                              onNavigate(child.id)
                            }}
                            className={`w-full text-left px-4 py-2 hover:bg-slate-50 ${
                              child.id === activeId ? 'text-indigo-600' : 'text-slate-700'
                            }`}
                          >
                            <span className="block font-medium">{child.label}</span>
                            {child.description && <span className="block text-xs text-slate-400">{child.description}</span>}
                          </button>
                        ))}
                      </div>
                    )}
                  </li>
                )
              }
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
