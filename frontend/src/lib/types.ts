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
  total_posts: number
  total_reactions: number | null
  total_shares: number | null
  total_comments: number | null
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
  conversation_id: string | null
  message_id: string | null
  language: "en" | "my"
  clarification_question: string | null
  chart: {
    type: "bar" | "line"
    x_key: string
    y_keys: string[]
  } | null
  actions: {
    action: "pin" | "export_csv" | "view_raw_reviews"
    label: string
  }[]
}

export interface ChatHistoryMessage {
  message_id: string
  role: "user" | "assistant"
  created_at: string
  question: string | null
  response: ChatResponse | null
}

export interface ChatConversation {
  conversation_id: string
  created_at: string
  updated_at: string
  messages: ChatHistoryMessage[]
}

export interface ChatHistoryResponse {
  history: ChatConversation[]
}

export type ChatStreamEvent =
  | {
      type: "meta"
      conversation_id: string
      language: "en" | "my"
    }
  | { type: "status"; message: string }
  | { type: "explanation_delta"; delta: string }
  | { type: "clarification"; question: string }
  | { type: "response"; response: ChatResponse }
  | { type: "error"; error: string }
  | { type: "done" }

export interface PinnedChatInsight {
  id: string
  question: string
  explanation: string | null
  results: Record<string, unknown>[]
  chart: ChatResponse["chart"]
  pinned_at: string
}

export interface AssociationRule {
  antecedent: string[]
  consequent: string[]
  support: number
  confidence: number
  lift: number
  cooccurrence_count?: number
  samples?: AssociationRuleSample[]
}

export interface AssociationRuleSample {
  feedback_id: string
  entity_id: number | null
  entity_name: string | null
  review_text: string | null
  created_at: string | null
}

export interface MiningFilterSummary {
  entity_ids: number[]
  days: number | null
}

export interface AssociationRuleMeta {
  total_transactions: number
  multi_aspect_transactions: number
  minimum_transactions: number
  sufficient_data: boolean
  min_support: number
  min_confidence: number
  filters: MiningFilterSummary
  assumption: string
}

export interface AssociationRuleResponse {
  rules: AssociationRule[]
  meta?: AssociationRuleMeta
}

export type MiningAxis =
  | "positive_ratio"
  | "negative_ratio"
  | "avg_confidence"
  | "total_reviews"

export type ClusterAlgorithm = "kmeans" | "hierarchical"

export interface EntityClusterMember {
  entity_id: number
  entity_name: string
  platform: string
  total_reviews: number
  positive_ratio: number
  negative_ratio: number
  avg_confidence: number
  x_value?: number
  y_value?: number
}

export interface EntityCluster {
  cluster_id: number
  label: string
  entities: EntityClusterMember[]
  centroid: {
    positive_ratio: number
    negative_ratio: number
    avg_confidence: number
    total_reviews?: number
    x_value?: number
    y_value?: number
  }
}

export interface EntityClusterMeta {
  algorithm: ClusterAlgorithm
  requested_k: number
  actual_clusters: number
  x_axis: MiningAxis
  y_axis: MiningAxis
  total_entities: number
  minimum_entities: number
  sufficient_data: boolean
  filters: MiningFilterSummary
  assumption: string
}

export interface EntityClusterResponse {
  clusters: EntityCluster[]
  meta?: EntityClusterMeta
}

// ---------- Brand mappings ----------

export interface BrandEntity {
  entity_id: number
  entity_name: string
  platform: string
}

export interface Brand {
  brand_id: number
  brand_name: string
  facebook_entity: BrandEntity
  foodpanda_shops: BrandEntity[]
}

export interface BrandWrite {
  brand_name: string
  facebook_entity_id: number
  foodpanda_entity_ids: number[]
}

// ---------- Competitor benchmarking ----------

export interface BenchmarkBrand {
  brand_id: number
  brand_name: string
  facebook_entity_id: number
  foodpanda_entity_ids: number[]
  review_count: number
  eligible: boolean
  facebook_post_count: number
  facebook_weighted_engagement: number
  facebook_share: number | null
  foodpanda_share: number | null
  combined_share_of_voice: number | null
  net_sentiment: number | null
  warning: string | null
}

export interface BenchmarkAspectCell {
  brand_id: number
  aspect: string
  observation_count: number
  positive_count: number
  negative_count: number
  neutral_count: number
  net_sentiment: number | null
  eligible: boolean
}

export interface BenchmarkInsight {
  kind: "advantage" | "vulnerability"
  aspect: string
  primary_brand_id: number
  competitor_brand_id: number
  delta: number
}

