import {
  buildNotification,
  findCompletedTasks,
  findMeetingSoonEvents,
  formatMeetingSoon,
  formatOpenClawMessageWaiting,
  formatSpotifyPlaying,
  formatTaskCompleted,
  hasSeenKey,
  hasTelegramSentKey,
  insertByPriority,
  lastAssistantFingerprint,
  loadSeenKeys,
  loadTelegramSentKeys,
  markSeenKey,
  markTelegramSentKey,
  NOTIFICATION_FADE_MS,
  NOTIFICATION_TTL_MS,
  shouldPreempt,
  tasksFingerprint,
  tasksSnapshot,
  voiceTransitionNotification,
  type ChiliNotification,
} from '../lib/chiliNotifications'
import { notifyChili } from '../lib/api'
import type {
  CalendarToday,
  NotionToday,
  OpenClawConversation,
  SpotifyNowPlaying,
  VoiceStatus,
  WalkReminder,
} from '../types'

export type NotificationInputs = {
  today: string
  nowMs: number
  calendar: CalendarToday
  notion: NotionToday
  spotify: SpotifyNowPlaying
  openclaw: OpenClawConversation
  voiceStatus: VoiceStatus
  spotifyIntentToken: number
  walkReminder: WalkReminder
}

type DisplayState = {
  visible: ChiliNotification | null
  exiting: boolean
  queue: ChiliNotification[]
}

export class ChiliNotificationController {
  private seenKeys = loadSeenKeys()
  private telegramSentKeys = loadTelegramSentKeys()
  private meetingKeysCollected = new Set<string>()
  private walkReminderKeysCollected = new Set<string>()
  private notionSnapshot = new Map<string, string>()
  private notionSeeded = false
  private openClawFingerprint: string | null = null
  private openClawSeeded = false
  private previousVoice: VoiceStatus | null = null
  private spotifyTrack: string | null = null
  private spotifyIntent = 0
  private lastSpokenId: string | null = null
  private dismissTimer: number | null = null
  private fadeTimer: number | null = null
  private onChange: (() => void) | null = null

  static create(): ChiliNotificationController {
    return new ChiliNotificationController()
  }

  subscribe(onChange: () => void) {
    this.onChange = onChange
  }

  dispose() {
    this.clearTimers()
    this.onChange = null
  }

  private bump() {
    this.onChange?.()
  }

  private clearTimers() {
    if (this.dismissTimer !== null) {
      window.clearTimeout(this.dismissTimer)
      this.dismissTimer = null
    }
    if (this.fadeTimer !== null) {
      window.clearTimeout(this.fadeTimer)
      this.fadeTimer = null
    }
  }

  private markDisplayed(notification: ChiliNotification): boolean {
    if (hasSeenKey(notification.dedupeKey, this.seenKeys)) return false
    this.seenKeys = markSeenKey(notification.dedupeKey, this.seenKeys)
    this.sendTelegram(notification)
    return true
  }

  private sendTelegram(notification: ChiliNotification) {
    if (!notification.sendTelegram) return
    if (hasTelegramSentKey(notification.dedupeKey, this.telegramSentKeys)) return
    this.telegramSentKeys = markTelegramSentKey(notification.dedupeKey, this.telegramSentKeys)
    void notifyChili(notification.message, notification.dedupeKey).catch(() => {})
  }

  private isPending(state: DisplayState, dedupeKey: string): boolean {
    if (state.visible?.dedupeKey === dedupeKey) return true
    return state.queue.some((item) => item.dedupeKey === dedupeKey)
  }

