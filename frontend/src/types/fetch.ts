export interface ClinicalTrialsPageSnapshot {
  page_index: number;
  returned_count: number;
  next_page_token?: string | null;
}

export interface PubMedEfetchBatchSnapshot {
  batch_index: number;
  batch_ids: string[];
  returned_count: number;
}

export interface PubMedRoundSnapshot {
  round_index: number;
  retstart: number;
  retmax: number;
  returned_ids: number;
  efetch_batches: PubMedEfetchBatchSnapshot[];
}

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

export interface NamedCount {
  name: string;
  count: number;
}

export interface SponsorPhaseRow {
  sponsor: string;
  phase_counts: Record<string, number>;
  total_trials: number;
}

export interface WarningItem {
  code: string;
  level: string;
  scope: string;
  message: string;
  related_ids: string[];
  details: Record<string, unknown>;
}

export interface CoverageSnapshot {
  has_trial_evidence: boolean;
  has_literature_evidence: boolean;
  has_target_overview_evidence: boolean;
  has_pipeline_overview_evidence: boolean;
  has_research_update_evidence: boolean;
  has_competition_assessment_evidence: boolean;
  missing_dimensions: string[];
  notes: string[];
}

export interface GlobalAnalysisStats {
  total_trial_count: number;
  total_literature_count: number;
  trial_phase_distribution: Record<string, number>;
  trial_status_distribution: Record<string, number>;
  top_sponsors: NamedCount[];
  top_interventions: NamedCount[];
  top_conditions: NamedCount[];
  top_countries: NamedCount[];
  publication_count_by_year: Record<string, number>;
  publication_type_distribution: Record<string, number>;
  top_journals: NamedCount[];
  top_mesh_terms: NamedCount[];
  top_keywords: NamedCount[];
  literature_with_nct_mentions_count: number;
}

export interface TargetOverviewFacts {
  alias_terms: string[];
  disease_contexts: string[];
  top_mesh_terms: NamedCount[];
  top_keywords: NamedCount[];
  publication_type_distribution: Record<string, number>;
  representative_paper_keys: string[];
}

export interface PipelineOverviewFacts {
  phase_distribution: Record<string, number>;
  status_distribution: Record<string, number>;
  top_sponsors: NamedCount[];
  top_interventions: NamedCount[];
  top_conditions: NamedCount[];
  country_distribution: NamedCount[];
  active_trial_count: number;
  results_posted_count: number;
}

export interface ResearchUpdateFacts {
  publication_count_by_year: Record<string, number>;
  publication_type_distribution: Record<string, number>;
  top_journals: NamedCount[];
  top_mesh_terms: NamedCount[];
  top_keywords: NamedCount[];
  recent_paper_keys: string[];
  high_value_paper_keys: string[];
}

export interface CompetitionAssessmentFacts {
  sponsor_phase_matrix: SponsorPhaseRow[];
  active_sponsor_count: number;
  late_stage_trial_count: number;
  recruiting_trial_count: number;
  results_posted_count: number;
  literature_with_nct_mentions_count: number;
  sponsor_concentration: NamedCount[];
}

export interface QuerySummary {
  target: string;
  indication: string | null;
  aliases: string[];
}

export interface SectionInput<TFacts> {
  section_name: string;
  trial_keys: string[];
  literature_keys: string[];
  selection_notes: string[];
  truncation_notes: string[];
  warnings: string[];
  facts: TFacts;
}

export interface SectionInputBundle {
  target_overview: SectionInput<TargetOverviewFacts>;
  pipeline_overview: SectionInput<PipelineOverviewFacts>;
  research_update: SectionInput<ResearchUpdateFacts>;
  competition_assessment: SectionInput<CompetitionAssessmentFacts>;
}

export interface AnalysisBundleResponse {
  fetch_run_id: string;
  bundle_id: string;
  query: QuerySummary;
  global_stats: GlobalAnalysisStats;
  coverage: CoverageSnapshot;
  section_inputs: SectionInputBundle;
  warnings: WarningItem[];
  built_at: string;
}

export interface ReportWarningSummary {
  code: string;
  message: string;
  count: number;
}

export interface ReportSection {
  section_name: string;
  title: string;
  summary: string;
  markdown_body: string;
  key_takeaways: string[];
  trial_keys: string[];
  literature_keys: string[];
  warnings: string[];
}

export interface ReportResponse {
  report_id: string;
  fetch_run_id: string;
  analysis_bundle_id: string;
  target: string;
  indication: string | null;
  markdown_content: string;
  sections: ReportSection[];
  warnings: WarningItem[];
  warning_summary: ReportWarningSummary[];
  model: string | null;
  prompt_versions: string[];
  generated_at: string;
}

