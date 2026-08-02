"use client"

import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react"
import { useRouter } from "next/navigation"
import {
  BarChart3,
  Bot,
  Download,
  ExternalLink,
  History,
  Languages,
  Loader2,
  Pin,
  Plus,
  Send,
  Sparkles,
  Table2,
  TerminalSquare,
  Trash2,
} from "lucide-react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useToast } from "@/components/ui/toast"
import { api } from "@/lib/api"
import { myanmarLangProps } from "@/lib/myanmar"
import type {
  ChatHistoryResponse,
  ChatResponse,
  ChatStreamEvent,
  PinnedChatInsight,
} from "@/lib/types"
import { cn } from "@/lib/utils"

const PINNED_INSIGHTS_KEY = "burmese-absa:pinned-chat-insights"

interface ConversationTurn {
  id: string
  question: string
  explanation: string
  response: ChatResponse | null
  status: string | null
  error: string | null
}

function turnId() {
  return `turn-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function formatCell(value: unknown): string {
  if (value == null) return "—"
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(4)
  }
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

function historyToTurns(history: ChatHistoryResponse): {
  turns: ConversationTurn[]
  conversationId: string | null
} {
  const conversation = history.history[0]
  if (!conversation) return { turns: [], conversationId: null }
  const turns: ConversationTurn[] = []
  let pendingQuestion: string | null = null
  for (const message of conversation.messages) {
    if (message.role === "user" && message.question) {
      pendingQuestion = message.question
    } else if (message.role === "assistant" && message.response) {
      turns.push({
        id: message.message_id,
        question: pendingQuestion ?? message.response.question,
        explanation: message.response.explanation ?? "",
        response: message.response,
        status: null,
        error: message.response.error,
      })
      pendingQuestion = null
    }
  }
  return { turns, conversationId: conversation.conversation_id }
}

function csvCell(value: unknown): string {
  let text = formatCell(value)
  if (/^[=+\-@]/.test(text)) text = `'${text}`
  return `"${text.replaceAll('"', '""')}"`
}

