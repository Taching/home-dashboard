import { useEffect, useState } from 'react'
import { fetchActivityEvents, fetchVoiceStatus } from '../lib/api'
import type { ActivityEvent, VoiceStatus } from '../types'

const offlineStatus: VoiceStatus = {
  state: 'offline',
  updated_at: null,
  transcript: null,
  message: null,
}

function sameVoiceStatus(first: VoiceStatus, second: VoiceStatus) {
  return first.state === second.state
    && first.updated_at === second.updated_at
    && first.transcript === second.transcript
    && first.message === second.message
}

function sameEvents(first: ActivityEvent[], second: ActivityEvent[]) {
  if (first.length !== second.length) return false
  const last = first.length - 1
  if (last < 0) return true
  return first[last].at === second[last].at && first[last].detail === second[last].detail
}

export function useVoiceMonitor() {
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>(offlineStatus)
  const [activityEvents, setActivityEvents] = useState<ActivityEvent[]>([])

  useEffect(() => {
    const applyStatus = (next: VoiceStatus) => {
      setVoiceStatus((current) => (sameVoiceStatus(current, next) ? current : next))
    }
    const applyEvents = (next: ActivityEvent[]) => {
      setActivityEvents((current) => (sameEvents(current, next) ? current : next))
    }

    const refresh = () => {
      void fetchVoiceStatus()
        .then(applyStatus)
        .catch(() => applyStatus(offlineStatus))
      void fetchActivityEvents()
        .then(applyEvents)
        .catch(() => {})
    }

    refresh()
    const pollMs = voiceStatus.state === 'idle' || voiceStatus.state === 'offline' ? 3_000 : 750
    const interval = window.setInterval(refresh, pollMs)
    return () => window.clearInterval(interval)
  }, [voiceStatus.state])

  return { voiceStatus, activityEvents }
}
