import { formatClock } from '../lib/format'
import type { ActivityEvent, VoiceEventDirection, VoiceState, VoiceStatus } from '../types'

export const voiceLabels: Record<VoiceState, string> = {
  offline: 'Voice offline',
  idle: 'Say Hey Chili',
  listening: 'Listening…',
  thinking: 'Thinking…',
  complete: 'Done',
  error: 'Try again',
}

const directionGlyph: Record<VoiceEventDirection, string> = {
  in: '→',
  out: '←',
  info: '•',
}

function eventTime(at: string) {
  return formatClock(new Date(at))
}

function eventKey(event: ActivityEvent) {
  return `${event.at}:${event.direction}:${event.service}:${event.detail}`
}

function scrollLatestEventIntoView(element: HTMLElement | null) {
  element?.scrollIntoView({ block: 'end' })
}

type VoicePipelinePanelProps = {
  status: VoiceStatus
  events: ActivityEvent[]
}

export function VoicePipelinePanel({ status, events }: VoicePipelinePanelProps) {
  return (
    <section
      className={`voice-pipeline voice-pipeline-sidebar is-${status.state}`}
      aria-label="Activity feed"
      aria-live="polite"
    >
      {(status.transcript || status.message) && (
        <div className="voice-pipeline-caption">
          {status.transcript && <p className="voice-transcript">“{status.transcript}”</p>}
          {status.message && <p className="voice-message">{status.message}</p>}
        </div>
      )}
      <ol className="voice-pipeline-feed">
        {events.length === 0 ? (
          <li className="voice-pipeline-row is-empty">Waiting for activity…</li>
        ) : (
          events.map((event, index) => (
            <li
              key={eventKey(event)}
              ref={index === events.length - 1 ? scrollLatestEventIntoView : undefined}
              className={`voice-pipeline-row is-${event.direction} svc-${event.service}`}
            >
              <time dateTime={event.at}>{eventTime(event.at)}</time>
              <span className="voice-pipeline-arrow" aria-hidden="true">{directionGlyph[event.direction]}</span>
              <span className="voice-pipeline-service">{event.service}</span>
              <span className="voice-pipeline-detail">{event.detail}</span>
            </li>
          ))
        )}
      </ol>
    </section>
  )
}
