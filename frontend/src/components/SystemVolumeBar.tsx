import { useState, type CSSProperties } from 'react'

type Props = {
  volumePercent: number | null
  outputLabel: string
  available: boolean
  pending: boolean
  onSetVolume: (volumePercent: number) => void
}

type VolumeState = {
  source: number | null
  local: number
}

export function SystemVolumeBar({ volumePercent, outputLabel, available, pending, onSetVolume }: Props) {
  const [volumeState, setVolumeState] = useState<VolumeState>(() => ({
    source: volumePercent,
    local: volumePercent ?? 0,
  }))
  let localVolume = volumeState.local

  if (volumePercent !== volumeState.source) {
    localVolume = volumePercent ?? volumeState.local
    setVolumeState({ source: volumePercent, local: localVolume })
  }

  function setLocalVolume(value: number) {
    setVolumeState({ source: volumePercent, local: value })
  }

  function commitVolume(value: number) {
    if (!available || pending || value === volumePercent) return
    onSetVolume(value)
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
        }}
        onPointerUp={(event) => commitVolume(Number(event.currentTarget.value))}
        onKeyUp={(event) => commitVolume(Number(event.currentTarget.value))}
        onBlur={(event) => commitVolume(Number(event.currentTarget.value))}
      />
    </div>
  )
}
