import { useEffect, useState } from 'react'
import { fetchSpotifyWebPlaybackToken, registerSpotifyDevice, startSpotifyDj, transferSpotifyPlayback } from '../lib/api'

export type PlaybackTrack = { track: string, artist: string, artworkUrl: string | null }

declare global {
  interface Window { Spotify?: any }
}

function loadSdk() {
  if (window.Spotify) return Promise.resolve()
  return new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://sdk.scdn.co/spotify-player.js'
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Spotify player could not load'))
    document.head.append(script)
  })
}

export function useSpotifyPlayback(enabled: boolean) {
  const [deviceId, setDeviceId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [player, setPlayer] = useState<any>(null)
  const [active, setActive] = useState(false)
  const [paused, setPaused] = useState(true)
  const [track, setTrack] = useState<PlaybackTrack | null>(null)

  useEffect(() => {
    if (!enabled) return
    let localPlayer: any
    void (async () => {
      try {
        await loadSdk()
        localPlayer = new window.Spotify.Player({
          name: 'Chili Dashboard',
          getOAuthToken: async (callback: (token: string) => void) => callback((await fetchSpotifyWebPlaybackToken()).access_token),
          volume: 0.7,
          enableMediaSession: true,
        })
        localPlayer.addListener('ready', ({ device_id }: { device_id: string }) => {
          setDeviceId(device_id)
          void registerSpotifyDevice(device_id)
        })
        localPlayer.addListener('initialization_error', ({ message }: { message: string }) => setError(message))
        localPlayer.addListener('authentication_error', ({ message }: { message: string }) => setError(message))
        localPlayer.addListener('account_error', ({ message }: { message: string }) => setError(message))
        localPlayer.addListener('not_ready', () => {
          setActive(false)
          setDeviceId(null)
        })
        localPlayer.addListener('player_state_changed', (state: { paused: boolean, track_window?: { current_track?: { name: string, artists?: Array<{ name: string }>, album?: { images?: Array<{ url: string }> } } } } | null) => {
          setActive(Boolean(state))
          setPaused(state?.paused ?? true)
          const current = state?.track_window?.current_track
          if (current) {
            setTrack({
              track: current.name,
              artist: current.artists?.map((artist) => artist.name).join(', ') ?? 'Unknown artist',
              artworkUrl: current.album?.images?.[0]?.url ?? null,
            })
          }
        })
        await localPlayer.connect()
        setPlayer(localPlayer)
      } catch {
        setError('Spotify player could not start.')
      }
    })()
    return () => { localPlayer?.disconnect() }
  }, [enabled])

  async function playHere() {
    if (!player || !deviceId) return
    await player.activateElement()
    await transferSpotifyPlayback(deviceId)
  }

  async function togglePlayback() {
    if (!player) return
    await player.togglePlay()
  }

  async function previousTrack() {
    if (!player) return
    await player.previousTrack()
  }

  async function nextTrack() {
    if (!player) return
    await player.nextTrack()
  }

  async function startDj() {
    if (!player || !deviceId) {
      setError('Spotify player is not ready.')
      return
    }
    setError(null)
    try {
      await player.activateElement()
      await transferSpotifyPlayback(deviceId)
      await startSpotifyDj()
    } catch {
      setError('Spotify DJ could not start.')
    }
  }

  return { ready: Boolean(deviceId), active, paused, track, error, playHere, togglePlayback, previousTrack, nextTrack, startDj }
}
