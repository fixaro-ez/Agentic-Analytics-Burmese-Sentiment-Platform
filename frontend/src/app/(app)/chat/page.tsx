"use client"

import { useState } from "react"
import { Send } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export default function ChatPage() {
  const [question, setQuestion] = useState("")

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Chat with Data</h1>
        <p className="text-muted-foreground">
          Ask questions about your sentiment data in natural language.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Ask a Question</CardTitle>
          <CardDescription>
            Examples: &quot;Which entity has the most negative reviews?&quot;,
            &quot;Show me sentiment trends for Foodpanda shops&quot;
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Input
              placeholder="Type your question here..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              className="flex-1"
            />
            <Button>
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Results</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
            <p className="text-sm text-muted-foreground">
              TODO(Member 5): Display chat response.
              POST /api/chat/query with body: {`{ "question": "..." }`}.
              Show: SQL query (syntax highlighted), results table, explanation.
              Add chat history sidebar — GET /api/chat/history.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
