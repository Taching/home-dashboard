import type { LightState } from '../types'

export function formatClock(value: Date) {
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(value)
}

export function formatDate(value: Date) {
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'long', day: 'numeric', month: 'long',
  }).format(value)
}

export function formatRelativeTime(value: string | null) {
  if (!value) return 'No sensor reading yet'
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60_000))
  if (minutes < 1) return 'Updated just now'
  if (minutes === 1) return 'Updated 1 minute ago'
  return `Updated ${minutes} minutes ago`
}

export function lightCopy(state: LightState) {
  if (state === 'unknown') return 'Light · no confirmed command'
  return `Light · last set ${state}`
}
