import chiliLogo from '../assets/chili-logo.svg'
import type { MotionMode } from '../lib/motionMode'
import type { StartupCheck } from '../hooks/useStartupBoot'

type Props = {
  checks: StartupCheck[]
  motionMode: MotionMode
  fading?: boolean
}

function statusLabel(state: StartupCheck['state']) {
  switch (state) {
    case 'pending': return 'Waiting'
    case 'checking': return 'Checking'
    case 'ok': return 'Ready'
    case 'optional': return 'Optional'
    case 'failed': return 'Unavailable'
  }
}

export function StartupSplash({ checks, motionMode, fading = false }: Props) {
  const completed = checks.filter((check) => check.state !== 'pending' && check.state !== 'checking').length
  const progress = checks.length ? (completed / checks.length) * 100 : 0

  return (
    <div className={`startup-splash${fading ? ' is-fading' : ''}`} aria-live="polite">
      <div className="startup-splash-card">
        <img className="startup-logo" src={chiliLogo} alt="" />
        <p className="startup-title">Starting Chili</p>
        <p className="startup-subtitle">
          Checking services · {motionMode === 'lite' ? 'Lite motion' : 'Full motion'}
        </p>
        <div className="startup-progress" aria-hidden="true">
          <i style={{ width: `${progress}%` }} />
        </div>
        <ul className="startup-checklist">
          {checks.map((check) => (
            <li key={check.id} className={`startup-check-row is-${check.state}`}>
              <span className="startup-check-icon" aria-hidden="true" />
              <span className="startup-check-copy">
                <strong>{check.label}</strong>
                <small>{check.detail ?? statusLabel(check.state)}</small>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
