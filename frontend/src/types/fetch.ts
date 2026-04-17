export interface SourceFetchSummary {
  source_name: "clinicaltrials" | "pubmed";
  success: boolean;
  fetched_count: number;
  total_count: number | null;
  elapsed_ms: number;
  warning: string | null;
  request_snapshot: Record<string, unknown>;
}

export interface FetchCreateRequest {
  target: string;
  indication?: string;
  aliases?: string[];
  source_configs: Record<string, unknown>;
}

export interface FetchRunResponse {
  fetch_run_id: string;
  target: string;
  indication: string | null;
  aliases: string[];
  status: string;
  raw_record_count: number;
  source_results: SourceFetchSummary[];
  warnings: string[];
  created_at: string;
  updated_at: string;
}

export interface RawRecord {
  record_id: string;
  fetch_run_id: string;
  source_name: "clinicaltrials" | "pubmed";
  source_id: string;
  source_url: string | null;
  target: string;
  indication: string | null;
  query_snapshot: Record<string, unknown>;
  retrieved_at: string;
}

export interface RawRecordListResponse {
  fetch_run_id: string;
  total_items: number;
  limit: number;
  offset: number;
  items: RawRecord[];
}

