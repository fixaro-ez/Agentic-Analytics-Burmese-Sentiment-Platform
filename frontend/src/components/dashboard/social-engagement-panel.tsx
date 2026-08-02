"use client"

import { AlertCircle } from "lucide-react"
import { ReactionMixDonut } from "@/components/charts/reaction-mix-donut"
import { ReactionRatioTrend } from "@/components/charts/reaction-ratio-trend"
import { DataError } from "@/components/data-error"
import { Badge } from "@/components/ui/badge"
import {
  useEngagementTrends,
  useReactionMix,
} from "@/hooks/use-analytics"
import { useFilterStore } from "@/lib/stores/filters"

function ratio(value: number | null | undefined): string {
  return value == null ? "N/A" : `${(value * 100).toFixed(1)}%`
}

export function SocialEngagementPanel() {
  const entityId = useFilterStore((state) => state.entityId)
  const days = useFilterStore((state) => state.days)
  const mix = useReactionMix(entityId, days)
  const trends = useEngagementTrends(entityId, days)

  if (mix.error) {
    return <DataError message={mix.error} onRetry={mix.refetch} />
  }
  if (trends.error) {
    return <DataError message={trends.error} onRetry={trends.refetch} />
  }

  const reactionMix = mix.data ?? {
    like: 0,
    love: 0,
    care: 0,
    haha: 0,
    wow: 0,
    sad: 0,
    angry: 0,
    total_posts: 0,
    incomplete_posts: 0,
    positivity_ratio: null,
    negativity_ratio: null,
    haha_ratio: null,
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">
          Positivity {ratio(reactionMix.positivity_ratio)}
        </Badge>
        <Badge variant="outline">
          Negativity {ratio(reactionMix.negativity_ratio)}
        </Badge>
        <Badge variant="outline">
          Haha {ratio(reactionMix.haha_ratio)}
        </Badge>
        {reactionMix.incomplete_posts > 0 && (
          <Badge
            variant="outline"
            className="gap-1 border-badge-incomplete text-muted-foreground"
            title={`${reactionMix.incomplete_posts} posts are excluded from ratio calculations because their reaction breakdown is incomplete.`}
          >
            <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
            Data incomplete · {reactionMix.incomplete_posts}
          </Badge>
        )}
      </div>

      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.6fr)]">
        <div className="min-w-0">
          <p className="mb-2 text-sm font-medium">Reaction mix</p>
          <ReactionMixDonut data={reactionMix} loading={mix.loading} />
        </div>
        <div className="min-w-0">
          <p className="mb-2 text-sm font-medium">Reaction ratios over time</p>
          <ReactionRatioTrend
            data={trends.data?.trends ?? []}
            loading={trends.loading}
          />
        </div>
      </div>
    </div>
  )
}
