import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { fetchTrainingPreferences, saveTrainingPreferences } from '../lib/api'
import { useLiveResource } from '../hooks/useLiveResource'
import { PhoneChrome } from '../components/PhoneChrome'
import { PhoneNav } from '../components/PhoneNav'
import { PageSkeleton } from '../components/PageSkeleton'
import '../workout.css'

export function TrainingPreferencesPage() {
  const queryKey = useMemo(() => ['training-preferences'] as const, [])
  const { data, error } = useLiveResource((signal) => fetchTrainingPreferences(signal), { queryKey })
  const [notes, setNotes] = useState('')
  const [loadedNotes, setLoadedNotes] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

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
    setSaveError(null)
    void saveTrainingPreferences(notes)
      .then(() => setSaved(true))
      .catch(() => setSaveError('Could not save preferences. Try again.'))
      .finally(() => setPending(false))
  }

  if (!data && !error) return <PageSkeleton />

  return (
    <div className="workout-page">
      <PhoneChrome />
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
          <button type="submit" className="workout-primary-button" disabled={pending}>{pending ? 'Saving…' : 'Save'}</button>
        </form>
        {saved && <p className="workout-status">Saved.</p>}
        {(error || saveError) && <p className="workout-status" role="alert">{saveError ?? error}</p>}
      </section>
      <PhoneNav />
    </div>
  )
}
