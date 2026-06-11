import type { FormEvent } from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

import { adminApi } from '@/shared/api/adminApi'
import type { AdminAssistantMessage, RoleCode } from '@/shared/api/types'
import { getApiErrorMessage } from '@/shared/utils/apiError'

type ChatMessage = AdminAssistantMessage & {
  id: string
  status?: string
}

type Props = {
  roles: RoleCode[]
  userName?: string | null
}

const FIRST_MESSAGE: ChatMessage = {
  id: 'assistant-welcome',
  role: 'assistant',
  content: 'Здравствуйте. Я помогу с разделами панели, отчетами, импортом, расписанием, рисками и Telegram.',
}

function messageId(role: AdminAssistantMessage['role']) {
  return `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function ChatCloudIcon() {
  return (
    <svg aria-hidden="true" className="assistant-fab-icon" viewBox="0 0 24 24" focusable="false">
      <path d="M7.5 17.8H6.3c-2.4 0-4.3-1.7-4.3-3.9 0-1.7 1.1-3.1 2.8-3.7.5-2.9 3.2-5.1 6.4-5.1 3.1 0 5.8 2.1 6.4 4.9 2.5.4 4.4 2.4 4.4 4.8 0 2.7-2.4 4.9-5.4 4.9H13l-4.2 2.6c-.7.4-1.5-.1-1.4-.9l.1-3.6Z" />
      <path d="M8.1 12.4h7.8M8.1 15h5.4" />
    </svg>
  )
}

export function AdminAssistantWidget({ roles, userName }: Props) {
  const location = useLocation()
  const [isOpen, setIsOpen] = useState(false)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([FIRST_MESSAGE])
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const messagesRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)

  const canUseAssistant = roles.includes('admin') || roles.includes('curator')
  const roleLabel = useMemo(() => {
    if (roles.includes('admin')) return 'Админ'
    if (roles.includes('curator')) return 'Тьютор'
    return 'Панель'
  }, [roles])

  useEffect(() => {
    if (!isOpen) return
    inputRef.current?.focus()
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: 'smooth' })
  }, [isOpen, messages])

  if (!canUseAssistant) return null

  const submit = async (event?: FormEvent) => {
    event?.preventDefault()
    const text = input.trim()
    if (!text || isSending) return

    const history = messages
      .filter((item) => item.id !== FIRST_MESSAGE.id)
      .slice(-10)
      .map(({ role, content }) => ({ role, content }))
    const userMessage: ChatMessage = { id: messageId('user'), role: 'user', content: text }
    setMessages((current) => [...current, userMessage])
    setInput('')
    setError(null)
    setIsSending(true)
    try {
      const reply = await adminApi.askAssistant({
        message: text,
        current_path: location.pathname,
        history,
      })
      setMessages((current) => [
        ...current,
        {
          id: messageId('assistant'),
          role: 'assistant',
          content: reply.message,
          status: reply.status,
        },
      ])
    } catch (cause) {
      setError(getApiErrorMessage(cause, 'Помощник недоступен'))
      setMessages((current) => [
        ...current,
        {
          id: messageId('assistant'),
          role: 'assistant',
          content: 'Не удалось получить ответ. Проверьте подключение и попробуйте еще раз.',
          status: 'error',
        },
      ])
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className={`assistant-widget ${isOpen ? 'assistant-widget-open' : ''}`}>
      {isOpen ? (
        <section className="assistant-panel" aria-label="Чат помощника панели">
          <header className="assistant-panel-header">
            <div>
              <div className="assistant-kicker">{roleLabel}</div>
              <h3>Помощник панели</h3>
            </div>
            <button
              type="button"
              className="assistant-close"
              onClick={() => setIsOpen(false)}
              aria-label="Закрыть помощника"
            >
              ×
            </button>
          </header>

          <div ref={messagesRef} className="assistant-messages" aria-live="polite">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`assistant-message assistant-message-${message.role}`}
              >
                <div className="assistant-message-bubble">
                  {message.content.split('\n').map((line, index) => (
                    <p key={`${message.id}-${index}`}>{line}</p>
                  ))}
                </div>
                {message.role === 'assistant' && message.status ? (
                  <span className="assistant-message-meta">
                    {message.status === 'llm' ? 'AI' : message.status === 'fallback' ? 'FAQ' : message.status}
                  </span>
                ) : null}
              </div>
            ))}
            {isSending ? (
              <div className="assistant-message assistant-message-assistant">
                <div className="assistant-message-bubble assistant-typing">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            ) : null}
          </div>

          <div className="assistant-suggestions">
            {['Как импортировать расписание?', 'Как отправить рассылку?', 'Где посмотреть риски?'].map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setInput(item)}
                disabled={isSending}
              >
                {item}
              </button>
            ))}
          </div>

          <form className="assistant-form" onSubmit={submit}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void submit()
                }
              }}
              rows={2}
              maxLength={2000}
              placeholder={`${userName || 'Коллега'}, задайте вопрос`}
              aria-label="Сообщение помощнику"
              disabled={isSending}
            />
            <button type="submit" disabled={!input.trim() || isSending}>
              {isSending ? '...' : 'Отправить'}
            </button>
          </form>
          {error ? <div className="assistant-error">{error}</div> : null}
        </section>
      ) : null}

      <button
        type="button"
        className="assistant-fab"
        onClick={() => setIsOpen((value) => !value)}
        aria-label={isOpen ? 'Свернуть помощника' : 'Открыть помощника панели'}
        title={isOpen ? 'Свернуть помощника' : 'Открыть помощника панели'}
      >
        <ChatCloudIcon />
      </button>
    </div>
  )
}
