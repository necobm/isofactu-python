import { request } from './client'

export interface Country {
  /** ISO 3166-1 alpha-2 code (what gets stored). */
  code: string
  /** Name in Spanish. */
  name: string
  /** Regular expression the postal codes of the country match, when known. */
  postalCodePattern: string | null
}

export interface Province {
  /** ISO 3166-2 code. */
  code: string
  /** Name in Spanish (what gets stored). */
  name: string
}

/** Reference data for address forms (any logged-in user). */
export const geo = {
  countries: (signal?: AbortSignal) => request<Country[]>('/api/geo/countries', { signal }),

  /** Empty for countries without ISO provinces: the province is then free text. */
  provinces: (countryCode: string, signal?: AbortSignal) =>
    request<Province[]>(`/api/geo/countries/${encodeURIComponent(countryCode)}/provinces`, { signal }),

  /** Suggestions for the city field (may be empty: the city is free text then). */
  cities: (countryCode: string, provinceCode: string, signal?: AbortSignal) =>
    request<string[]>(
      `/api/geo/countries/${encodeURIComponent(countryCode)}/provinces/${encodeURIComponent(provinceCode)}/cities`,
      { signal },
    ),
}
