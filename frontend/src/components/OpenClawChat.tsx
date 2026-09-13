import { useEffect, useMemo, useRef } from 'react'
import openClawLogo from '../assets/openclaw-logo.svg'
import type { OpenClawConversation } from '../types'

type Props = {
  conversation: OpenClawConversation
}

export function OpenClawChat({ conversation }: Props) {
  const messages = useMemo(() => conversation.messages.slice(-4), [conversation.messages])
  const transcriptRef = useRef<HTMLDivElement | null>(null)
  const ready = conversation.status === 'ready'

  useEffect(() => {
    const transcript = transcriptRef.current
    if (!transcript) return
    const frame = window.requestAnimationFrame(() => {
      transcript.scrollTop = transcript.scrollHeight
    })
    return () => window.cancelAnimationFrame(frame)
  }, [messages])

  return (
    <section className={`openclaw-chat voice-assistant is-${conversation.status}`} aria-label="Assistant activity">
      <div className="openclaw-heading">
        <div className="openclaw-title">
          <span className="openclaw-brand">
            <img src={openClawLogo} alt="" />
          </span>
          <div>
            <p className="eyebrow">ASSISTANT</p>
            <h2>Recent activity</h2>
          </div>
        </div>
      </div>

      {!ready ? (
        <div className="panel-empty-state">
          <strong>Chili is offline</strong>
          <p>{conversation.message ?? 'The assistant connection will retry automatically.'}</p>
        </div>
      ) : (
        <div ref={transcriptRef} className="openclaw-transcript" aria-live="polite">
          {messages.length === 0 ? (
            <div className="voice-empty-state">
              <strong>No recent messages</strong>
              <p>Assistant activity will appear here.</p>
            </div>
          ) : messages.map((message) => (
            <article key={message.id} className={`openclaw-message is-${message.role}`}>
              <span className="openclaw-message-label">
                {message.sender === 'home-dashboard-agent'
                  ? 'Home Dashboard Agent'
                  : message.role === 'user' ? 'You' : 'Chili'}
              </span>
              <p className="openclaw-message-body">{message.text}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
