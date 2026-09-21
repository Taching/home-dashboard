import { useState } from 'react'
import { askCoach } from '../lib/api'
import { SparklesIcon } from './icons'

export function AskCoachButton({ sessionId }: { sessionId: string }) {
  const [pending, setPending] = useState(false)
  const [advice, setAdvice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const ask = () => {
    if (pending) return
    setPending(true)
    setError(null)
    void askCoach(sessionId)
      .then((response) => setAdvice(response.advice))
      .catch(() => setError('Coach is unavailable. Try again.'))
      .finally(() => setPending(false))
  }

  return (
    <div className="workout-section workout-chili coach-panel">
      <div className="workout-form">
        <button type="submit" className="coach-ask-button" onClick={ask} disabled={pending}>
          <SparklesIcon size={16} />
          {pending ? 'Asking coach…' : advice ? 'Ask again' : 'Ask coach'}
        </button>
      </div>
      {error && <p className="workout-status is-error">{error}</p>}
      {advice && (
        <div className="coach-advice">
          <span className="coach-advice-label">Chili says</span>
          <p className="workout-advice">{advice}</p>
        </div>
      )}
    </div>
  )
}
