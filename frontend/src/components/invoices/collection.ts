import type { Invoice } from '@/api'

/** Where an issued invoice stands regarding its payment by the client. */
export type CollectionStatus = 'collected' | 'pending' | 'overdue'

/** `null` for drafts and received invoices, which are not collected. */
export function collectionStatus(invoice: Invoice, today: string): CollectionStatus | null {
  if (invoice.kind !== 'ISSUED' || invoice.state !== 'ISSUED') return null
  if (invoice.collectedOn) return 'collected'
  return invoice.dueDate && invoice.dueDate < today ? 'overdue' : 'pending'
}

export const COLLECTION_LABELS: Record<CollectionStatus, string> = {
  collected: 'Cobrada',
  pending: 'Pendiente',
  overdue: 'Vencida',
}

export const COLLECTION_STYLES: Record<CollectionStatus, string> = {
  collected: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  pending: 'bg-amber-50 text-amber-700 border-amber-200',
  overdue: 'bg-rose-50 text-rose-700 border-rose-200',
}
