"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function EntitiesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Entities</h1>
        <p className="text-muted-foreground">
          Manage tracked Facebook pages and Foodpanda shops.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>All Entities</CardTitle>
          <CardDescription>Facebook pages and Foodpanda shops being tracked</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
            <p className="text-sm text-muted-foreground">
              TODO(Member 4): Data table listing entities.
              Fetch GET /api/entities. Display entity_name, platform, entity_id.
              Add filtering by platform (facebook/foodpanda).
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
