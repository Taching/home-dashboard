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

export function SystemHealthPanel({ system }: { system: SystemStatus }) {
  return (
    <section className="health-panel" aria-labelledby="health-title">
      <div className="health-heading">
        <div>
          <p className="eyebrow">RASPBERRY PI</p>
          <h3 id="health-title">System health</h3>
        </div>
        <p>1m load {system.load_1m === null ? '--' : system.load_1m.toFixed(2)}</p>
      </div>
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
    </section>
  )
}
