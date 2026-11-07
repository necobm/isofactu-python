import type { DocumentType } from '@/api'
import { Field, INPUT_CLASS } from '@/components/form'
import SearchSelect from '@/components/SearchSelect'
import { DOCUMENT_TYPES, type PartyFormState, type PartyGeo } from '@/lib/party'

interface PartyFieldsProps {
  /** Prefix of the element ids (`client` → `client-name`, `client-zip`...). */
  idPrefix: string
  form: PartyFormState
  /** Receives the fields that changed. */
  onChange: (patch: Partial<PartyFormState>) => void
  disabled?: boolean
}

/** Name and NIF / CIF of a client or supplier. */
export function PartyIdentityFields({
  idPrefix,
  form,
  onChange,
  disabled,
  autoFocus,
}: PartyFieldsProps & { autoFocus?: boolean }) {
  return (
    <>
      <Field
        id={`${idPrefix}-name`}
        label="Nombre o razón social"
        type="text"
        autoComplete="organization"
        autoFocus={autoFocus}
        maxLength={255}
        required
        value={form.fullName}
        onChange={(e) => onChange({ fullName: e.target.value })}
        disabled={disabled}
      />
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <label htmlFor={`${idPrefix}-document-type`} className="block text-xs font-medium text-slate-600 mb-1.5">
            Tipo de identificación
          </label>
          <select
            id={`${idPrefix}-document-type`}
            value={form.documentType}
            onChange={(e) => onChange({ documentType: e.target.value as DocumentType })}
            disabled={disabled}
            className={`${INPUT_CLASS} bg-white`}
          >
            {DOCUMENT_TYPES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="sm:col-span-2">
          <Field
            id={`${idPrefix}-document-number`}
            label="NIF / CIF"
            type="text"
            autoComplete="off"
            maxLength={100}
            value={form.documentNumber}
            onChange={(e) => onChange({ documentNumber: e.target.value })}
            disabled={disabled}
            className="font-mono uppercase"
            hint={
              form.documentType === 'NIF'
                ? 'DNI (8 dígitos y letra) o NIE (X/Y/Z, 7 dígitos y letra).'
                : form.documentType === 'CIF'
                  ? 'Letra, 7 dígitos y carácter de control (p. ej. B12345674).'
                  : 'Identificador fiscal extranjero u otro documento.'
            }
          />
        </div>
      </div>
    </>
  )
}

/**
 * Postal address of a client or supplier: street, postal code, country, province (by
 * country) and city (by province, as suggestions).
 */
export function PartyAddressFields({ idPrefix, form, onChange, disabled, geo }: PartyFieldsProps & { geo: PartyGeo }) {
  const { countries, provinces, provinceOptions, freeTextProvince, cities, cityOptions } = geo
  return (
    <>
      <Field
        id={`${idPrefix}-street`}
        label="Dirección"
        type="text"
        autoComplete="street-address"
        maxLength={255}
        required
        value={form.street}
        onChange={(e) => onChange({ street: e.target.value })}
        disabled={disabled}
      />
      <div className="grid grid-cols-3 gap-4">
        <Field
          id={`${idPrefix}-zip`}
          label="Código postal"
          type="text"
          autoComplete="postal-code"
          maxLength={50}
          required
          value={form.zipCode}
          onChange={(e) => onChange({ zipCode: e.target.value })}
          disabled={disabled}
        />
        <div className="col-span-2">
          <SearchSelect
            id={`${idPrefix}-country`}
            label="País"
            options={(countries.data ?? []).map((c) => ({ value: c.code, label: c.name }))}
            value={form.countryIsoCode || null}
            // A new country means a new set of provinces and cities
            onChange={(code) => onChange({ countryIsoCode: code ?? '', province: '', city: '' })}
            placeholder="Buscar país…"
            loading={countries.status === 'loading'}
            disabled={disabled}
            required
            noOptionsMessage="Ningún país coincide"
          />
        </div>
      </div>
      {freeTextProvince ? (
        <Field
          id={`${idPrefix}-province`}
          label="Provincia"
          type="text"
          autoComplete="address-level1"
          maxLength={100}
          required
          value={form.province}
          onChange={(e) => onChange({ province: e.target.value })}
          disabled={disabled}
          hint="Este país no tiene provincias definidas: escríbela."
        />
      ) : (
        <SearchSelect
          id={`${idPrefix}-province`}
          label="Provincia"
          options={provinceOptions}
          value={form.province || null}
          onChange={(name) => onChange({ province: name ?? '', city: '' })}
          placeholder={form.countryIsoCode ? 'Buscar provincia…' : 'Selecciona primero el país'}
          loading={provinces.status === 'loading'}
          disabled={disabled || !form.countryIsoCode}
          required
          noOptionsMessage="Ninguna provincia coincide"
        />
      )}
      {freeTextProvince || cityOptions.length === 0 ? (
        <Field
          id={`${idPrefix}-city`}
          label="Ciudad"
          type="text"
          autoComplete="address-level2"
          maxLength={100}
          required
          value={form.city}
          onChange={(e) => onChange({ city: e.target.value })}
          disabled={disabled || !form.province}
          hint={
            !form.province
              ? 'Selecciona primero la provincia.'
              : cities.status === 'loading'
                ? 'Cargando ciudades…'
                : 'No hay lista de ciudades para esta provincia: escríbela.'
          }
        />
      ) : (
        <SearchSelect
          id={`${idPrefix}-city`}
          label="Ciudad"
          options={cityOptions}
          value={form.city || null}
          onChange={(city) => onChange({ city: city ?? '' })}
          placeholder="Buscar ciudad…"
          loading={cities.status === 'loading'}
          disabled={disabled}
          required
          creatable
          noOptionsMessage="Ninguna ciudad coincide: escríbela para usarla"
          hint="Si no aparece en la lista, escríbela y pulsa Intro."
        />
      )}
    </>
  )
}
