type Props = {
  sensorStatus: string
  broadLinkStatus: string
  feedback: string | null
}

export function SystemStrip({ sensorStatus, broadLinkStatus, feedback }: Props) {
  return (
    <section className="system-strip" aria-label="System status">
      <p>Sensor <span className={`status status-${sensorStatus.toLowerCase()}`}>{sensorStatus}</span></p>
      <p>BroadLink <span className={`status status-${broadLinkStatus.toLowerCase()}`}>{broadLinkStatus}</span></p>
      <p className="command-feedback" aria-live="polite">{feedback}</p>
      <p className="shortcuts">L light · R refresh · S screen</p>
    </section>
  )
}
