"use client"

import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts"

import type { BenchmarkBrand } from "@/lib/types"

const COLORS = ["var(--color-entity-primary)", "var(--color-entity-compare-1)"]

export function ShareOfVoiceDonut({ brands }: { brands: BenchmarkBrand[] }) {
  const data = brands
    .filter((brand) => brand.combined_share_of_voice != null)
    .map((brand) => ({
      name: brand.brand_name,
      value: (brand.combined_share_of_voice ?? 0) * 100,
    }))
  if (!data.length) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
        Combined share needs at least one Facebook post and one Foodpanda review
        across the two selected brands.
      </div>
    )
  }
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius={62}
            outerRadius={96}
            paddingAngle={2}
          >
            {data.map((item, index) => (
              <Cell key={item.name} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(value) => `${Number(value).toFixed(1)}%`} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
