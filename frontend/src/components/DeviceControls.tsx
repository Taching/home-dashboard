import type { Light, LightState, WaterPump } from '../types'

type DevicePillProps = {
  active: boolean
  pending: boolean
  disabled?: boolean
  onClick: () => void
  ariaLabel: string
}

function DevicePill({ active, pending, disabled, onClick, ariaLabel }: DevicePillProps) {
  return (
    <button
      type="button"
      className={`device-pill${active ? ' is-on' : ''}`}
      onClick={onClick}
      disabled={disabled || pending}
      aria-label={pending ? 'Sending command' : ariaLabel}
      aria-pressed={active}
    >
      <span aria-hidden="true" />
      <small>{pending ? '…' : active ? 'ON' : 'OFF'}</small>
    </button>
  )
}

type Props = {
  light: Light
  pump: WaterPump
  lightPending: boolean
  pumpPending: boolean
  onToggleLight: () => void
  onTogglePump: () => void
}

function lightAction(state: LightState) {
  return state === 'on' ? 'Turn light off' : 'Turn light on'
}

function pumpAction(pump: WaterPump) {
  return pump.state === 'running' ? 'Stop plant pump' : 'Water plants for 20 seconds'
}

function statusLine(light: Light, pump: WaterPump) {
  const lightStatus = light.available ? 'Light ready' : 'Light unavailable'
  let pumpStatus = 'Pump unavailable'
  if (pump.available) {
    pumpStatus = pump.state === 'running' ? 'Watering' : 'Pump ready'
  }
  return `${lightStatus} · ${pumpStatus}`
}

export function DeviceControls({
  light,
  pump,
  lightPending,
  pumpPending,
  onToggleLight,
  onTogglePump,
}: Props) {
  const lightOn = light.last_command_state === 'on'
  const pumpOn = pump.state === 'running'

  return (
    <section className="device-controls" aria-label="Home controls">
      <div className={`device-row${light.available ? '' : ' is-unavailable'}`}>
        <p className="device-label">Light</p>
        <DevicePill
          active={lightOn}
          pending={lightPending}
          disabled={!light.available}
          onClick={onToggleLight}
          ariaLabel={lightAction(light.last_command_state)}
        />
      </div>
      <div className={`device-row${pump.available ? '' : ' is-unavailable'}`}>
        <p className="device-label">{pumpOn ? 'Plant pump · watering' : 'Plant pump'}</p>
        <DevicePill
          active={pumpOn}
          pending={pumpPending}
          disabled={!pump.available && !pumpOn}
          onClick={onTogglePump}
          ariaLabel={pumpAction(pump)}
        />
      </div>
      <p className="device-controls-status">{statusLine(light, pump)}</p>
    </section>
  )
}
