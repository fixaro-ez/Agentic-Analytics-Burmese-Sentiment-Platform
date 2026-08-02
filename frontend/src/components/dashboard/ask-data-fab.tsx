"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { MessageSquareText } from "lucide-react"
import { Button } from "@/components/ui/button"

export function AskDataFab() {
  const pathname = usePathname()

  if (pathname === "/chat") return null

  return (
    <Button
      asChild
      className="fixed bottom-6 right-6 z-40 hidden h-12 gap-2 rounded-full px-4 shadow-lg sm:inline-flex"
    >
      <Link href="/chat" aria-label="Ask with Data">
        <MessageSquareText className="h-5 w-5" aria-hidden="true" />
        <span>Ask with Data</span>
      </Link>
    </Button>
  )
}
