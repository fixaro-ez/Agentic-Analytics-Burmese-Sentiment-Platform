"use client"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { myanmarLangProps } from "@/lib/myanmar"
import type { Brand } from "@/lib/types"

export function BrandSelect({
  label,
  brands,
  value,
  onChange,
  exclude,
}: {
  label: string
  brands: Brand[]
  value: number | null
  onChange: (brandId: number) => void
  exclude?: number | null
}) {
  return (
    <label className="space-y-2 text-sm">
      <span className="font-medium">{label}</span>
      <Select
        value={value == null ? "" : String(value)}
        onValueChange={(next) => onChange(Number(next))}
      >
        <SelectTrigger>
          <SelectValue placeholder="Choose brand" />
        </SelectTrigger>
        <SelectContent>
          {brands
            .filter((brand) => brand.brand_id !== exclude)
            .map((brand) => (
              <SelectItem key={brand.brand_id} value={String(brand.brand_id)}>
                {brand.brand_name}
              </SelectItem>
            ))}
        </SelectContent>
      </Select>
    </label>
  )
}

export function BranchSelector({
  brand,
  selected,
  onChange,
}: {
  brand: Brand | undefined
  selected: number[]
  onChange: (ids: number[]) => void
}) {
  if (!brand) return null
  const allSelected =
    brand.foodpanda_shops.length > 0 &&
    selected.length === brand.foodpanda_shops.length
  return (
    <fieldset className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <legend className="text-sm font-medium">Foodpanda branches</legend>
        <button
          type="button"
          className="text-xs font-medium text-primary hover:underline"
          onClick={() =>
            onChange(
              allSelected
                ? []
                : brand.foodpanda_shops.map((shop) => shop.entity_id)
            )
          }
        >
          {allSelected ? "Clear" : "Select all"}
        </button>
      </div>
      <div className="max-h-36 space-y-1 overflow-y-auto rounded-lg border bg-background p-2">
        {brand.foodpanda_shops.map((shop) => (
          <label
            key={shop.entity_id}
            className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
          >
            <input
              type="checkbox"
              className="h-4 w-4 accent-primary"
              checked={selected.includes(shop.entity_id)}
              onChange={() =>
                onChange(
                  selected.includes(shop.entity_id)
                    ? selected.filter((id) => id !== shop.entity_id)
                    : [...selected, shop.entity_id]
                )
              }
            />
            <span {...myanmarLangProps(shop.entity_name)}>
              {shop.entity_name}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export function DaysSelect({
  value,
  onChange,
}: {
  value: number
  onChange: (days: number) => void
}) {
  return (
    <label className="space-y-2 text-sm">
      <span className="font-medium">Date range</span>
      <Select value={String(value)} onValueChange={(next) => onChange(Number(next))}>
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="7">Last 7 days</SelectItem>
          <SelectItem value="30">Last 30 days</SelectItem>
          <SelectItem value="90">Last 90 days</SelectItem>
          <SelectItem value="180">Last 180 days</SelectItem>
        </SelectContent>
      </Select>
    </label>
  )
}
