import { doneMarkLabel } from '../lib/workoutMatch'
import type { DailyBriefing } from '../types'

function splitAdvice(text: string) {
  const parts = text.split(/(?<=[.!?])\s+/).map((part) => part.trim()).filter(Boolean)
  const tomorrowIndex = parts.findIndex((part) => /^Tomorrow\b/i.test(part))
  const rest = tomorrowIndex >= 0 ? parts.slice(0, tomorrowIndex) : parts
  const tomorrow = tomorrowIndex >= 0 ? parts.slice(tomorrowIndex).join(' ') : null
  return {
    lead: rest[0] ?? text,
    points: rest.slice(1),
    tomorrow,
  }
}

const WINDOW_LABEL = {
  morning: 'MORNING',
  lunch: 'LUNCH',
  evening: 'EVENING',
} as const

function chiliEyebrow(window: DailyBriefing['advice_window']) {
  return window ? `CHILI · ${WINDOW_LABEL[window]}` : 'CHILI · TODAY'
}

export function ChiliAdvice({ plan }: { plan: DailyBriefing | null }) {
  const advice = plan?.advice?.trim()
  const eyebrow = chiliEyebrow(plan?.advice_window)
  const doneLabel = doneMarkLabel(plan?.today?.training?.status ?? plan?.workout?.status)
  if (!advice) {
    return (
      <section className={`chili-advice${doneLabel ? ' is-done' : ''}`} aria-label="Chili's advice for today">
        <p className="eyebrow">{eyebrow}{doneLabel && <span className="chili-advice-done">✓ {doneLabel}</span>}</p>
        <p className="chili-advice-lead">Chili is reading the day.</p>
      </section>
    )
  }

  const { lead, points, tomorrow } = splitAdvice(advice)
  return (
    <section className={`chili-advice${doneLabel ? ' is-done' : ''}`} aria-label="Chili's advice for today">
      <p className="eyebrow">{eyebrow}{doneLabel && <span className="chili-advice-done">✓ {doneLabel}</span>}</p>
      <p className="chili-advice-lead">{lead}</p>
      {points.length > 0 && (
        <ul>
          {points.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      )}
      {tomorrow && <p className="chili-advice-next">{tomorrow}</p>}
    </section>
  )
}
