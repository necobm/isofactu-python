import { request } from './client'
import type {
  Client,
  ClientCollection,
  ClientInput,
  FiscalData,
  FiscalDataInput,
  HealthStatus,
  Invoice,
  InvoiceCollection,
  InvoiceInput,
  InvoiceState,
  ReceivedInvoiceDraft,
  ReceivedInvoiceInput,
  Serial,
  SerialInput,
} from './types'

export type PageParams = {
  limit?: number
  offset?: number
}

export type InvoiceListParams = PageParams & {
  /** Restrict the collection to invoices in this state. */
  state?: InvoiceState
}

export type ClientListParams = PageParams & {
  /** Case-insensitive match on the name or the document number. */
  q?: string
}

export const api = {
  health: (signal?: AbortSignal) => request<HealthStatus>('/api/health', { signal }),

  listInvoices: (params: InvoiceListParams = {}, signal?: AbortSignal) =>
    request<InvoiceCollection>('/api/invoice', { query: params, signal }),

  getInvoice: (id: number, signal?: AbortSignal) =>
    request<Invoice>(`/api/invoice/${id}`, { signal }),

  createInvoice: (input: InvoiceInput) =>
    request<Invoice>('/api/invoice', { method: 'POST', body: input }),

  /** Replaces a draft invoice; issues it when `state` is ISSUED. */
  updateInvoice: (id: number, input: InvoiceInput) =>
    request<Invoice>(`/api/invoice/${id}`, { method: 'PUT', body: input }),

  /** Invoices received from suppliers (expenses). */
  listReceivedInvoices: (params: PageParams = {}, signal?: AbortSignal) =>
    request<InvoiceCollection>('/api/received-invoice', { query: params, signal }),

  getReceivedInvoice: (id: number, signal?: AbortSignal) =>
    request<Invoice>(`/api/received-invoice/${id}`, { signal }),

  createReceivedInvoice: (input: ReceivedInvoiceInput) =>
    request<Invoice>('/api/received-invoice', { method: 'POST', body: input }),

  /**
   * Reads a supplier's invoice from a PDF to pre-fill the form (nothing is stored).
   * `503` when PDF import is not configured, `413` too large, `422` not a PDF / not an
   * invoice, `502` unreadable.
   */
  extractReceivedInvoice: (file: File, signal?: AbortSignal) => {
    const body = new FormData()
    body.append('file', file)
    return request<ReceivedInvoiceDraft>('/api/received-invoice/extract', { method: 'POST', body, signal })
  },

  /** Replaces a received invoice (they can always be edited). */
  updateReceivedInvoice: (id: number, input: ReceivedInvoiceInput) =>
    request<Invoice>(`/api/received-invoice/${id}`, { method: 'PUT', body: input }),

  /** The account's fiscal data (issuer of its invoices), `null` until set up. */
  getFiscalData: (signal?: AbortSignal) => request<FiscalData | null>('/api/fiscal-data', { signal }),

  saveFiscalData: (input: FiscalDataInput) =>
    request<FiscalData>('/api/fiscal-data', { method: 'PUT', body: input }),

  /** The numbering series of the account, with their usage and next number. */
  listSerials: (signal?: AbortSignal) => request<Serial[]>('/api/serial', { signal }),

  createSerial: (input: SerialInput) => request<Serial>('/api/serial', { method: 'POST', body: input }),

  updateSerial: (id: number, input: SerialInput) =>
    request<Serial>(`/api/serial/${id}`, { method: 'PUT', body: input }),

  /** `409` when an issued invoice uses the serial. */
  deleteSerial: (id: number) => request<void>(`/api/serial/${id}`, { method: 'DELETE' }),

  listClients: (params: ClientListParams = {}, signal?: AbortSignal) =>
    request<ClientCollection>('/api/client', { query: params, signal }),

  getClient: (id: number, signal?: AbortSignal) => request<Client>(`/api/client/${id}`, { signal }),

  createClient: (input: ClientInput) => request<Client>('/api/client', { method: 'POST', body: input }),

  updateClient: (id: number, input: ClientInput) =>
    request<Client>(`/api/client/${id}`, { method: 'PUT', body: input }),

  /** Invoices created with the client keep their own copy of its data. */
  deleteClient: (id: number) => request<void>(`/api/client/${id}`, { method: 'DELETE' }),
}
