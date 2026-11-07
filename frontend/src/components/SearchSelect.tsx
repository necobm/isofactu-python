import Select, { type StylesConfig } from 'react-select'
import CreatableSelect from 'react-select/creatable'

export interface SelectOption {
  value: string
  label: string
}

interface SearchSelectProps {
  id: string
  label: string
  options: SelectOption[]
  /** The selected `value`, or `''` / `null` for none. */
  value: string | null
  onChange: (value: string | null) => void
  placeholder?: string
  hint?: string
  disabled?: boolean
  loading?: boolean
  required?: boolean
  /** Let the user type a value that is not among the options. */
  creatable?: boolean
  /** Shown when the user's search matches nothing. */
  noOptionsMessage?: string
}

// Matches the look of `INPUT_CLASS` (components/form.tsx)
const STYLES: StylesConfig<SelectOption, false> = {
  control: (base, state) => ({
    ...base,
    minHeight: 38,
    borderRadius: '0.5rem',
    borderColor: state.isFocused ? 'transparent' : '#e2e8f0',
    boxShadow: state.isFocused ? '0 0 0 2px #6366f1' : 'none',
    backgroundColor: state.isDisabled ? '#f8fafc' : '#ffffff',
    fontSize: '0.875rem',
    '&:hover': { borderColor: state.isFocused ? 'transparent' : '#cbd5e1' },
  }),
  valueContainer: (base) => ({ ...base, padding: '0 0.75rem' }),
  placeholder: (base) => ({ ...base, color: '#cbd5e1' }),
  singleValue: (base, state) => ({ ...base, color: state.isDisabled ? '#94a3b8' : '#334155' }),
  input: (base) => ({ ...base, color: '#334155', margin: 0 }),
  menu: (base) => ({ ...base, borderRadius: '0.5rem', fontSize: '0.875rem', zIndex: 30 }),
  option: (base, state) => ({
    ...base,
    backgroundColor: state.isSelected ? '#4f46e5' : state.isFocused ? '#eef2ff' : 'transparent',
    color: state.isSelected ? '#ffffff' : '#334155',
  }),
  indicatorSeparator: () => ({ display: 'none' }),
  dropdownIndicator: (base) => ({ ...base, color: '#94a3b8', padding: '0 0.5rem' }),
  clearIndicator: (base) => ({ ...base, color: '#94a3b8', padding: '0 0.25rem' }),
}

/**
 * Searchable single-value select (react-select) with the shared field styling. With
 * `creatable`, values outside the list can be typed in; the option list then acts as
 * suggestions.
 */
export default function SearchSelect({
  id,
  label,
  options,
  value,
  onChange,
  placeholder = 'Buscar…',
  hint,
  disabled = false,
  loading = false,
  required = false,
  creatable = false,
  noOptionsMessage = 'Sin resultados',
}: SearchSelectProps) {
  const selected = value ? (options.find((o) => o.value === value) ?? (creatable ? { value, label: value } : null)) : null
  const shared = {
    inputId: id,
    options,
    value: selected,
    onChange: (option: SelectOption | null) => onChange(option?.value ?? null),
    placeholder,
    isDisabled: disabled,
    isLoading: loading,
    isClearable: !required,
    isSearchable: true,
    styles: STYLES,
    loadingMessage: () => 'Cargando…',
    noOptionsMessage: () => noOptionsMessage,
  }
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-slate-600 mb-1.5">
        {label}
      </label>
      {creatable ? (
        <CreatableSelect
          {...shared}
          formatCreateLabel={(input) => `Usar «${input}»`}
          onCreateOption={(input) => onChange(input.trim())}
        />
      ) : (
        <Select {...shared} />
      )}
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  )
}
