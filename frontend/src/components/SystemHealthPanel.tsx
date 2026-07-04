import type { CSSProperties } from 'react'
import type { SystemStatus } from '../types'

function percentLabel(value: number | null) {
  return value === null ? '--' : `${value.toFixed(0)}%`
}

function temperatureLabel(value: number | null) {
  return value === null ? '--' : `${value.toFixed(1)}°`
}

function memoryLabel(system: SystemStatus) {
  if (system.memory_used_mb === null || system.memory_total_mb === null) return '--'
  return `${system.memory_used_mb} / ${system.memory_total_mb} MB`
}

function storageLabel(system: SystemStatus) {
  if (system.storage_free_gb === null || system.storage_total_gb === null) return '--'
  return `${system.storage_free_gb.toFixed(1)} GB free`
}

function statusClass(value: number | null) {
  if (value === null) return ''
  if (value >= 90) return ' is-hot'
  if (value >= 70) return ' is-warm'
  return ''
}

function temperatureStatusClass(value: number | null) {
  if (value === null) return ''
  if (value >= 75) return ' is-hot'
  if (value >= 65) return ' is-warm'
  return ''
}

function gaugeStyle(value: number | null) {
  return { '--value': `${Math.max(0, Math.min(value ?? 0, 100))}%` } as CSSProperties
}

type HealthMetricProps = {
  label: string
  value: string
  detail?: string
  percent?: number | null
  className?: string
}

function HealthMetric({ label, value, detail, percent, className = '' }: HealthMetricProps) {
  return (
    <div className={`health-metric${className}`}>
      <dt>{label}</dt>
      <dd>
        <span>{value}</span>
        {detail && <small>{detail}</small>}
      </dd>
      {percent !== undefined && <i aria-hidden="true" style={gaugeStyle(percent)} />}
    </div>
  )
}

function BluetoothIcon() {
  return (
    <svg className="health-bluetooth-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M17.71 7.71 12 2h-1v7.59L6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 11 14.41V22h1l5.71-5.71-4.3-4.29 4.3-4.29zM13 5.83l1.88 1.88L13 9.59V5.83zm1.88 10.46L13 18.17v-3.76l1.88 1.88z" />
    </svg>
  )
}

function bluetoothLine(system: SystemStatus) {
  if (system.bluetooth_status === 'unavailable') return 'Bluetooth unavailable'
  if (system.bluetooth_status === 'disconnected') return 'No speaker connected'
  const name = system.bluetooth_device_name ?? 'Bluetooth speaker'
  return system.bluetooth_is_default_output ? `${name} · default output` : name
}

function bluetoothClass(system: SystemStatus) {
  if (system.bluetooth_status === 'connected') return ' is-connected'
  if (system.bluetooth_status === 'disconnected') return ' is-disconnected'
  return ' is-unavailable'
}

export function SystemHealthPanel({ system }: { system: SystemStatus }) {
  return (
    <section className="health-panel" aria-label="System health">
      <dl>
        <HealthMetric
          label="CPU temp"
          value={temperatureLabel(system.cpu_temperature_c)}
          className={temperatureStatusClass(system.cpu_temperature_c)}
        />
        <HealthMetric
          label="CPU load"
          value={percentLabel(system.load_percent)}
          percent={system.load_percent}
          className={statusClass(system.load_percent)}
        />
        <HealthMetric
          label="Memory"
          value={percentLabel(system.memory_used_percent)}
          detail={memoryLabel(system)}
          percent={system.memory_used_percent}
          className={statusClass(system.memory_used_percent)}
        />
        <HealthMetric
          label="Storage"
          value={percentLabel(system.storage_used_percent)}
          detail={storageLabel(system)}
          percent={system.storage_used_percent}
          className={statusClass(system.storage_used_percent)}
        />
      </dl>
      <p className={`health-bluetooth${bluetoothClass(system)}`} aria-label={`Bluetooth audio: ${bluetoothLine(system)}`}>
        <BluetoothIcon />
        <span>{bluetoothLine(system)}</span>
      </p>
    </section>
  )
}
