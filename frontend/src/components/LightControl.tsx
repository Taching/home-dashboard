import { lightCopy } from '../lib/format'
import type { Light, LightState } from '../types'

type Props = {
  light: Light
  pending: boolean
  onToggle: () => void
}

function nextAction(state: LightState) {
  return state === 'on' ? 'Turn off' : 'Turn on'
}

export function LightControl({ light, pending, onToggle }: Props) {
  return (
    <section className={`light-control ${light.available ? '' : 'is-unavailable'}`} aria-label="Light control">
      <div>
        <p className="eyebrow">LIGHT</p>
        <p className="light-copy">{lightCopy(light.last_command_state)}</p>
      </div>
      <button type="button" onClick={onToggle} disabled={pending} aria-describedby="light-availability">
        {pending ? 'Sending…' : nextAction(light.last_command_state)}
      </button>
      <p id="light-availability" className="availability">
        {light.available ? 'BroadLink ready' : 'BroadLink unavailable'}
      </p>
    </section>
  )
}
