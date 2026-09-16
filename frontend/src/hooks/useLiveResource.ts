import { useCallback, useEffect, useRef, useState } from 'react'
import { subscribeToPlanningChanges } from '../lib/planningRefresh'
import { usePolling } from './usePolling'

type LiveResourceOptions<T> = {
  enabled?: boolean
  intervalMs?: number | null
  immediate?: boolean
  initialData?: T
  subscribe?: (refresh: () => void) => () => void
}

export function useLiveResource<T>(
  load: () => Promise<T>,
  deps: readonly unknown[] = [],
  options: LiveResourceOptions<T> = {},
) {
  const {
    enabled = true,
    intervalMs = 15_000,
    immediate = true,
    initialData,
    subscribe = subscribeToPlanningChanges,
  } = options
  const [data, setData] = useState<T | null>(initialData ?? null)
  const [error, setError] = useState<string | null>(null)
  const loadRef = useRef(load)
  loadRef.current = load

  const refresh = useCallback(async () => {
    if (!enabled) return
    try {
      const next = await loadRef.current()
      setData(next)
      setError(null)
    } catch {
      setError('Could not refresh.')
    }
  }, [enabled])

  const depKey = JSON.stringify(deps)
  useEffect(() => {
    if (immediate) void refresh()
  }, [depKey, immediate, refresh])

  usePolling(refresh, enabled ? intervalMs : null, false)

  useEffect(() => {
    if (!enabled) return undefined
    return subscribe(() => void refresh())
  }, [enabled, refresh, subscribe])

  return { data, error, refresh, setData }
}
