import { useEffect, useRef, useState, type CSSProperties } from 'react'

type Props = {
  volumePercent: number | null
  outputLabel: string
  available: boolean
  pending: boolean
  onSetVolume: (volumePercent: number) => void
}

export function SystemVolumeBar({ volumePercent, outputLabel, available, pending, onSetVolume }: Props) {
  const [localVolume, setLocalVolume] = useState(volumePercent ?? 0)
  const commitTimer = useRef<number | null>(null)
  const lastCommitted = useRef(volumePercent ?? 0)

  useEffect(() => {
    if (volumePercent !== null) {
      setLocalVolume(volumePercent)
      lastCommitted.current = volumePercent
    }
  }, [volumePercent])

  useEffect(() => () => {
    if (commitTimer.current !== null) window.clearTimeout(commitTimer.current)
  }, [])

  function commitVolume(value: number, immediate = false) {
    if (!available || pending || value === lastCommitted.current) return
    if (commitTimer.current !== null) {
      window.clearTimeout(commitTimer.current)
      commitTimer.current = null
    }
    if (immediate) {
      lastCommitted.current = value
      onSetVolume(value)
      return
    }
    commitTimer.current = window.setTimeout(() => {
      lastCommitted.current = value
      onSetVolume(value)
      commitTimer.current = null
    }, 200)
  }

  return (
    <div className={`system-volume${available ? '' : ' is-unavailable'}`}>
      <div className="system-volume-header">
        <span className="system-volume-label">{outputLabel}</span>
        <span className="system-volume-value">{available ? `${localVolume}%` : 'Unavailable'}</span>
      </div>
      <input
        type="range"
        className="system-volume-slider"
        min={0}
        max={100}
        step={1}
        value={localVolume}
        disabled={!available}
        style={{ '--volume-fill': `${localVolume}%` } as CSSProperties}
        aria-label={`${outputLabel} volume`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={localVolume}
        onChange={(event) => {
          const value = Number(event.target.value)
          setLocalVolume(value)
          commitVolume(value)
        }}
        onPointerUp={(event) => commitVolume(Number(event.currentTarget.value), true)}
        onKeyUp={(event) => commitVolume(Number(event.currentTarget.value), true)}
      />
    </div>
  )
}
