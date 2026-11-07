import type { ReactNode } from 'react'

interface StatCardProps {
  title: string
  /** The figure; `null` while it is loading. */
  value: string | null
  subtitle?: ReactNode
  icon: ReactNode
  iconBg: string
  iconColor: string
  /** Extra content under the figure (details, a link...). */
  footer?: ReactNode
}

export default function StatCard({ title, value, subtitle, icon, iconBg, iconColor, footer }: StatCardProps) {
  return (
    <div className="bg-white rounded-xl p-5 border border-slate-100 shadow-sm flex flex-col" aria-busy={value === null}>
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-slate-500 font-medium">{title}</p>
          {value === null ? (
            <div className="h-8 w-36 mt-1 rounded-md bg-slate-100 animate-pulse" />
          ) : (
            <p className="text-2xl font-bold text-slate-800 mt-1 tracking-tight">{value}</p>
          )}
          {subtitle && <div className="text-xs text-slate-400 mt-1">{subtitle}</div>}
        </div>
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${iconBg}`}>
          <span className={iconColor}>{icon}</span>
        </div>
      </div>
      {footer && <div className="mt-3 pt-3 border-t border-slate-50 text-xs">{footer}</div>}
    </div>
  )
}
