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
};

export type ChatResponse = {
  answer: string;
  evidence: EvidenceItem[];
  confidence: string;
};
