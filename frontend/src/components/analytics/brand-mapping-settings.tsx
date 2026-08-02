"use client"

import { useMemo, useState } from "react"
import { Link2, Loader2, Pencil, Plus, Trash2 } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useBrands } from "@/hooks/use-analytics"
import { api } from "@/lib/api"
import { myanmarLangProps } from "@/lib/myanmar"
import type {
  Brand,
  BrandWrite,
  EntitySentimentOverview,
} from "@/lib/types"

export function BrandMappingSettings({
  entities,
}: {
  entities: EntitySentimentOverview[]
}) {
  const brands = useBrands()
  const [editing, setEditing] = useState<Brand | "new" | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function remove(brand: Brand) {
    if (!window.confirm(`Delete the mapping for ${brand.brand_name}?`)) return
    setBusy(true)
    setError(null)
    try {
      await api.delete(`/api/brands/${brand.brand_id}`)
      brands.refetch()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete mapping.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card id="brand-mappings" className="scroll-mt-24">
      <CardHeader className="gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Link2 className="h-5 w-5 text-primary" aria-hidden="true" />
            Brand Mapping
          </CardTitle>
          <CardDescription className="mt-1">
            Assign one Facebook page and one or more Foodpanda branches to each
            brand. Benchmark comparisons use only these explicit links.
          </CardDescription>
        </div>
        <div>
          <Button type="button" onClick={() => setEditing("new")} disabled={busy}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add brand
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {error && (
          <p className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            {error}
          </p>
        )}
        {brands.loading ? (
          <div className="flex h-28 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : brands.error ? (
          <p className="rounded-lg border border-dashed p-6 text-center text-sm text-destructive">
            {brands.error}
          </p>
        ) : brands.data?.brands.length ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {brands.data.brands.map((brand) => (
              <article key={brand.brand_id} className="rounded-xl border p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3
                      className="truncate font-semibold"
                      {...myanmarLangProps(brand.brand_name)}
                    >
                      {brand.brand_name}
                    </h3>
                    <p
                      className="mt-2 text-sm text-muted-foreground"
                      {...myanmarLangProps(brand.facebook_entity.entity_name)}
                    >
                      Facebook: {brand.facebook_entity.entity_name}
                    </p>
                  </div>
                  <div className="flex gap-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={`Edit ${brand.brand_name}`}
                      onClick={() => setEditing(brand)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${brand.brand_name}`}
                      onClick={() => void remove(brand)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {brand.foodpanda_shops.map((shop) => (
                    <Badge
                      key={shop.entity_id}
                      variant="secondary"
                      {...myanmarLangProps(shop.entity_name)}
                    >
                      {shop.entity_name}
                    </Badge>
                  ))}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed p-8 text-center">
            <p className="font-medium">No brand mappings yet</p>
            <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">
              Create at least two mappings before running a brand benchmark.
            </p>
          </div>
        )}
      </CardContent>

      {editing && (
        <BrandMappingDialog
          key={editing === "new" ? "new" : editing.brand_id}
          editing={editing}
          entities={entities}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            brands.refetch()
          }}
        />
      )}
    </Card>
  )
}

function BrandMappingDialog({
  editing,
  entities,
  onClose,
  onSaved,
}: {
  editing: Brand | "new"
  entities: EntitySentimentOverview[]
  onClose: () => void
  onSaved: () => void
}) {
  const facebook = useMemo(
    () => entities.filter((entity) => entity.platform.toLowerCase() === "facebook"),
    [entities]
  )
  const foodpanda = useMemo(
    () => entities.filter((entity) => entity.platform.toLowerCase() === "foodpanda"),
    [entities]
  )
  const [name, setName] = useState(
    editing === "new" ? "" : editing.brand_name
  )
  const [facebookId, setFacebookId] = useState(
    editing === "new" ? "" : String(editing.facebook_entity.entity_id)
  )
  const [shopIds, setShopIds] = useState<number[]>(
    editing === "new"
      ? []
      : editing.foodpanda_shops.map((shop) => shop.entity_id)
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function toggleShop(entityId: number) {
    setShopIds((current) =>
      current.includes(entityId)
        ? current.filter((id) => id !== entityId)
        : [...current, entityId]
    )
  }

  async function save() {
    if (!name.trim() || !facebookId || !shopIds.length) {
      setError("Brand name, one Facebook page, and at least one branch are required.")
      return
    }
    setSaving(true)
    setError(null)
    const body: BrandWrite = {
      brand_name: name.trim(),
      facebook_entity_id: Number(facebookId),
      foodpanda_entity_ids: shopIds,
    }
    try {
      if (editing === "new") {
        await api.post("/api/brands", body)
      } else if (editing) {
        await api.put(`/api/brands/${editing.brand_id}`, body)
      }
      onSaved()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save mapping.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={editing !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {editing === "new" ? "Add brand mapping" : "Edit brand mapping"}
          </DialogTitle>
          <DialogDescription>
            A Facebook page or Foodpanda branch can belong to only one brand.
          </DialogDescription>
        </DialogHeader>
        <div className="mt-5 space-y-5">
          <label className="block space-y-2 text-sm">
            <span className="font-medium">Brand name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="h-10 w-full rounded-md border bg-background px-3 outline-none focus:ring-2 focus:ring-ring"
              placeholder="e.g. Acme Burger"
            />
          </label>
          <div className="space-y-2 text-sm">
            <span className="font-medium">Facebook page</span>
            <Select value={facebookId} onValueChange={setFacebookId}>
              <SelectTrigger>
                <SelectValue placeholder="Choose a Facebook page" />
              </SelectTrigger>
              <SelectContent>
                {facebook.map((entity) => (
                  <SelectItem
                    key={entity.entity_id}
                    value={String(entity.entity_id)}
                  >
                    {entity.entity_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Foodpanda branches</legend>
            <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border p-2">
              {foodpanda.length ? (
                foodpanda.map((entity) => (
                  <label
                    key={entity.entity_id}
                    className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm hover:bg-muted"
                  >
                    <input
                      type="checkbox"
                      checked={shopIds.includes(entity.entity_id)}
                      onChange={() => toggleShop(entity.entity_id)}
                      className="h-4 w-4 accent-primary"
                    />
                    <span {...myanmarLangProps(entity.entity_name)}>
                      {entity.entity_name}
                    </span>
                  </label>
                ))
              ) : (
                <p className="p-3 text-sm text-muted-foreground">
                  No Foodpanda entities are available.
                </p>
              )}
            </div>
          </fieldset>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" onClick={() => void save()} disabled={saving}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            Save mapping
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
