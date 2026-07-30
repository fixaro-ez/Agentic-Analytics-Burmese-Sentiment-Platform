"use client";

import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";

export function ChatWithDataDrawer() {
  return (
    <Sheet>
      {}
      <SheetTrigger asChild>
        <Button className="fixed bottom-4 right-4 z-50">💬 Ask Data AI</Button>
      </SheetTrigger>

      {/* Drawer */}
      <SheetContent side="right" className="w-[420px] sm:w-full">
        <div className="p-4 space-y-6">
          <h2 className="text-lg font-bold">Summary</h2>
          <p>AI will explain your quesetions here.</p>

          <h3 className="font-semibold">Chart/Table</h3>
          <div className="border rounded p-2 text-sm text-muted-foreground">
            Tremor chart/table goes here
          </div>

          {/* Collapsible SQL audit */}
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button variant="outline" size="sm">
                Show SQL Query
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2">
              <pre className="bg-gray-100 p-2 rounded text-xs overflow-x-auto">
{`SELECT branch, AVG(delivery_time)
FROM orders
WHERE date = '2026-07-25'
GROUP BY branch
ORDER BY AVG(delivery_time) DESC;`}
              </pre>
            </CollapsibleContent>
          </Collapsible>

          {/* Action controls */}
          <div className="flex gap-2 mt-4">
            <Button variant="secondary">📌 Pin</Button>
            <Button variant="secondary">⬇️ Export CSV</Button>
            <Button variant="secondary">🔍 View Raw Reviews</Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
