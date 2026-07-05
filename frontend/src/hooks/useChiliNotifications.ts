import { useEffect, useRef, useState } from 'react'
import {
  ChiliNotificationController,
  type DisplayState,
} from '../lib/chiliNotificationController'
import { useClock } from './useClock'
import type {
  CalendarToday,
  NotionToday,
  OpenClawConversation,
  SpotifyNowPlaying,
  WalkReminder,
  VoiceStatus,
} from '../types'

type Inputs = {
  today: string
  calendar: CalendarToday
  notion: NotionToday
  spotify: SpotifyNowPlaying
  openclaw: OpenClawConversation
  voiceStatus: VoiceStatus
  spotifyIntentToken: number
  walkReminder: WalkReminder
}

export function useChiliNotifications({
  today,
  calendar,
  notion,
  spotify,
  openclaw,
  voiceStatus,
  spotifyIntentToken,
  walkReminder,
}: Inputs) {
  const now = useClock()
  const controllerRef = useRef<ChiliNotificationController | null>(null)
  const stateRef = useRef<DisplayState | null>(null)
  const [, rerender] = useState(0)

  if (!controllerRef.current) {
    const controller = ChiliNotificationController.create()
    controller.subscribe(() => rerender((value) => value + 1))
    controllerRef.current = controller
    stateRef.current = controller.createState()
  }

  const controller = controllerRef.current
  const state = stateRef.current!

  useEffect(() => {
    controller.sync(state, {
      today,
      nowMs: now.getTime(),
      calendar,
      notion,
      spotify,
      openclaw,
      voiceStatus,
      spotifyIntentToken,
      walkReminder,
    })
  }, [calendar, controller, notion, now, openclaw, spotify, spotifyIntentToken, state, today, voiceStatus, walkReminder])

  useEffect(() => () => controller.dispose(), [controller])

  return {
    active: state.visible,
    exiting: state.exiting,
    queueLength: state.queue.length,
  }
}
