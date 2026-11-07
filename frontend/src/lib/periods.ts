/**
 * Reporting periods offered by the dashboard, as ISO date ranges in local time. Invoices
 * cannot be dated in the future, so the current periods simply end today.
 */

export type PeriodId = 'month' | 'quarter' | 'year' | 'last12' | 'lastYear' | 'all'

export const PERIODS: { id: PeriodId; label: string }[] = [
  { id: 'month', label: 'Este mes' },
  { id: 'quarter', label: 'Este trimestre' },
  { id: 'year', label: 'Este año' },
  { id: 'last12', label: 'Últimos 12 meses' },
  { id: 'lastYear', label: 'Año anterior' },
  { id: 'all', label: 'Todo' },
]

/** A local date as YYYY-MM-DD. */
export function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

/** The `[from, to]` range of a period (`all`: no bounds, the server uses the whole history). */
export function periodRange(id: PeriodId, today: Date = new Date()): { from?: string; to?: string } {
  const year = today.getFullYear()
  const month = today.getMonth()
  const to = isoDate(today)
  switch (id) {
    case 'month':
      return { from: isoDate(new Date(year, month, 1)), to }
    case 'quarter':
      return { from: isoDate(new Date(year, month - (month % 3), 1)), to }
    case 'year':
      return { from: isoDate(new Date(year, 0, 1)), to }
    case 'last12':
      return { from: isoDate(new Date(year, month - 11, 1)), to }
    case 'lastYear':
      return { from: isoDate(new Date(year - 1, 0, 1)), to: isoDate(new Date(year - 1, 11, 31)) }
    case 'all':
      return {}
  }
}

const monthName = new Intl.DateTimeFormat('es-ES', { month: 'short' })
const monthAndYear = new Intl.DateTimeFormat('es-ES', { month: 'long', year: 'numeric' })

/** "2026-03" -> "mar" (or "mar 26" when the series spans several years). */
export function monthLabel(month: string, withYear: boolean): string {
  const [year, index] = month.split('-').map(Number)
  const name = monthName.format(new Date(year, index - 1, 1)).replace('.', '')
  return withYear ? `${name} ${String(year).slice(2)}` : name
}

/** "2026-03" -> "marzo de 2026" */
export function longMonthLabel(month: string): string {
  const [year, index] = month.split('-').map(Number)
  return monthAndYear.format(new Date(year, index - 1, 1))
}
