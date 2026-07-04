import type { Reading } from '../types'

const TIME_ZONE = 'Asia/Tokyo'

function hourKey(value: string) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: TIME_ZONE, month: '2-digit', day: '2-digit', hour: '2-digit', hour12: false,
  }).formatToParts(new Date(value))
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? ''
  return `${get('day')}/${get('month')} ${get('hour')}:00`
}

export function TemperatureTrend({ readings }: { readings: Reading[] }) {
  const hourly = Array.from(
    readings
      .slice()
      .sort((first, second) => new Date(first.recorded_at).getTime() - new Date(second.recorded_at).getTime())
      .reduce((groups, reading) => groups.set(hourKey(reading.recorded_at), reading), new Map<string, Reading>()),
  ).slice(-8)

  if (hourly.length === 0) {
    return <p className="empty-trend">Hourly readings appear after the first sensor record.</p>
  }

  const latest = hourly[hourly.length - 1][1]

  return (
    <div className="hourly-readings" aria-label="Recent hourly temperature and humidity readings">
      <div className="hourly-latest">
        <strong>{latest.temperature_c.toFixed(1)}<small>°C</small></strong>
        <span>{latest.humidity_percent.toFixed(0)}% humidity</span>
      </div>
      <ol>
        {hourly.map(([label, reading], index) => {
          const previous = hourly[index - 1]?.[1]
          const delta = previous ? reading.temperature_c - previous.temperature_c : 0
          return (
            <li key={label}>
              <time>{label}</time>
              <span>{reading.temperature_c.toFixed(1)}°</span>
              <span>{reading.humidity_percent.toFixed(0)}%</span>
              <small className={delta > 0.05 ? 'is-up' : delta < -0.05 ? 'is-down' : ''}>
                {index === 0 ? '—' : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}°`}
              </small>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
