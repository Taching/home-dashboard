import { FormEvent, useEffect, useRef, useState } from 'react'
import type { OpenClawConversation } from '../types'

type Props = {
  conversation: OpenClawConversation
  pending: boolean
  feedback: string | null
  onSend: (message: string) => void
}

export function OpenClawChat({ conversation, pending, feedback, onSend }: Props) {
  const [draft, setDraft] = useState('')
  const transcript = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = transcript.current
    if (element) element.scrollTop = element.scrollHeight
  }, [conversation.messages.length])

  function submit(event: FormEvent) {
    event.preventDefault()
    const message = draft.trim()
    if (!message || pending) return
    onSend(message)
    setDraft('')
  }

  return (
    <section className="openclaw-chat" aria-label="Ask Chili">
      <div className="region-heading">
        <div>
          <p className="eyebrow">ASSISTANT</p>
          <h2>Ask Chili</h2>
        </div>
        <p className={`openclaw-status is-${conversation.status}`}>{conversation.status === 'ready' ? 'Shared with Telegram' : conversation.status === 'not_configured' ? 'Setup needed' : 'Unavailable'}</p>
      </div>
      {conversation.status === 'not_configured' ? (
        <p className="setup-state">Configure OpenClaw on the Pi to connect this shared chat.</p>
      ) : conversation.status === 'unavailable' ? (
        <p className="setup-state is-error">{conversation.message ?? 'OpenClaw is unavailable'}</p>
      ) : (
        <>
          <div className="openclaw-transcript" ref={transcript} aria-live="polite">
            {conversation.messages.length === 0 ? <p>Open your Telegram chat with Chili to begin.</p> : conversation.messages.map((message) => (
              <p key={message.id} className={`openclaw-message is-${message.role}`}>
                <span>{message.role === 'user' ? 'You' : 'Chili'}</span>{message.text}
              </p>
            ))}
          </div>
          <form className="openclaw-form" onSubmit={submit}>
            <label className="sr-only" htmlFor="chili-message">Message Chili</label>
            <input
              id="chili-message"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Message Chili…"
              maxLength={3000}
              disabled={pending}
            />
            <button type="submit" disabled={pending || !draft.trim()}>{pending ? 'Sending…' : 'Send'}</button>
          </form>
          <p className={`openclaw-feedback${feedback ? ' is-error' : ''}`} aria-live="polite">{feedback}</p>
        </>
      )}
    </section>
  )
}
