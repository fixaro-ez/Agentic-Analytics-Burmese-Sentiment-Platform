"use client"

import { FormEvent, useState } from "react"
import { Send } from "lucide-react"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api } from "@/lib/api"
import type { ChatResponse } from "@/lib/types"

function formatCell(value: unknown): string {
  if (value == null) return "—"
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4)
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

export default function ChatPage() {
  const [question, setQuestion] = useState("")
  const [response, setResponse] = useState<ChatResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = question.trim()
    if (trimmed.length < 2 || loading) return

    setLoading(true)
    setError(null)
    try {
      const result = await api.post<ChatResponse>("/api/chat/query", {
        question: trimmed,
      })
      if (result.error) throw new Error(result.error)
      setResponse(result)
    } catch (err) {
      setResponse(null)
      setError(err instanceof Error ? err.message : "Unable to answer the question")
    } finally {
      setLoading(false)
    }
  }

  const rows = response?.results ?? []
  const columns = rows[0] ? Object.keys(rows[0]) : []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Chat with Data</h1>
        <p className="text-muted-foreground">
          Ask for sentiment summaries, rankings, trends, or aspect results.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Ask a Question</CardTitle>
          <CardDescription>
            Try “Which entity has the most negative reviews?” or “Show sentiment trends.”
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex gap-2" onSubmit={handleSubmit}>
            <Label htmlFor="data-question" className="sr-only">
              Question about sentiment data
            </Label>
            <Input
              id="data-question"
              placeholder="Type your question here..."
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              className="min-w-0 flex-1"
              maxLength={500}
              autoComplete="off"
            />
            <Button
              type="submit"
              size="icon"
              disabled={question.trim().length < 2 || loading}
              aria-label={loading ? "Answering question" : "Ask question"}
            >
              <Send className="h-4 w-4" aria-hidden="true" />
            </Button>
          </form>
          {error && (
            <p className="mt-3 text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
        </CardContent>
      </Card>

      <Card aria-busy={loading}>
        <CardHeader>
          <CardTitle>Results</CardTitle>
          {response?.explanation && (
            <CardDescription>{response.explanation}</CardDescription>
          )}
        </CardHeader>
        <CardContent aria-live="polite">
          {loading ? (
            <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
              Analyzing your question...
            </div>
          ) : response ? (
            <div className="space-y-4">
              {rows.length > 0 ? (
                <div className="overflow-x-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        {columns.map((column) => (
                          <TableHead key={column}>{column.replaceAll("_", " ")}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rows.map((row, rowIndex) => (
                        <TableRow key={rowIndex}>
                          {columns.map((column) => (
                            <TableCell key={column}>{formatCell(row[column])}</TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <p className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
                  The query completed, but there were no matching records.
                </p>
              )}
              {response.sql && (
                <details>
                  <summary className="cursor-pointer text-sm font-medium">View read-only SQL</summary>
                  <pre className="mt-2 overflow-x-auto rounded-md bg-muted p-3 text-xs">
                    <code>{response.sql}</code>
                  </pre>
                </details>
              )}
            </div>
          ) : (
            <div className="flex h-40 items-center justify-center rounded-md border border-dashed p-6 text-center">
              <p className="text-sm text-muted-foreground">
                Your answer and supporting data will appear here.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
