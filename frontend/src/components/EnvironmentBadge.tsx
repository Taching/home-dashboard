type Props = {
  temperature: number | null
  humidity: number | null
}

export function EnvironmentBadge({ temperature, humidity }: Props) {
  if (temperature === null || humidity === null) {
    return (
      <div className="environment-badge is-empty" aria-label="Sensor readings unavailable">
        <span className="environment-badge-label">Room</span>
        <span>Sensor offline</span>
      </div>
    )
  }

  return (
    <div
      className="environment-badge"
      aria-label={`Room ${temperature.toFixed(1)} degrees Celsius, ${humidity.toFixed(0)} percent humidity`}
    >
      <span className="environment-badge-label">Room</span>
      <strong>{temperature.toFixed(1)}<small>°C</small></strong>
      <span>{humidity.toFixed(0)}% humidity</span>
    </div>
  )
}
