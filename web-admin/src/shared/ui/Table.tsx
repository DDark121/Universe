import type { ReactNode } from 'react'

export type TableColumn<T> = {
  key: string
  title: string
  render: (row: T) => ReactNode
}

type Props<T> = {
  columns: Array<TableColumn<T>>
  rows: T[]
  getRowKey: (row: T, index: number) => string
}

export function Table<T>({ columns, rows, getRowKey }: Props<T>) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key}>{column.title}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={getRowKey(row, idx)}>
              {columns.map((column) => (
                <td key={`${column.key}-${idx}`}>{column.render(row)}</td>
              ))}
            </tr>
          ))}
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="muted">
                Нет данных
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  )
}
