import { NextResponse } from "next/server";
import { sql } from "@vercel/postgres"; // or your Postgres client
import OpenAI from "openai";

const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

export async function POST(req: Request) {
  const { query } = await req.json();

  // 1. Generate SQL from natural language
  const completion = await client.chat.completions.create({
    model: "gpt-4o-mini", // or whichever model you’re using
    messages: [
      { role: "system", content: "You are a SQL generator for a Postgres star schema." },
      { role: "user", content: query }
    ]
  });

  const sqlQuery = completion.choices[0].message?.content || "SELECT 1";

  // 2. Execute SQL (read-only)
  const result = await sql`${sqlQuery}`;

  // 3. Return structured response
  return NextResponse.json({
    summary: "Generated summary here",
    sql: sqlQuery,
    rows: result.rows,
  });
}
