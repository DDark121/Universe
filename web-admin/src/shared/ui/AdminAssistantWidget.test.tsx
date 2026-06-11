import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { askAssistant } = vi.hoisted(() => ({
  askAssistant: vi.fn(),
}))

vi.mock('@/shared/api/adminApi', () => ({
  adminApi: {
    askAssistant,
  },
}))

import { AdminAssistantWidget } from '@/shared/ui/AdminAssistantWidget'

beforeEach(() => {
  askAssistant.mockReset()
  askAssistant.mockResolvedValue({
    message: 'Откройте раздел «Импорт», выберите AI import и проверьте draft.',
    used_faq_ids: [],
    status: 'llm',
  })
})

it('opens assistant bubble and sends a panel question', async () => {
  render(
    <MemoryRouter initialEntries={['/imports']}>
      <AdminAssistantWidget roles={['admin']} userName="Admin User" />
    </MemoryRouter>,
  )

  fireEvent.click(screen.getByRole('button', { name: 'Открыть помощника панели' }))

  expect(screen.getByRole('heading', { name: 'Помощник панели' })).toBeInTheDocument()
  const input = screen.getByLabelText('Сообщение помощнику')
  fireEvent.change(input, { target: { value: 'Как импортировать расписание?' } })
  fireEvent.click(screen.getByRole('button', { name: 'Отправить' }))

  await waitFor(() => {
    expect(askAssistant).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'Как импортировать расписание?',
        current_path: '/imports',
      }),
    )
  })
  expect(await screen.findByText(/проверьте draft/i)).toBeInTheDocument()
  expect(screen.getByText('AI')).toBeInTheDocument()
})

it('does not render for teacher-only users', () => {
  render(
    <MemoryRouter>
      <AdminAssistantWidget roles={['teacher']} userName="Teacher User" />
    </MemoryRouter>,
  )

  expect(screen.queryByRole('button', { name: 'Открыть помощника панели' })).not.toBeInTheDocument()
})
