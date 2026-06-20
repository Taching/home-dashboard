import type { Reading } from '../types'

export function TemperatureTrend({ readings }: { readings: Reading[] }) {
  const values = readings.map((reading) => reading.temperature_c)
  if (values.length < 2) {
    return <p className="empty-trend">Trend appears after two recorded readings.</p>
  }

  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const points = readings.map((reading, index) => {
    const x = (index / (readings.length - 1)) * 100
    const y = 100 - ((reading.temperature_c - min) / range) * 84 - 8
    return `${x},${y}`
  }).join(' ')

  return (
    <svg className="trend" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="24 hour temperature trend" role="img">
      <polyline points={points} />
    </svg>
  )
}
