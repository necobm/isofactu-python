/**
 * Client-side mirror of the backend's fixed-point arithmetic (`app/invoicing/money.py`), so the
 * totals previewed while editing match what the server will store: amounts are rounded per line
 * to two decimals, half-up.
 */

/** Round half-up to `places` decimals (avoiding binary float artefacts like 1.005 -> 1.00). */
export function roundHalfUp(value: number, places = 2): number {
  const factor = 10 ** places
  const scaled = Number((Math.abs(value) * factor).toPrecision(15))
  return (Math.sign(value) || 1) * (Math.floor(scaled + 0.5) / factor)
}

export interface LineAmounts {
  subtotal: number
  taxAmount: number
  total: number
}

export interface InvoiceAmounts extends LineAmounts {
  retentionAmount: number
}

/** Amounts of a line, computed exactly like `InvoiceLine` on the server. */
export function lineAmounts(quantity: number, unitPrice: number, taxRate: number): LineAmounts {
  const subtotal = roundHalfUp(quantity * unitPrice)
  const taxAmount = roundHalfUp(subtotal * roundHalfUp(taxRate / 100, 4))
  return { subtotal, taxAmount, total: roundHalfUp(subtotal + taxAmount) }
}

/**
 * Invoice totals as the server computes them: per-line amounts summed up, then the IRPF
 * retention (a percentage of the whole subtotal) deducted from the total.
 */
export function invoiceAmounts(lines: LineAmounts[], retentionRate: number): InvoiceAmounts {
  let subtotal = 0
  let taxAmount = 0
  let linesTotal = 0
  for (const line of lines) {
    subtotal = roundHalfUp(subtotal + line.subtotal)
    taxAmount = roundHalfUp(taxAmount + line.taxAmount)
    linesTotal = roundHalfUp(linesTotal + line.total)
  }
  const retentionAmount = roundHalfUp(subtotal * roundHalfUp(retentionRate / 100, 4))
  return { subtotal, taxAmount, retentionAmount, total: roundHalfUp(linesTotal - retentionAmount) }
}
