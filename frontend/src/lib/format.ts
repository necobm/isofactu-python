const currency = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' })
const number = new Intl.NumberFormat('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const shortDate = new Intl.DateTimeFormat('es-ES', { day: '2-digit', month: 'short', year: 'numeric' })
const dateTime = new Intl.DateTimeFormat('es-ES', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/** 1234.5 -> "1234,50 €" */
export function formatCurrency(value: number): string {
  return currency.format(value)
}

/** 1234.5 -> "1234,50" */
export function formatAmount(value: number): string {
  return number.format(value)
}

/** "2026-06-08" -> "08 jun 2026" */
export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  return shortDate.format(new Date(year, month - 1, day))
}

/** 21 -> "21 %", 10.5 -> "10,5 %" */
export function formatRate(value: number): string {
  return `${value.toLocaleString('es-ES', { maximumFractionDigits: 2 })} %`
}

/** "2026-06-08T14:30:00Z" -> "08 jun 2026, 16:30" (local time) */
export function formatDateTime(isoDateTime: string): string {
  return dateTime.format(new Date(isoDateTime))
}
