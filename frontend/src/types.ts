export type TrendPoint = {
  year: number;
  count: number;
};

export type KeywordCount = {
  keyword: string;
  count: number;
};

export type FieldCount = {
  field: string;
  count: number;
};

export type CollaborationEdge = {
  source: string;
  target: string;
  weight: number;
};

export type DashboardOverview = {
  total_papers: number;
  year_range: {
    start: number | null;
    end: number | null;
  };
  publication_trend: TrendPoint[];
  field_distribution: FieldCount[];
  top_keywords: KeywordCount[];
  collaboration_edges: CollaborationEdge[];
};

export type EvidenceItem = {
  paper_id: string;
  title: string;
  year: number | null;
  reason: string;
  authors?: string[];
  snippet?: string;
};

export type ChatResponse = {
  answer: string;
  evidence: EvidenceItem[];
  confidence: string;
};

export type SearchResultItem = {
  paper_id: string;
  title: string;
  year: number | null;
  field: string;
  authors: string[];
  snippet: string;
  score: number;
  matched_by: string[];
};

export type SearchResponse = {
  query: string;
  count: number;
  results: SearchResultItem[];
};

export type TrendKeyword = {
  keyword: string;
  doc_count: number | null;
  normalized_df: number | null;
  momentum_score: number | null;
  burst_score: number | null;
  trend_slope: number | null;
  trend_r2: number | null;
  forecast_year: number | null;
  forecast_normalized_df: number | null;
  forecast_low: number | null;
  forecast_high: number | null;
  trend_score: number | null;
  lifecycle_stage: string | null;
  representative_title: string | null;
  representative_year: number | null;
};

export type TrendSeriesPoint = {
  year: number;
  normalized_df: number;
};

export type TrendsResponse = {
  generated_at: string | null;
  fit_years: number[];
  forecast_year: number | null;
  method: string;
  uncertainty_note: string;
  top_hot: TrendKeyword[];
  top_emerging: TrendKeyword[];
  series: TrendSeriesPoint[];
  keyword: string | null;
};

export type Recommendation = {
  paper_id: string;
  title: string;
  year: number | null;
  field: string;
  score: number;
  semantic_similarity: number;
  shared_keywords: string[];
  shared_authors: string[];
  factors: Record<string, number>;
};

export type RecommendResponse = {
  paper_id: string;
  count: number;
  recommendations: Recommendation[];
};

export type GraphNode = {
  id: string;
  label?: string | null;
  [key: string]: unknown;
};

export type GraphEdge = {
  source: string;
  target: string;
  weight: number;
};

export type GraphResponse = {
  type: string;
  center: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
};
