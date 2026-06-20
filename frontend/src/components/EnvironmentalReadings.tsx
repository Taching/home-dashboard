import { formatRelativeTime } from '../lib/format'

type Props = {
  temperature: number | null
  humidity: number | null
  updatedAt: string | null
  stale: boolean
}

export function EnvironmentalReadings({ temperature, humidity, updatedAt, stale }: Props) {
  return (
    <section className="readings" aria-label="Current room readings">
      <div>
        <p>Temperature</p>
        <strong>{temperature ?? '—'}<small>°C</small></strong>
      </div>
      <div>
        <p>Humidity</p>
        <strong>{humidity ?? '—'}<small>%</small></strong>
      </div>
      <p className={`freshness ${stale ? 'is-stale' : ''}`}>{formatRelativeTime(updatedAt)}</p>
    </section>
  )
}
