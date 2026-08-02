"use client"

import { X } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useEntitySentiments } from "@/hooks/use-analytics"
import { myanmarLangProps } from "@/lib/myanmar"
import { cn } from "@/lib/utils"

const MAX_COMPARISONS = 2
const DOT_CLASSES = ["bg-entity-compare-1", "bg-entity-compare-2"]

interface EntityComparisonPickerProps {
  primaryEntityId: number | null
  selectedIds: number[]
  onChange: (ids: number[]) => void
  label?: string
  className?: string
}

export function EntityComparisonPicker({
  primaryEntityId,
  selectedIds,
  onChange,
  label = "Compare with",
  className,
}: EntityComparisonPickerProps) {
  const entitiesQuery = useEntitySentiments()
  const entities = entitiesQuery.data?.entities ?? []
  const selected = selectedIds
    .filter((id) => id !== primaryEntityId)
    .slice(0, MAX_COMPARISONS)
  const available = entities.filter(
    (entity) =>
      entity.entity_id !== primaryEntityId &&
      !selected.includes(entity.entity_id)
  )
  const disabled =
    primaryEntityId == null ||
    entitiesQuery.loading ||
    selected.length >= MAX_COMPARISONS ||
    available.length === 0

  const nameFor = (id: number) =>
    entities.find((entity) => entity.entity_id === id)?.entity_name ?? `#${id}`

  const placeholder =
    primaryEntityId == null
      ? "Select an entity above"
      : entitiesQuery.loading
        ? "Loading entities..."
        : selected.length >= MAX_COMPARISONS
          ? "Comparison limit reached"
          : available.length === 0
            ? "No entities available"
            : "Add entity"

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <Select
        value=""
        disabled={disabled}
        onValueChange={(value) => {
          const id = Number(value)
          if (!Number.isFinite(id)) return
          onChange([...selected, id].slice(0, MAX_COMPARISONS))
        }}
      >
        <SelectTrigger
          className="h-9 w-full sm:w-52"
          aria-label={label}
          title={primaryEntityId == null ? "Choose a primary entity first" : undefined}
        >
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {available.map((entity) => (
            <SelectItem
              key={entity.entity_id}
              value={String(entity.entity_id)}
              {...myanmarLangProps(entity.entity_name)}
            >
              {entity.entity_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {selected.map((id, index) => (
        <Badge key={id} variant="secondary" className="gap-1.5 pr-1">
          <span
            aria-hidden="true"
            className={cn(
              "h-2 w-2 shrink-0 rounded-full",
              DOT_CLASSES[index % DOT_CLASSES.length]
            )}
          />
          <span {...myanmarLangProps(nameFor(id))}>{nameFor(id)}</span>
          <button
            type="button"
            className="inline-flex min-h-6 min-w-6 items-center justify-center rounded-sm hover:bg-accent"
            onClick={() => onChange(selected.filter((selectedId) => selectedId !== id))}
            aria-label={`Remove comparison entity ${nameFor(id)}`}
          >
            <X className="h-3 w-3" aria-hidden="true" />
          </button>
        </Badge>
      ))}
    </div>
  )
}
