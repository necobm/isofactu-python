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

/** Name, identification and address of a party of an invoice. */
export interface Party {
  fullName: string
  document: IdentificationDocument
  address: Address
}

/** A stored client / supplier. */
export interface Subject extends Party {
  id: number
}

/** The tenant's own identity as invoice issuer (`null` until set up). */
export interface FiscalData {
  companyName: string
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
  /** Copy of the account's fiscal data taken when the invoice was (last) saved. */
  issuer: Party
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

// -- accounts ------------------------------------------------------------------------

/** SUPER_ADMIN manages the accounts of the system; ADMIN is a tenant with its own data. */
export type Role = 'SUPER_ADMIN' | 'ADMIN'

/** PAUSED accounts (the default for new ones) cannot log in. */
export type AccountStatus = 'ACTIVE' | 'PAUSED'

export interface User {
  id: number
  email: string
  name: string
  role: Role
  status: AccountStatus
  /** False until the user sets a password through the activation link. */
  hasPassword: boolean
  /** Expiry (ISO datetime) of the outstanding activation link, `null` when there is none. */
  activationExpiresAt: string | null
  createdAt: string
  lastLoginAt: string | null
}

export interface UserCollection {
  items: User[]
  total: number
  limit: number
  offset: number
}

/** What the activation page shows before the password is chosen. */
export interface ActivationInfo {
  email: string
  name: string
  expiresAt: string
}

export interface SystemSettings {
  /** How long activation links stay valid (applies to links issued from now on). */
  activationLinkTtlHours: number
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
  /** The issuer is not sent: the server stamps the account's fiscal data. */
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

export interface FiscalDataInput {
  companyName: string
  document: IdentificationDocument
  /** `province` is optional; the rest is required by the server. */
  address: Address
}

export interface LoginInput {
  email: string
  password: string
}

export interface UserInput {
  email: string
  name?: string
  /** Defaults to ADMIN on the server. */
  role?: Role
}

export interface PasswordChangeInput {
  currentPassword: string
  newPassword: string
}
