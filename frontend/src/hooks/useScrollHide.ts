import { useEffect, useState } from 'react'

const JITTER_PX = 8
const REVEAL_NEAR_TOP_PX = 8
const HIDE_AFTER_PX = 64

/**
 * True while the reader is scrolling down the document; false again as soon
 * as they scroll up or return near the top. Drives the floating phone chrome.
 */
export function useScrollHide() {
  const [hidden, setHidden] = useState(false)

  useEffect(() => {
    let last = window.scrollY
    let frame = 0
    const sample = () => {
      frame = 0
      const y = window.scrollY
      const delta = y - last
      if (y <= REVEAL_NEAR_TOP_PX) {
        setHidden(false)
        last = y
        return
      }
      if (Math.abs(delta) <= JITTER_PX) return
      setHidden(delta > 0 && y > HIDE_AFTER_PX)
      last = y
    }
    const onScroll = () => {
      if (frame) return
      frame = window.requestAnimationFrame(sample)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [])

  return hidden
}
