import type { SpotifyNowPlaying } from '../types'
import { SpotifyEqualizer } from './SpotifyEqualizer'

export function MediaRegion({ spotify }: { spotify: SpotifyNowPlaying }) {
  const hasTrack = Boolean(spotify.track)

  return (
    <section className={`media-region spotify-widget${spotify.is_playing ? ' is-playing' : ''}`} aria-label="Spotify now playing">
      <div className={`spotify-player${hasTrack ? '' : ' is-empty'}${spotify.is_playing ? ' is-playing' : ''}`}>
        {hasTrack ? (
          <div className="now-playing">
            <div className={`now-playing-art${spotify.is_playing ? ' is-playing' : ''}`}>
              {spotify.artwork_url ? <img src={spotify.artwork_url} alt="" /> : <div className="artwork-fallback" aria-hidden="true">♪</div>}
              {spotify.is_playing && <span className="spotify-art-glow" aria-hidden="true" />}
            </div>
            <div>
              <div className="now-playing-title-row">
                <strong>{spotify.track}</strong>
                {spotify.is_playing && <SpotifyEqualizer active />}
              </div>
              <p>{spotify.artist ?? 'Unknown artist'}</p>
              <small className={`now-playing-status${spotify.is_playing ? ' is-playing' : ''}`}>
                {spotify.is_playing ? 'Now playing' : 'Paused'}
              </small>
            </div>
          </div>
        ) : (
          <div className="spotify-empty-state">
            <div className="artwork-fallback" aria-hidden="true">♪</div>
            <div>
              <strong>{spotify.status === 'ready' ? 'Nothing playing' : 'Spotify offline'}</strong>
              <p>{spotify.status === 'ready' ? 'Ask Chili to play some music.' : 'Playback status is unavailable.'}</p>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
