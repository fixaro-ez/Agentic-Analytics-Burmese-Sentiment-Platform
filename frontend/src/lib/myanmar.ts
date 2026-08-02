/**
 * Burmese (Myanmar) text helpers.
 *
 * Native Myanmar Unicode should render with Noto Sans Myanmar (v3 spec §5.4),
 * while Burglish/English keeps the default UI font. Apply `lang="my"` to any
 * element containing Myanmar text — globals.css switches the font-family for
 * that subtree automatically.
 */

// Myanmar Unicode blocks: Myanmar (U+1000–109F), Myanmar Extended-A (U+AA60–AA7F),
// Myanmar Extended-B (U+A9E0–A9FF).
const MYANMAR_RE = /[က-ၟꩠ-ꩿꧠ-꧿]/u

/** True if the string contains at least one Myanmar Unicode character. */
export function containsMyanmar(text: string | null | undefined): boolean {
  return !!text && MYANMAR_RE.test(text)
}

/**
 * Props to spread onto an element so Burmese text gets lang="my" (and thus
 * Noto Sans Myanmar via globals.css). Returns an empty object for
 * Burglish/English so the default UI font is kept.
 */
export function myanmarLangProps(
  text: string | null | undefined
): { lang: "my" } | Record<string, never> {
  return containsMyanmar(text) ? { lang: "my" } : {}
}

/**
 * Grapheme-aware truncation (v3 spec §5.4): Myanmar script combines multiple
 * codepoints per visual character, so naive slice() can split a character in
 * half. Uses Intl.Segmenter when available, with a codepoint-safe fallback.
 */
export function truncateGraphemes(
  text: string | null | undefined,
  maxGraphemes: number
): string {
  if (!text) return ""
  if (typeof Intl !== "undefined" && "Segmenter" in Intl) {
    const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" })
    const segments = Array.from(segmenter.segment(text))
    if (segments.length <= maxGraphemes) return text
    return segments
      .slice(0, maxGraphemes)
      .map((s) => s.segment)
      .join("") + "…"
  }
  const codepoints = Array.from(text)
  if (codepoints.length <= maxGraphemes) return text
  return codepoints.slice(0, maxGraphemes).join("") + "…"
}
