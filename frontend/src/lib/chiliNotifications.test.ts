import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildNotification,
  findCompletedTasks,
  findMeetingSoonEvents,
  formatSpotifyPlaying,
  formatTaskCompleted,
  insertByPriority,
  notificationPriority,
  shouldPreempt,
  tasksSnapshot,
} from './chiliNotifications.ts'
import type { CalendarToday } from '../types.ts'

test('formatSpotifyPlaying includes track and artist', () => {
  assert.equal(formatSpotifyPlaying('Wonderwall', 'Oasis'), 'Playing for you: Wonderwall — Oasis')
})

test('formatTaskCompleted uses task title', () => {
  assert.equal(formatTaskCompleted('Pay bill'), 'Good job finishing Pay bill')
})

test('insertByPriority orders by priority then age', () => {
  const low = buildNotification('spotify_playing', 'Playing for you: A', 'spotify:a')
  const high = buildNotification('meeting_soon', 'Meeting soon', 'meeting:1')
  const queue = insertByPriority(insertByPriority([], low), high)
  assert.equal(queue[0]?.kind, 'meeting_soon')
})

test('shouldPreempt prefers higher priority notifications', () => {
  const active = buildNotification('spotify_playing', 'Playing for you: A', 'spotify:a')
  const incoming = buildNotification('task_completed', 'Good job finishing X', 'task:1')
  assert.equal(shouldPreempt(active, incoming), true)
  assert.equal(shouldPreempt(incoming, active), false)
})

test('findCompletedTasks detects removed notion tasks', () => {
  const previous = tasksSnapshot([
    { id: 'a', title: 'One', due_at: null, is_overdue: false, status: null, priority: null, task_type: null },
    { id: 'b', title: 'Two', due_at: null, is_overdue: false, status: null, priority: null, task_type: null },
  ])
  const completed = findCompletedTasks(previous, [
    { id: 'b', title: 'Two', due_at: null, is_overdue: false, status: null, priority: null, task_type: null },
  ])
  assert.deepEqual(completed, [{ id: 'a', title: 'One' }])
})

test('findMeetingSoonEvents matches ten minute window', () => {
  const now = new Date('2026-07-05T10:50:00+09:00')
  const calendar: CalendarToday = {
    status: 'ready',
    synced_at: null,
    events: [{
      id: 'meet-1',
      title: 'Mango Standup',
      start_at: '2026-07-05T11:00:00+09:00',
      end_at: '2026-07-05T11:30:00+09:00',
      is_all_day: false,
      is_current: false,
    }],
  }
  const matches = findMeetingSoonEvents(calendar, '2026-07-05', now.getTime())
  assert.equal(matches.length, 1)
  assert.equal(matches[0]?.title, 'Mango Standup')
})

test('notificationPriority ranks meetings above spotify', () => {
  assert.ok(notificationPriority('meeting_soon') < notificationPriority('spotify_playing'))
})
