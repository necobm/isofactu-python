import type { ReactNode } from 'react'

interface AuthLayoutProps {
  title: string
  subtitle?: ReactNode
  children: ReactNode
}

/** Centered card used by the pages shown outside the app shell (login, activation). */
export default function AuthLayout({ title, subtitle, children }: AuthLayoutProps) {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center px-4 py-10">
      <div className="flex items-center gap-2.5 mb-8">
        <div className="w-9 h-9 bg-indigo-600 rounded-lg flex items-center justify-center">
          <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <span className="font-bold text-slate-800 text-xl tracking-tight">Isofactu</span>
      </div>
      <div className="w-full max-w-md bg-white rounded-xl border border-slate-200 shadow-sm px-8 py-8">
        <h1 className="text-lg font-bold text-slate-800">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </div>
    </div>
  )
}
