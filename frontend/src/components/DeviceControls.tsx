import type { Display, Light, SystemStatus, WaterPump } from '../types'

function formatHour(hour: number) {
  const suffix = hour >= 12 ? 'p.m.' : 'a.m.'
  return `${hour % 12 || 12} ${suffix}`
}

function StatusItem({
  label,
  detail,
  active,
  unavailable = false,
  activeLabel = 'On',
  inactiveLabel = 'Off',
}: {
  label: string
  detail?: string
  active: boolean
  unavailable?: boolean
  activeLabel?: string
  inactiveLabel?: string
}) {
  const stateLabel = unavailable ? 'Unavailable' : active ? activeLabel : inactiveLabel
  return (
    <div
      className={`device-row${active ? ' is-active' : ' is-inactive'}${unavailable ? ' is-unavailable' : ''}`}
      aria-label={`${label}: ${stateLabel}${detail ? `. ${detail}` : ''}`}
      title={`${label}: ${stateLabel}${detail ? ` · ${detail}` : ''}`}
    >
      <span className="device-label">{label}</span>
      <i className="passive-device-state" aria-hidden="true" />
      <span className="sr-only">{stateLabel}</span>
    </div>
  )
}

export function DeviceControls({
  light,
  pump,
  display,
  system,
}: {
  light: Light
  pump: WaterPump
  display: Display
  system: SystemStatus
}) {
  const lightOn = light.last_command_state === 'on'
  const pumpOn = pump.state === 'running'
  const scheduleLabel = `${formatHour(display.schedule_on_hour)}–${formatHour(display.schedule_off_hour)}`

  return (
    <section className="device-controls passive-controls" aria-label="Home status">
      <StatusItem label="Light" active={lightOn} unavailable={!light.available} />
      <StatusItem label="Plant pump" active={pumpOn} unavailable={!pump.available && !pumpOn} />
      <StatusItem label="Screen" active={display.state === 'visible'} />
      <StatusItem
        label="Bluetooth"
        detail={`${system.bluetooth_device_name ?? 'Speaker'}${system.bluetooth_is_default_output ? '' : ' · not current output'}`}
        active={system.bluetooth_status === 'connected'}
        unavailable={system.bluetooth_status !== 'connected'}
        activeLabel="Connected"
      />
      <StatusItem label="Schedule" detail={scheduleLabel} active={display.schedule_enabled} />
    </section>
  )
}
