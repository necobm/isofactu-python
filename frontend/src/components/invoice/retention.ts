/**
 * IRPF withholding presets. The retention applies to the whole invoice (a percentage of the
 * subtotal deducted from the total); `null` means no retention.
 */
export const RETENTION_OPTIONS: { label: string; value: number | null }[] = [
  { label: 'Sin retención', value: null },
  { label: '7 % IRPF', value: 7 },
  { label: '15 % IRPF', value: 15 },
]
