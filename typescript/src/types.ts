/**
 * Request/response types for all 9 tools.
 *
 * HAND-DERIVED FROM BACKEND SOURCE, NOT SPEC-GENERATED. There is no OpenAPI
 * spec to codegen from — https://hpsilab.com/api/openapi.json 404s and the
 * only written reference is a hand-maintained markdown file in the Python SDK
 * repo (docs/api.md). These interfaces were built by reading the actual FastAPI
 * route handlers as of 2026-07-19:
 *   - analyze_stock              -> backend/app/routers/growth_engine.py (proxies mcp_server.py's analyze_stock tool)
 *   - get_ai_prediction          -> backend/app/routers/predict.py + app/schemas/predict.py (PredictResponse)
 *   - get_iv_radar               -> backend/app/routers/iv.py (/iv_batch)
 *   - get_option_pressure        -> backend/app/routers/black_scholes.py (/option_pressure/{symbol})
 *   - get_monte_carlo            -> backend/app/routers/montecarlo.py
 *   - get_equity_curves          -> backend/app/routers/qml.py (/equity_curve/{ticker})
 *   - get_pretrade_risk_scan     -> backend/app/routers/pretrade_risk_router.py
 *   - generate_stock_images      -> backend/app/routers/stock_report.py (/stock_report/{symbol}/images)
 *   - generate_stock_research_report -> backend/app/routers/growth_engine.py (proxies mcp_server.py's generate_stock_research_report tool)
 *
 * If the backend response shape changes, these types will silently drift —
 * there is no build-time check against the live API. Re-sync by hand.
 *
 * PretradeRiskScanResult's riskDeltas/sizingChecks/exposure/correlation were
 * traced into app/modules/portfolio_risk_engine.py (run_pretrade_risk_scan and
 * its _risk_deltas/_sizing_checks/_exposure/_correlation helpers) and are
 * fully typed below, not guessed.
 */

// ---------------------------------------------------------------------------
// analyze_stock
// ---------------------------------------------------------------------------

export type ToolResponseStatus = "ok" | "error" | "unavailable";

export interface ToolResponseEnvelope {
  status: ToolResponseStatus;
  response: string | null;
  error?: string;
}

export interface AnalyzeStockToolResponses {
  get_ai_prediction?: ToolResponseEnvelope;
  get_iv_radar?: ToolResponseEnvelope;
  get_option_pressure?: ToolResponseEnvelope;
  get_equity_curves?: ToolResponseEnvelope;
  get_monte_carlo?: ToolResponseEnvelope;
}

export interface AnalyzeStockResult {
  symbol: string;
  signal: "Bullish" | "Bearish" | "Neutral";
  confidence_score: number;
  bullish_factors: string[];
  bearish_factors: string[];
  summary: string;
  disclaimer: string;
  tool_responses: AnalyzeStockToolResponses;
}

// ---------------------------------------------------------------------------
// get_ai_prediction
// ---------------------------------------------------------------------------

export interface AiPredictionRow {
  last_date: string;
  model_variant?: string | null;
  last_close: number;
  ensemble_up_probability: number;
  rf_up_probability: number;
  lr_up_probability: number;
  daily_vol_est?: number | null;
  suggested_stop_loss_price?: number | null;
  suggested_take_profit_price?: number | null;
  sentiment_score?: number | null;
}

/** `GET /api/ai_prediction/{symbol}` returns a JSON array (usually one row). */
export type AiPredictionResult = AiPredictionRow[];

// ---------------------------------------------------------------------------
// get_iv_radar
// ---------------------------------------------------------------------------

export type IvRegime = "SQUEEZE_PHASE" | "BULLISH_SKEW" | "BEARISH_SKEW" | "COMPRESSION" | "NEUTRAL";
export type IvRowStatus = "ok" | "stale" | "no_25d" | "no_expiry" | "no_atm_iv" | "error";

