"use client"

import { useEffect, useMemo, useState, useSyncExternalStore } from "react"
import { User } from "@supabase/supabase-js"
import dynamic from "next/dynamic"
import { Activity, Download, Menu, Moon, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { createClient } from "@/lib/supabase/client"
import { useEtlHistory } from "@/hooks/use-analytics"
import { cn } from "@/lib/utils"

const EtlHealthDialog = dynamic(
  () =>
    import("@/components/etl/etl-health-dialog").then(
      (module) => module.EtlHealthDialog
    ),
  { ssr: false }
)
const ScrapeManagerDrawer = dynamic(
  () =>
    import("@/components/scraping/scrape-manager-drawer").then(
      (module) => module.ScrapeManagerDrawer
    ),
  { ssr: false }
)

interface HeaderProps {
  sidebarOpen: boolean
  onMenuClick: () => void
}

const emptySubscribe = () => () => {}

function relativeTime(value: string | null | undefined): {
  label: string
  minutes: number | null
} {
  if (!value) return { label: "No sync yet", minutes: null }
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return { label: "Sync time unavailable", minutes: null }
  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60_000))
  if (minutes < 1) return { label: "just now", minutes }
  if (minutes < 60) return { label: `${minutes}m ago`, minutes }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return { label: `${hours}h ago`, minutes }
  return { label: `${Math.floor(hours / 24)}d ago`, minutes }
}

export function Header({ sidebarOpen, onMenuClick }: HeaderProps) {
  const [user, setUser] = useState<User | null>(null)
  const [healthOpen, setHealthOpen] = useState(false)
  const [scrapeOpen, setScrapeOpen] = useState(false)
  const supabase = useMemo(() => createClient(), [])
  const { resolvedTheme, setTheme } = useTheme()
  const sync = useEtlHistory(1, 60_000)
  // Hydration-safe "is client" flag (theme is only known on the client).
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false
  )

  useEffect(() => {
    // The session user is only presentation data here; API authorization is
    // still verified server-side. Avoid a separate Auth server round trip.
    supabase.auth.getSession().then(({ data }) => setUser(data.session?.user ?? null))
  }, [supabase])

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (
        (event.metaKey || event.ctrlKey) &&
        event.shiftKey &&
        event.key.toLowerCase() === "s"
      ) {
        event.preventDefault()
        setScrapeOpen(true)
      }
    }
    window.addEventListener("keydown", handleShortcut)
    return () => window.removeEventListener("keydown", handleShortcut)
  }, [])

  const initials = user?.email
    ? user.email.substring(0, 2).toUpperCase()
    : "U"
  const latestRun = sync.data?.[0]
  const syncTime = relativeTime(latestRun?.completed_at ?? latestRun?.started_at)
  const syncStale = syncTime.minutes != null && syncTime.minutes > 30
  const syncProblem =
    !!sync.error || latestRun?.status === "failed" || syncStale
  const isDarkTheme = mounted && resolvedTheme === "dark"

  return (
    <header className="sticky top-0 z-30 flex h-14 min-w-0 items-center justify-between border-b bg-background px-4 sm:px-6">
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        onClick={onMenuClick}
        aria-label="Open navigation"
        aria-controls="app-sidebar"
        aria-expanded={sidebarOpen}
      >
        <Menu className="h-5 w-5" aria-hidden="true" />
      </Button>
      <div className="hidden md:block" />
      <div className="flex min-w-0 items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          className={cn(
            "h-9 gap-1.5 px-2 text-xs",
            syncProblem && "border-alert-critical/60 text-alert-critical"
          )}
          onClick={() => setHealthOpen(true)}
          aria-label={`Open pipeline health. Last sync ${syncTime.label}`}
          aria-haspopup="dialog"
          title={
            sync.error
              ? `Pipeline status unavailable: ${sync.error}`
              : `Latest ${latestRun?.run_type ?? "pipeline"} run: ${latestRun?.status ?? "unknown"}`
          }
        >
          <Activity className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden lg:inline">
            {sync.loading ? "Checking sync" : syncTime.label}
          </span>
        </Button>

        <Button
          variant="outline"
          size="sm"
          className="h-9 gap-1.5 px-2 text-xs"
          onClick={() => setScrapeOpen(true)}
          aria-label="Open Scrape Manager"
          aria-haspopup="dialog"
          title="Scrape Manager (Cmd/Ctrl+Shift+S)"
        >
          <Download className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">Scrape</span>
        </Button>

        <Button
          variant="ghost"
          size="icon"
          onClick={() =>
            setTheme(isDarkTheme ? "light" : "dark")
          }
          aria-label={
            isDarkTheme
              ? "Switch to light mode"
              : "Switch to dark mode"
          }
        >
          {isDarkTheme ? (
            <Sun className="h-5 w-5" aria-hidden="true" />
          ) : (
            <Moon className="h-5 w-5" aria-hidden="true" />
          )}
        </Button>
        <span className="hidden max-w-64 truncate text-sm text-muted-foreground sm:block">
          {user?.email}
        </span>
        <Avatar className="h-8 w-8 shrink-0">
          <AvatarFallback className="text-xs">{initials}</AvatarFallback>
        </Avatar>
      </div>
      {healthOpen && (
        <EtlHealthDialog open={healthOpen} onOpenChange={setHealthOpen} />
      )}
      {scrapeOpen && (
        <ScrapeManagerDrawer open={scrapeOpen} onOpenChange={setScrapeOpen} />
      )}
    </header>
  )
}
