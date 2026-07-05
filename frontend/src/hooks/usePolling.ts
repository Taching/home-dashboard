import { useEffect } from 'react'

export function usePolling(task: () => void | Promise<void>, intervalMs: number | null, immediate = true) {
  useEffect(() => {
    if (intervalMs === null) return
    if (immediate) void task()
    const interval = window.setInterval(() => void task(), intervalMs)
    return () => window.clearInterval(interval)
  }, [immediate, intervalMs, task])
}
