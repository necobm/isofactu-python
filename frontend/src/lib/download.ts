/** Hands a file over to the browser, which saves it as `filename` (the usual download flow). */
export function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Give the browser a moment to start reading the blob before releasing it
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
