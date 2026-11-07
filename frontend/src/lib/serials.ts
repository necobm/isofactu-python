import type { Serial } from '@/api'

/** Whether an invoice issued on `isoDate` (YYYY-MM-DD) may take a number from `serial`. */
export function isSerialAvailableOn(serial: Serial, isoDate: string): boolean {
  if (serial.startDate && isoDate < serial.startDate) return false
  if (serial.endDate && isoDate > serial.endDate) return false
  return true
}

/** "F-2026-" + "…" + "/A" → how the serial reads in a list or a select. */
export function describeSerial(serial: Serial): string {
  return `${serial.prefix}‹nº›${serial.suffix}`
}
