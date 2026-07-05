import { useOptimistic, useState, useTransition, type FormEvent } from 'react'
import openClawLogo from '../assets/openclaw-logo.svg'
import type { OpenClawConversation } from '../types'

type Props = {
  conversation: OpenClawConversation
  pending: boolean
  feedback: string | null
  onSend: (message: string) => Promise<void>
  onRefresh: () => void
}

function scrollLatestMessageIntoView(element: HTMLElement | null) {
  element?.scrollIntoView({ block: 'end' })
}

export function OpenClawChat({ conversation, pending, feedback, onSend, onRefresh }: Props) {
  const [draft, setDraft] = useState('')
  const [, startTransition] = useTransition()

  const [messages, addOptimisticMessage] = useOptimistic(
    conversation.messages,
    (current, newText: string) => [
      ...current,
      {
        id: `optimistic-${Date.now()}`,
        role: 'user' as const,
        text: newText,
        created_at: new Date().toISOString(),
      },
    ],
  )

  function submit(event: FormEvent) {
    event.preventDefault()
    const message = draft.trim()
    if (!message || pending) return
    setDraft('')
    startTransition(async () => {
      addOptimisticMessage(message)
      await onSend(message)
    })
  }

  return (
    <section className={`openclaw-chat is-${conversation.status}`} aria-label="Ask Chili">
      <div className="openclaw-heading">
        <div className="openclaw-title">
          <span className="openclaw-brand">
            <img src={openClawLogo} alt="OpenClaw" />
          </span>
          <div>
            <p className="eyebrow">ASSISTANT</p>
            <h2>Ask Chili</h2>
          </div>
        </div>
        <p className={`openclaw-status is-${conversation.status}`}>
          {conversation.status === 'ready' ? 'Shared with Telegram' : conversation.status === 'not_configured' ? 'Setup needed' : 'Unavailable'}
        </p>
      </div>
      {conversation.status === 'not_configured' ? (
        <div className="panel-empty-state">
          <strong>OpenClaw not connected</strong>
          <p>Configure the Pi gateway and Telegram bridge to enable this shared chat.</p>
          <button type="button" onClick={onRefresh}>Check connection</button>
        </div>
      ) : conversation.status === 'unavailable' ? (
        <div className="panel-empty-state is-error">
          <strong>OpenClaw unavailable</strong>
          <p>{conversation.message ?? 'OpenClaw is unavailable.'}</p>
          <button type="button" onClick={onRefresh}>Retry</button>
        </div>
      ) : (
        <>
          <div className="openclaw-transcript" aria-live="polite">
            {messages.length === 0 ? (
              <p className="openclaw-empty-hint">Say “Hey Chili” or type below. Log walks like “I walked 30 min and 2 km today”. Messages sync with Telegram.</p>
            ) : messages.map((message, index) => (
              <article
                key={message.id}
                ref={index === messages.length - 1 ? scrollLatestMessageIntoView : undefined}
                className={`openclaw-message is-${message.role}`}
              >
                <span className="openclaw-message-label">{message.role === 'user' ? 'You' : 'Chili'}</span>
                <p className="openclaw-message-body">{message.text}</p>
              </article>
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
