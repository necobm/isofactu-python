import { useEffect, useId, useState } from 'react'
import { api, type Subject } from '@/api'
import { useApi } from '@/lib/useApi'

const MAX_RESULTS = 8
const DEBOUNCE_MS = 250

interface ClientPickerProps {
  value: Subject | null
  onChange: (client: Subject | null) => void
}

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

/** Searches the subjects stored in the database (by name or NIF/CIF) and picks one as client. */
export default function ClientPicker({ value, onChange }: ClientPickerProps) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const debouncedQuery = useDebounced(query.trim(), DEBOUNCE_MS)
  const listId = useId()

  const results = useApi(
    (signal) => api.listSubjects({ q: debouncedQuery || undefined, limit: MAX_RESULTS }, signal),
    [debouncedQuery],
  )
  const matches = results.data ?? []
  const searching = results.status === 'loading' || debouncedQuery !== query.trim()

  function select(subject: Subject) {
    onChange(subject)
    setQuery('')
    setOpen(false)
  }

  if (value) {
    return (
      <div className="flex items-start justify-between gap-4 rounded-lg border border-indigo-100 bg-indigo-50/40 px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-800">{value.fullName}</p>
          <p className="text-xs text-slate-500">
            {value.document.type} {value.document.number}
          </p>
          {(value.address.street || value.address.city) && (
            <p className="mt-1 text-xs text-slate-400">
              {[value.address.street, [value.address.zipCode, value.address.city].filter(Boolean).join(' ')]
                .filter(Boolean)
                .join(' · ')}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => onChange(null)}
          className="shrink-0 text-xs font-medium text-indigo-600 hover:text-indigo-700"
        >
          Cambiar
        </button>
      </div>
    )
  }

  return (
    <div className="relative">
      <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11A6 6 0 105 11a6 6 0 0012 0z" />
      </svg>
      <input
        type="text"
        role="combobox"
        aria-label="Buscar cliente"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setOpen(false)
          if (e.key === 'Enter' && open && matches.length > 0) {
            e.preventDefault()
            select(matches[0])
          }
        }}
        placeholder="Buscar cliente por nombre o CIF / NIF..."
        autoComplete="off"
        className="w-full pl-9 pr-4 py-2 text-sm text-slate-700 border border-slate-200 rounded-lg placeholder-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
      />

      {open && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 w-full max-h-72 overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-lg py-1 text-sm"
        >
          {results.status === 'error' && (
            <li className="px-4 py-3 text-xs text-rose-500">No se pudo buscar: {results.error.message}</li>
          )}
          {results.status !== 'error' && matches.length === 0 && (
            <li className="px-4 py-3 text-xs text-slate-400">
              {searching ? 'Buscando…' : 'Ningún cliente coincide con la búsqueda.'}
            </li>
          )}
          {matches.map((subject) => (
            <li
              key={subject.id}
              role="option"
              aria-selected={false}
              // mousedown (not click) so the selection happens before the input blurs
              onMouseDown={(e) => {
                e.preventDefault()
                select(subject)
              }}
              className="flex cursor-pointer items-center justify-between gap-4 px-4 py-2 hover:bg-indigo-50"
            >
              <span className="truncate font-medium text-slate-700">{subject.fullName}</span>
              <span className="shrink-0 text-xs text-slate-400">
                {subject.document.type} {subject.document.number}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
