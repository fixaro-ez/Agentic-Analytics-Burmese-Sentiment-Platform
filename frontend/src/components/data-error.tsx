"use client"

import { AlertCircle } from "lucide-react"

import { Button } from "@/components/ui/button"

interface DataErrorProps {
  message: string
  onRetry?: () => void
}

export function DataError({ message, onRetry }: DataErrorProps) {
  return (
    <div
      className="flex min-h-40 flex-col items-center justify-center gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-6 text-center"
      role="alert"
    >
      <AlertCircle className="h-5 w-5 text-destructive" aria-hidden="true" />
      <div>
        <p className="text-sm font-medium">Unable to load this data</p>
        <p className="mt-1 max-w-lg text-sm text-muted-foreground">{message}</p>
      </div>
      {onRetry && (
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}