export interface BenchmarkResponse {
  brands: BenchmarkBrand[]
  aspects: BenchmarkAspectCell[]
  insights: BenchmarkInsight[]
  meta: {
    filters: {
      brands: Array<{
        brand_id: number
        foodpanda_entity_ids: number[]
      }>
      days: number
    }
    minimum_reviews: number
    delta_threshold: number
    sufficient_data: boolean
    eligible_brand_count: number
    channel_shares_available: boolean
    assumptions: string[]
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
  phase: string | null
  progress_percent: number | null
  cancellation_requested: boolean
  saved_entity_id: string | null
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

export interface ScrapeReadiness {
  source: "facebook" | "foodpanda"
  ready: boolean
  mongodb_ready: boolean
  cookies_ready: boolean | null
  pipeline_ready?: boolean | null
  postgres_ready?: boolean | null
  models_ready?: boolean | null
  pipeline_message?: string | null
  message: string
}

export interface SavedScrapeEntity {
  id: string
  dim_entity_id: number | null
  source: "facebook" | "foodpanda"
  source_url: string
  display_name: string
  max_posts: number
  headless: boolean
  auto_pipeline: boolean
  created_at: string
  updated_at: string
  last_scraped_at: string | null
  last_scrape_status: string | null
  last_scrape_error: string | null
}

export interface ScrapeSchedule {
  id: string
  entity_id: string
  cron_expression: string
  timezone: string
  active: boolean
  created_at: string
  updated_at: string
  next_run: string | null
  last_run_at: string | null
  display_name: string | null
  source: string | null
}

export interface ScrapeDetectResponse {
  source: "facebook" | "foodpanda" | null
  entity_name: string | null
  supported: boolean
  message: string
}

export const ASPECT_LABELS: Record<string, string> = {
  product_quality: "Product Quality",
  fulfillment_and_speed: "Fulfillment & Speed",
  price_and_value: "Price & Value",
  staff_and_service: "Staff & Service",
  variety_and_availability: "Variety & Availability",
}

export interface EntityAspectItem {
  aspect_category: string
  sentiment_label: string
  count: number
}

export interface EntityReview {
  feedback_id: string
  review_text: string | null
  sentiment_label: string | null
  confidence_score: number | null
  aspect_category: string | null
  created_at: string | null
}

export interface EntityReviewPage {
  reviews: EntityReview[]
  total: number
  next_cursor: string | null
  focus_review: EntityReview | null
}

export interface EntityDetail {
  entity_id: number
  entity_name: string
  platform: string
  total_posts: number
  total_reactions: number | null
  total_shares: number | null
  total_comments: number | null
  total_reviews: number
  positive_count: number
  negative_count: number
  neutral_count: number
  positive_ratio: number | null
  negative_ratio: number | null
  avg_confidence: number | null
  aspects: EntityAspectItem[]
}

// ---------- Dashboard KPI strip ----------

export interface DailyVolume {
  date: string
  count: number
}

export interface KpiResponse {
  total_reviews: number
  prev_total_reviews: number
  volume_delta_pct: number | null
  daily_volumes: DailyVolume[]
  sentiment_health: number | null
  sentiment_health_delta: number | null
  hangry_index: number | null
  hangry_delta: number | null
}

// ---------- Social engagement (Facebook reactions) ----------

export interface ReactionMix {
  like: number
  love: number
  care: number
  haha: number
  wow: number
  sad: number
  angry: number
  total_posts: number
  incomplete_posts: number
  positivity_ratio: number | null
  negativity_ratio: number | null
  haha_ratio: number | null
}

export interface EngagementTrendPoint {
  date: string
  total_reactions: number | null
  total_shares: number | null
  total_comments: number | null
  positivity_ratio: number | null
  negativity_ratio: number | null
  haha_ratio: number | null
}

// ---------- Top drivers & flagged reviews ----------

export interface DriverItem {
  aspect: string
  negative_count: number
  total_count: number
  negative_share: number
  avg_confidence: number | null
}

export interface FlaggedReview {
  review_text: string | null
  sentiment_label: string | null
  confidence_score: number | null
  aspect_category: string | null
  entity_name: string | null
  created_at: string | null
}

// ---------- ETL (used by the topbar sync badge) ----------

export interface EtlRunHistory {
  run_id: string
  run_type: string
  status: string
  started_at: string
  completed_at: string | null
  duration_seconds: number | null
  stats: Record<string, unknown> | null
  error: string | null
}

export type PipelineStatus =
  | "active"
  | "healthy"
  | "idle"
  | "stale"
  | "error"
  | "unavailable"

export interface PipelineNodeHealth {
  id: "scraper" | "mongodb" | "nlp" | "postgresql"
  label: string
  status: PipelineStatus
  metrics: Record<string, string | number | boolean | null>
  detail: string
  last_activity_at: string | null
  error: string | null
}

export interface PostgresLoadStatus {
  table: string
  row_count: number | null
  last_loaded_at: string | null
  rows_loaded: number | null
  status: PipelineStatus
}

export interface EtlHealthResponse {
  generated_at: string
  overall_status: PipelineStatus
  stale_after_minutes: number
  nodes: PipelineNodeHealth[]
  loads: PostgresLoadStatus[]
  latest_run: EtlRunHistory | null
}