export interface IvRadarRow {
  symbol: string;
  status: IvRowStatus;
  spot?: number;
  expiry?: string;
  iv_context_version?: number;
  atm_iv?: number;
  iv30?: number;
  iv30_expiry?: string;
  hv30?: number | null;
  iv_hv_spread?: number | null;
  iv_hv_spread_points?: number | null;
  call_25d_iv?: number;
  put_25d_iv?: number;
  near_month_iv?: number;
  near_month_expiry?: string;
  far_month_iv?: number | null;
  far_month_expiry?: string | null;
  term_structure?: "contango" | "backwardation" | "flat" | null;
  vol_interpretation?: string;
  risk_reversal_25d?: number;
  squeeze_score?: number;
  iv_rank?: number | null;
  iv_percentile?: number | null;
  regime?: IvRegime;
  call_volume?: number;
  put_volume?: number;
  put_call_volume_ratio?: number | null;
  total_open_interest?: number | null;
  /** Only present when status is "stale" (served from the persistent cache). */
  stale?: boolean;
  stale_reason?: string;
  /** Only present when status is "error"/"no_expiry"/"no_atm_iv". */
  error?: string;
  from_cache?: boolean;
  cache_updated_at?: string | null;
}

export interface IvRadarResult {
  status: "success";
  count: number;
  results: IvRadarRow[];
}

// ---------------------------------------------------------------------------
// get_option_pressure
// ---------------------------------------------------------------------------

export interface OptionPressureResult {
  status: "success";
  symbol: string;
  spot?: number;
  expiry?: string;
  days_to_expiry?: number;
  max_pain?: number;
  gamma_wall?: number;
  gamma_wall_net?: number;
  expected_high?: number;
  squeeze_price?: number;
  expiry_low?: number;
  expiry_high?: number;
  weekly_expected_move?: number;
  avg_iv?: number;
  avg_call_iv?: number;
  avg_put_iv?: number;
  total_oi?: number;
  total_volume?: number;
  calls_count?: number;
  puts_count?: number;
}

// ---------------------------------------------------------------------------
// get_monte_carlo
// ---------------------------------------------------------------------------

export interface MonteCarloResult {
  ticker: string;
  support: number;
  /** Duplicate of `resistance` (backend emits both keys). */
  threshold: number;
  resistance: number;
  prob_below: number;
  prob_above: number;
  mean_price: number;
  median_price: number;
  lower_bound: number;
  upper_bound: number;
  volatility: number;
  std_tomorrow: number;
  /** Confidence interval used for lower_bound/upper_bound, e.g. 0.9 for 90%. */
  ci: number;
  /** Raw simulated final prices — can be large (thousands of paths). */
  final_prices: number[];
  msg?: string;
}

// ---------------------------------------------------------------------------
// get_equity_curves
// ---------------------------------------------------------------------------

export interface EquityCurveSummaryRow {
  ticker: string;
  totalReturn?: number;
  sharpe?: number;
  maxDrawdown?: number;
  winRate?: number;
  plRatio?: number;
  [key: string]: unknown;
}

export interface EquityCurvePoint {
  ticker: string;
  dates: string;
  equity: number;
}

export interface EquitySignal {
  ticker: string;
  strategy?: string;
  direction?: string;
  strength?: number;
  [key: string]: unknown;
}

export interface EquityCurvesResult {
  status: "success";
  ticker: string;
  summary: EquityCurveSummaryRow[];
  equity: EquityCurvePoint[];
  signals: EquitySignal[];
  from_cache: boolean;
  updated_at?: string | null;
}

// ---------------------------------------------------------------------------
// get_pretrade_risk_scan
// ---------------------------------------------------------------------------

export interface PretradeRiskDistribution {
  /** Histogram bin edges (n+1 values). */
  bins: number[];
  /** Counts per bin (n values). */
  frequencies: number[];
  /** KDE curve x/y points (200 values each per mcp_server/CLAUDE.md). */
  kde_x: number[];
  kde_y: number[];
}

export interface PretradeRiskRange90 {
  lower: number;
  upper: number;
}

/** One "before" (SPY benchmark) vs "after" (this symbol) risk comparison row.
 * Source: portfolio_risk_engine._risk_deltas. */
export interface RiskDeltaRow {
  label: "Annualized Volatility" | "Beta (vs SPY)" | "1-Day VaR (95%)" | "Max Drawdown (1Y)";
  beforeValue: number;
  afterValue: number;
  unit: "%" | "";
  higherIsRiskier: boolean;
}

