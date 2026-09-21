import { useEffect, useState } from 'react'
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
  TrainingOverview,
} from '../types'

type Inputs = {
  today: string
  calendar: CalendarToday
  notion: NotionToday
  spotify: SpotifyNowPlaying
  openclaw: OpenClawConversation
  spotifyIntentToken: number
  walkReminder: WalkReminder
  lastAdjustment?: TrainingOverview['last_adjustment']
}

export function useChiliNotifications({
  today,
  calendar,
  notion,
  spotify,
  openclaw,
  spotifyIntentToken,
  walkReminder,
  lastAdjustment,
}: Inputs) {
  const now = useClock()
  const [, rerender] = useState(0)
  const [controller] = useState(() => ChiliNotificationController.create())
  const [state] = useState<DisplayState>(() => controller.createState())

  useEffect(() => controller.subscribe(() => rerender((value) => value + 1)), [controller])

  useEffect(() => {
    controller.sync(state, {
      today,
      nowMs: now.getTime(),
      calendar,
      notion,
      spotify,
      openclaw,
      spotifyIntentToken,
      walkReminder,
      lastAdjustment,
    })
  }, [calendar, controller, lastAdjustment, notion, now, openclaw, spotify, spotifyIntentToken, state, today, walkReminder])

  useEffect(() => () => controller.dispose(), [controller])

  return {
    active: state.visible,
    exiting: state.exiting,
    queueLength: state.queue.length,
  }
}
