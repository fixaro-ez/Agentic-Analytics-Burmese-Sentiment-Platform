"use client"

import { useState } from "react"
import { GitFork, Orbit } from "lucide-react"

import { EntityComparisonPicker } from "@/components/analytics/entity-comparison-picker"
import { AssociationRulesPanel } from "@/components/mining/association-rules-panel"
import { EntityClustersPanel } from "@/components/mining/entity-clusters-panel"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import { useFilterStore } from "@/lib/stores/filters"

export default function MiningPage() {
  const entityId = useFilterStore((state) => state.entityId)
  const days = useFilterStore((state) => state.days)
  const [comparison, setComparison] = useState<{
    primaryEntityId: number | null
    ids: number[]
  }>({ primaryEntityId: null, ids: [] })
  const compareIds =
    comparison.primaryEntityId === entityId ? comparison.ids : []

  return (
    <div className="mx-auto w-full max-w-[96rem] space-y-5">
      <header className="flex flex-col gap-2 border-b pb-4 sm:flex-row sm:items-end sm:justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Feedback Patterns</h1>
        <p className="text-xs text-muted-foreground">
          Last {days}d ·{" "}
          {entityId == null
            ? "all entities"
            : `${1 + compareIds.length} selected ${1 + compareIds.length === 1 ? "entity" : "entities"}`}
        </p>
      </header>

      {entityId != null && (
        <EntityComparisonPicker
          primaryEntityId={entityId}
          selectedIds={compareIds}
          onChange={(ids) => setComparison({ primaryEntityId: entityId, ids })}
          label="Compare with"
        />
      )}

      <Tabs defaultValue="rules">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="rules" className="gap-2">
            <GitFork className="h-4 w-4" aria-hidden="true" />
            Topic connections
          </TabsTrigger>
          <TabsTrigger value="clusters" className="gap-2">
            <Orbit className="h-4 w-4" aria-hidden="true" />
            Entity groups
          </TabsTrigger>
        </TabsList>

        <TabsContent value="rules">
          <AssociationRulesPanel
            entityId={entityId}
            compareIds={compareIds}
            days={days}
          />
        </TabsContent>
        <TabsContent value="clusters">
          <EntityClustersPanel
            entityId={entityId}
            compareIds={compareIds}
            days={days}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}