  private speak(notification: ChiliNotification) {
    if (notification.kind === 'openclaw_message') return
    if (notification.id === this.lastSpokenId) return
    if (typeof window === 'undefined' || !window.speechSynthesis) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    if (window.speechSynthesis.speaking) return
    this.lastSpokenId = notification.id
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(notification.message))
  }

  private scheduleDismiss(state: DisplayState, notification: ChiliNotification) {
    this.clearTimers()
    this.dismissTimer = window.setTimeout(() => {
      this.dismissTimer = null
      if (state.visible?.id !== notification.id) return
      state.exiting = true
      this.bump()
      this.fadeTimer = window.setTimeout(() => {
        this.fadeTimer = null
        state.exiting = false
        state.visible = null
        this.bump()
        this.tryShowNext(state)
      }, NOTIFICATION_FADE_MS)
    }, NOTIFICATION_TTL_MS)
  }

  private showNotification(state: DisplayState, notification: ChiliNotification) {
    if (!this.markDisplayed(notification)) return
    state.exiting = false
    state.visible = notification
    this.speak(notification)
    this.scheduleDismiss(state, notification)
    this.bump()
  }

  private tryShowNext(state: DisplayState) {
    while (state.queue.length > 0) {
      if (state.visible || state.exiting) return
      const [next, ...rest] = state.queue
      state.queue = rest
      if (hasSeenKey(next.dedupeKey, this.seenKeys)) continue
      this.showNotification(state, next)
      return
    }
  }

  private enqueue(state: DisplayState, notification: ChiliNotification) {
    if (hasSeenKey(notification.dedupeKey, this.seenKeys)) return
    if (this.isPending(state, notification.dedupeKey)) return

    const current = state.visible
    if (current && shouldPreempt(current, notification)) {
      state.queue = insertByPriority(state.queue, current)
      this.clearTimers()
      this.showNotification(state, notification)
      return
    }

    if (!current) {
      this.showNotification(state, notification)
      return
    }

    state.queue = insertByPriority(state.queue, notification)
    this.bump()
  }

  collectNotifications(inputs: NotificationInputs): ChiliNotification[] {
    const found: ChiliNotification[] = []

    for (const event of findMeetingSoonEvents(inputs.calendar, inputs.today, inputs.nowMs)) {
      const dedupeKey = `meeting:${event.id}:${inputs.today}`
      if (
        this.meetingKeysCollected.has(dedupeKey)
        || hasSeenKey(dedupeKey, this.seenKeys)
        || hasTelegramSentKey(dedupeKey, this.telegramSentKeys)
      ) {
        continue
      }
      this.meetingKeysCollected.add(dedupeKey)
      found.push(buildNotification(
        'meeting_soon',
        formatMeetingSoon(event.title, 10),
        dedupeKey,
        { sendTelegram: true },
      ))
    }

    if (
      inputs.walkReminder.active
      && inputs.walkReminder.message
      && inputs.walkReminder.dedupe_key
      && !this.walkReminderKeysCollected.has(inputs.walkReminder.dedupe_key)
      && !hasSeenKey(inputs.walkReminder.dedupe_key, this.seenKeys)
    ) {
      this.walkReminderKeysCollected.add(inputs.walkReminder.dedupe_key)
      found.push(buildNotification(
        'walk_reminder',
        inputs.walkReminder.message,
        inputs.walkReminder.dedupe_key,
      ))
    }

    if (inputs.notion.status === 'ready') {
      const notionKey = `${inputs.notion.synced_at ?? ''}:${tasksFingerprint(inputs.notion.tasks)}`
      if (!this.notionSeeded) {
        this.notionSeeded = true
        this.notionSnapshot = tasksSnapshot(inputs.notion.tasks)
        this.lastNotionKey = notionKey
      } else if (notionKey !== this.lastNotionKey) {
        for (const task of findCompletedTasks(this.notionSnapshot, inputs.notion.tasks)) {
          found.push(buildNotification(
            'task_completed',
            formatTaskCompleted(task.title),
            `task:completed:${task.id}`,
          ))
        }
        this.notionSnapshot = tasksSnapshot(inputs.notion.tasks)
        this.lastNotionKey = notionKey
      }
    }

    const openClawFingerprint = lastAssistantFingerprint(inputs.openclaw.messages)
    if (!this.openClawSeeded) {
      this.openClawSeeded = true
      this.openClawFingerprint = openClawFingerprint
    } else if (openClawFingerprint && openClawFingerprint !== this.openClawFingerprint) {
      this.openClawFingerprint = openClawFingerprint
      found.push(buildNotification(
        'openclaw_message',
        formatOpenClawMessageWaiting(),
        `openclaw:${openClawFingerprint}`,
      ))
    }

    if (this.previousVoice) {
      const voiceNotification = voiceTransitionNotification(this.previousVoice, inputs.voiceStatus)
      if (voiceNotification) found.push(voiceNotification)
    }
    this.previousVoice = inputs.voiceStatus

    if (inputs.spotifyIntentToken !== 0 && inputs.spotifyIntentToken !== this.spotifyIntent) {
      this.spotifyIntent = inputs.spotifyIntentToken
      this.spotifyTrack = null
    }

    if (
      inputs.spotify.status === 'ready'
      && inputs.spotify.is_playing
      && inputs.spotify.track
      && this.spotifyIntent !== 0
    ) {
      const trackKey = `${inputs.spotify.track}:${inputs.spotify.artist ?? ''}`
      if (this.spotifyTrack !== trackKey) {
        this.spotifyTrack = trackKey
        this.spotifyIntent = 0
        found.push(buildNotification(
          'spotify_playing',
          formatSpotifyPlaying(inputs.spotify.track, inputs.spotify.artist),
          `spotify:${trackKey}`,
        ))
      }
    }

    return found
  }

  private lastNotionKey = ''

  sync(state: DisplayState, inputs: NotificationInputs) {
    for (const notification of this.collectNotifications(inputs)) {
      this.enqueue(state, notification)
    }
  }

  createState(): DisplayState {
    return { visible: null, exiting: false, queue: [] }
  }
}

export type { DisplayState }
