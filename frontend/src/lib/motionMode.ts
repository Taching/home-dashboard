export type MotionMode = 'full' | 'lite'

const STORAGE_KEY = 'chili-motion-mode'

export function getMotionMode(): MotionMode {
  try {
    if (localStorage.getItem(STORAGE_KEY) === 'lite') return 'lite'
  } catch {
    // Storage may be unavailable in some kiosk profiles.
  }
  return 'full'
}

export function setMotionMode(mode: MotionMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode)
  } catch {
    // Ignore write failures; reload still applies for the session.
  }
}
