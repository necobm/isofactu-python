/**
 * API contract exposed by the FastAPI backend (see /api/docs).
 * Monetary amounts are JSON numbers with at most two decimals (120.98).
 */

export type DocumentType = 'CIF' | 'NIF' | 'OTHER'

/**
 * Lifecycle state of an issued invoice: being prepared (DRAFT) or emitted with a number
 * (ISSUED). Received invoices have no lifecycle: they are always ISSUED (by their supplier)
 * and can always be edited.
 */
export type InvoiceState = 'DRAFT' | 'ISSUED'

/**
 * Which book an invoice belongs to: ISSUED (income, sent to a client) or RECEIVED
 * (expense, from a supplier).
 */
export type InvoiceKind = 'ISSUED' | 'RECEIVED'

export type PaymentMethod = 'TRANSFER' | 'CASH' | 'CARD' | 'DIRECT_DEBIT'

export interface InvoiceNumber {
  /** Issued invoices: copied from the serial when issued. Received: the supplier's series. */
  prefix: string
  number: string
  suffix: string
  /** `prefix + number + suffix`. */
  formatted: string
}

/** A numbering series: `prefix` + sequential number + `suffix`. */
export interface Serial {
  id: number
  prefix: string
  suffix: string
  initialNumber: number
  /** First issue date allowed (ISO date), `null` = no limit. */
  startDate: string | null
  /** Last issue date allowed (ISO date), `null` = no limit. */
  endDate: string | null
  /** Issued invoices numbered with this serial. */
  issuedCount: number
  nextNumber: number
  nextNumberFormatted: string
  /** Prefix, suffix and initial number are frozen once the serial is in use. */
  locked: boolean
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

/**
 * The recipient as stored on an invoice: the invoice's own copy of a client (issued
 * invoices) or of the account's fiscal data (received invoices).
 */
export interface Subject extends Party {
  id: number
}

/** An entry of the tenant's client directory. */
export interface Client extends Party {
  id: number
}

export interface ClientCollection {
  items: Client[]
  total: number
  limit: number
  offset: number
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
  kind: InvoiceKind
  issueDate: string // ISO date (YYYY-MM-DD)
  /**
   * `null` while an issued invoice is a draft. Received invoices carry the supplier's
   * number, as entered.
   */
  invoiceNumber: InvoiceNumber | null
  /** The serial the number was (or, for a draft, will be) taken from. Always `null` on received invoices. */
  serialId: number | null
  state: InvoiceState
  /**
   * Issued: copy of the account's fiscal data taken when the invoice was (last) saved.
   * Received: the supplier, as entered.
   */
  issuer: Party
  /** Issued: copy of the client. Received: copy of the account's fiscal data. */
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
   * The serial the number is taken from. Required to issue (the serial must be available
   * on the issue date); a draft may carry it to remember the choice.
   */
  serialId?: number | null
  /** The issuer is not sent: the server stamps the account's fiscal data. */
  /**
   * The client whose data is copied as recipient. Required when creating; on a draft
   * update it replaces the recipient, and omitting it keeps the current one.
   */
  clientId?: number
  notes?: string
  dueDate?: string | null
  paymentMethod?: PaymentMethod
  /** IRPF withholding (%) on the whole invoice. Defaults to 0. */
  retentionRate?: number
  lines: InvoiceLineInput[]
}

/** A client or supplier as sent to the server (every field required and validated). */
export interface PartyInput {
  fullName: string
  document: IdentificationDocument
  address: Address
}

export type ClientInput = PartyInput

/** The number printed on a supplier's invoice: whole, as printed (series included). */
export interface ReceivedInvoiceNumberInput {
  number: string
}

/**
 * What could be read from the PDF of a received invoice, to pre-fill the form. Nothing is
 * stored; whatever could not be read is empty / `null`.
 */
export interface ReceivedInvoiceDraft {
  /** The supplier. */
  issuer: Party
  invoiceNumber: ReceivedInvoiceNumberInput | null
  issueDate: string | null
  dueDate: string | null
  paymentMethod: PaymentMethod | null
  retentionRate: number
  lines: InvoiceLineInput[]
  /** The total printed on the invoice, to check the lines against. */
  printedTotal: number | null
  /** Who the invoice is addressed to. */
  customerName: string | null
  /** Whether it is addressed to the account (NIF / CIF of the fiscal data); `null` = unknown. */
  addressedToAccount: boolean | null
}

/** A received invoice has no state: it is stored as issued (by its supplier) and can always be edited. */
export interface ReceivedInvoiceInput {
  issueDate?: string
  /** The supplier. The recipient is not sent: the server stamps the account's fiscal data. */
  issuer: PartyInput
  invoiceNumber: ReceivedInvoiceNumberInput
  notes?: string
  dueDate?: string | null
  paymentMethod?: PaymentMethod
  /** IRPF withholding (%) on the whole invoice. Defaults to 0. */
  retentionRate?: number
  lines: InvoiceLineInput[]
}

export interface SerialInput {
  prefix: string
  suffix: string
  /** Defaults to 1 on the server. */
  initialNumber?: number
  startDate?: string | null
  endDate?: string | null
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