/** Source: portfolio_risk_engine._sizing_checks. */
export interface SizingCheck {
  label: "Volatility" | "Drawdown Risk" | "Market Exposure" | "Liquidity";
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface ExposureBySymbolRow {
  symbol: string;
  currentPct: number;
  postTradePct: number;
  deltaPct: number;
}

export interface ExposureBySectorRow {
  sector: string;
  currentPct: number;
  postTradePct: number;
  deltaPct: number;
}

/** No watchlist to compare against (e.g. anonymous caller, or signed-in with
 * an empty watchlist) — degrades gracefully rather than fabricating a number. */
export interface ExposureUnavailable {
  available: false;
  reason: string;
  bySector: [];
  bySymbol: [];
  concentrationFlag: "unknown";
  assumedPositionWeight: null;
  weightingMethod: "equal_weight_proxy";
}

export interface ExposureAvailable {
  available: true;
  bySector: ExposureBySectorRow[];
  bySymbol: ExposureBySymbolRow[];
  concentrationFlag: "pass" | "warn" | "fail";
  assumedPositionWeight: number;
  weightingMethod: "equal_weight_proxy";
}

/** Source: portfolio_risk_engine._exposure. Equal-weight watchlist proxy —
 * there is no real portfolio table, so this is not actual dollar exposure. */
export type PretradeExposure = ExposureAvailable | ExposureUnavailable;

export interface CorrelationPeer {
  symbol: string;
  correlation: number;
}

export interface CorrelationAggregate {
  avgCorrelationWithPortfolio: number;
  level: "high" | "moderate" | "low";
  mostCorrelated: CorrelationPeer;
  leastCorrelated: CorrelationPeer;
}

export interface CorrelationMatrix {
  symbols: string[];
  /** Square matrix aligned to `symbols`, same order on both axes. */
  values: number[][];
}

/** No watchlist, or not enough overlapping price history (< 30 trading days)
 * to compute a correlation. */
export interface CorrelationUnavailable {
  available: false;
  reason: string;
  aggregate: null;
  matrix: null;
}

export interface CorrelationAvailable {
  available: true;
  aggregate: CorrelationAggregate;
  matrix: CorrelationMatrix;
}

/** Source: portfolio_risk_engine._correlation. */
export type PretradeCorrelation = CorrelationAvailable | CorrelationUnavailable;

export interface PretradeRiskScanResult {
  symbol: string;
  asOf: string;
  riskDeltas: RiskDeltaRow[];
  regime: "bull" | "bear" | "chop";
  regimeConfidence: number;
  distribution: PretradeRiskDistribution;
  range_90: PretradeRiskRange90;
  mean: number;
  threshold: number;
  sizingChecks: SizingCheck[];
  exposure: PretradeExposure;
  correlation: PretradeCorrelation;
}

// ---------------------------------------------------------------------------
// generate_stock_images / generate_stock_research_report (shared image type)
// ---------------------------------------------------------------------------

export type StockReportImageType =
  | "ai_prediction"
  | "iv_radar"
  | "option_pressure"
  | "monte_carlo"
  | "equity_curves";

export type StockReportImageStatus = "available" | "unavailable" | "not_generated" | "pending";

export interface StockReportImageRecord {
  type: StockReportImageType;
  url: string;
  status: StockReportImageStatus;
  error?: string;
  /** Only present on generate_stock_research_report, which inlines charts as
   * base64 so the report is self-contained. generate_stock_images never sets these. */
  base64?: string;
  data_uri?: string;
}

export interface GenerateStockImagesResult {
  symbol: string;
  images: StockReportImageRecord[];
  disclaimer: string;
}

export interface ResearchReportConsensus {
  ai: string;
  monte_carlo: string;
  options: string;
  iv_structure: string;
}

export interface GenerateStockResearchReportResult {
  symbol: string;
  status: "ok" | "partial" | "error";
  direction: string;
  direction_score: number;
  direction_score_logic: string;
  iv_opportunity_score: number;
  iv_opportunity_score_logic: string;
  consensus: ResearchReportConsensus;
  summary: string;
  bullish_factors: string[];
  bearish_factors: string[];
  report_markdown: string;
  images: StockReportImageRecord[];
  image_status: string;
  disclaimer: string;
}
