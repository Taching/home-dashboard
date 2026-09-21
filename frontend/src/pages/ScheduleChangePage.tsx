import { useEffect, useState, type FormEvent } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { requestScheduleChange } from '../lib/api'
import type { PlanAdjustment } from '../types'
import '../workout.css'

function todayStamp() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' })
}

type Phase = 'idle' | 'sent' | 'done' | 'error'

export function ScheduleChangePage() {
  const [instruction, setInstruction] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const [sentText, setSentText] = useState('')
  const [decision, setDecision] = useState<PlanAdjustment | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    document.documentElement.classList.add('is-workout')
    document.title = 'Change my schedule · Chili'
    return () => document.documentElement.classList.remove('is-workout')
  }, [])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const text = instruction.trim()
    if (phase === 'sent' || !text) return

    // Optimistic: acknowledge the send immediately, reconcile with the real
    // result (success or failure) once the request comes back.
    setSentText(text)
    setInstruction('')
    setDecision(null)
    setError(null)
    setPhase('sent')

    void requestScheduleChange(text)
      .then((response) => {
        setDecision(response.decision)
        setPhase('done')
      })
      .catch((err: Error) => {
        setError(err.message || 'Could not understand that. Try rephrasing.')
        setInstruction(text)
        setPhase('error')
      })
  }

  const busy = phase === 'sent'

  return (
    <div className="workout-page">
      <header className="workout-top">
        <span className="workout-brand">
          <img src={chiliLogo} alt="" />
          Chili
        </span>
        <a className="workout-back" href={`/daily/${todayStamp()}`}>Daily</a>
      </header>
      <section className="workout-hero">
        <p>Something changed</p>
        <h1>Change my schedule</h1>
        <span>Storm, sick, emergency — tell Chili what happened and it will replan.</span>
      </section>
      <section className="workout-section">
        <form className="workout-form" onSubmit={submit}>
          <label className="workout-field">
            <span>What's going on?</span>
            <textarea
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              disabled={busy}
              maxLength={2000}
              placeholder="e.g. there's a storm today, I'm sick, emergency — need to move things"
            />
          </label>
          <button type="submit" disabled={busy || !instruction.trim()}>
            Change my schedule
          </button>
        </form>
      </section>
      {(phase === 'sent' || phase === 'done') && (
        <section className="workout-section workout-chili">
          <p className="workout-done-badge">✓ Sent</p>
          <p className="workout-note">“{sentText}”</p>
          {phase === 'sent' && <p className="workout-status">Chili is adjusting your plan…</p>}
          {phase === 'done' && decision && (
            <>
              <p className="workout-advice">{decision.banner}</p>
              <div className="daily-plan-change">
                <strong>How</strong>
                <ul>{decision.how.map((line) => <li key={line}>{line}</li>)}</ul>
                <strong>Why</strong>
                <ul>{decision.why.map((line) => <li key={line}>{line}</li>)}</ul>
              </div>
            </>
          )}
        </section>
      )}
      {phase === 'error' && (
        <p className="workout-status" role="alert">{error}</p>
      )}
    </div>
  )
}
