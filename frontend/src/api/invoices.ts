import { request } from './client'
import type {
  HealthStatus,
  Invoice,
  InvoiceCollection,
  InvoiceInput,
  InvoiceState,
  Subject,
  SubjectInput,
} from './types'

export type PageParams = {
  limit?: number
  offset?: number
}

export type InvoiceListParams = PageParams & {
  /** Restrict the collection to invoices in this state. */
  state?: InvoiceState
}

export type SubjectListParams = PageParams & {
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

  listSubjects: (params: SubjectListParams = {}, signal?: AbortSignal) =>
    request<Subject[]>('/api/subject', { query: params, signal }),

  createSubject: (input: SubjectInput) =>
    request<Subject>('/api/subject', { method: 'POST', body: input }),
}
