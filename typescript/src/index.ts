export { HPSILabClient } from "./client";
export type {
  AnalyzeStockOptions,
  GenerateStockImagesOptions,
  GenerateStockResearchReportOptions,
} from "./client";

export type { FetchLike, HPSILabClientConfig, ResolvedConfig } from "./config";
export { ANONYMOUS_READONLY_HEADER, DEFAULT_BASE_URL, DEFAULT_RETRIES, DEFAULT_TIMEOUT_MS } from "./config";

export { getRateLimit } from "./http";
export type { RateLimitInfo } from "./http";

export {
  APIError,
  AuthenticationError,
  HPSILabError,
  NetworkError,
  PaymentError,
  RateLimitError,
  ResponseError,
  TimeoutError,
  ValidationError,
} from "./errors";
export type { HPSILabErrorOptions } from "./errors";

export type {
  AiPredictionResult,
  AiPredictionRow,
  AnalyzeStockResult,
  AnalyzeStockToolResponses,
  CorrelationAggregate,
  CorrelationAvailable,
  CorrelationMatrix,
  CorrelationPeer,
  CorrelationUnavailable,
  EquityCurvePoint,
  EquityCurveSummaryRow,
  EquityCurvesResult,
  EquitySignal,
  ExposureAvailable,
  ExposureBySectorRow,
  ExposureBySymbolRow,
  ExposureUnavailable,
  GenerateStockImagesResult,
  GenerateStockResearchReportResult,
  IvRadarResult,
  IvRadarRow,
  IvRegime,
  IvRowStatus,
  MonteCarloResult,
  OptionPressureResult,
  PretradeCorrelation,
  PretradeExposure,
  PretradeRiskDistribution,
  PretradeRiskRange90,
  PretradeRiskScanResult,
  ResearchReportConsensus,
  RiskDeltaRow,
  SizingCheck,
  StockReportImageRecord,
  StockReportImageStatus,
  StockReportImageType,
  ToolResponseEnvelope,
  ToolResponseStatus,
} from "./types";
