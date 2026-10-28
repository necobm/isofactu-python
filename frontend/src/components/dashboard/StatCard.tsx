import type { ReactNode } from 'react'

interface StatCardProps {
  title: string
  value: string
  subtitle?: string
  trend?: number
  trendLabel?: string
  icon: ReactNode
  iconBg: string
  iconColor: string
}

export default function StatCard({ title, value, subtitle, trend, trendLabel, icon, iconBg, iconColor }: StatCardProps) {
  const isPositive = (trend ?? 0) > 0

  return (
    <div className="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-slate-500 font-medium">{title}</p>
          <p className="text-2xl font-bold text-slate-800 mt-1 tracking-tight">{value}</p>
          {subtitle && <p className="text-xs text-slate-400 mt-1">{subtitle}</p>}
        </div>
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${iconBg}`}>
          <span className={iconColor}>{icon}</span>
        </div>
      </div>
      {trend !== undefined && (
        <div className="flex items-center gap-1 mt-3">
          <span className={`text-xs font-medium ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
            {isPositive ? '▲' : '▼'} {Math.abs(trend)}%
          </span>
          <span className="text-xs text-slate-400">{trendLabel ?? 'vs mes anterior'}</span>
        </div>
      )}
    </div>
  )
}
