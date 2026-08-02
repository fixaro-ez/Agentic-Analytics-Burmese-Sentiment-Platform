"use client"

import { useMemo, useSyncExternalStore } from "react"
import { Pin, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import type { PinnedChatInsight } from "@/lib/types"

const STORAGE_KEY = "burmese-absa:pinned-chat-insights"

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback)
  window.addEventListener("pinned-chat-insights-changed", callback)
  return () => {
    window.removeEventListener("storage", callback)
    window.removeEventListener("pinned-chat-insights-changed", callback)
  }
}

function getSnapshot() {
  return localStorage.getItem(STORAGE_KEY) ?? "[]"
}

function getServerSnapshot() {
  return "[]"
}

export function PinnedChatInsights() {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
  const insights = useMemo(() => {
    try {
      return JSON.parse(snapshot) as PinnedChatInsight[]
    } catch {
      return []
    }
  }, [snapshot])

  if (!insights.length) return null

  function remove(id: string) {
    const next = insights.filter((item) => item.id !== id)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    window.dispatchEvent(new CustomEvent("pinned-chat-insights-changed"))
  }

  return (
    <section aria-labelledby="pinned-insights-title">
      <div className="mb-3 flex items-center gap-2">
        <Pin className="h-4 w-4 text-primary" aria-hidden="true" />
        <h2 id="pinned-insights-title" className="text-sm font-semibold">
          Pinned AI insights
        </h2>
        <span className="text-xs text-muted-foreground">
          {insights.length} saved from Chat with Data
        </span>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        {insights.slice(0, 4).map((insight) => (
          <article
            key={insight.id}
            className="relative rounded-xl border bg-card p-4 pr-11 shadow-[0_8px_24px_rgba(0,0,0,0.1)]"
          >
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="absolute right-2 top-2 h-8 w-8 text-muted-foreground"
              onClick={() => remove(insight.id)}
              aria-label={`Remove pinned insight: ${insight.question}`}
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
            <h3 className="text-sm font-medium">{insight.question}</h3>
            {insight.explanation && (
              <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">
                {insight.explanation}
              </p>
            )}
            <p className="mt-3 text-xs text-muted-foreground">
              {insight.results.length.toLocaleString()} result rows · pinned{" "}
              {new Date(insight.pinned_at).toLocaleDateString()}
            </p>
          </article>
        ))}
      </div>
    </section>
  )
}
