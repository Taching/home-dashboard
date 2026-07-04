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
    <section className="media-region spotify-widget" aria-label="Spotify now playing">
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
          <div className="spotify-empty-state">
            <div className="artwork-fallback" aria-hidden="true">♪</div>
            <div>
              {spotify.status === 'not_configured' ? (
                <>
                  <strong>Spotify not connected</strong>
                  <p>Connect your account to control playback from Chili.</p>
                  <a className="setup-link" href="/api/v1/spotify/connect">Connect Spotify</a>
                </>
              ) : spotify.status === 'ready' ? (
                <>
                  <strong>Nothing playing</strong>
                  <p>Start Spotify from any device, then bring playback here.</p>
                </>
              ) : (
                <>
                  <strong>Spotify unavailable</strong>
                  <p className="is-error">Playback status could not be loaded.</p>
                </>
              )}
            </div>
          </div>
        )}
      </div>
      {spotify.status === 'ready' && (
        <div className="player-actions">
          <div className="transport-controls" aria-label="Spotify playback controls">
            <button type="button" className="transport-icon" disabled title="Shuffle will be added next" aria-label="Shuffle"><span aria-hidden="true">⤨</span></button>
            <button type="button" className="transport-icon" onClick={onPrevious} disabled={!playerActive} aria-label="Previous track"><span aria-hidden="true">Ⅰ◀</span></button>
            {playerActive ? (
              <button type="button" onClick={onTogglePlayback} className="transport-play" aria-label={playerPaused ? 'Play' : 'Pause'}><span className={playerPaused ? 'play-glyph' : 'pause-glyph'} aria-hidden="true">{playerPaused ? '▶' : 'Ⅱ'}</span></button>
            ) : (
              <button type="button" onClick={onPlayHere} disabled={!playerReady} className="transport-play" aria-label="Play on Chili Dashboard"><span className="play-glyph" aria-hidden="true">▶</span></button>
            )}
            <button type="button" className="transport-icon" onClick={onNext} disabled={!playerActive} aria-label="Next track"><span aria-hidden="true">▶Ⅰ</span></button>
            <button type="button" className="transport-icon" disabled title="Repeat will be added next" aria-label="Repeat"><span aria-hidden="true">↻</span></button>
          </div>
          <a className="media-secondary" href="/api/v1/spotify/connect" aria-label="Reconnect Spotify" title="Reconnect Spotify"><span aria-hidden="true">↻</span></a>
          {playerError && <p className="setup-state is-error">{playerError}</p>}
        </div>
      )}
    </section>
  )
}
