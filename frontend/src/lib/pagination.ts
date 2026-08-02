export interface PaginationResult<T> {
  items: T[]
  page: number
  pageCount: number
  rangeStart: number
  rangeEnd: number
  total: number
}

export function paginate<T>(
  items: T[],
  requestedPage: number,
  pageSize: number
): PaginationResult<T> {
  if (!Number.isInteger(pageSize) || pageSize <= 0) {
    throw new RangeError("pageSize must be a positive integer")
  }

  const total = items.length
  const pageCount = Math.ceil(total / pageSize)
  const lastPage = Math.max(pageCount - 1, 0)
  const normalizedPage = Number.isFinite(requestedPage)
    ? Math.trunc(requestedPage)
    : 0
  const page = Math.min(Math.max(normalizedPage, 0), lastPage)
  const offset = page * pageSize

  return {
    items: items.slice(offset, offset + pageSize),
    page,
    pageCount,
    rangeStart: total === 0 ? 0 : offset + 1,
    rangeEnd: Math.min(offset + pageSize, total),
    total,
  }
}
