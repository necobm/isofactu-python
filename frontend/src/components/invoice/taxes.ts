/** VAT presets selectable per invoice line (Spanish rates), as percentages. */

export const VAT_RATE_OPTIONS: { label: string; value: number }[] = [
  { label: '21% IVA', value: 21 },
  { label: '10% IVA', value: 10 },
  { label: '4% IVA', value: 4 },
  { label: 'Exento', value: 0 },
]

/** Label of a VAT rate, for rates that do not match a preset too ("IVA 5 %"). */
export function vatLabel(rate: number): string {
  return VAT_RATE_OPTIONS.find((option) => option.value === rate)?.label ?? `IVA ${rate} %`
}

/**
 * The VAT presets, plus `current` when it is not one of them (e.g. a rate read from a
 * supplier's invoice, such as an IGIC rate), so that the select shows the real value.
 */
export function vatRateOptions(current: number): { label: string; value: number }[] {
  return VAT_RATE_OPTIONS.some((option) => option.value === current)
    ? VAT_RATE_OPTIONS
    : [...VAT_RATE_OPTIONS, { label: vatLabel(current), value: current }]
}

export interface LineDraft {
  id: number
  description: string
  quantity: string | number
  unitPrice: string | number
  /** VAT percentage applied to the line. */
  taxRate: number
}
