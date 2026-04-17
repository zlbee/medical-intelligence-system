export interface ComponentStatus {
  status: "ok" | "degraded";
  detail: string;
}

export interface HealthResponse {
  service: string;
  environment: string;
  version: string;
  status: "ok" | "degraded";
  timestamp: string;
  database: ComponentStatus;
}