function exportCsv(response: ChatResponse) {
  const rows = response.results ?? []
  if (!rows.length) return false
  const columns = Object.keys(rows[0])
  const csv = [
    columns.map(csvCell).join(","),
    ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(",")),
  ].join("\r\n")
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = `chat-data-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(url)
  return true
}

function pinInsight(response: ChatResponse): PinnedChatInsight {
  const existing = JSON.parse(
    localStorage.getItem(PINNED_INSIGHTS_KEY) ?? "[]"
  ) as PinnedChatInsight[]
  const insight: PinnedChatInsight = {
    id: response.message_id ?? turnId(),
    question: response.question,
    explanation: response.explanation,
    results: response.results ?? [],
    chart: response.chart,
    pinned_at: new Date().toISOString(),
  }
  const next = [insight, ...existing.filter((item) => item.id !== insight.id)].slice(
    0,
    8
  )
  localStorage.setItem(PINNED_INSIGHTS_KEY, JSON.stringify(next))
  window.dispatchEvent(new CustomEvent("pinned-chat-insights-changed"))
  return insight
}

function ResultChart({ response }: { response: ChatResponse }) {
  const spec = response.chart
  const rows = response.results ?? []
  if (!spec || !rows.length) return null
  const seriesColors = [
    "var(--accent-primary)",
    "var(--sentiment-negative)",
    "var(--sentiment-neutral)",
  ]

  return (
    <div className="h-64 min-w-0" aria-label="Chart result">
      <ResponsiveContainer width="100%" height="100%">
        {spec.type === "line" ? (
          <LineChart data={rows} margin={{ top: 8, right: 12, left: -18, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey={spec.x_key} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: 8,
              }}
            />
            <Legend />
            {spec.y_keys.map((key, index) => (
              <Line
                key={key}
                dataKey={key}
                type="monotone"
                stroke={seriesColors[index % seriesColors.length]}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        ) : (
          <BarChart data={rows} margin={{ top: 8, right: 12, left: -18, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis
              dataKey={spec.x_key}
              tick={{ fontSize: 11 }}
              interval={0}
              angle={-18}
              textAnchor="end"
              height={56}
            />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: 8,
              }}
            />
            <Legend />
            {spec.y_keys.map((key, index) => (
              <Bar
                key={key}
                dataKey={key}
                fill={seriesColors[index % seriesColors.length]}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}

function ResultTable({ response }: { response: ChatResponse }) {
  const rows = response.results ?? []
  if (!rows.length) {
    return (
      <p className="rounded-lg border border-dashed p-5 text-center text-sm text-muted-foreground">
        The query completed, but no records matched.
      </p>
    )
  }
  const columns = Object.keys(rows[0])
  return (
    <div className="max-h-72 overflow-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((column) => (
              <TableHead key={column} className="whitespace-nowrap">
                {column.replaceAll("_", " ")}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, rowIndex) => (
            <TableRow key={rowIndex}>
              {columns.map((column) => {
                const text = formatCell(row[column])
                return (
                  <TableCell
                    key={column}
                    className="whitespace-nowrap"
                    {...myanmarLangProps(text)}
                  >
                    {text}
                  </TableCell>
                )
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function AssistantResponse({
  turn,
}: {
  turn: ConversationTurn
}) {
  const [view, setView] = useState<"chart" | "table">("chart")
  const router = useRouter()
  const { toast } = useToast()
  const response = turn.response
  const explanation =
    turn.explanation || response?.clarification_question || response?.explanation

  function viewRawReviews() {
    const entityId = response?.results?.find(
      (row) => typeof row.entity_id === "number"
    )?.entity_id
    router.push(typeof entityId === "number" ? `/entities/${entityId}` : "/entities")
  }

  return (
    <div className="ml-0 space-y-4 rounded-xl border bg-card p-4 shadow-[0_10px_30px_rgba(0,0,0,0.12)]">
      <div className="flex items-center gap-2 text-sm font-medium">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/12 text-primary">
          <Bot className="h-4 w-4" aria-hidden="true" />
        </span>
        Data analyst
      </div>

      {turn.error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3">
          <p className="text-sm font-medium text-destructive">
            The analysis could not finish
          </p>
          <p className="mt-1 text-sm text-destructive/90">{turn.error}</p>
          <p className="mt-2 text-xs text-muted-foreground">
            Check the API connection, then send the question again.
          </p>
        </div>
      ) : (
        <>
          <section>
            <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Explanation
            </h3>
            <p
              className="text-sm leading-6"
              {...myanmarLangProps(explanation)}
            >
              {explanation || turn.status || "Preparing the explanation…"}
            </p>
          </section>

          {response?.clarification_question ? (
            <p className="rounded-lg border border-primary/25 bg-primary/8 p-3 text-sm">
              Reply with an entity, date range, or sentiment so I can run the right
              query.
            </p>
          ) : response ? (
            <>
              <section>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Result
                  </h3>
                  {response.chart && (response.results?.length ?? 0) > 0 && (
                    <div className="flex rounded-md border p-0.5" aria-label="Result view">
                      <Button
                        type="button"
                        variant={view === "chart" ? "secondary" : "ghost"}
                        size="sm"
                        className="h-7 px-2"
                        onClick={() => setView("chart")}
                        aria-pressed={view === "chart"}
                      >
                        <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" />
                        Chart
                      </Button>
                      <Button
                        type="button"
                        variant={view === "table" ? "secondary" : "ghost"}
                        size="sm"
                        className="h-7 px-2"
                        onClick={() => setView("table")}
                        aria-pressed={view === "table"}
                      >
                        <Table2 className="h-3.5 w-3.5" aria-hidden="true" />
                        Table
                      </Button>
                    </div>
                  )}
                </div>
                {view === "chart" && response.chart ? (
                  <ResultChart response={response} />
                ) : (
                  <ResultTable response={response} />
                )}
              </section>

              {response.sql && (
                <details className="group rounded-lg border bg-muted/30">
                  <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-xs font-medium">
                    <TerminalSquare className="h-3.5 w-3.5" aria-hidden="true" />
                    Read-only SQL
                    <span className="ml-auto text-muted-foreground group-open:hidden">
                      Show
                    </span>
                  </summary>
                  <pre className="overflow-x-auto border-t p-3 text-xs leading-5">
                    <code>{response.sql}</code>
                  </pre>
                </details>
              )}

              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Actions
                </h3>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      pinInsight(response)
                      toast({
                        title: "Pinned to Dashboard",
                        description: "The answer is available in Pinned AI insights.",
                        variant: "success",
                      })
                    }}
                  >
                    <Pin className="h-3.5 w-3.5" aria-hidden="true" />
                    Pin
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      if (exportCsv(response)) {
                        toast({
                          title: "CSV exported",
                          description: "The current result table was downloaded.",
                          variant: "success",
                        })
                      }
                    }}
                    disabled={!response.results?.length}
                  >
                    <Download className="h-3.5 w-3.5" aria-hidden="true" />
                    Export CSV
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={viewRawReviews}
                  >
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                    Raw reviews
                  </Button>
                </div>
              </section>
            </>
          ) : null}
        </>
      )}
    </div>
  )
}

export function ChatWorkspace() {
  const [question, setQuestion] = useState("")
  const [language, setLanguage] = useState<"en" | "my">("en")
  const [turns, setTurns] = useState<ConversationTurn[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [clearDialogOpen, setClearDialogOpen] = useState(false)
  const [clearing, setClearing] = useState(false)
  const historyLoadedRef = useRef(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const { toast } = useToast()

  useEffect(() => {
    if (historyLoadedRef.current) return
    historyLoadedRef.current = true
    api
      .get<ChatHistoryResponse>("/api/chat/history")
      .then((history) => {
        const restored = historyToTurns(history)
        setTurns(restored.turns)
        setConversationId(restored.conversationId)
      })
      .catch(() => {
        // The chat remains usable when optional history retrieval fails.
      })
  }, [])

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    })
  }, [turns])

  function updateTurn(id: string, update: Partial<ConversationTurn>) {
    setTurns((current) =>
      current.map((turn) => (turn.id === id ? { ...turn, ...update } : turn))
    )
  }

  async function submitQuestion(value: string) {
    const trimmed = value.trim()
    if (trimmed.length < 2 || loading) return
    const id = turnId()
    setQuestion("")
    setLoading(true)
    setTurns((current) => [
      ...current,
      {
        id,
        question: trimmed,
        explanation: "",
        response: null,
        status: "Connecting to the analytics service…",
        error: null,
      },
    ])

    try {
      const response = await api.stream("/api/chat/stream", {
        question: trimmed,
        conversation_id: conversationId,
        language,
      })
      if (!response.body) throw new Error("The server returned an empty stream")
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value: chunk } = await reader.read()
        buffer += decoder.decode(chunk ?? new Uint8Array(), { stream: !done })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.trim()) continue
          let event: ChatStreamEvent
          try {
            event = JSON.parse(line) as ChatStreamEvent
          } catch {
            throw new Error("The server sent an unreadable response")
          }
          if (event.type === "meta") {
            setConversationId(event.conversation_id)
          } else if (event.type === "status") {
            updateTurn(id, { status: event.message })
          } else if (event.type === "explanation_delta") {
            setTurns((current) =>
              current.map((turn) =>
                turn.id === id
                  ? {
                      ...turn,
                      explanation: turn.explanation + event.delta,
                      status: null,
                    }
                  : turn
              )
            )
          } else if (event.type === "clarification") {
            updateTurn(id, { explanation: event.question, status: null })
          } else if (event.type === "response") {
            updateTurn(id, {
              response: event.response,
              explanation:
                event.response.explanation ??
                event.response.clarification_question ??
                "",
              status: null,
              error: event.response.error,
            })
          } else if (event.type === "error") {
            updateTurn(id, { error: event.error, status: null })
          }
        }
        if (done) break
      }
      if (buffer.trim()) {
        const event = JSON.parse(buffer) as ChatStreamEvent
        if (event.type === "error") updateTurn(id, { error: event.error })
      }
    } catch (error) {
      updateTurn(id, {
        status: null,
        error:
          error instanceof Error
            ? error.message
            : "The analytics service could not answer",
      })
    } finally {
      setLoading(false)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void submitQuestion(question)
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      void submitQuestion(question)
    }
  }

  function startNewConversation() {
    setTurns([])
    setConversationId(null)
    setQuestion("")
  }

  async function clearChatHistory() {
    if (loading || clearing) return
    setClearing(true)
    try {
      await api.delete<void>("/api/chat/history")
      setTurns([])
      setConversationId(null)
      setQuestion("")
      setClearDialogOpen(false)
      toast({
        title: "Chat history cleared",
        description: "Pinned dashboard insights were kept.",
        variant: "success",
      })
    } catch (error) {
      toast({
        title: "Chat history was not cleared",
        description:
          error instanceof Error
            ? error.message
            : "The analytics service could not clear your history.",
        variant: "destructive",
      })
    } finally {
      setClearing(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-[calc(100vh-10rem)] w-full max-w-6xl flex-col">
      <header className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary">
            <Sparkles className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Chat with Data</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Read-only analysis with multi-turn context
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div
            className="flex rounded-md border bg-card p-0.5"
            aria-label="Response language"
          >
            <Button
              type="button"
              size="sm"
              variant={language === "en" ? "secondary" : "ghost"}
              className="h-8 px-3"
              onClick={() => setLanguage("en")}
              aria-pressed={language === "en"}
            >
              EN
            </Button>
            <Button
              type="button"
              size="sm"
              variant={language === "my" ? "secondary" : "ghost"}
              className="h-8 px-3"
              onClick={() => setLanguage("my")}
              aria-pressed={language === "my"}
            >
              <Languages className="h-3.5 w-3.5" aria-hidden="true" />
              မြန်မာ
            </Button>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-9"
            onClick={startNewConversation}
            disabled={loading}
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            New chat
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-9 text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={() => setClearDialogOpen(true)}
            disabled={loading || clearing || turns.length === 0}
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            Clear history
          </Button>
        </div>
      </header>

      <section className="flex min-h-[38rem] flex-1 flex-col overflow-hidden rounded-xl border bg-card shadow-[0_18px_50px_rgba(0,0,0,0.10)]">
        <div
          ref={scrollRef}
          className="min-h-0 flex-1 space-y-6 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8"
          aria-live="polite"
        >
          {turns.length === 0 ? (
            <div className="flex min-h-full items-center justify-center py-10">
              <div className="w-full max-w-2xl text-center">
                <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <History className="h-6 w-6" aria-hidden="true" />
                </span>
                <h2 className="mt-5 text-xl font-semibold tracking-tight">
                  Ask the dataset, not a dashboard
                </h2>
                <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
                  Compare entities, inspect sentiment trends, or break results down
                  by ABSA aspect. Every generated query is validated as read-only.
                </p>
                <div className="mt-6 grid gap-2 text-left sm:grid-cols-3">
                  {[
                    "Which entity has the most negative reviews?",
                    "Show sentiment trends over time",
                    "Which aspects appear most often?",
                  ].map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      className="min-h-20 rounded-lg border bg-background px-3 py-3 text-left text-sm leading-5 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      onClick={() => void submitQuestion(prompt)}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            turns.map((turn) => (
              <div key={turn.id} className="mx-auto max-w-4xl space-y-3">
                <div className="ml-auto max-w-[86%] rounded-xl bg-primary px-3.5 py-2.5 text-sm text-primary-foreground sm:max-w-[75%]">
                  <p {...myanmarLangProps(turn.question)}>{turn.question}</p>
                </div>
                <AssistantResponse turn={turn} />
              </div>
            ))
          )}
        </div>

        <form
          className="border-t bg-background/95 px-3 pb-3 pt-3 sm:px-5 sm:pb-5"
          onSubmit={handleSubmit}
        >
          <label htmlFor="chat-question" className="sr-only">
            Question about analytics data
          </label>
          <div className="mx-auto max-w-4xl rounded-xl border bg-card p-2 shadow-[0_8px_28px_rgba(0,0,0,0.10)] focus-within:ring-1 focus-within:ring-ring">
            <textarea
              id="chat-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder={
                language === "my"
                  ? "ဒေတာအကြောင်း မေးပါ…"
                  : "Ask about sentiment, entities, or aspects…"
              }
              maxLength={500}
              rows={2}
              className="max-h-32 min-h-14 w-full resize-none bg-transparent px-2 py-1 text-sm outline-none placeholder:text-muted-foreground"
              disabled={loading}
            />
            <div className="flex items-center justify-between gap-2">
              <span className="px-2 text-[11px] text-muted-foreground">
                Enter to send · Shift+Enter for a new line
              </span>
              <Button
                type="submit"
                size="icon"
                className="h-8 w-8"
                disabled={question.trim().length < 2 || loading}
                aria-label={loading ? "Answering question" : "Send question"}
              >
                <Send
                  className={cn("h-4 w-4", loading && "animate-pulse")}
                  aria-hidden="true"
                />
              </Button>
            </div>
          </div>
        </form>
      </section>

      <Dialog
        open={clearDialogOpen}
        onOpenChange={(open) => {
          if (!clearing) setClearDialogOpen(open)
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Clear chat history?</DialogTitle>
            <DialogDescription>
              This permanently removes every Chat with Data conversation. Pinned
              dashboard insights will stay available.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={clearing}>
                Cancel
              </Button>
            </DialogClose>
            <Button
              type="button"
              variant="destructive"
              onClick={() => void clearChatHistory()}
              disabled={clearing}
            >
              {clearing ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              )}
              {clearing ? "Clearing…" : "Clear history"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
