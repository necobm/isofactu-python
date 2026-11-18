import type { Invoice } from '@/api'

/** Whether an invoice can be deleted: drafts and received invoices, never issued ones. */
export function isDeletable(invoice: Invoice): boolean {
  return invoice.kind === 'RECEIVED' || invoice.state === 'DRAFT'
}
