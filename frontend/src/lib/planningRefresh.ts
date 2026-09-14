const EVENT_NAME = 'chili:planning-changed'
const CHANNEL_NAME = 'chili-planning'

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

  const channel = 'BroadcastChannel' in window ? new BroadcastChannel(CHANNEL_NAME) : null
  if (channel) channel.onmessage = onLocalChange

  return () => {
    window.removeEventListener(EVENT_NAME, onLocalChange)
    channel?.close()
  }
}
