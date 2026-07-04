type Props = {
  sensorStatus: string
  broadLinkStatus: string
  temperature: number | null
  humidity: number | null
  feedback: string | null
}

export function SystemStrip({ sensorStatus, broadLinkStatus, temperature, humidity, feedback }: Props) {
  return (
    <section className="system-strip" aria-label="System status">
      <p>Sensor <span className={`status status-${sensorStatus.toLowerCase()}`}>{sensorStatus}</span></p>
      <p className="environment-summary">Room {temperature ?? '—'}°C · {humidity ?? '—'}%</p>
      <p>BroadLink <span className={`status status-${broadLinkStatus.toLowerCase()}`}>{broadLinkStatus}</span></p>
      <p className="command-feedback" aria-live="polite">{feedback}</p>
    </section>
  )
}
