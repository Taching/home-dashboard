import { useSyncExternalStore } from 'react'
import { dayKey } from '../components/PlanningRegion'

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

/** Calendar day in Asia/Tokyo; updates when the kiosk crosses midnight. */
export function useToday() {
  return dayKey(useClock())
}
