import { useState } from 'react'
import TopNav from '@/components/TopNav'
import Dashboard from '@/pages/Dashboard'
import Invoices from '@/pages/Invoices'
import InvoiceForm from '@/pages/InvoiceForm'
import type { Page } from '@/types'

const pageTitles: Record<Page, { title: string; subtitle: string }> = {
  dashboard: { title: 'Panel de Control', subtitle: 'Bienvenido de nuevo, Admin. Aquí tienes el resumen de tu actividad financiera.' },
  facturas: { title: 'Facturas', subtitle: 'Gestiona y consulta tus borradores y facturas emitidas.' },
  gastos: { title: 'Gestión de Gastos', subtitle: 'Registra y controla tus gastos.' },
  clientes: { title: 'Directorio de Clientes', subtitle: 'Administra tu cartera de clientes.' },
  createInvoice: { title: '', subtitle: '' },
  editInvoice: { title: '', subtitle: '' },
}

export default function App() {
  const [activePage, setActivePage] = useState<Page>('dashboard')
  const [editingInvoiceId, setEditingInvoiceId] = useState<number | null>(null)
  const { title, subtitle } = pageTitles[activePage]

  function showInvoices() {
    setEditingInvoiceId(null)
    setActivePage('facturas')
  }

  function editDraft(invoiceId: number) {
    setEditingInvoiceId(invoiceId)
    setActivePage('editInvoice')
  }

  if (activePage === 'createInvoice' || (activePage === 'editInvoice' && editingInvoiceId !== null)) {
    return (
      <>
        <TopNav activePage="facturas" onNavigate={setActivePage} />
        <InvoiceForm
          key={editingInvoiceId ?? 'new'}
          invoiceId={editingInvoiceId ?? undefined}
          onBack={showInvoices}
          onSaved={showInvoices}
        />
      </>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <TopNav activePage={activePage} onNavigate={setActivePage} />

      {/* Page header */}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-screen-xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-800">{title}</h1>
            <p className="text-sm text-slate-400 mt-0.5">{subtitle}</p>
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
        {(activePage === 'gastos' || activePage === 'clientes') && (
          <div className="flex items-center justify-center h-64 text-slate-400">
            <p className="text-lg">Próximamente...</p>
          </div>
        )}
      </main>
    </div>
  )
}
