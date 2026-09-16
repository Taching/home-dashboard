const EVENT_NAME = 'chili:planning-changed'
const CHANNEL_NAME = 'chili-planning'
const STREAM_PATH = '/api/v1/planning/stream'
const RECONNECT_MS = 3_000

export function announcePlanningChange() {
  window.dispatchEvent(new Event(EVENT_NAME))
  if (!('BroadcastChannel' in window)) return
  const channel = new BroadcastChannel(CHANNEL_NAME)
  channel.postMessage({ type: 'planning-changed', at: Date.now() })
  channel.close()
}

export function subscribeToPlanningChanges(refresh: () => void) {
  const onLocalChange = () => refresh()
  window.addEventListener(EVENT_NAME, onLocalChange)
  window.addEventListener('focus', onLocalChange)
  window.addEventListener('online', onLocalChange)
  const onVisible = () => {
    if (document.visibilityState === 'visible') refresh()
  }
  document.addEventListener('visibilitychange', onVisible)

  const channel = 'BroadcastChannel' in window ? new BroadcastChannel(CHANNEL_NAME) : null
  if (channel) channel.onmessage = onLocalChange

  let stream: EventSource | null = null
  let reconnect: number | null = null
  const connect = () => {
    if (!('EventSource' in window)) return
    stream = new EventSource(STREAM_PATH)
    stream.addEventListener('planning', onLocalChange)
    stream.onerror = () => {
      stream?.close()
      stream = null
      if (reconnect != null) return
      reconnect = window.setTimeout(() => {
        reconnect = null
        connect()
      }, RECONNECT_MS)
    }
  }
  connect()

  return () => {
    window.removeEventListener(EVENT_NAME, onLocalChange)
    window.removeEventListener('focus', onLocalChange)
    window.removeEventListener('online', onLocalChange)
    document.removeEventListener('visibilitychange', onVisible)
    channel?.close()
    stream?.close()
    if (reconnect != null) window.clearTimeout(reconnect)
  }
}
