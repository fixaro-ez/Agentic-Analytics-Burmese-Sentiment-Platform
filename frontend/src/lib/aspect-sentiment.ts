import type { AspectBreakdown } from "./types"

export type AspectSortKey = "volume" | "negativity" | "trend"

export interface AspectSentimentRow {
  aspect: string
  positiveCount: number
  neutralCount: number
  negativeCount: number
  positiveShare: number
  neutralShare: number
  negativeShare: number
  total: number
}

export function buildAspectSentimentRows(
  data: AspectBreakdown[],
  sortBy: AspectSortKey = "volume",
  trendDeltas?: Record<string, number>
): AspectSentimentRow[] {
  const grouped = data.reduce((acc, item) => {
    const aspect = item.aspect
    if (!acc[aspect]) {
      acc[aspect] = {
        aspect,
        positiveCount: 0,
        neutralCount: 0,
        negativeCount: 0,
      }
    }

    const sentiment = item.sentiment.toLowerCase()
    if (sentiment === "positive") acc[aspect].positiveCount += item.count
    if (sentiment === "neutral") acc[aspect].neutralCount += item.count
    if (sentiment === "negative") acc[aspect].negativeCount += item.count
    return acc
  }, {} as Record<string, Omit<AspectSentimentRow, "positiveShare" | "neutralShare" | "negativeShare" | "total">>)

  return Object.values(grouped)
    .map((row) => {
      const total =
        row.positiveCount + row.neutralCount + row.negativeCount
      return {
        ...row,
        positiveShare: total ? (row.positiveCount / total) * 100 : 0,
        neutralShare: total ? (row.neutralCount / total) * 100 : 0,
        negativeShare: total ? (row.negativeCount / total) * 100 : 0,
        total,
      }
    })
    .sort((first, second) => {
      if (sortBy === "negativity") {
        return (
          second.negativeShare - first.negativeShare ||
          second.negativeCount - first.negativeCount
        )
      }
      if (sortBy === "trend") {
        return (
          (trendDeltas?.[second.aspect] ?? 0) -
          (trendDeltas?.[first.aspect] ?? 0)
        )
      }
      return second.total - first.total
    })
}
