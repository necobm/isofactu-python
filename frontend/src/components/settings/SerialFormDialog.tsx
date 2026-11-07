import { useEffect, useState, type FormEvent } from 'react'
import { ApiError, type Serial, type SerialInput } from '@/api'
import { Field, FormMessage, PRIMARY_BUTTON_CLASS, SECONDARY_BUTTON_CLASS } from '@/components/form'

const PART_PATTERN = /^[A-Za-z0-9._/-]*$/

interface SerialFormDialogProps {
  /** The serial being edited; omitted when creating a new one. */
  serial?: Serial
  onSubmit: (input: SerialInput) => Promise<void>
  onClose: () => void
}

/** Modal form to create or edit a numbering serial. */
export default function SerialFormDialog({ serial, onSubmit, onClose }: SerialFormDialogProps) {
  const editing = serial !== undefined
  const locked = serial?.locked ?? false
  const [prefix, setPrefix] = useState(serial?.prefix ?? '')
  const [suffix, setSuffix] = useState(serial?.suffix ?? '')
  const [initialNumber, setInitialNumber] = useState(String(serial?.initialNumber ?? 1))
  const [startDate, setStartDate] = useState(serial?.startDate ?? '')
  const [endDate, setEndDate] = useState(serial?.endDate ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose, busy])

  const number = Number(initialNumber)
  const preview = `${prefix}${Number.isInteger(number) && number >= 1 ? number : '…'}${suffix}`

  function validate(): string | null {
    if (!prefix.trim() && !suffix.trim()) return 'Indica al menos un prefijo o un sufijo.'
    if (!PART_PATTERN.test(prefix) || !PART_PATTERN.test(suffix)) {
      return 'Prefijo y sufijo solo admiten letras, números y los separadores . _ / - (sin espacios).'
    }
    if (!Number.isInteger(number) || number < 1) return 'El número inicial debe ser un entero mayor o igual que 1.'
    if (startDate && endDate && endDate < startDate) return 'La fecha de fin no puede ser anterior a la de inicio.'
    return null
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const problem = validate()
    if (problem) {
      setError(problem)
      return
    }
    setBusy(true)
    setError(null)
    try {
      await onSubmit({
        prefix: prefix.trim(),
        suffix: suffix.trim(),
        initialNumber: number,
        startDate: startDate || null,
        endDate: endDate || null,
      })
    } catch (err) {
      setError(describe(err))
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onClose()
      }}
    >
      <form
        onSubmit={handleSubmit}
        role="dialog"
        aria-modal="true"
        aria-labelledby="serial-form-title"
        className="w-full max-w-lg rounded-xl bg-white shadow-xl"
        noValidate
      >
        <div className="px-6 pt-5 pb-4 space-y-4">
          <div>
            <h2 id="serial-form-title" className="text-base font-semibold text-slate-800">
              {editing ? 'Editar serie' : 'Nueva serie'}
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Los números de factura se forman con el prefijo, un número correlativo y el sufijo.
            </p>
          </div>
          {locked && (
            <FormMessage tone="info">
              Esta serie ya tiene facturas emitidas: el prefijo, el sufijo y el número inicial no pueden cambiar. Para
              dejar de usarla, ponle una fecha de fin.
            </FormMessage>
          )}
          {error && <FormMessage tone="error">{error}</FormMessage>}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Field
              id="serial-prefix"
              label="Prefijo"
              type="text"
              autoComplete="off"
              autoFocus={!locked}
              maxLength={100}
              value={prefix}
              onChange={(e) => setPrefix(e.target.value)}
              disabled={busy || locked}
              className="font-mono"
              placeholder="F-2026-"
            />
            <Field
              id="serial-initial"
              label="Número inicial"
              type="number"
              inputMode="numeric"
              min={1}
              step={1}
              value={initialNumber}
              onChange={(e) => setInitialNumber(e.target.value)}
              disabled={busy || locked}
            />
            <Field
              id="serial-suffix"
              label="Sufijo"
              type="text"
              autoComplete="off"
              maxLength={100}
              value={suffix}
              onChange={(e) => setSuffix(e.target.value)}
              disabled={busy || locked}
              className="font-mono"
              placeholder="/A"
            />
          </div>
          <p className="text-xs text-slate-500">
            Primer número: <span className="font-mono font-medium text-slate-700">{preview}</span>
            <span className="text-slate-400"> · Se necesita al menos prefijo o sufijo.</span>
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field
              id="serial-start"
              label="Válida desde"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              disabled={busy}
              hint="Opcional. Fecha de emisión mínima."
            />
            <Field
              id="serial-end"
              label="Válida hasta"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              disabled={busy}
              hint="Opcional. Sin fecha de fin, la serie no caduca."
            />
          </div>
        </div>
        <div className="flex justify-end gap-3 border-t border-slate-100 px-6 py-4">
          <button type="button" onClick={onClose} disabled={busy} className={SECONDARY_BUTTON_CLASS}>
            Cancelar
          </button>
          <button type="submit" disabled={busy} className={PRIMARY_BUTTON_CLASS}>
            {busy ? 'Guardando…' : editing ? 'Guardar' : 'Crear serie'}
          </button>
        </div>
      </form>
    </div>
  )
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return error.message.includes('in use')
      ? 'La serie ya tiene facturas emitidas: su prefijo, sufijo y número inicial no pueden cambiar.'
      : 'Ya existe una serie con el mismo prefijo y sufijo.'
    if (error.status === 422) return `Revisa los datos: ${error.message}`
    return error.message
  }
  return 'No se pudo guardar la serie. Inténtalo de nuevo.'
}
