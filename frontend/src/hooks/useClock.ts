import { useSyncExternalStore } from 'react'

const SECOND_MS = 1_000

function subscribe(onStoreChange: () => void) {
  const interval = window.setInterval(onStoreChange, SECOND_MS)
  return () => window.clearInterval(interval)
}

function getSnapshot() {
  return Math.floor(Date.now() / SECOND_MS)
}

export function useClock() {
  const currentSecond = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  return new Date(currentSecond * SECOND_MS)
}
