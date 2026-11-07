import { COLLECTION_LABELS, COLLECTION_STYLES, type CollectionStatus } from './collection'

export default function CollectionBadge({ status }: { status: CollectionStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${COLLECTION_STYLES[status]}`}
    >
      {COLLECTION_LABELS[status]}
    </span>
  )
}
