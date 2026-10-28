import { api, type Subject, type SubjectInput } from '@/api'

/**
 * The company that issues every invoice (single-tenant application).
 *
 * TODO: replace this placeholder with the company profile once the settings section exists;
 * it is resolved to a stored subject (found by document number, created on first use) so that
 * the invoicing API, which links invoices to subjects, keeps working unchanged.
 */
export const MOCK_ISSUER: SubjectInput = {
  fullName: 'Mi Empresa S.L.',
  document: { type: 'CIF', number: 'B12345674' },
  address: {
    street: 'Calle Mayor 1',
    zipCode: '28001',
    city: 'Madrid',
    province: 'Madrid',
    countryIsoCode: 'ES',
  },
}

/** The subject standing for the issuing company, creating it if it does not exist yet. */
export async function resolveIssuer(): Promise<Subject> {
  const number = MOCK_ISSUER.document!.number!
  const candidates = await api.listSubjects({ q: number, limit: 10 })
  return candidates.find((subject) => subject.document.number === number) ?? api.createSubject(MOCK_ISSUER)
}
