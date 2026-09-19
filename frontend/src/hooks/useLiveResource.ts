import { useCallback, useEffect, useEffectEvent } from 'react'
import { keepPreviousData, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { subscribeToPlanningChanges } from '../lib/planningRefresh'

type LiveResourceOptions<T> = {
  queryKey: QueryKey
  enabled?: boolean
  intervalMs?: number | null
  initialData?: T
  subscribe?: (refresh: () => void) => () => void
}

export function useLiveResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  options: LiveResourceOptions<T>,
) {
  const {
    queryKey,
    enabled = true,
    intervalMs = 60_000,
    initialData,
    subscribe = subscribeToPlanningChanges,
  } = options
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => load(signal),
    enabled,
    initialData,
    placeholderData: keepPreviousData,
    staleTime: 15_000,
    refetchInterval: intervalMs ?? false,
  })
  const refetch = query.refetch
  const invalidate = useEffectEvent(() => {
    void queryClient.invalidateQueries({ queryKey })
  })

  useEffect(() => {
    if (!enabled) return undefined
    return subscribe(invalidate)
  }, [enabled, subscribe])

  const refresh = useCallback(async () => {
    await refetch({ cancelRefetch: true })
  }, [refetch])
  const setData = useCallback((next: T) => {
    queryClient.setQueryData<T>(queryKey, next)
  }, [queryClient, queryKey])

  return {
    data: query.data ?? null,
    error: query.isError ? 'Could not refresh.' : null,
    isLoading: query.isPending,
    isRefreshing: query.isFetching && !query.isPending,
    refresh,
    setData,
  }
}
