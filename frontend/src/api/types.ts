/**
 * API contract exposed by the FastAPI backend (see /api/docs).
 * Monetary amounts are JSON numbers with at most two decimals (120.98).
 */

export type DocumentType = 'CIF' | 'NIF' | 'OTHER'

/** Lifecycle state of an invoice: being prepared (DRAFT) or finalised and emitted (ISSUED). */
export type InvoiceState = 'DRAFT' | 'ISSUED'

export type PaymentMethod = 'TRANSFER' | 'CASH' | 'CARD' | 'DIRECT_DEBIT'

export interface InvoiceNumber {
  serial: string | null
  number: string
  /** `serial-number`, or just `number` when there is no serial. */
  formatted: string
}

export interface IdentificationDocument {
  type: DocumentType
  number: string
}

export interface Address {
  street: string
  zipCode: string
  city: string
  province: string
  countryIsoCode: string
}

export interface Subject {
  id: number
  fullName: string
  document: IdentificationDocument
  address: Address
}

export interface InvoiceLine {
  id: number
  description: string
  quantity: number
  unitPrice: number
  taxRate: number
  subtotal: number
  taxAmount: number
  total: number
}

export interface Invoice {
  id: number
  issueDate: string // ISO date (YYYY-MM-DD)
  /** `null` while the invoice is a draft. */
  invoiceNumber: InvoiceNumber | null
  state: InvoiceState
  issuer: Subject
  recipient: Subject
  notes: string
  dueDate: string | null // ISO date (YYYY-MM-DD)
  paymentMethod: PaymentMethod
  /** IRPF withholding (%) on the whole invoice; `retentionAmount` is deducted from `total`. */
  retentionRate: number
  lines: InvoiceLine[]
  subtotal: number
  taxAmount: number
  retentionAmount: number
  total: number
}

export interface InvoiceCollection {
  items: Invoice[]
  total: number
  limit: number
  offset: number
}

export interface HealthStatus {
  status: string
  app: string
  version: string
}

// -- write models --------------------------------------------------------------------

export interface InvoiceLineInput {
  description: string
  quantity: number
  unitPrice: number
  taxRate: number
}

export interface InvoiceInput {
  issueDate?: string
  /** Defaults to DRAFT on the server. */
  state?: InvoiceState
  /**
   * Only for ISSUED invoices (drafts are numberless). Omit `number` to have the next
   * sequential number of the serial assigned by the server.
   */
  invoiceNumber?: { serial?: string | null; number?: string | null }
  issuerId: number
  recipientId: number
  notes?: string
  dueDate?: string | null
  paymentMethod?: PaymentMethod
  /** IRPF withholding (%) on the whole invoice. Defaults to 0. */
  retentionRate?: number
  lines: InvoiceLineInput[]
}

export interface SubjectInput {
  fullName: string
  document?: Partial<IdentificationDocument>
  address?: Partial<Address>
}
