import { useState } from 'react'
import { askCoach } from '../lib/api'

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
    <div className="workout-section workout-chili">
      <div className="workout-form">
        <button type="submit" onClick={ask} disabled={pending}>
          {pending ? 'Asking coach…' : advice ? 'Ask again' : 'Ask coach'}
        </button>
      </div>
      {error && <p className="workout-status">{error}</p>}
      {advice && <p className="workout-advice">{advice}</p>}
    </div>
  )
}
