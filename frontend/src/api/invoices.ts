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
