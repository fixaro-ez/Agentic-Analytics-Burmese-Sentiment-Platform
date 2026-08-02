import type { SentimentTrendPoint } from "./types"

export interface WeeklySentimentPoint {
  weekStart: string
  weekEnd: string
  weekLabel: string
  weekRange: string
  positiveCount: number
  neutralCount: number
  negativeCount: number
  negativeValue: number
  aboveTotal: number
  totalReviews: number
}

const monthDayFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
})

function toIsoDate(date: Date) {
  return date.toISOString().slice(0, 10)
}

function startOfWeek(date: Date) {
  const result = new Date(date)
  const daysSinceMonday = (result.getUTCDay() + 6) % 7
  result.setUTCDate(result.getUTCDate() - daysSinceMonday)
  return result
}

export function aggregateSentimentByWeek(
  data: SentimentTrendPoint[]
): WeeklySentimentPoint[] {
  const weeks = new Map<
    string,
    Pick<
      WeeklySentimentPoint,
      "positiveCount" | "neutralCount" | "negativeCount"
    >
  >()

  for (const point of data) {
    const date = new Date(`${point.date.slice(0, 10)}T00:00:00Z`)
    if (Number.isNaN(date.getTime())) continue

    const weekKey = toIsoDate(startOfWeek(date))
    const current = weeks.get(weekKey) ?? {
      positiveCount: 0,
      neutralCount: 0,
      negativeCount: 0,
    }

    current.positiveCount += point.positive_count
    current.neutralCount += point.neutral_count
    current.negativeCount += point.negative_count
    weeks.set(weekKey, current)
  }

  return [...weeks.entries()]
    .sort(([first], [second]) => first.localeCompare(second))
    .map(([weekStart, counts]) => {
      const start = new Date(`${weekStart}T00:00:00Z`)
      const end = new Date(start)
      end.setUTCDate(end.getUTCDate() + 6)
      const totalReviews =
        counts.positiveCount + counts.neutralCount + counts.negativeCount

      return {
        weekStart,
        weekEnd: toIsoDate(end),
        weekLabel: monthDayFormatter.format(start),
        weekRange: `${monthDayFormatter.format(start)}–${monthDayFormatter.format(end)}`,
        ...counts,
        negativeValue: -counts.negativeCount,
        aboveTotal: counts.neutralCount + counts.positiveCount,
        totalReviews,
      }
    })
}
