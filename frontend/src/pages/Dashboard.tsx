import StatCard from '@/components/dashboard/StatCard'
import TaxTracker from '@/components/dashboard/TaxTracker'
import RevenueChart from '@/components/dashboard/RevenueChart'
import InvoiceStatusChart from '@/components/dashboard/InvoiceStatusChart'
import RecentInvoices from '@/components/dashboard/RecentInvoices'

const EuroIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
)

const ReceiptIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2z" />
  </svg>
)

const ClockIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
)

interface DashboardProps {
  onViewInvoices: () => void
}

export default function Dashboard({ onViewInvoices }: DashboardProps) {
  return (
    <div className="space-y-6 max-w-screen-xl mx-auto">
      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        <StatCard
          title="Ingresos Mensuales"
          value="€12.450,00"
          subtitle="Junio 2026"
          trend={8.2}
          icon={<EuroIcon />}
          iconBg="bg-indigo-50"
          iconColor="text-indigo-600"
        />
        <StatCard
          title="Gastos Mensuales"
          value="€4.200,50"
          subtitle="Junio 2026"
          trend={-3.1}
          icon={<ReceiptIcon />}
          iconBg="bg-rose-50"
          iconColor="text-rose-500"
        />
        <StatCard
          title="Facturas Pendientes"
          value="7"
          subtitle="Por cobrar"
          trend={-2}
          trendLabel="vs mes anterior"
          icon={<ClockIcon />}
          iconBg="bg-amber-50"
          iconColor="text-amber-500"
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <RevenueChart />
        </div>
        <div className="flex flex-col gap-4">
          <TaxTracker />
          <InvoiceStatusChart />
        </div>
      </div>

      {/* Recent invoices */}
      <RecentInvoices onViewAll={onViewInvoices} />
    </div>
  )
}
