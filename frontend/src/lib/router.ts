import { useEffect, useState } from 'react'

/**
 * Minimal URL handling: the app is state-driven, but links sent by e-mail must deep-link
 * into it (`/activate/<token>`). `usePathname` re-renders on navigation; `navigate` pushes a
 * new entry in the history.
 */

const NAVIGATE_EVENT = 'app:navigate'

export function usePathname(): string {
  const [pathname, setPathname] = useState(window.location.pathname)
  useEffect(() => {
    const sync = () => setPathname(window.location.pathname)
    window.addEventListener('popstate', sync)
    window.addEventListener(NAVIGATE_EVENT, sync)
    return () => {
      window.removeEventListener('popstate', sync)
      window.removeEventListener(NAVIGATE_EVENT, sync)
    }
  }, [])
  return pathname
}

export function navigate(path: string): void {
  if (window.location.pathname !== path) window.history.pushState(null, '', path)
  window.dispatchEvent(new Event(NAVIGATE_EVENT))
}

/** The token of an activation link (`/activate/<token>`), if the current path is one. */
export function activationToken(pathname: string): string | null {
  const match = /^\/activate\/([^/]+)\/?$/.exec(pathname)
  return match ? decodeURIComponent(match[1]) : null
}
