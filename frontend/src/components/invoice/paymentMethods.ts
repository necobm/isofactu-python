import type { PaymentMethod } from '@/api'

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  TRANSFER: 'Transferencia bancaria',
  CASH: 'Efectivo',
  CARD: 'Tarjeta',
  DIRECT_DEBIT: 'Domiciliación bancaria',
}

export const PAYMENT_METHODS = Object.keys(PAYMENT_METHOD_LABELS) as PaymentMethod[]
