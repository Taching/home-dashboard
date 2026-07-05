import type { Display, Light, LightState, WaterPump } from '../types'

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

function formatHour(hour: number) {
  const suffix = hour >= 12 ? 'p.m.' : 'a.m.'
  const normalized = hour % 12 || 12
  return `${normalized} ${suffix}`
}

type Props = {
  light: Light
  pump: WaterPump
  display: Display
  lightPending: boolean
  pumpPending: boolean
  displayPending: boolean
  schedulePending: boolean
  onToggleLight: () => void
  onTogglePump: () => void
  onToggleDisplay: () => void
  onToggleSchedule: () => void
}

function lightAction(state: LightState) {
  return state === 'on' ? 'Turn light off' : 'Turn light on'
}

function pumpAction(pump: WaterPump) {
  return pump.state === 'running' ? 'Stop plant pump' : 'Water plants for 20 seconds'
}

export function DeviceControls({
  light,
  pump,
  display,
  lightPending,
  pumpPending,
  displayPending,
  schedulePending,
  onToggleLight,
  onTogglePump,
  onToggleDisplay,
  onToggleSchedule,
}: Props) {
  const lightOn = light.last_command_state === 'on'
  const pumpOn = pump.state === 'running'
  const screenOn = display.state === 'visible'
  const scheduleLabel = `${formatHour(display.schedule_on_hour)}–${formatHour(display.schedule_off_hour)}`

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
      <div className="device-row">
        <p className="device-label">Screen</p>
        <DevicePill
          active={screenOn}
          pending={displayPending}
          onClick={onToggleDisplay}
          ariaLabel={screenOn ? 'Turn screen off' : 'Turn screen on'}
        />
      </div>
      <div className="device-row">
        <p className="device-label">Auto schedule · {scheduleLabel}</p>
        <DevicePill
          active={display.schedule_enabled}
          pending={schedulePending}
          onClick={onToggleSchedule}
          ariaLabel={
            display.schedule_enabled
              ? `Turn off automatic screen schedule (${scheduleLabel})`
              : `Turn on automatic screen schedule (${scheduleLabel})`
          }
        />
      </div>
    </section>
  )
}
