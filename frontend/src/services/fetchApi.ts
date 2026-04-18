import type {
  AnalysisBundleResponse,
  FetchCreateRequest,
  FetchRunResponse,
  RawRecordListResponse,
  ReportResponse,
} from "../types/fetch";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function createFetchRun(
  payload: FetchCreateRequest,
): Promise<FetchRunResponse> {
  const response = await fetch(`${API_BASE_URL}/api/fetches`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`采集请求失败：${response.status} ${errorText}`);
  }

  return response.json() as Promise<FetchRunResponse>;
}

export async function listRawRecords(
  fetchRunId: string,
): Promise<RawRecordListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/fetches/${fetchRunId}/records`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`原始记录查询失败：${response.status} ${errorText}`);
  }
  return response.json() as Promise<RawRecordListResponse>;
}

export async function buildAnalysisBundle(
  fetchRunId: string,
): Promise<AnalysisBundleResponse> {
  const response = await fetch(`${API_BASE_URL}/api/fetches/${fetchRunId}/analysis`, {
    method: "POST",
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`阶段 2 分析构建失败：${response.status} ${errorText}`);
  }
  return response.json() as Promise<AnalysisBundleResponse>;
}

export async function getAnalysisBundle(
  fetchRunId: string,
): Promise<AnalysisBundleResponse> {
  const response = await fetch(`${API_BASE_URL}/api/fetches/${fetchRunId}/analysis`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`分析快照查询失败：${response.status} ${errorText}`);
  }
  return response.json() as Promise<AnalysisBundleResponse>;
}

export async function buildReport(
  fetchRunId: string,
): Promise<ReportResponse> {
  const response = await fetch(`${API_BASE_URL}/api/fetches/${fetchRunId}/report`, {
    method: "POST",
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`阶段 3 报告生成失败：${response.status} ${errorText}`);
  }
  return response.json() as Promise<ReportResponse>;
}

export async function getReport(
  fetchRunId: string,
): Promise<ReportResponse> {
  const response = await fetch(`${API_BASE_URL}/api/fetches/${fetchRunId}/report`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`报告查询失败：${response.status} ${errorText}`);
  }
  return response.json() as Promise<ReportResponse>;
}

