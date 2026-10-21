import { useEffect, useMemo, useState } from 'react'
import { PageSkeleton } from '../components/PageSkeleton'
import { useLiveResource } from '../hooks/useLiveResource'
import {
  fetchExercises,
  fetchExercise,
  fetchExerciseFilters,
  fetchExerciseAlternatives,
  setExerciseOverride,
  type ExerciseItem,
  type AlternativeResult,
  type ExerciseFilters,
} from '../lib/api'
import { SearchIcon, ChevronDownIcon, ChevronUpIcon, CheckCircleIcon, XCircleIcon, StarIcon } from '../components/icons'
import { PhoneChrome } from '../components/PhoneChrome'
import { PhoneNav } from '../components/PhoneNav'
import '../workout.css'

function formatEquipment(equipment: string[]): string {
  if (!equipment.length) return 'None'
  return equipment.map((e) => e.replace(/\+/g, ' + ')).join(', ')
}

function formatMuscles(muscles: string[]): string {
  if (!muscles.length) return 'None'
  return muscles.join(', ')
}

function formatTags(tags: string[]): string {
  if (!tags.length) return 'None'
  return tags.join(', ')
}

function DifficultyBadge({ difficulty }: { difficulty: string }) {
  const colors: Record<string, string> = {
    beginner: 'is-easy',
    intermediate: 'is-normal',
    advanced: 'is-hard',
  }
  return <span className={`workout-pill ${colors[difficulty] || 'is-normal'}`}>{difficulty}</span>
}

function CategoryBadge({ category }: { category: string }) {
  return <span className="workout-pill is-deload">{category}</span>
}

function ExerciseCard({
  exercise,
  onSelect,
  compact = false,
}: {
  exercise: ExerciseItem
  onSelect: () => void
  compact?: boolean
}) {
  return (
    <button type="button" className="workout-plan-link" onClick={onSelect}>
      <strong>{exercise.name}</strong>
      {!compact && (
        <span>
          {exercise.movement_pattern.replace(/_/g, ' ')} · {exercise.primary_region}
          {exercise.equipment.length > 0 && ` · ${exercise.equipment[0].split('+')[0]}`}
        </span>
      )}
      {compact && <span>{exercise.substitution_group.replace(/_/g, ' ')}</span>}
    </button>
  )
}

function ExerciseDetail({
  exercise,
  onBack,
  onFindAlternatives,
}: {
  exercise: ExerciseItem
  onBack: () => void
  onFindAlternatives: () => void
}) {
  return (
    <div className="workout-section">
      <button type="button" className="workout-back" onClick={onBack}>
        ← Back
      </button>
      <h2>{exercise.name}</h2>
      {exercise.aliases.length > 0 && (
        <p className="workout-status">Also known as: {exercise.aliases.join(', ')}</p>
      )}

      <div className="workout-hero-meta">
        <CategoryBadge category={exercise.category} />
        <DifficultyBadge difficulty={exercise.difficulty} />
      </div>

      <div className="workout-checks">
        <div className="workout-check">
          <span>
            <strong>Movement Pattern</strong>
            <em>{exercise.movement_pattern.replace(/_/g, ' ')}</em>
          </span>
        </div>
        <div className="workout-check">
          <span>
            <strong>Training Intent</strong>
            <em>{exercise.training_intent}</em>
          </span>
        </div>
        <div className="workout-check">
          <span>
            <strong>Primary Region</strong>
            <em>{exercise.primary_region.replace(/_/g, ' ')}</em>
          </span>
        </div>
        <div className="workout-check">
          <span>
            <strong>Primary Muscles</strong>
            <em>{formatMuscles(exercise.primary_muscles)}</em>
          </span>
        </div>
        <div className="workout-check">
          <span>
            <strong>Equipment</strong>
            <em>{formatEquipment(exercise.equipment)}</em>
          </span>
        </div>
        <div className="workout-check">
          <span>
            <strong>Substitution Group</strong>
            <em>{exercise.substitution_group.replace(/_/g, ' ')}</em>
          </span>
        </div>
        <div className="workout-check">
          <span>
            <strong>Movement Speed</strong>
            <em>{exercise.movement_speed}</em>
          </span>
        </div>
        <div className="workout-check">
          <span>
            <strong>Laterality</strong>
            <em>{exercise.laterality.replace(/_/g, ' ')}</em>
          </span>
        </div>
        <div className="workout-check">
          <span>
            <strong>Plane</strong>
            <em>{exercise.plane}</em>
          </span>
        </div>
        {exercise.bjj_tags.length > 0 && (
          <div className="workout-check">
            <span>
              <strong>BJJ Tags</strong>
              <em>{formatTags(exercise.bjj_tags)}</em>
            </span>
          </div>
        )}
      </div>

      {exercise.risk_notes && (
        <div className="workout-section workout-chili">
          <h3>Note</h3>
          <p className="workout-advice">{exercise.risk_notes}</p>
        </div>
      )}

      <button
        type="button"
        className="workout-primary-button"
        onClick={onFindAlternatives}
      >
        Find alternatives
      </button>
    </div>
  )
}

