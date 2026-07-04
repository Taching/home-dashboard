import type { SpotifyNowPlaying } from '../types'
import type { PlaybackTrack } from '../hooks/useSpotifyPlayback'

type Props = {
  spotify: SpotifyNowPlaying
  playerReady: boolean
  playerActive: boolean
  playerPaused: boolean
  playerTrack: PlaybackTrack | null
  playerError: string | null
  onPlayHere: () => void
  onTogglePlayback: () => void
  onPrevious: () => void
  onNext: () => void
}

export function MediaRegion({ spotify, playerReady, playerActive, playerPaused, playerTrack, playerError, onPlayHere, onTogglePlayback, onPrevious, onNext }: Props) {
  const activeTrack = playerTrack ?? (spotify.track ? { track: spotify.track, artist: spotify.artist ?? 'Unknown artist', artworkUrl: spotify.artwork_url } : null)

  return (
    <section className="media-region" aria-label="Spotify now playing">
      <div className="region-heading">
        <div>
          <p className="eyebrow">MEDIA</p>
          <h2>Spotify</h2>
        </div>
        {activeTrack && <p>{playerActive ? (playerPaused ? 'Paused' : 'Playing') : spotify.is_playing ? 'Playing' : 'Paused'}</p>}
      </div>
      <div className={`spotify-player${activeTrack ? '' : ' is-empty'}`}>
        {activeTrack ? (
          <div className="now-playing">
            {activeTrack.artworkUrl ? <img src={activeTrack.artworkUrl} alt="" /> : <div className="artwork-fallback" aria-hidden="true">♪</div>}
            <div>
              <strong>{activeTrack.track}</strong>
              <p>{activeTrack.artist}</p>
              <small>{playerActive ? 'Chili Dashboard' : spotify.device_name}</small>
            </div>
          </div>
        ) : (
          <>
            <div className="artwork-fallback" aria-hidden="true">♪</div>
            {spotify.status === 'not_configured'
              ? <a className="setup-link" href="/api/v1/spotify/connect">Connect Spotify</a>
              : spotify.status === 'ready'
                ? <p className="setup-state">Nothing playing</p>
                : <p className="setup-state is-error">Spotify unavailable</p>}
          </>
        )}
      </div>
      {spotify.status === 'ready' && (
        <div className="player-actions">
          <div className="transport-controls" aria-label="Spotify playback controls">
            <button type="button" className="transport-icon" disabled title="Shuffle will be added next" aria-label="Shuffle"><span aria-hidden="true">⤨</span></button>
            <button type="button" className="transport-icon" onClick={onPrevious} disabled={!playerActive} aria-label="Previous track"><span aria-hidden="true">Ⅰ◀</span></button>
            {playerActive ? (
              <button type="button" onClick={onTogglePlayback} className="transport-play" aria-label={playerPaused ? 'Play' : 'Pause'}><span aria-hidden="true">{playerPaused ? '▶' : 'Ⅱ'}</span></button>
            ) : (
              <button type="button" onClick={onPlayHere} disabled={!playerReady} className="transport-play" aria-label="Play on Chili Dashboard"><span aria-hidden="true">▶</span></button>
            )}
            <button type="button" className="transport-icon" onClick={onNext} disabled={!playerActive} aria-label="Next track"><span aria-hidden="true">▶Ⅰ</span></button>
            <button type="button" className="transport-icon" disabled title="Repeat will be added next" aria-label="Repeat"><span aria-hidden="true">↻</span></button>
          </div>
          <p className="device-state">{playerActive ? 'Playing on Chili Dashboard' : playerReady ? 'Chili Dashboard is ready' : 'Starting player…'}</p>
          <a className="media-secondary" href="/api/v1/spotify/connect">Reconnect</a>
          {playerError && <p className="setup-state is-error">{playerError}</p>}
        </div>
      )}
    </section>
  )
}
