import { useState } from 'react'
import TopNav, { type NavItem } from '@/components/TopNav'
import { useAuth } from '@/lib/auth-context'
import Dashboard from '@/pages/Dashboard'
import FiscalDataSettings from '@/pages/FiscalDataSettings'
import SerialSettings from '@/pages/SerialSettings'
import Invoices from '@/pages/Invoices'
import InvoiceForm from '@/pages/InvoiceForm'
import type { Page } from '@/types'

const NAV_ITEMS: NavItem<Page>[] = [
  { id: 'dashboard', label: 'Panel' },
  { id: 'facturas', label: 'Facturas' },
  { id: 'gastos', label: 'Gastos' },
  { id: 'clientes', label: 'Clientes' },
  { id: 'ajustes', label: 'Ajustes' },
]

const pageTitles: Record<Page, { title: string; subtitle: string }> = {
  dashboard: { title: 'Panel de Control', subtitle: 'Aquí tienes el resumen de tu actividad financiera.' },
  facturas: { title: 'Facturas', subtitle: 'Gestiona y consulta tus borradores y facturas emitidas.' },
  gastos: { title: 'Gestión de Gastos', subtitle: 'Registra y controla tus gastos.' },
  clientes: { title: 'Directorio de Clientes', subtitle: 'Administra tu cartera de clientes.' },
  ajustes: { title: 'Ajustes de la cuenta', subtitle: 'Tus datos fiscales (el emisor de tus facturas) y las series de numeración.' },
  createInvoice: { title: '', subtitle: '' },
  editInvoice: { title: '', subtitle: '' },
}

/** Shell for ADMIN users (tenants): their invoices, clients and expenses. */
export default function TenantApp() {
  const { user } = useAuth()
  const [activePage, setActivePage] = useState<Page>('dashboard')
  const [editingInvoiceId, setEditingInvoiceId] = useState<number | null>(null)
  // Where to go back to after saving the fiscal data from the invoice form
  const [afterSettings, setAfterSettings] = useState<Page | null>(null)
  const { title, subtitle } = pageTitles[activePage]

  function showInvoices() {
    setEditingInvoiceId(null)
    setActivePage('facturas')
  }

  function editDraft(invoiceId: number) {
    setEditingInvoiceId(invoiceId)
    setActivePage('editInvoice')
  }

  /** Jump to the settings from the invoice form; saving the fiscal data there brings the
   * user back to the form. */
  function configureFiscalData() {
    setAfterSettings(activePage)
    setActivePage('ajustes')
  }

  function fiscalDataSaved() {
    if (afterSettings) {
      setActivePage(afterSettings)
      setAfterSettings(null)
    }
  }

  if (activePage === 'createInvoice' || (activePage === 'editInvoice' && editingInvoiceId !== null)) {
    return (
      <>
        <TopNav items={NAV_ITEMS} activeId="facturas" onNavigate={setActivePage} />
        <InvoiceForm
          key={editingInvoiceId ?? 'new'}
          invoiceId={editingInvoiceId ?? undefined}
          onBack={showInvoices}
          onSaved={showInvoices}
          onOpenSettings={configureFiscalData}
        />
      </>
    )
  }

  const greeting = activePage === 'dashboard' && user ? `Bienvenido de nuevo, ${user.name || user.email}. ` : ''

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <TopNav items={NAV_ITEMS} activeId={activePage} onNavigate={setActivePage} />

      {/* Page header */}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-screen-xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-800">{title}</h1>
            <p className="text-sm text-slate-400 mt-0.5">
              {greeting}
              {subtitle}
            </p>
          </div>
          <button
            onClick={() => {
              setEditingInvoiceId(null)
              setActivePage('createInvoice')
            }}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Nueva Factura
          </button>
        </div>
      </div>

      {/* Main content */}
      <main className="flex-1 max-w-screen-xl mx-auto w-full px-6 py-6">
        {activePage === 'dashboard' && <Dashboard onViewInvoices={() => setActivePage('facturas')} />}
        {activePage === 'facturas' && <Invoices onEditDraft={editDraft} />}
        {activePage === 'ajustes' && (
          <div className="space-y-6">
            <FiscalDataSettings onSaved={fiscalDataSaved} />
            <SerialSettings />
          </div>
        )}
        {(activePage === 'gastos' || activePage === 'clientes') && (
          <div className="flex items-center justify-center h-64 text-slate-400">
            <p className="text-lg">Próximamente...</p>
          </div>
        )}
      </main>
    </div>
  )
}
