import assert from 'node:assert/strict'
import test from 'node:test'

import { canLogWorkout, doneMarkLabel, kindsMatch, slugForType, workoutAlreadyLogged } from './workoutMatch.ts'

test('kindsMatch accepts aliases and rejects a different program', () => {
  assert.equal(kindsMatch('strength_a', 'strength_a'), true)
  assert.equal(kindsMatch('zone_2', 'zone2'), true)
  assert.equal(kindsMatch('bjj_normal', 'bjj'), true)
  assert.equal(kindsMatch('competition', 'bjj_hard'), true)
  assert.equal(kindsMatch('strength_a', 'strength_b'), false)
  assert.equal(kindsMatch('rest', 'strength_a'), false)
})

test('canLogWorkout blocks rest and mismatched other sessions', () => {
  assert.equal(canLogWorkout('strength_a', 'strength_a'), true)
  assert.equal(canLogWorkout('strength_a', 'strength_b'), false)
  assert.equal(canLogWorkout('rest', 'rest'), false)
  assert.equal(canLogWorkout('recovery', 'strength_a'), false)
})

test('doneMarkLabel is only for a logged session', () => {
  assert.equal(doneMarkLabel('completed'), 'Done')
  assert.equal(doneMarkLabel('partial'), 'Partial')
  assert.equal(doneMarkLabel('skipped'), 'Skipped')
  assert.equal(doneMarkLabel('planned'), null)
  assert.equal(doneMarkLabel(null), null)
  assert.equal(workoutAlreadyLogged('completed'), true)
  assert.equal(workoutAlreadyLogged('planned'), false)
})

test('slugForType maps competition to the hard BJJ program', () => {
  assert.equal(slugForType('competition'), 'bjj_hard')
  assert.equal(slugForType('bjj_normal'), 'bjj')
  assert.equal(slugForType('zone_2'), 'zone2')
})
