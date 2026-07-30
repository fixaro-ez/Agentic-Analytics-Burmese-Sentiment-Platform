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

export interface AlertConfig {
  negative_threshold: number
  spike_window_hours: number
  spike_zscore: number
}

export interface AssociationRule {
  antecedent: string[]
  consequent: string[]
  support: number
  confidence: number
  lift: number
}

export interface EntityClusterMember {
  entity_id: number
  entity_name: string
  platform: string
  total_reviews: number
  positive_ratio: number
  negative_ratio: number
  avg_confidence: number
}

export interface EntityCluster {
  cluster_id: number
  label: string
  entities: EntityClusterMember[]
  centroid: {
    positive_ratio: number
    negative_ratio: number
    avg_confidence: number
  }
}

// ---------- Scraping types ----------

export interface ScrapeRunResponse {
  run_id: string
  status: string
  message: string
}

export interface ScrapeRunStatus {
  run_id: string
  source: string
  entity_name: string
  url: string
  status: string
  started_at: string
  completed_at: string | null
  duration_seconds: number | null
  stats: Record<string, unknown> | null
  error: string | null
  etl_run_id: string | null
}

export interface ScrapeRunHistory {
  run_id: string
  run_type: string
  status: string
  started_at: string
  completed_at: string | null
  duration_seconds: number | null
  stats: Record<string, unknown> | null
  error: string | null
}

export interface CookieStatus {
  exists: boolean
  valid: boolean
  expires_at: string | null
  message: string
}

export const ASPECT_LABELS: Record<string, string> = {
  product_or_service_quality: "Product/Service Quality",
  fulfillment_and_speed: "Fulfillment & Speed",
  price_and_value: "Price & Value",
  digital_experience: "Digital Experience",
  customer_support: "Customer Support",
  variety_and_availability: "Variety & Availability",
}

export interface EntityAspectItem {
  aspect_category: string
  sentiment_label: string
  count: number
}

export interface EntityReview {
  review_text: string | null
  sentiment_label: string | null
  confidence_score: number | null
  aspect_category: string | null
  created_at: string | null
}

export interface EntityDetail {
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
  aspects: EntityAspectItem[]
  reviews: EntityReview[]
}
