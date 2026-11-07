import type { InputHTMLAttributes, ReactNode } from 'react'

export const INPUT_CLASS =
  'w-full text-sm text-slate-700 border border-slate-200 rounded-lg px-3 py-2 placeholder-slate-300 ' +
  'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:bg-slate-50 disabled:text-slate-400'

export const PRIMARY_BUTTON_CLASS =
  'text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 px-4 py-2 rounded-lg transition-colors ' +
  'disabled:opacity-50 disabled:cursor-not-allowed'

export const SECONDARY_BUTTON_CLASS =
  'text-sm font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 px-4 py-2 rounded-lg ' +
  'transition-colors disabled:opacity-50 disabled:cursor-not-allowed'

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  id: string
  label: string
  hint?: ReactNode
}

/** Labelled text input with the shared styling. */
export function Field({ id, label, hint, className, ...input }: FieldProps) {
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-slate-600 mb-1.5">
        {label}
      </label>
      <input id={id} className={`${INPUT_CLASS} ${className ?? ''}`} {...input} />
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  )
}

/** Inline error / success message of a form. */
export function FormMessage({ tone, children }: { tone: 'error' | 'success' | 'info'; children: ReactNode }) {
  const styles = {
    error: 'border-rose-200 bg-rose-50 text-rose-700',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    info: 'border-amber-200 bg-amber-50 text-amber-700',
  }
  return (
    <p role={tone === 'error' ? 'alert' : 'status'} className={`rounded-lg border px-4 py-3 text-sm ${styles[tone]}`}>
      {children}
    </p>
  )
}
