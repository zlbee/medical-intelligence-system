import { useEffect, useState, type FormEvent } from "react";

import {
  buildAnalysisBundle,
  buildReport,
  createFetchRun,
  getAnalysisBundle,
  getReport,
  listRawRecords,
} from "../services/fetchApi";
import { fetchHealth } from "../services/healthApi";
import type {
  AnalysisBundleResponse,
  FetchRunResponse,
  ClinicalTrialsPageSnapshot,
  NamedCount,
  PubMedRoundSnapshot,
  RawRecord,
  ReportResponse,
  SourceFetchSummary,
  WarningItem,
} from "../types/fetch";
import type { HealthResponse } from "../types/health";

type LoadState = "idle" | "loading" | "success" | "error";
type SubmitState = "idle" | "submitting" | "success" | "error";
type AnalysisState = "idle" | "loading" | "success" | "error";
type ReportState = "idle" | "loading" | "success" | "error";
type ReportAction = "build" | "download" | null;
type RawRecordSampleGroup = {
  sourceName: RawRecord["source_name"];
  totalCount: number;
  items: RawRecord[];
};
type TruncationNoteItem = {
  key: string;
  sectionLabel: string;
  note: string;
};
type ChartDatum = {
  label: string;
  value: number;
};
type ChartPoint = ChartDatum & {
  x: number;
  y: number;
};

const MAX_RAW_RECORD_SAMPLES_PER_SOURCE = 5;
const MAX_RAW_RECORD_FETCH_PER_SOURCE = 200;
const PHASE_SORT_ORDER: Record<string, number> = {
  EARLY_PHASE1: 10,
  PHASE1: 20,
  PHASE1__PHASE2: 30,
  PHASE2: 40,
  PHASE2__PHASE3: 50,
  PHASE3: 60,
  PHASE4: 70,
  NOT_APPLICABLE: 80,
};

function formatDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}/${month}/${day}`;
}

function formatClinicalTrialsDate(date: Date): string {
  return formatDate(date).replaceAll("/", "-");
}

const today = new Date();
const oneYearAgo = new Date(today);
oneYearAgo.setFullYear(today.getFullYear() - 1);

// Keep the target/alias terms in the dedicated form fields. The default
// ClinicalTrials query term only contributes additional study filters so the
// frontend can safely merge both parts before submission.
const defaultClinicalTrialsFilterTerm = [
  "(AREA[Phase]PHASE2 OR AREA[Phase]PHASE3)",
  "AREA[StudyType]INTERVENTIONAL",
  `AREA[LastUpdatePostDate]RANGE[${formatClinicalTrialsDate(oneYearAgo)}, MAX]`,
].join(" AND ");

const defaultSourceConfigs = JSON.stringify(
  {
    clinicaltrials: {
      enabled: true,
      page_size: 10,
      count_total: true,
      query: {
        term: defaultClinicalTrialsFilterTerm,
      },
      filters: {
        overallStatus: ["RECRUITING", "ACTIVE_NOT_RECRUITING", "COMPLETED"],
      },
    },
    pubmed: {
      enabled: true,
      retmax: 10,
      batch_size: 5,
      sort: "pub_date",
      filters: {
        publication_types: [
          "Clinical Trial",
          "Clinical Trial, Phase II",
          "Clinical Trial, Phase III",
        ],
        date_from: formatDate(oneYearAgo),
        date_to: formatDate(today),
        has_abstract: true,
      },
    },
  },
  null,
  2,
);

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatCountMap(values: Record<string, number>, limit = 5): string {
  const entries = Object.entries(values);
  if (!entries.length) {
    return "暂无";
  }
  return entries
    .slice(0, limit)
    .map(([name, count]) => `${name}: ${count}`)
    .join(" / ");
}

function formatNamedCounts(items: NamedCount[], limit = 4): string {
  if (!items.length) {
    return "暂无";
  }
  return items
    .slice(0, limit)
    .map((item) => `${item.name} (${item.count})`)
    .join(" / ");
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatPhaseToken(token: string): string {
  const normalized = token.trim().toUpperCase();
  const explicitLabels: Record<string, string> = {
    EARLY_PHASE1: "Early Phase 1",
    PHASE1: "Phase 1",
    PHASE2: "Phase 2",
    PHASE3: "Phase 3",
    PHASE4: "Phase 4",
    NOT_APPLICABLE: "Not Applicable",
  };
  const explicitLabel = explicitLabels[normalized];
  if (explicitLabel) {
    return explicitLabel;
  }
  return normalized
    .replace(/PHASE(\d)/g, "Phase $1")
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatPhaseLabel(value: string): string {
  return value.split("__").map(formatPhaseToken).join(" / ");
}

function buildPhaseChartData(distribution: Record<string, number>): ChartDatum[] {
  return Object.entries(distribution)
    .filter(([, count]) => count > 0)
    .sort(([leftPhase], [rightPhase]) => {
      const leftOrder = PHASE_SORT_ORDER[leftPhase] ?? 999;
      const rightOrder = PHASE_SORT_ORDER[rightPhase] ?? 999;
      if (leftOrder !== rightOrder) {
        return leftOrder - rightOrder;
      }
      return leftPhase.localeCompare(rightPhase);
    })
    .map(([phase, count]) => ({
      label: formatPhaseLabel(phase),
      value: count,
    }));
}

function buildPublicationTrendData(distribution: Record<string, number>): ChartDatum[] {
  return Object.entries(distribution)
    .filter(([, count]) => count > 0)
    .sort(([leftYear], [rightYear]) => {
      const leftValue = Number(leftYear);
      const rightValue = Number(rightYear);
      if (Number.isNaN(leftValue) || Number.isNaN(rightValue)) {
        return leftYear.localeCompare(rightYear);
      }
      return leftValue - rightValue;
    })
    .map(([year, count]) => ({
      label: year,
      value: count,
    }));
}

function buildTruncationNoteItems(
  analysisResult: AnalysisBundleResponse | null,
): TruncationNoteItem[] {
  if (!analysisResult) {
    return [];
  }

  return [
    ...analysisResult.section_inputs.target_overview.truncation_notes.map((note) => ({
      key: `target-${note}`,
      sectionLabel: "靶点概述",
      note,
    })),
    ...analysisResult.section_inputs.pipeline_overview.truncation_notes.map((note) => ({
      key: `pipeline-${note}`,
      sectionLabel: "在研管线",
      note,
    })),
    ...analysisResult.section_inputs.research_update.truncation_notes.map((note) => ({
      key: `research-${note}`,
      sectionLabel: "研究动态",
      note,
    })),
    ...analysisResult.section_inputs.competition_assessment.truncation_notes.map((note) => ({
      key: `competition-${note}`,
      sectionLabel: "竞争格局",
      note,
    })),
  ];
}

type WarningSummary = {
  key: string;
  message: string;
  count: number;
  errorType: string | null;
  errorText: string | null;
};

function summarizeWarnings(warnings: WarningItem[]): WarningSummary[] {
  const summaryMap = new Map<string, WarningSummary>();

  for (const warning of warnings) {
    const errorType =
      typeof warning.details.error_type === "string" ? warning.details.error_type : null;
    const errorText =
      typeof warning.details.error === "string" ? warning.details.error : null;
    const key = [warning.code, warning.message, errorType ?? "", errorText ?? ""].join("|");
    const existing = summaryMap.get(key);

    if (existing) {
      existing.count += 1;
      continue;
    }

    // Stage 2 may emit one warning per failed record. We aggregate identical failures
    // so the UI stays readable while still surfacing the underlying cause.
    summaryMap.set(key, {
      key,
      message: warning.message,
      count: 1,
      errorType,
      errorText,
    });
  }

  return Array.from(summaryMap.values());
}

type SnapshotSummary = {
  stopReason: string | null;
  lines: string[];
};

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function buildClinicalTrialsTargetExpression(target: string, aliases: string[]): string {
  const terms = [target, ...aliases]
    .map((item) => item.trim())
    .filter(Boolean);
  const uniqueTerms = Array.from(new Set(terms));

  if (uniqueTerms.length === 1) {
    return uniqueTerms[0];
  }

  return uniqueTerms.join(" OR ");
}

function mergeClinicalTrialsTargetIntoSourceConfigs(
  sourceConfigs: Record<string, unknown>,
  target: string,
  aliases: string[],
): Record<string, unknown> {
  const clinicalTrialsConfig = sourceConfigs.clinicaltrials;
  if (!isObjectRecord(clinicalTrialsConfig)) {
    return sourceConfigs;
  }

  const clinicalTrialsQuery = isObjectRecord(clinicalTrialsConfig.query)
    ? clinicalTrialsConfig.query
    : {};
  const configuredTerm =
    typeof clinicalTrialsQuery.term === "string" ? clinicalTrialsQuery.term.trim() : "";
  const targetExpression = buildClinicalTrialsTargetExpression(target, aliases);

  if (!configuredTerm || !targetExpression) {
    return sourceConfigs;
  }

  // The source-config editor is intended for supplemental ClinicalTrials filters.
  // Merge the target inputs back into query.term so adding phase/date constraints
  // does not silently discard the requested target.
  return {
    ...sourceConfigs,
    clinicaltrials: {
      ...clinicalTrialsConfig,
      query: {
        ...clinicalTrialsQuery,
        term: `(${targetExpression}) AND (${configuredTerm})`,
      },
    },
  };
}

function sampleItemsEvenly<T>(items: T[], sampleSize: number): T[] {
  if (items.length <= sampleSize) {
    return items;
  }
  if (sampleSize <= 1) {
    return items.slice(0, 1);
  }

  // Keep the sample deterministic and spread across the whole result set so
  // the preview covers early, middle, and late records from each source.
  const selectedIndices = new Set<number>();
  const stride = (items.length - 1) / (sampleSize - 1);

  for (let index = 0; index < sampleSize; index += 1) {
    selectedIndices.add(Math.round(index * stride));
  }

  for (let index = 0; selectedIndices.size < sampleSize && index < items.length; index += 1) {
    selectedIndices.add(index);
  }

  return Array.from(selectedIndices)
    .sort((left, right) => left - right)
    .slice(0, sampleSize)
    .map((index) => items[index]);
}

function buildRawRecordSampleGroups(
  records: RawRecord[],
  sourceResults: SourceFetchSummary[],
  maxPerSource: number,
): RawRecordSampleGroup[] {
  const sourceGroups = new Map<RawRecord["source_name"], RawRecord[]>();
  const sourceTotals = new Map<RawRecord["source_name"], number>();

  for (const source of sourceResults) {
    if (source.fetched_count <= 0) {
      continue;
    }
    sourceGroups.set(source.source_name, []);
    sourceTotals.set(source.source_name, source.fetched_count);
  }

  for (const record of records) {
    const group = sourceGroups.get(record.source_name) ?? [];
    group.push(record);
    sourceGroups.set(record.source_name, group);
  }

  return Array.from(sourceGroups.entries()).map(([sourceName, items]) => ({
    sourceName,
    totalCount: sourceTotals.get(sourceName) ?? items.length,
    items: sampleItemsEvenly(items, maxPerSource),
  }));
}

async function loadRawRecordSamples(
  fetchRunId: string,
  sourceResults: SourceFetchSummary[],
): Promise<RawRecord[]> {
  const sourceRequests = sourceResults
    .filter((source) => source.fetched_count > 0)
    .map((source) =>
      listRawRecords(fetchRunId, {
        sourceName: source.source_name,
        // Request source-specific records so one source cannot crowd out the other
        // when the API default pagination limit is smaller than the total fetch size.
        limit: Math.min(source.fetched_count, MAX_RAW_RECORD_FETCH_PER_SOURCE),
      }),
    );

  const settledResponses = await Promise.allSettled(sourceRequests);
  return settledResponses.flatMap((result) =>
    result.status === "fulfilled" ? result.value.items : [],
  );
}

function isClinicalTrialsPageSnapshot(value: unknown): value is ClinicalTrialsPageSnapshot {
  return (
    isObjectRecord(value) &&
    typeof value.page_index === "number" &&
    typeof value.returned_count === "number"
  );
}

function isPubMedRoundSnapshot(value: unknown): value is PubMedRoundSnapshot {
  return (
    isObjectRecord(value) &&
    typeof value.round_index === "number" &&
    typeof value.retstart === "number" &&
    typeof value.retmax === "number" &&
    typeof value.returned_ids === "number" &&
    Array.isArray(value.efetch_batches)
  );
}

function formatStopReason(reason: string | null): string {
  if (!reason) {
    return "未知";
  }

  const labels: Record<string, string> = {
    record_cap_reached: "达到环境变量记录上限",
    no_next_page_token: "来源不再返回下一页",
    empty_page: "下一页为空",
    no_more_ids: "来源未返回更多 PMID",
    retstart_exhausted_total_count: "已达到来源可返回总量",
  };
  const label = labels[reason];
  return label ? `${reason}（${label}）` : reason;
}

// The fetch API returns source-specific request snapshots. We normalize the few
// fields we care about here so the UI can show pagination progress without
// coupling the whole page to backend payload details.
function summarizeSourceRequestSnapshot(source: SourceFetchSummary): SnapshotSummary {
  const snapshot = isObjectRecord(source.request_snapshot) ? source.request_snapshot : {};
  const stopReason =
    typeof snapshot.stop_reason === "string" ? snapshot.stop_reason : null;
  const appliedRecordCap =
    typeof snapshot.applied_record_cap === "number" ? snapshot.applied_record_cap : null;
  const lines: string[] = [];

  if (appliedRecordCap !== null) {
    lines.push(`记录上限：${appliedRecordCap}`);
  }

  if (source.source_name === "clinicaltrials") {
    const pages = Array.isArray(snapshot.pages)
      ? snapshot.pages.filter(isClinicalTrialsPageSnapshot)
      : [];
    if (pages.length) {
      const pagePreview = pages
        .slice(0, 3)
        .map((page) => `第 ${page.page_index + 1} 页 ${page.returned_count} 条`)
        .join(" / ");
      lines.push(
        `分页摘要：共 ${pages.length} 页${pagePreview ? `，${pagePreview}` : ""}${
          pages.length > 3 ? ` / 其余 ${pages.length - 3} 页` : ""
        }`,
      );
    }
  }

  if (source.source_name === "pubmed") {
    const rounds = Array.isArray(snapshot.rounds)
      ? snapshot.rounds.filter(isPubMedRoundSnapshot)
      : [];
    if (rounds.length) {
      const totalBatches = rounds.reduce(
        (sum, round) => sum + round.efetch_batches.length,
        0,
      );
      const roundPreview = rounds
        .slice(0, 3)
        .map(
          (round) =>
            `第 ${round.round_index + 1} 轮 retstart=${round.retstart} / IDs ${round.returned_ids}`,
        )
        .join(" / ");
      lines.push(
        `轮次摘要：共 ${rounds.length} 轮 esearch，${totalBatches} 个 efetch 批次${
          roundPreview ? `，${roundPreview}` : ""
        }${rounds.length > 3 ? ` / 其余 ${rounds.length - 3} 轮` : ""}`,
      );
    }
  }

  return {
    stopReason,
    lines,
  };
}

function buildReportFileName(report: ReportResponse): string {
  const targetPart = report.target.trim().replace(/[\\/:*?"<>|\s]+/g, "-") || "report";
  return `${targetPart}-${report.fetch_run_id}.md`;
}

function buildPolylinePath(points: ChartPoint[]): string {
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");
}

function buildAreaPath(points: ChartPoint[], baselineY: number): string {
  if (!points.length) {
    return "";
  }
  const linePath = buildPolylinePath(points);
  const firstPoint = points[0];
  const lastPoint = points[points.length - 1];
  return `${linePath} L ${lastPoint.x} ${baselineY} L ${firstPoint.x} ${baselineY} Z`;
}

function PhaseDistributionChart({ data }: { data: ChartDatum[] }) {
  if (!data.length) {
    return <p className="chart-empty">暂无可视化阶段分布数据。</p>;
  }

  const chartWidth = 480;
  const labelColumnWidth = 136;
  const barAreaWidth = 220;
  const chartHeight = 18 + data.length * 38;
  const maxValue = Math.max(...data.map((item) => item.value), 1);
  const total = data.reduce((sum, item) => sum + item.value, 0);
  const topBucket = data.reduce((currentTop, item) =>
    item.value > currentTop.value ? item : currentTop,
  );

  return (
    <div className="chart-shell">
      <div className="chart-meta">
        <span>总试验数 {formatNumber(total)}</span>
        <span>
          最高频阶段 {topBucket.label} ({formatNumber(topBucket.value)})
        </span>
      </div>
      <svg
        className="chart-svg"
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        role="img"
        aria-label="管线阶段分布图"
      >
        {data.map((item, index) => {
          const y = 18 + index * 38;
          const barWidth = (item.value / maxValue) * barAreaWidth;
          return (
            <g key={item.label} transform={`translate(0 ${y})`}>
              <text className="chart-label" x={0} y={15}>
                {item.label}
              </text>
              <rect
                className="chart-bar-track"
                x={labelColumnWidth}
                y={0}
                rx={10}
                ry={10}
                width={barAreaWidth}
                height={20}
              />
              <rect
                className="chart-bar-fill"
                x={labelColumnWidth}
                y={0}
                rx={10}
                ry={10}
                width={barWidth}
                height={20}
              />
              <text className="chart-value" x={labelColumnWidth + barAreaWidth + 12} y={15}>
                {formatNumber(item.value)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function PublicationTrendChart({ data }: { data: ChartDatum[] }) {
  if (!data.length) {
    return <p className="chart-empty">暂无年度文献趋势数据。</p>;
  }

  const chartWidth = 520;
  const chartHeight = 260;
  const paddingLeft = 40;
  const paddingRight = 20;
  const paddingTop = 24;
  const paddingBottom = 40;
  const plotWidth = chartWidth - paddingLeft - paddingRight;
  const plotHeight = chartHeight - paddingTop - paddingBottom;
  const maxValue = Math.max(...data.map((item) => item.value), 1);
  const horizontalGridCount = 4;
  const peakPoint = data.reduce((currentPeak, item) =>
    item.value > currentPeak.value ? item : currentPeak,
  );
  const points = data.map((item, index) => {
    const x =
      paddingLeft +
      (data.length === 1 ? plotWidth / 2 : (index / (data.length - 1)) * plotWidth);
    // Anchor the trend line to a zero-based baseline so year-over-year volume
    // changes remain visually comparable even when the series is short.
    const y = paddingTop + plotHeight - (item.value / maxValue) * plotHeight;
    return {
      ...item,
      x,
      y,
    };
  });
  const trendPath = buildPolylinePath(points);
  const areaPath = buildAreaPath(points, paddingTop + plotHeight);

  return (
    <div className="chart-shell">
      <div className="chart-meta">
        <span>
          覆盖年份 {data[0].label} - {data[data.length - 1].label}
        </span>
        <span>
          峰值 {peakPoint.label} ({formatNumber(peakPoint.value)})
        </span>
      </div>
      <svg
        className="chart-svg"
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        role="img"
        aria-label="年度文献趋势图"
      >
        {Array.from({ length: horizontalGridCount + 1 }, (_, index) => {
          const value = (maxValue / horizontalGridCount) * (horizontalGridCount - index);
          const y = paddingTop + (plotHeight / horizontalGridCount) * index;
          return (
            <g key={value}>
              <line
                className="chart-grid-line"
                x1={paddingLeft}
                y1={y}
                x2={chartWidth - paddingRight}
                y2={y}
              />
              <text className="chart-axis-value" x={0} y={y + 4}>
                {Math.round(value)}
              </text>
            </g>
          );
        })}
        <path className="chart-area-path" d={areaPath} />
        <path className="chart-line-path" d={trendPath} />
        {points.map((point) => (
          <g key={point.label}>
            <circle className="chart-point" cx={point.x} cy={point.y} r={5} />
            <text className="chart-point-value" x={point.x} y={point.y - 10} textAnchor="middle">
              {formatNumber(point.value)}
            </text>
            <text
              className="chart-axis-label"
              x={point.x}
              y={chartHeight - 12}
              textAnchor="middle"
            >
              {point.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function downloadMarkdownReport(report: ReportResponse): void {
  const blob = new Blob([report.markdown_content], { type: "text/markdown;charset=utf-8" });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = buildReportFileName(report);
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

export function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [submitError, setSubmitError] = useState<string>("");
  const [target, setTarget] = useState("HER2");
  const [indication, setIndication] = useState("breast cancer");
  const [aliases, setAliases] = useState("ERBB2");
  const [sourceConfigText, setSourceConfigText] = useState(defaultSourceConfigs);
  const [isRawRecordSamplesExpanded, setIsRawRecordSamplesExpanded] = useState(false);
  const [isTruncationNotesExpanded, setIsTruncationNotesExpanded] = useState(false);
  const [fetchResult, setFetchResult] = useState<FetchRunResponse | null>(null);
  const [rawRecords, setRawRecords] = useState<RawRecord[]>([]);
  const [analysisState, setAnalysisState] = useState<AnalysisState>("idle");
  const [analysisError, setAnalysisError] = useState("");
  const [analysisResult, setAnalysisResult] = useState<AnalysisBundleResponse | null>(
    null,
  );
  const [reportState, setReportState] = useState<ReportState>("idle");
  const [reportError, setReportError] = useState("");
  const [reportResult, setReportResult] = useState<ReportResponse | null>(null);
  const [reportAction, setReportAction] = useState<ReportAction>(null);
  const warningSummaries = analysisResult
    ? summarizeWarnings(analysisResult.warnings)
    : [];
  const rawRecordSampleGroups = fetchResult
    ? buildRawRecordSampleGroups(
        rawRecords,
        fetchResult.source_results,
        MAX_RAW_RECORD_SAMPLES_PER_SOURCE,
      )
    : [];
  const rawRecordSampleCount = rawRecordSampleGroups.reduce(
    (total, group) => total + group.items.length,
    0,
  );
  const rawRecordSampleSummary = rawRecordSampleGroups
    .map((group) => `${group.sourceName} ${group.items.length}/${group.totalCount}`)
    .join(" / ");
  const phaseChartData = analysisResult
    ? buildPhaseChartData(analysisResult.global_stats.trial_phase_distribution)
    : [];
  const publicationTrendData = analysisResult
    ? buildPublicationTrendData(analysisResult.global_stats.publication_count_by_year)
    : [];
  const truncationNoteItems = buildTruncationNoteItems(analysisResult);

  useEffect(() => {
    let isMounted = true;

    async function loadHealth() {
      setLoadState("loading");
      try {
        const response = await fetchHealth();
        if (!isMounted) {
          return;
        }
        setHealth(response);
        setLoadState("success");
      } catch (error) {
        if (!isMounted) {
          return;
        }
        const message =
          error instanceof Error ? error.message : "无法连接后端健康检查接口。";
        setErrorMessage(message);
        setLoadState("error");
      }
    }

    loadHealth();

    return () => {
      isMounted = false;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError("");
    setSubmitState("submitting");
    setFetchResult(null);
    setRawRecords([]);
    setAnalysisState("idle");
    setAnalysisError("");
    setAnalysisResult(null);
    setReportState("idle");
    setReportError("");
    setReportResult(null);
    setReportAction(null);
    setIsRawRecordSamplesExpanded(false);
    setIsTruncationNotesExpanded(false);

    try {
      const aliasList = aliases
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const parsedSourceConfigs = JSON.parse(sourceConfigText) as Record<string, unknown>;
      const sourceConfigs = mergeClinicalTrialsTargetIntoSourceConfigs(
        parsedSourceConfigs,
        target,
        aliasList,
      );
      const payload = {
        target,
        indication,
        aliases: aliasList,
        source_configs: sourceConfigs,
      };
      const created = await createFetchRun(payload);
      const sampledRecords = await loadRawRecordSamples(
        created.fetch_run_id,
        created.source_results,
      );
      setFetchResult(created);
      setRawRecords(sampledRecords);
      setSubmitState("success");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "采集请求执行失败。";
      setSubmitError(message);
      setSubmitState("error");
    }
  }

  async function handleBuildAnalysis() {
    if (!fetchResult) {
      return;
    }
    setAnalysisError("");
    setAnalysisState("loading");
    setReportState("idle");
    setReportError("");
    setReportResult(null);
    setReportAction(null);
    setIsTruncationNotesExpanded(false);

    try {
      const built = await buildAnalysisBundle(fetchResult.fetch_run_id);
      setAnalysisResult(built);
      setAnalysisState("success");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "阶段 2 分析执行失败。";
      setAnalysisError(message);
      setAnalysisState("error");
    }
  }

  async function handleLoadExistingAnalysis() {
    if (!fetchResult) {
      return;
    }
    setAnalysisError("");
    setAnalysisState("loading");
    setReportState("idle");
    setReportError("");
    setReportResult(null);
    setReportAction(null);
    setIsTruncationNotesExpanded(false);

    try {
      const loaded = await getAnalysisBundle(fetchResult.fetch_run_id);
      setAnalysisResult(loaded);
      setAnalysisState("success");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "分析快照查询失败。";
      setAnalysisError(message);
      setAnalysisState("error");
    }
  }

  async function handleBuildReport() {
    if (!fetchResult) {
      return;
    }
    setReportError("");
    setReportState("loading");
    setReportAction("build");

    try {
      const built = await buildReport(fetchResult.fetch_run_id);
      setReportResult(built);
      setReportState("success");
      setReportAction(null);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "阶段 3 报告生成失败。";
      setReportError(message);
      setReportState("error");
      setReportAction(null);
    }
  }

  async function handleDownloadReport() {
    if (!fetchResult) {
      return;
    }
    setReportError("");
    setReportState("loading");
    setReportAction("download");

    try {
      const report = reportResult ?? (await getReport(fetchResult.fetch_run_id));
      setReportResult(report);
      setReportState("success");
      setReportAction(null);
      downloadMarkdownReport(report);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Markdown 报告下载失败。";
      setReportError(message);
      setReportState("error");
      setReportAction(null);
    }
  }

  return (
    <main className="page-shell">
      <section className="hero-card">
        <div className="eyebrow">Medical Intelligence System</div>
        <h1>医疗情报系统</h1>
      </section>

      <section className="grid">
        <article className="panel">
          <h2>后端健康状态</h2>
          {loadState === "loading" && <p>正在检测后端服务状态...</p>}
          {loadState === "error" && (
            <p className="status status-error">检测失败：{errorMessage}</p>
          )}
          {loadState === "success" && health && (
            <div className="status-stack">
              <div className="status status-ok">
                服务状态：{health.status} / 数据库：{health.database.status}
              </div>
              <dl className="meta-list">
                <div>
                  <dt>服务名称</dt>
                  <dd>{health.service}</dd>
                </div>
                <div>
                  <dt>环境</dt>
                  <dd>{health.environment}</dd>
                </div>
                <div>
                  <dt>版本</dt>
                  <dd>{health.version}</dd>
                </div>
                <div>
                  <dt>数据库</dt>
                  <dd>{health.database.detail}</dd>
                </div>
              </dl>
            </div>
          )}
        </article>
      </section>

      <section className="panel playground-panel">
        <h2>阶段 1 采集面板</h2>
        <p className="panel-intro">
          这里可以直接输入靶点，并使用 JSON 配置两个来源的查询筛选条件。`page_size`
          / `retmax` / `batch_size` 表示单轮批大小，累计抓取上限由后端环境变量控制。
        </p>
        <form className="fetch-form" onSubmit={handleSubmit}>
          <label>
            <span>靶点</span>
            <input value={target} onChange={(event) => setTarget(event.target.value)} />
          </label>
          <label>
            <span>适应症</span>
            <input
              value={indication}
              onChange={(event) => setIndication(event.target.value)}
            />
          </label>
          <label>
            <span>别名（逗号分隔）</span>
            <input value={aliases} onChange={(event) => setAliases(event.target.value)} />
          </label>
          <label>
            <span>来源配置 JSON</span>
            <textarea
              rows={18}
              value={sourceConfigText}
              onChange={(event) => setSourceConfigText(event.target.value)}
            />
          </label>
          <button type="submit" disabled={submitState === "submitting"}>
            {submitState === "submitting" ? "正在采集..." : "执行多源采集"}
          </button>
        </form>

        {submitState === "error" && (
          <p className="status status-error">执行失败：{submitError}</p>
        )}

        {fetchResult && (
          <div className="result-stack">
            <div className="status status-ok">
              采集完成：{fetchResult.status}，原始记录 {fetchResult.raw_record_count} 条
            </div>

            <div className="result-grid">
              <article className="result-card">
                <h3>采集任务摘要</h3>
                <dl className="meta-list">
                  <div>
                    <dt>任务 ID</dt>
                    <dd>{fetchResult.fetch_run_id}</dd>
                  </div>
                  <div>
                    <dt>靶点</dt>
                    <dd>{fetchResult.target}</dd>
                  </div>
                  <div>
                    <dt>warning 数量</dt>
                    <dd>{fetchResult.warnings.length}</dd>
                  </div>
                </dl>
              </article>

              <article className="result-card">
                <h3>来源抓取结果</h3>
                <ul className="result-list">
                  {fetchResult.source_results.map((item) => {
                    const snapshotSummary = summarizeSourceRequestSnapshot(item);

                    return (
                      <li key={item.source_name}>
                        <strong>{item.source_name}</strong>
                        <span>
                          {item.success ? "成功" : "失败"}，抓取 {item.fetched_count} 条
                          {item.total_count !== null ? ` / 总量 ${item.total_count}` : ""}
                        </span>
                        {snapshotSummary.stopReason && (
                          <div className="source-result-meta">
                            <strong>stop_reason</strong>
                            <span>{formatStopReason(snapshotSummary.stopReason)}</span>
                          </div>
                        )}
                        {snapshotSummary.lines.length > 0 && (
                          <ul className="source-result-summary">
                            {snapshotSummary.lines.map((line) => (
                              <li key={`${item.source_name}-${line}`}>{line}</li>
                            ))}
                          </ul>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </article>
            </div>

            <article className="result-card">
              <div className="card-head">
                <div>
                  <h3>原始记录样本</h3>
                  <p className="card-caption">
                    按来源抽样展示，每个来源最多 {MAX_RAW_RECORD_SAMPLES_PER_SOURCE} 条。
                  </p>
                </div>
                {rawRecordSampleCount > 0 && (
                  <button
                    type="button"
                    className="action-button action-button-secondary action-button-compact"
                    onClick={() =>
                      setIsRawRecordSamplesExpanded((currentValue) => !currentValue)
                    }
                  >
                    {isRawRecordSamplesExpanded
                      ? "收起样本"
                      : `展开样本（${rawRecordSampleCount} 条）`}
                  </button>
                )}
              </div>
              {rawRecordSampleCount === 0 ? (
                <p className="record-summary">暂无原始记录样本。</p>
              ) : isRawRecordSamplesExpanded ? (
                <ul className="record-group-list">
                  {rawRecordSampleGroups.map((group) => (
                    <li key={group.sourceName}>
                      <div className="record-group-head">
                        <strong>{group.sourceName}</strong>
                        <span>
                          展示 {group.items.length} / {group.totalCount} 条
                        </span>
                      </div>
                      <ul className="record-list">
                        {group.items.map((record) => (
                          <li key={record.record_id}>
                            <div className="record-head">
                              <strong>{record.source_name}</strong>
                              <span>{record.source_id}</span>
                            </div>
                            {record.source_url && (
                              <a href={record.source_url} target="_blank" rel="noreferrer">
                                {record.source_url}
                              </a>
                            )}
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="record-summary">当前样本：{rawRecordSampleSummary}</p>
              )}
            </article>

            {/* Keep stages separate so each workflow surfaces its own actions and status. */}
            <article className="panel">
              <h2>阶段 2 智能分析</h2>
              <p className="panel-intro">
                在阶段 1 的原始记录基础上执行数据标准化、评分排序、智能增强、事实统计。
              </p>
              <div className="action-row">
                <button
                  type="button"
                  className="action-button"
                  onClick={handleBuildAnalysis}
                  disabled={analysisState === "loading"}
                >
                  {analysisState === "loading"
                    ? "正在构建分析快照..."
                    : analysisResult
                      ? "重新构建阶段 2 智能分析"
                      : "执行阶段 2 智能分析"}
                </button>
                <button
                  type="button"
                  className="action-button action-button-secondary"
                  onClick={handleLoadExistingAnalysis}
                  disabled={analysisState === "loading"}
                >
                  读取已保存分析快照
                </button>
              </div>

              {analysisState === "error" && (
                <p className="status status-error">执行失败：{analysisError}</p>
              )}

              {analysisResult && (
                <div className="analysis-stack">
                  <div className="status status-ok">
                    分析快照已生成：试验 {analysisResult.global_stats.total_trial_count} 条，
                    文献 {analysisResult.global_stats.total_literature_count} 条，构建时间{" "}
                    {formatDateTime(analysisResult.built_at)}
                  </div>

                  <div className="result-grid">
                    <article className="result-card analysis-card">
                      <h3>分析摘要</h3>
                      <dl className="meta-list">
                        <div>
                          <dt>Bundle ID</dt>
                          <dd>{analysisResult.bundle_id}</dd>
                        </div>
                        <div>
                          <dt>靶点</dt>
                          <dd>{analysisResult.query.target}</dd>
                        </div>
                        <div>
                          <dt>缺失章节</dt>
                          <dd>
                            {analysisResult.coverage.missing_dimensions.length
                              ? analysisResult.coverage.missing_dimensions.join(" / ")
                              : "无"}
                          </dd>
                        </div>
                      </dl>
                    </article>

                    <article className="result-card analysis-card">
                      <h3>全局统计</h3>
                      <ul className="compact-list">
                        <li>
                          <strong>阶段分布</strong>
                          <span>
                            {formatCountMap(
                              analysisResult.global_stats.trial_phase_distribution,
                            )}
                          </span>
                        </li>
                        <li>
                          <strong>主要 Sponsor</strong>
                          <span>
                            {formatNamedCounts(analysisResult.global_stats.top_sponsors)}
                          </span>
                        </li>
                        <li>
                          <strong>文献年份分布</strong>
                          <span>
                            {formatCountMap(
                              analysisResult.global_stats.publication_count_by_year,
                            )}
                          </span>
                        </li>
                        <li>
                          <strong>高频期刊</strong>
                          <span>
                            {formatNamedCounts(analysisResult.global_stats.top_journals)}
                          </span>
                        </li>
                      </ul>
                    </article>

                    <article className="result-card analysis-card">
                      <h3>Coverage 与 Warning</h3>
                      <ul className="compact-list">
                        <li>
                          <strong>Target Overview</strong>
                          <span>
                            {analysisResult.coverage.has_target_overview_evidence
                              ? "已覆盖"
                              : "缺少证据"}
                          </span>
                        </li>
                        <li>
                          <strong>Pipeline Overview</strong>
                          <span>
                            {analysisResult.coverage.has_pipeline_overview_evidence
                              ? "已覆盖"
                              : "缺少证据"}
                          </span>
                        </li>
                        <li>
                          <strong>Research Update</strong>
                          <span>
                            {analysisResult.coverage.has_research_update_evidence
                              ? "已覆盖"
                              : "缺少证据"}
                          </span>
                        </li>
                        <li>
                          <strong>Competition Assessment</strong>
                          <span>
                            {analysisResult.coverage.has_competition_assessment_evidence
                              ? "已覆盖"
                              : "缺少证据"}
                          </span>
                        </li>
                      </ul>
                      {warningSummaries.length > 0 && (
                        <ul className="tag-list">
                          {warningSummaries.map((warning) => (
                            <li key={warning.key} className="tag">
                              {warning.message}
                              {warning.count > 1 ? ` (${warning.count} 次)` : ""}
                              {warning.errorText
                                ? ` 原因：${warning.errorType ?? "UnknownError"} - ${warning.errorText}`
                                : ""}
                            </li>
                          ))}
                        </ul>
                      )}
                    </article>
                  </div>

                  <div className="result-grid">
                    <article className="result-card analysis-card chart-card">
                      <h3>管线阶段分布图</h3>
                      <p className="card-caption">基于阶段 2 全局统计中的试验 phase 分布绘制。</p>
                      <PhaseDistributionChart data={phaseChartData} />
                    </article>

                    <article className="result-card analysis-card chart-card">
                      <h3>年度文献趋势图</h3>
                      <p className="card-caption">
                        基于阶段 2 全局统计中的年度文献数绘制近年趋势。
                      </p>
                      <PublicationTrendChart data={publicationTrendData} />
                    </article>
                  </div>

                  <div className="result-grid">
                    <article className="result-card analysis-card">
                      <h3>章节 1：靶点概述输入</h3>
                      <ul className="compact-list">
                        <li>
                          <strong>试验证据</strong>
                          <span>{analysisResult.section_inputs.target_overview.trial_keys.length} 条</span>
                        </li>
                        <li>
                          <strong>文献证据</strong>
                          <span>
                            {analysisResult.section_inputs.target_overview.literature_keys.length} 条
                          </span>
                        </li>
                        <li>
                          <strong>别名</strong>
                          <span>
                            {analysisResult.section_inputs.target_overview.facts.alias_terms.join(
                              " / ",
                            ) || "暂无"}
                          </span>
                        </li>
                        <li>
                          <strong>代表性文献</strong>
                          <span>
                            {analysisResult.section_inputs.target_overview.facts.representative_paper_keys.length} 条
                          </span>
                        </li>
                      </ul>
                    </article>

                    <article className="result-card analysis-card">
                      <h3>章节 2：在研管线概览输入</h3>
                      <ul className="compact-list">
                        <li>
                          <strong>试验证据</strong>
                          <span>
                            {analysisResult.section_inputs.pipeline_overview.trial_keys.length} 条
                          </span>
                        </li>
                        <li>
                          <strong>阶段分布</strong>
                          <span>
                            {formatCountMap(
                              analysisResult.section_inputs.pipeline_overview.facts.phase_distribution,
                            )}
                          </span>
                        </li>
                        <li>
                          <strong>主要 Sponsor</strong>
                          <span>
                            {formatNamedCounts(
                              analysisResult.section_inputs.pipeline_overview.facts.top_sponsors,
                            )}
                          </span>
                        </li>
                        <li>
                          <strong>活跃试验数</strong>
                          <span>
                            {analysisResult.section_inputs.pipeline_overview.facts.active_trial_count}
                          </span>
                        </li>
                      </ul>
                    </article>

                    <article className="result-card analysis-card">
                      <h3>章节 3：近期研究动态输入</h3>
                      <ul className="compact-list">
                        <li>
                          <strong>文献证据</strong>
                          <span>
                            {analysisResult.section_inputs.research_update.literature_keys.length} 条
                          </span>
                        </li>
                        <li>
                          <strong>年份分布</strong>
                          <span>
                            {formatCountMap(
                              analysisResult.section_inputs.research_update.facts.publication_count_by_year,
                            )}
                          </span>
                        </li>
                        <li>
                          <strong>近期文献</strong>
                          <span>
                            {analysisResult.section_inputs.research_update.facts.recent_paper_keys.length} 条
                          </span>
                        </li>
                        <li>
                          <strong>高价值文献</strong>
                          <span>
                            {analysisResult.section_inputs.research_update.facts.high_value_paper_keys.length} 条
                          </span>
                        </li>
                      </ul>
                    </article>

                    <article className="result-card analysis-card">
                      <h3>章节 4：竞争格局判断输入</h3>
                      <ul className="compact-list">
                        <li>
                          <strong>试验证据</strong>
                          <span>
                            {analysisResult.section_inputs.competition_assessment.trial_keys.length} 条
                          </span>
                        </li>
                        <li>
                          <strong>文献证据</strong>
                          <span>
                            {analysisResult.section_inputs.competition_assessment.literature_keys.length} 条
                          </span>
                        </li>
                        <li>
                          <strong>活跃 Sponsor</strong>
                          <span>
                            {analysisResult.section_inputs.competition_assessment.facts.active_sponsor_count}
                          </span>
                        </li>
                        <li>
                          <strong>后期项目数</strong>
                          <span>
                            {analysisResult.section_inputs.competition_assessment.facts.late_stage_trial_count}
                          </span>
                        </li>
                      </ul>
                    </article>
                  </div>

                  {truncationNoteItems.length > 0 && (
                    <article className="result-card analysis-card">
                      <div className="card-head">
                        <div>
                          <h3>裁剪说明</h3>
                          <p className="card-caption">
                            按章节汇总阶段 2 输入构建时触发的裁剪与截断提示。
                          </p>
                        </div>
                        <button
                          type="button"
                          className="action-button action-button-secondary action-button-compact"
                          onClick={() =>
                            setIsTruncationNotesExpanded((currentValue) => !currentValue)
                          }
                        >
                          {isTruncationNotesExpanded
                            ? "收起裁剪说明"
                            : `展开裁剪说明（${truncationNoteItems.length} 条）`}
                        </button>
                      </div>
                      {isTruncationNotesExpanded ? (
                        <ul className="compact-list">
                          {truncationNoteItems.map((item) => (
                            <li key={item.key}>
                              <strong>{item.sectionLabel}</strong>
                              <span>{item.note}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="record-summary">
                          当前共有 {truncationNoteItems.length} 条裁剪说明，点击按钮后展开查看。
                        </p>
                      )}
                    </article>
                  )}
                </div>
              )}
            </article>

            <article className="panel">
              <h2>阶段 3 智能报告</h2>
              <p className="panel-intro">
                基于阶段 2 分析快照生成 Markdown 智能报告，并支持直接下载已保存结果。
              </p>
              <div className="action-row">
                <button
                  type="button"
                  className="action-button"
                  onClick={handleBuildReport}
                  disabled={reportState === "loading"}
                >
                  {reportState === "loading" && reportAction === "build"
                    ? "正在生成阶段 3 智能报告..."
                    : reportResult
                      ? "重新生成智能报告"
                      : "生成智能报告"}
                </button>
                <button
                  type="button"
                  className="action-button action-button-secondary"
                  onClick={handleDownloadReport}
                  disabled={reportState === "loading"}
                >
                  {reportState === "loading" && reportAction === "download"
                    ? "正在下载 Markdown..."
                    : "下载 Markdown 报告"}
                </button>
              </div>

              {reportState === "error" && (
                <p className="status status-error">执行失败：{reportError}</p>
              )}

              {reportResult && (
                <article className="result-card analysis-card report-card">
                  <h3>阶段 3 报告</h3>
                  <dl className="meta-list">
                    <div>
                      <dt>Report ID</dt>
                      <dd>{reportResult.report_id}</dd>
                    </div>
                    <div>
                      <dt>关联 Bundle</dt>
                      <dd>{reportResult.analysis_bundle_id}</dd>
                    </div>
                    <div>
                      <dt>生成时间</dt>
                      <dd>{formatDateTime(reportResult.generated_at)}</dd>
                    </div>
                    <div>
                      <dt>章节数 / Warning</dt>
                      <dd>
                        {reportResult.sections.length} / {reportResult.warning_summary.length}
                      </dd>
                    </div>
                  </dl>
                </article>
              )}
            </article>
          </div>
        )}
      </section>
    </main>
  );
}
