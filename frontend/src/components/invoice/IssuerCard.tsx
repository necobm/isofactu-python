import type { Party } from '@/api'

/** Compact read-only summary of who issues the invoice (the account's fiscal data). */
export default function IssuerCard({ issuer }: { issuer: Party }) {
  const { street, zipCode, city, province, countryIsoCode } = issuer.address
  const locality = [zipCode, city].filter(Boolean).join(' ')
  const region = [province, countryIsoCode].filter(Boolean).join(', ')
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 px-4 py-3">
      <p className="text-sm font-semibold text-slate-800">{issuer.fullName}</p>
      <p className="text-xs text-slate-500">
        {issuer.document.type} {issuer.document.number}
      </p>
      <p className="mt-1 text-xs text-slate-400">{[street, locality, region].filter(Boolean).join(' · ')}</p>
    </div>
  )
}