function AlternativeCard({
  alternative,
  onSelect,
  onPrefer,
  onExclude,
}: {
  alternative: AlternativeResult
  onSelect: () => void
  onPrefer: () => void
  onExclude: () => void
}) {
  const [showReasons, setShowReasons] = useState(false)

  return (
    <div className="workout-check">
      <div style={{ flex: 1 }}>
        <button
          type="button"
          className="workout-plan-link"
          onClick={onSelect}
          style={{ width: '100%', textAlign: 'left' }}
        >
          <strong>{alternative.name}</strong>
          <span>Score: {alternative.score}</span>
        </button>
        <button
          type="button"
          className="workout-status"
          onClick={() => setShowReasons(!showReasons)}
          style={{ background: 'none', border: 'none', padding: '0.25rem 0', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
        >
          {showReasons ? <ChevronUpIcon size={14} /> : <ChevronDownIcon size={14} />}
          {showReasons ? 'Hide reasons' : 'Show reasons'}
        </button>
        {showReasons && (
          <ul style={{ margin: '0.5rem 0', paddingLeft: '1.25rem', fontSize: '0.875rem' }}>
            {alternative.why.map((reason, i) => (
              <li key={i}>{reason}</li>
            ))}
          </ul>
        )}
        {alternative.tradeoff && (
          <p className="workout-status" style={{ color: 'var(--color-warning, #e67e22)', marginTop: '0.25rem' }}>
            Tradeoff: {alternative.tradeoff}
          </p>
        )}
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
          <button
            type="button"
            className="workout-pill is-easy"
            onClick={onPrefer}
            title="Prefer this alternative"
          >
            <StarIcon size={12} /> Prefer
          </button>
          <button
            type="button"
            className="workout-pill is-hard"
            onClick={onExclude}
            title="Exclude this alternative"
          >
            <XCircleIcon size={12} /> Exclude
          </button>
        </div>
      </div>
    </div>
  )
}

function AlternativesView({
  sourceExercise,
  onBack,
  onSelectAlternative,
}: {
  sourceExercise: ExerciseItem
  onBack: () => void
  onSelectAlternative: (slug: string) => void
}) {
  const [alternatives, setAlternatives] = useState<AlternativeResult[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [equipment, setEquipment] = useState<string[]>([])
  const [allowAdvanced, setAllowAdvanced] = useState(false)
  const [showEquipmentPicker, setShowEquipmentPicker] = useState(true)

  const commonEquipment = [
    'barbell', 'dumbbell', 'kettlebell', 'bodyweight', 'bench', 'cable',
    'pull_up_bar', 'resistance_band', 'rack', 'trap_bar', 'box', 'mat',
  ]

  const handleSearch = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchExerciseAlternatives(sourceExercise.slug, {
        available_equipment: equipment,
        allow_advanced: allowAdvanced,
        max_results: 10,
      })
      setAlternatives(result.alternatives)
      setShowEquipmentPicker(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load alternatives')
    } finally {
      setLoading(false)
    }
  }

  const handleOverride = async (target: string, decision: 'prefer' | 'exclude') => {
    try {
      await setExerciseOverride(sourceExercise.slug, target, decision)
      setError(null)
      handleSearch()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save prefer/exclude.')
    }
  }

  const toggleEquipment = (item: string) => {
    setEquipment((prev) =>
      prev.includes(item) ? prev.filter((e) => e !== item) : [...prev, item]
    )
  }

  return (
    <div className="workout-section">
      <button type="button" className="workout-back" onClick={onBack}>
        ← Back to {sourceExercise.name}
      </button>
      <h2>Alternatives for {sourceExercise.name}</h2>

      {showEquipmentPicker ? (
        <>
          <p className="workout-status">Select the equipment you have available:</p>
          <div className="workout-checks" style={{ marginBottom: '1rem' }}>
            {commonEquipment.map((item) => (
              <button
                key={item}
                type="button"
                className={`workout-pill ${equipment.includes(item) ? 'is-easy' : ''}`}
                onClick={() => toggleEquipment(item)}
                style={{ margin: '0.25rem' }}
              >
                {equipment.includes(item) && <CheckCircleIcon size={12} />}
                {item.replace(/_/g, ' ')}
              </button>
            ))}
          </div>
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={allowAdvanced}
                onChange={(e) => setAllowAdvanced(e.target.checked)}
              />
              Include advanced exercises
            </label>
          </div>
          <button
            type="button"
            className="workout-primary-button"
            onClick={handleSearch}
            disabled={equipment.length === 0}
          >
            Search alternatives
          </button>
        </>
      ) : (
        <>
          <p className="workout-status">
            Equipment: {equipment.length > 0 ? equipment.map((e) => e.replace(/_/g, ' ')).join(', ') : 'None'}
            <button
              type="button"
              className="workout-pill"
              onClick={() => setShowEquipmentPicker(true)}
              style={{ marginLeft: '0.5rem' }}
            >
              Change
            </button>
          </p>

          {loading && <p className="workout-status">Loading alternatives...</p>}
          {error && <p className="workout-status" style={{ color: 'red' }}>{error}</p>}

          {alternatives && alternatives.length === 0 && (
            <p className="workout-status">No alternatives found with this equipment combination.</p>
          )}

          {alternatives && alternatives.length > 0 && (
            <div className="workout-checks">
              {alternatives.map((alt) => (
                <AlternativeCard
                  key={alt.slug}
                  alternative={alt}
                  onSelect={() => onSelectAlternative(alt.slug)}
                  onPrefer={() => handleOverride(alt.slug, 'prefer')}
                  onExclude={() => handleOverride(alt.slug, 'exclude')}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function FilterSection({
  filters,
  activeFilters,
  onFilterChange,
}: {
  filters: ExerciseFilters
  activeFilters: Record<string, string>
  onFilterChange: (key: string, value: string) => void
}) {
  const [expanded, setExpanded] = useState(false)

  const filterGroups = [
    { key: 'pattern', label: 'Movement', options: filters.movement_patterns },
    { key: 'intent', label: 'Intent', options: filters.training_intents },
    { key: 'region', label: 'Region', options: filters.primary_regions },
    { key: 'category', label: 'Category', options: filters.categories },
  ]

  return (
    <div className="workout-section">
      <button
        type="button"
        className="workout-status"
        onClick={() => setExpanded(!expanded)}
        style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.25rem', width: '100%', justifyContent: 'space-between' }}
      >
        <span>Filters</span>
        {expanded ? <ChevronUpIcon size={16} /> : <ChevronDownIcon size={16} />}
      </button>

      {expanded && (
        <div style={{ marginTop: '0.5rem' }}>
          {filterGroups.map((group) => (
            <div key={group.key} style={{ marginBottom: '0.75rem' }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>
                {group.label}
              </label>
              <select
                value={activeFilters[group.key] || ''}
                onChange={(e) => onFilterChange(group.key, e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  borderRadius: '0.25rem',
                  border: '1px solid var(--color-border)',
                  background: 'var(--color-bg)',
                  color: 'var(--color-text)',
                  marginTop: '0.25rem',
                }}
              >
                <option value="">All</option>
                {group.options.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt.replace(/_/g, ' ')}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

type ViewState =
  | { type: 'list' }
  | { type: 'detail'; slug: string }
  | { type: 'alternatives'; sourceSlug: string }

function viewFromPath(): ViewState {
  const match = window.location.pathname.match(/^\/training\/exercises\/([^/]+)\/?$/)
  if (match?.[1]) return { type: 'detail', slug: decodeURIComponent(match[1]) }
  return { type: 'list' }
}

function setPathForView(next: ViewState) {
  if (next.type === 'list') {
    window.history.replaceState(null, '', '/training/exercises')
    return
  }
  if (next.type === 'detail') {
    window.history.replaceState(null, '', `/training/exercises/${encodeURIComponent(next.slug)}`)
  }
}

export function ExerciseLibraryPage() {
  const [view, setView] = useState<ViewState>(viewFromPath)
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})

  const go = (next: ViewState) => {
    setView(next)
    if (next.type !== 'alternatives') setPathForView(next)
  }

  const filterQueryKey = useMemo(() => ['exercise-filters'] as const, [])
  const { data: filterOptions } = useLiveResource(
    (signal) => fetchExerciseFilters(signal),
    { queryKey: filterQueryKey },
  )

  const searchParams = useMemo(() => ({
    search: search || undefined,
    ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)),
  }), [search, filters])

  const exercisesQueryKey = useMemo(
    () => ['exercises', JSON.stringify(searchParams)] as const,
    [searchParams],
  )
  const { data: exercisesData, error: exercisesError } = useLiveResource(
    (signal) => fetchExercises(searchParams, signal),
    { queryKey: exercisesQueryKey },
  )

  const detailSlug = view.type === 'detail' ? view.slug : view.type === 'alternatives' ? view.sourceSlug : null
  const detailQueryKey = useMemo(() => ['exercise', detailSlug] as const, [detailSlug])
  const { data: selectedExercise } = useLiveResource(
    (signal) => (detailSlug ? fetchExercise(detailSlug, signal) : Promise.resolve(null)),
    { queryKey: detailQueryKey, enabled: detailSlug !== null },
  )

  useEffect(() => {
    document.documentElement.classList.add('is-workout')
    document.title = 'Exercise Library · Chili'
    return () => document.documentElement.classList.remove('is-workout')
  }, [])

  const handleFilterChange = (key: string, value: string) => {
    setFilters((prev) => {
      const next = { ...prev }
      if (value) next[key] = value
      else delete next[key]
      return next
    })
  }

  if (!filterOptions && !exercisesData) {
    return <PageSkeleton />
  }

  return (
    <div className="workout-page">
      <PhoneChrome />

      <section className="workout-hero">
        <p>Exercise Library</p>
        <h1>{view.type === 'list' ? 'Browse Exercises' : selectedExercise?.name || 'Loading...'}</h1>
        <span>{exercisesData?.count ?? 0} exercises available</span>
      </section>

      {view.type === 'list' && (
        <>
          <div className="workout-section">
            <label className="exercise-search">
              <SearchIcon size={18} />
              <input
                type="search"
                placeholder="Search exercises..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
          </div>

          {filterOptions && (
            <FilterSection
              filters={filterOptions}
              activeFilters={filters}
              onFilterChange={handleFilterChange}
            />
          )}

          {exercisesError && (
            <p className="workout-status is-error" role="alert">
              {exercisesError}
            </p>
          )}

          <section className="workout-section">
            <h2>Exercises</h2>
            {exercisesData?.exercises.length === 0 ? (
              <p className="workout-empty">No exercises match your search.</p>
            ) : (
              <div className="workout-checks exercise-list">
                {exercisesData?.exercises.map((exercise) => (
                  <ExerciseCard
                    key={exercise.slug}
                    exercise={exercise}
                    onSelect={() => go({ type: 'detail', slug: exercise.slug })}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      )}

      {view.type === 'detail' && selectedExercise && (
        <ExerciseDetail
          exercise={selectedExercise}
          onBack={() => go({ type: 'list' })}
          onFindAlternatives={() => setView({ type: 'alternatives', sourceSlug: selectedExercise.slug })}
        />
      )}

      {view.type === 'alternatives' && selectedExercise && (
        <AlternativesView
          sourceExercise={selectedExercise}
          onBack={() => go({ type: 'detail', slug: view.sourceSlug })}
          onSelectAlternative={(slug) => go({ type: 'detail', slug })}
        />
      )}
      <PhoneNav />
    </div>
  )
}
