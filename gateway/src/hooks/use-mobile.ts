"use client"

import * as React from "react"

const MOBILE_BREAKPOINT = 768

export function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState<boolean>(false)

  React.useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)

    // Usar mql.matches — consistente con matchMedia, considera scrollbar
    const onChange = (event: MediaQueryListEvent) => {
      setIsMobile(event.matches)
    }

    // Inicializar con el valor correcto inmediatamente
    setIsMobile(mql.matches)

    mql.addEventListener("change", onChange)
    return () => mql.removeEventListener("change", onChange)
  }, [])

  return isMobile
}
