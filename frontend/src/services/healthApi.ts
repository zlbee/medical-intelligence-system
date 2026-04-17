import type { HealthResponse } from "../types/health";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) {
    throw new Error(`健康检查请求失败，状态码：${response.status}`);
  }
  return response.json() as Promise<HealthResponse>;
}

