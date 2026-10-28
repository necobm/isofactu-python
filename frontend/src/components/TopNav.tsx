import type { Page } from '@/types'

const navItems: { id: Page; label: string }[] = [
  { id: 'dashboard', label: 'Panel' },
  { id: 'facturas', label: 'Facturas' },
  { id: 'gastos', label: 'Gastos' },
  { id: 'clientes', label: 'Clientes' },
]

interface TopNavProps {
  activePage: Page
  onNavigate: (page: Page) => void
}

export default function TopNav({ activePage, onNavigate }: TopNavProps) {
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
            {navItems.map((item) => {
              const isActive = activePage === item.id
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

        {/* Right: bell + avatar */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <button className="relative p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
            <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-indigo-500 rounded-full" />
          </button>
          <button className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center overflow-hidden hover:ring-2 hover:ring-indigo-400 transition-all">
            <svg className="w-5 h-5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </button>
        </div>
      </div>
    </header>
  )
}
