"use client"

import { Suspense, useState } from "react"
import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { FilterBar } from "@/components/layout/filter-bar"
import { FilterSync } from "@/components/layout/filter-sync"
import { AskDataFab } from "@/components/dashboard/ask-data-fab"

export default function AppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <>
      <a
        href="#main-content"
        className="fixed left-3 top-3 z-[100] -translate-y-20 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-lg transition-transform focus:translate-y-0 focus:outline-none focus:ring-2 focus:ring-ring"
      >
        Skip to main content
      </a>
      <div className="flex min-h-screen w-full max-w-full overflow-x-hidden">
        <Sidebar open={sidebarOpen} onOpenChange={setSidebarOpen} />
        <div className="min-w-0 flex-1 md:ml-60">
          <Header
            sidebarOpen={sidebarOpen}
            onMenuClick={() => setSidebarOpen(true)}
          />
          <Suspense fallback={null}>
            <FilterSync>
              <FilterBar />
              <main
                id="main-content"
                tabIndex={-1}
                className="min-w-0 overflow-x-hidden px-4 py-5 sm:p-6"
              >
                {children}
              </main>
            </FilterSync>
          </Suspense>
        </div>
      </div>
      <AskDataFab />
    </>
  )
}
