import { useMemo } from 'react'
import { geo, type DocumentType, type Party, type PartyInput } from '@/api'
import { isValidCif, isValidNif, normaliseId } from '@/lib/spanishIds'
import { useApi } from '@/lib/useApi'

/**
 * Editing state of a counterpart of the tenant — a client, or the supplier of a received
 * invoice — shared by the client form and the received invoice form. The server applies
 * the same rules to both (`PartyWrite`).
 */
export interface PartyFormState {
  fullName: string
  documentType: DocumentType
  documentNumber: string
  street: string
  zipCode: string
  city: string
  province: string
  countryIsoCode: string
}

export const EMPTY_PARTY: PartyFormState = {
  fullName: '',
  documentType: 'NIF',
  documentNumber: '',
  street: '',
  zipCode: '',
  city: '',
  province: '',
  countryIsoCode: 'ES',
}

export const DOCUMENT_TYPES: { value: DocumentType; label: string }[] = [
  { value: 'NIF', label: 'NIF' },
  { value: 'CIF', label: 'CIF' },
  { value: 'OTHER', label: 'Otro' },
]

export function partyFormFrom(party: Party): PartyFormState {
  return {
    fullName: party.fullName,
    documentType: party.document.type,
    documentNumber: party.document.number,
    ...party.address,
  }
}

export function toPartyInput(form: PartyFormState): PartyInput {
  return {
    fullName: form.fullName.trim(),
    document: {
      type: form.documentType,
      number: form.documentType === 'OTHER' ? form.documentNumber.trim() : normaliseId(form.documentNumber),
    },
    address: {
      street: form.street.trim(),
      zipCode: form.zipCode.trim(),
      city: form.city.trim(),
      province: form.province.trim(),
      countryIsoCode: form.countryIsoCode.trim().toUpperCase() || 'ES',
    },
  }
}

/**
 * Reference data behind the address fields: the countries, the provinces of the chosen
 * country and the cities of the chosen province (suggestions). With `enabled` false
 * nothing is fetched (for forms that only sometimes show a party).
 */
export function usePartyGeo(form: PartyFormState, enabled = true) {
  const countries = useApi((signal) => (enabled ? geo.countries(signal) : Promise.resolve([])), [enabled])
  const country = useMemo(
    () => countries.data?.find((c) => c.code === form.countryIsoCode) ?? null,
    [countries.data, form.countryIsoCode],
  )
  const provinces = useApi(
    (signal) => (enabled && form.countryIsoCode ? geo.provinces(form.countryIsoCode, signal) : Promise.resolve([])),
    [enabled, form.countryIsoCode],
  )
  const provinceOptions = useMemo(
    () => (provinces.data ?? []).map((p) => ({ value: p.name, label: p.name })),
    [provinces.data],
  )
  /** Countries without ISO provinces take a free-text province. */
  const freeTextProvince =
    form.countryIsoCode !== '' && provinces.status === 'success' && provinces.data.length === 0
  const province = provinces.data?.find((p) => p.name === form.province) ?? null
  const provinceCode = province?.code ?? null
  const cities = useApi(
    (signal) =>
      provinceCode ? geo.cities(form.countryIsoCode, provinceCode, signal) : Promise.resolve([] as string[]),
    [form.countryIsoCode, provinceCode],
  )
  const cityOptions = useMemo(() => (cities.data ?? []).map((c) => ({ value: c, label: c })), [cities.data])

  return { countries, country, provinces, provinceOptions, freeTextProvince, province, cities, cityOptions }
}

export type PartyGeo = ReturnType<typeof usePartyGeo>

/**
 * What is wrong with the party (client-side mirror of the server rules), or `null`.
 * `who` names the party in the messages: "del cliente", "del proveedor".
 */
export function validateParty(input: PartyInput, partyGeo: PartyGeo, who: string): string | null {
  const { country, freeTextProvince, province, cityOptions } = partyGeo
  if (input.fullName.length < 2) return `Indica el nombre o razón social ${who}.`
  if (!input.document.number) return `Indica el NIF / CIF ${who}.`
  if (input.document.type === 'NIF' && !isValidNif(input.document.number)) {
    return 'El NIF no es válido: comprueba los dígitos y la letra (DNI: 8 dígitos y letra; NIE: X/Y/Z, 7 dígitos y letra).'
  }
  if (input.document.type === 'CIF' && !isValidCif(input.document.number)) {
    return 'El CIF no es válido: comprueba la letra, los 7 dígitos y el carácter de control.'
  }
  if (input.address.street.length < 3) return `Indica la dirección ${who}.`
  if (!input.address.zipCode) return 'Indica el código postal.'
  if (!input.address.countryIsoCode) return 'Selecciona el país.'
  if (country?.postalCodePattern && !new RegExp(country.postalCodePattern).test(input.address.zipCode)) {
    return `El código postal no tiene el formato de ${country.name}.`
  }
  if (!input.address.province) return freeTextProvince ? 'Indica la provincia.' : 'Selecciona la provincia.'
  if (!freeTextProvince && !province) return 'Selecciona una provincia de la lista.'
  if (!input.address.city) return cityOptions.length ? 'Selecciona o escribe la ciudad.' : 'Indica la ciudad.'
  return null
}
