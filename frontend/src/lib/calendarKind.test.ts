import assert from 'node:assert/strict'
import test from 'node:test'

import { calendarEventKind } from './calendarKind.ts'

test('Asuene calendars are work', () => {
  assert.equal(calendarEventKind({ calendar_title: 'wada.takatoshi@asuene.com' }), 'work')
  assert.equal(calendarEventKind({ calendar_title: 'Asuene Shared' }), 'work')
})

test('anything else is personal', () => {
  assert.equal(calendarEventKind({ calendar_title: 'Holidays in Japan' }), 'personal')
  assert.equal(calendarEventKind({ calendar_title: '日本の祝日' }), 'personal')
  assert.equal(calendarEventKind({ calendar_title: null }), 'personal')
  assert.equal(calendarEventKind({}), 'personal')
})

test('training source wins over calendar title', () => {
  assert.equal(calendarEventKind({
    source: 'training',
    calendar_title: 'Chili Training',
    training_session_id: 's1',
  }), 'training')
})
