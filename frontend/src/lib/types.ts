export interface Entity {
  entity_id: number
  entity_name: string
  platform: string
  platform_metadata: Record<string, unknown> | null
}

export interface EntityListResponse {
  entities: Entity[]
  total: number
}

export interface SentimentOverview {
  total_reviews: number
  positive_count: number
  negative_count: number
  neutral_count: number
  positive_ratio: number
  negative_ratio: number
  avg_confidence: number | null
}

export interface EntitySentimentOverview {
  entity_id: number
  entity_name: string
  platform: string
  total_reviews: number
  positive_count: number
  negative_count: number
  neutral_count: number
  positive_ratio: number | null
  negative_ratio: number | null
  avg_confidence: number | null
}

export interface AspectBreakdown {
  aspect: string
  sentiment: string
  count: number
  avg_confidence: number
}

export interface SentimentTrendPoint {
  date: string
  entity_id: number | null
  entity_name: string | null
  total_reviews: number
  positive_count: number
  negative_count: number
  neutral_count: number
  positive_ratio: number
}

export interface FacebookEngagement {
  entity_id: number
  entity_name: string
  total_posts: number
  total_reactions: number | null
  total_shares: number | null
  total_comments: number | null
  avg_positivity_ratio: number | null
  avg_negativity_ratio: number | null
}

export interface ChatResponse {
  question: string
  sql: string | null
  results: Record<string, unknown>[] | null
  explanation: string | null
  error: string | null
}

export interface AlertItem {
  alert_id: number
  entity_id: number | null
  entity_name: string | null
  alert_type: string
  severity: string
  message: string
  created_at: string
  acknowledged: boolean
}

export const ASPECT_LABELS: Record<string, string> = {
  product_or_service_quality: "Product/Service Quality",
  fulfillment_and_speed: "Fulfillment & Speed",
  price_and_value: "Price & Value",
  digital_experience: "Digital Experience",
  customer_support: "Customer Support",
  variety_and_availability: "Variety & Availability",
}
