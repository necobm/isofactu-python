/**
 * IRPF withholding presets. The retention applies to the whole invoice (a percentage of the
 * subtotal deducted from the total); `null` means no retention.
 */
export const RETENTION_OPTIONS: { label: string; value: number | null }[] = [
  { label: 'Sin retención', value: null },
  { label: '7 % IRPF', value: 7 },
  { label: '15 % IRPF', value: 15 },
]

/**
 * The IRPF presets, plus `current` when it is not one of them (e.g. the 19 % withheld on
 * rents, read from a supplier's invoice), so that the select shows the real value.
 */
export function retentionOptions(current: number | null): { label: string; value: number | null }[] {
  return RETENTION_OPTIONS.some((option) => option.value === current)
    ? RETENTION_OPTIONS
    : [...RETENTION_OPTIONS, { label: `${current} % IRPF`, value: current }]
}
