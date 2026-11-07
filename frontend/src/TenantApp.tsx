import { useState } from 'react'
import TopNav, { type NavItem } from '@/components/TopNav'
import { useAuth } from '@/lib/auth-context'
import ClientForm from '@/pages/ClientForm'
import Clients from '@/pages/Clients'
import Dashboard from '@/pages/Dashboard'
import FiscalDataSettings from '@/pages/FiscalDataSettings'
import SerialSettings from '@/pages/SerialSettings'
import Invoices from '@/pages/Invoices'
import InvoiceForm from '@/pages/InvoiceForm'
import type { InvoiceKind } from '@/api'
import type { Page } from '@/types'

const NAV_ITEMS: NavItem<Page>[] = [
  { id: 'dashboard', label: 'Panel' },
  {
    id: 'facturasEmitidas',
    label: 'Facturas',
    children: [
      { id: 'facturasEmitidas', label: 'Emitidas', description: 'Ingresos: las facturas a tus clientes' },
      { id: 'facturasRecibidas', label: 'Recibidas', description: 'Gastos: las facturas de tus proveedores' },
    ],
  },
  { id: 'gastos', label: 'Gastos' },
  { id: 'clientes', label: 'Clientes' },
  { id: 'ajustes', label: 'Ajustes' },
]

const pageTitles: Record<Page, { title: string; subtitle: string }> = {
  dashboard: { title: 'Panel de Control', subtitle: 'Aquí tienes el resumen de tu actividad financiera.' },
  facturasEmitidas: { title: 'Facturas emitidas', subtitle: 'Tus ingresos: gestiona y consulta tus borradores y las facturas emitidas a tus clientes.' },
  facturasRecibidas: { title: 'Facturas recibidas', subtitle: 'Tus gastos: registra las facturas de tus proveedores y corrígelas cuando lo necesites.' },
  gastos: { title: 'Gestión de Gastos', subtitle: 'Registra y controla tus gastos.' },
  clientes: { title: 'Directorio de Clientes', subtitle: 'Administra tu cartera de clientes.' },
  ajustes: { title: 'Ajustes de la cuenta', subtitle: 'Tus datos fiscales (el emisor de tus facturas y el receptor de las que recibes) y las series de numeración.' },
  createInvoice: { title: '', subtitle: '' },
  editInvoice: { title: '', subtitle: '' },
  createReceivedInvoice: { title: '', subtitle: '' },
  editReceivedInvoice: { title: '', subtitle: '' },
  createClient: { title: '', subtitle: '' },
  editClient: { title: '', subtitle: '' },
}

/** Each invoice book: its list page and the pages of its form. */
const INVOICE_PAGES: Record<InvoiceKind, { list: Page; create: Page; edit: Page }> = {
  ISSUED: { list: 'facturasEmitidas', create: 'createInvoice', edit: 'editInvoice' },
  RECEIVED: { list: 'facturasRecibidas', create: 'createReceivedInvoice', edit: 'editReceivedInvoice' },
}

function formKind(page: Page): InvoiceKind | null {
  if (page === 'createInvoice' || page === 'editInvoice') return 'ISSUED'
  if (page === 'createReceivedInvoice' || page === 'editReceivedInvoice') return 'RECEIVED'
  return null
}

/** Shell for ADMIN users (tenants): their invoices (issued and received), clients and expenses. */
export default function TenantApp() {
  const { user } = useAuth()
  const [activePage, setActivePage] = useState<Page>('dashboard')
  const [editingInvoiceId, setEditingInvoiceId] = useState<number | null>(null)
  const [editingClientId, setEditingClientId] = useState<number | null>(null)
  // Where to go back to after saving the fiscal data from the invoice form
  const [afterSettings, setAfterSettings] = useState<Page | null>(null)
  const { title, subtitle } = pageTitles[activePage]

  function showInvoices(kind: InvoiceKind) {
    setEditingInvoiceId(null)
    setActivePage(INVOICE_PAGES[kind].list)
  }

  function createInvoice(kind: InvoiceKind) {
    setEditingInvoiceId(null)
    setActivePage(INVOICE_PAGES[kind].create)
  }

  /** Issued invoices: drafts only. Received invoices can always be edited. */
  function editInvoice(kind: InvoiceKind, invoiceId: number) {
    setEditingInvoiceId(invoiceId)
    setActivePage(INVOICE_PAGES[kind].edit)
  }

  function showClients() {
    setEditingClientId(null)
    setActivePage('clientes')
  }

  function editClient(clientId: number) {
    setEditingClientId(clientId)
    setActivePage('editClient')
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

  const kind = formKind(activePage)
  if (kind && (activePage === INVOICE_PAGES[kind].create || editingInvoiceId !== null)) {
    return (
      <>
        <TopNav items={NAV_ITEMS} activeId={INVOICE_PAGES[kind].list} onNavigate={setActivePage} />
        <InvoiceForm
          key={`${kind}-${editingInvoiceId ?? 'new'}`}
          kind={kind}
          invoiceId={editingInvoiceId ?? undefined}
          onBack={() => showInvoices(kind)}
          onSaved={() => showInvoices(kind)}
          onOpenSettings={configureFiscalData}
        />
      </>
    )
  }

  if (activePage === 'createClient' || (activePage === 'editClient' && editingClientId !== null)) {
    return (
      <>
        <TopNav items={NAV_ITEMS} activeId="clientes" onNavigate={setActivePage} />
        <ClientForm
          key={editingClientId ?? 'new'}
          clientId={editingClientId ?? undefined}
          onBack={showClients}
          onSaved={showClients}
        />
      </>
    )
  }

  const greeting = activePage === 'dashboard' && user ? `Bienvenido de nuevo, ${user.name || user.email}. ` : ''
  const onClients = activePage === 'clientes'
  const onReceived = activePage === 'facturasRecibidas'

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
              if (onClients) {
                setEditingClientId(null)
                setActivePage('createClient')
              } else {
                createInvoice(onReceived ? 'RECEIVED' : 'ISSUED')
              }
            }}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            {onClients ? 'Nuevo Cliente' : onReceived ? 'Registrar Factura Recibida' : 'Nueva Factura'}
          </button>
        </div>
      </div>

      {/* Main content */}
      <main className="flex-1 max-w-screen-xl mx-auto w-full px-6 py-6">
        {activePage === 'dashboard' && <Dashboard onViewInvoices={() => setActivePage('facturasEmitidas')} />}
        {activePage === 'facturasEmitidas' && (
          <Invoices key="ISSUED" kind="ISSUED" onEdit={(id) => editInvoice('ISSUED', id)} />
        )}
        {activePage === 'facturasRecibidas' && (
          <Invoices key="RECEIVED" kind="RECEIVED" onEdit={(id) => editInvoice('RECEIVED', id)} />
        )}
        {activePage === 'clientes' && <Clients onEdit={editClient} />}
        {activePage === 'ajustes' && (
          <div className="space-y-6">
            <FiscalDataSettings onSaved={fiscalDataSaved} />
            <SerialSettings />
          </div>
        )}
        {activePage === 'gastos' && (
          <div className="flex items-center justify-center h-64 text-slate-400">
            <p className="text-lg">Próximamente...</p>
          </div>
        )}
      </main>
    </div>
  )
}
