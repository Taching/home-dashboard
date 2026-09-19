export function normalizeKind(kind: string | undefined) {
  const value = (kind || '').toLowerCase()
  if (value === 'zone_2') return 'zone2'
  return value
}

export function kindsMatch(planned: string | undefined, logged: string | undefined) {
  const plannedKind = normalizeKind(planned)
  const loggedKind = normalizeKind(logged)
  if (!loggedKind) return true
  if (plannedKind === 'competition') {
    return ['competition', 'bjj', 'bjj_hard', 'bjj_normal'].includes(loggedKind)
  }
  if (loggedKind === 'bjj') return plannedKind.startsWith('bjj') || plannedKind === 'competition'
  if (loggedKind === 'rest') return plannedKind === 'rest' || plannedKind === 'recovery'
  return plannedKind === loggedKind
}

export function workoutAlreadyLogged(status: string | null | undefined) {
  return ['completed', 'partial', 'skipped'].includes(status ?? '')
}

export function workoutFormLocked(status: string | null | undefined) {
  return workoutAlreadyLogged(status)
}

export function doneMarkLabel(status: string | null | undefined) {
  if (status === 'completed') return 'Done'
  if (status === 'partial') return 'Partial'
  if (status === 'skipped') return 'Skipped'
  return null
}

export function slugForType(type: string) {
  if (type === 'zone_2') return 'zone2'
  if (type === 'competition' || type === 'bjj_hard') return 'bjj_hard'
  if (type.startsWith('bjj_')) return 'bjj'
  return type
}

export function canLogWorkout(plannedType: string | undefined, loggedKind: string | undefined) {
  if (!plannedType || plannedType === 'rest') return false
  if (plannedType === 'recovery') return !loggedKind || loggedKind === 'recovery'
  return kindsMatch(plannedType, loggedKind)
}
