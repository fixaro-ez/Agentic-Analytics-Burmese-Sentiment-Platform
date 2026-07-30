"use client"

import { useEffect, useMemo, useState } from "react"
import { User } from "@supabase/supabase-js"
import { Menu } from "lucide-react"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { createClient } from "@/lib/supabase/client"

interface HeaderProps {
  sidebarOpen: boolean
  onMenuClick: () => void
}

export function Header({ sidebarOpen, onMenuClick }: HeaderProps) {
  const [user, setUser] = useState<User | null>(null)
  const supabase = useMemo(() => createClient(), [])

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => setUser(data.user))
  }, [supabase])

  const initials = user?.email
    ? user.email.substring(0, 2).toUpperCase()
    : "U"

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
        <span className="hidden max-w-64 truncate text-sm text-muted-foreground sm:block">
          {user?.email}
        </span>
        <Avatar className="h-8 w-8 shrink-0">
          <AvatarFallback className="text-xs">{initials}</AvatarFallback>
        </Avatar>
      </div>
    </header>
  )
}
