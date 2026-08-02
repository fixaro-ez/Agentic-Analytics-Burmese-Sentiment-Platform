export type DetectedScrapeUrl = {
  source: "facebook" | "foodpanda" | null
  name: string
}

export function detectScrapeUrl(value: string): DetectedScrapeUrl {
  try {
    const url = new URL(value)
    if (url.protocol !== "https:") return { source: null, name: "" }
    const hostname = url.hostname.toLowerCase()
    const source =
      hostname === "facebook.com" || hostname.endsWith(".facebook.com")
        ? "facebook"
        : hostname.includes("foodpanda.")
          ? "foodpanda"
          : null
    if (!source) return { source: null, name: "" }
    if (
      source === "foodpanda" &&
      !/^\/(?:[a-z]{2}\/)?restaurant\/[a-z0-9]{4}\/[^/]+(?:\/reviews)?\/?$/i.test(
        url.pathname
      )
    ) {
      return { source: null, name: "" }
    }
    const ignored = new Set([
      "pages",
      "posts",
      "photos",
      "videos",
      "restaurant",
      "restaurants",
    ])
    const parts = decodeURIComponent(url.pathname)
      .split("/")
      .filter((part) => part && !ignored.has(part.toLowerCase()))
    const slug = source === "foodpanda" ? parts.at(-1) : parts[0]
    const normalizedSlug =
      source === "foodpanda"
        ? (slug ?? "")
        : (slug ?? "").replace(/^[a-z0-9]{5,12}-/i, "")
    const name = normalizedSlug
      .replaceAll(/[-_.]+/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase())
      .trim()
    return { source, name }
  } catch {
    return { source: null, name: "" }
  }
}

export function splitSseBuffer(buffer: string): {
  data: string[]
  remainder: string
} {
  const blocks = buffer.replaceAll("\r\n", "\n").split("\n\n")
  const remainder = blocks.pop() ?? ""
  const data = blocks.flatMap((block) => {
    const lines = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
    return lines.length ? [lines.join("\n")] : []
  })
  return { data, remainder }
}
