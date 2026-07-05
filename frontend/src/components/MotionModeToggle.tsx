import { getMotionMode, setMotionMode, type MotionMode } from '../lib/motionMode'

type Props = {
  mode: MotionMode
}

function selectMode(next: MotionMode) {
  if (next === getMotionMode()) return
  setMotionMode(next)
  window.location.reload()
}

export function MotionModeToggle({ mode }: Props) {
  return (
    <div className="motion-toggle-zone" aria-label="Motion mode">
      <div className="motion-toggle-panel">
        <span className="motion-toggle-label">Motion</span>
        <button
          type="button"
          className={mode === 'full' ? 'is-active' : ''}
          onClick={() => selectMode('full')}
        >
          Full
        </button>
        <button
          type="button"
          className={mode === 'lite' ? 'is-active' : ''}
          onClick={() => selectMode('lite')}
        >
          Lite
        </button>
      </div>
    </div>
  )
}
