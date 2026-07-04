type Props = {
  active: boolean
}

export function SpotifyEqualizer({ active }: Props) {
  return (
    <span className={`spotify-equalizer${active ? ' is-active' : ''}`} aria-hidden="true">
      <i /><i /><i /><i />
    </span>
  )
}
