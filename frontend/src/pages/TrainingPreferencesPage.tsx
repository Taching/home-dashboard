import { useEffect, useMemo, useState, type FormEvent } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { fetchTrainingPreferences, saveTrainingPreferences } from '../lib/api'
import { useLiveResource } from '../hooks/useLiveResource'
import '../workout.css'

function todayStamp() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' })
}

export function TrainingPreferencesPage() {
  const queryKey = useMemo(() => ['training-preferences'] as const, [])
  const { data, error } = useLiveResource((signal) => fetchTrainingPreferences(signal), { queryKey })
  const [notes, setNotes] = useState('')
  const [loadedNotes, setLoadedNotes] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    document.documentElement.classList.add('is-workout')
    document.title = 'Training preferences · Chili'
    return () => document.documentElement.classList.remove('is-workout')
  }, [])

  if (data && data.notes !== loadedNotes) {
    setLoadedNotes(data.notes ?? '')
    setNotes(data.notes ?? '')
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setSaved(false)
    void saveTrainingPreferences(notes)
      .then(() => setSaved(true))
      .finally(() => setPending(false))
  }

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
        <p>Settings</p>
        <h1>Training preferences</h1>
        <span>Free text only. This flavors Chili's advice and replans — it never changes the schedule rules.</span>
      </section>
      <section className="workout-section">
        <form className="workout-form" onSubmit={submit}>
          <label className="workout-field">
            <span>Notes (injuries, likes/dislikes, constraints…)</span>
            <textarea
              value={notes}
              onChange={(event) => { setNotes(event.target.value); setSaved(false) }}
              maxLength={2000}
              rows={8}
            />
          </label>
          <button type="submit" disabled={pending}>{pending ? 'Saving…' : 'Save'}</button>
        </form>
        {saved && <p className="workout-status">Saved.</p>}
        {error && <p className="workout-status" role="alert">{error}</p>}
      </section>
    </div>
  )
}
