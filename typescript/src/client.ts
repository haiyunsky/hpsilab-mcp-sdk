/**
 * HPSILabClient — flat method surface mirroring the real Python SDK
 * (HpsiMcpClient, github.com/haiyunsky/hpsilab-mcp-sdk) 1:1 by tool name,
 * camelCased. No client.stock / client.options / client.research /
 * client.monitor submodules — confirmed against Step 0 research that the
 * live product has exactly 9 flat tools and no others.
 *
 * Python keeps optional params positional with defaults (`refresh: bool =
 * False`); this SDK groups them into a trailing options object per method,
 * which is the idiomatic TS shape for the same call. Method names and
 * required positional `symbol` args otherwise match Python exactly.
 */

import { resolveConfig, type HPSILabClientConfig, type ResolvedConfig } from "./config";
import { request } from "./http";
import { AuthenticationError, ValidationError } from "./errors";
import type {
  AiPredictionResult,
  AnalyzeStockResult,
  EquityCurvesResult,
  GenerateStockImagesResult,
  GenerateStockResearchReportResult,
  IvRadarResult,
  MonteCarloResult,
  OptionPressureResult,
  PretradeRiskScanResult,
  StockReportImageType,
} from "./types";

export interface AnalyzeStockOptions {
  /** Bypass the backend's fresh-IV cache. Defaults to false. */
  refresh?: boolean;
}

export interface GenerateStockImagesOptions {
  /** Regenerate instead of using cached PNGs. Defaults to false. */
  force?: boolean;
  /** Subset of chart types to generate. Omit for all 5. */
  types?: StockReportImageType[];
}

export interface GenerateStockResearchReportOptions {
  /** Bypass the backend's fresh-IV cache for the IV-driven modules. Defaults to false. */
  refresh?: boolean;
  /** Force a fresh chart render instead of reusing the image cache. Defaults to false. */
  forceImages?: boolean;
}

export class HPSILabClient {
  private readonly config: ResolvedConfig;

  constructor(options: HPSILabClientConfig = {}) {
    this.config = resolveConfig(options);
  }

  private cleanSymbol(symbol: string): string {
    if (typeof symbol !== "string") {
      throw new ValidationError("Symbol must be a string.");
    }
    const cleaned = symbol.trim();
    if (!cleaned) {
      throw new ValidationError("Symbol is required.");
    }
    return cleaned;
  }

  /** Thin per-instance wrapper around `request()`. Rate-limit metadata is
   * attached to the returned value itself (see http.ts's `getRateLimit()`),
   * not stored here — keeping this method call-scoped, not instance-scoped,
   * is what makes it safe for a single client instance to serve concurrent
   * calls (e.g. multiple users in one Node server process). */
  private run<T>(method: "GET" | "POST", path: string, params?: Record<string, string | undefined>): Promise<T> {
    return request<T>(this.config, method, path, params);
  }

  /** Free. Recommended starting point — aggregates the other 5 read tools into
   * one direction signal. `GET /api/analyze_stock/{symbol}`. */
  async analyzeStock(symbol: string, options: AnalyzeStockOptions = {}): Promise<AnalyzeStockResult> {
    const clean = this.cleanSymbol(symbol);
    return this.run<AnalyzeStockResult>("GET", `/api/analyze_stock/${encodeURIComponent(clean)}`, {
      refresh: options.refresh ? "true" : undefined,
    });
  }

  /** Free. Next-day up probability and model consensus.
   * `GET /api/ai_prediction/{symbol}`. */
  async getAiPrediction(symbol: string): Promise<AiPredictionResult> {
    const clean = this.cleanSymbol(symbol);
    return this.run<AiPredictionResult>("GET", `/api/ai_prediction/${encodeURIComponent(clean)}`);
  }

  /** Free. Implied-volatility structure, squeeze score, risk reversal.
   * `GET /api/iv_batch?symbols={symbol}`. */
  async getIvRadar(symbol: string): Promise<IvRadarResult> {
    const clean = this.cleanSymbol(symbol);
    return this.run<IvRadarResult>("GET", "/api/iv_batch", { symbols: clean });
  }

  /** Free. Max Pain, Gamma Wall, likely weekly high.
   * `GET /api/option_pressure/{symbol}`. */
  async getOptionPressure(symbol: string): Promise<OptionPressureResult> {
    const clean = this.cleanSymbol(symbol);
    return this.run<OptionPressureResult>("GET", `/api/option_pressure/${encodeURIComponent(clean)}`);
  }

  /** Free. 10-day Monte Carlo price simulation.
   * `GET /api/monte_carlo/{symbol}`. */
  async getMonteCarlo(symbol: string): Promise<MonteCarloResult> {
    const clean = this.cleanSymbol(symbol);
    return this.run<MonteCarloResult>("GET", `/api/monte_carlo/${encodeURIComponent(clean)}`);
  }

  /** Free. Backtest performance for one symbol (Sharpe, drawdown, win rate).
   * `GET /api/equity_curve/{symbol}`. Note: the Python SDK also exposes a
   * `get_equity_curve` (singular) alias for this same endpoint; this SDK
   * ships only `getEquityCurves`, matching the 9 real tools. */
  async getEquityCurves(symbol: string): Promise<EquityCurvesResult> {
    const clean = this.cleanSymbol(symbol);
    return this.run<EquityCurvesResult>("GET", `/api/equity_curve/${encodeURIComponent(clean)}`);
  }

  /** Pro (signed-in plans free within quota; anonymous MCP callers pay $0.15 via
   * x402 at the MCP layer). Full pre-trade risk scan.
   * `GET /api/pretrade-risk-scan?symbol={symbol}`.
   *
   * Unlike generateStockResearchReport, this endpoint's route
   * (pretrade_risk_router.py) resolves the caller via
   * `get_current_user_or_mcp_anonymous`, which accepts the
   * `x-mcp-anonymous-readonly: 1` header this SDK already sends by default
   * when no apiKey is configured — so an anonymous call to this method
   * succeeds today (with degraded exposure/correlation fields, since there is
   * no watchlist to compare against). No client-side pre-check is added here.
   * That anonymous path is explicitly documented backend-side as temporary
   * ("Set to false once OAuth is in place" — see mcp_server/README.md's
   * MCP_ALLOW_ANONYMOUS_READONLY). If the backend flips that flag, anonymous
   * calls to this method will start throwing AuthenticationError (401) same
   * as any other missing-auth failure — there is no guarantee this stays
   * anonymous-callable long-term. */
  async getPretradeRiskScan(symbol: string): Promise<PretradeRiskScanResult> {
    const clean = this.cleanSymbol(symbol);
    return this.run<PretradeRiskScanResult>("GET", "/api/pretrade-risk-scan", { symbol: clean });
  }

  /** Free. Generates stock-report PNGs and returns their URLs.
   * `POST /api/stock_report/{symbol}/images`. */
  async generateStockImages(
    symbol: string,
    options: GenerateStockImagesOptions = {},
  ): Promise<GenerateStockImagesResult> {
    const clean = this.cleanSymbol(symbol);
    return this.run<GenerateStockImagesResult>("POST", `/api/stock_report/${encodeURIComponent(clean)}/images`, {
      force: options.force ? "true" : undefined,
      types: options.types?.length ? options.types.join(",") : undefined,
    });
  }

  /** Pro (signed-in plans free within monthly quota; anonymous MCP callers pay
   * $0.35 via x402 at the MCP layer). Full markdown research report with five
   * embedded charts. `POST /api/stock_report/{symbol}/research_report`.
   *
   * REST-only anonymous access is NOT available for this endpoint: its route
   * (growth_engine.py's generate_stock_research_report_rest) calls
   * `_request_token(request)`, which raises a plain 401 whenever no cookie or
   * Authorization header is present at all — it does not check the
   * `x-mcp-anonymous-readonly` header the way getPretradeRiskScan's route
   * does. Anonymous pay-per-call only exists at the MCP transport layer via
   * x402, which this REST SDK does not implement. To fail fast with a clear
   * diagnosis instead of an opaque 401 from the network, this method
   * pre-checks for an apiKey before making the request. */
  async generateStockResearchReport(
    symbol: string,
    options: GenerateStockResearchReportOptions = {},
  ): Promise<GenerateStockResearchReportResult> {
    const clean = this.cleanSymbol(symbol);
    if (!this.config.apiKey) {
      throw new AuthenticationError(
        "generateStockResearchReport requires an API key — anonymous access is not available " +
          "for this endpoint via REST. (analyzeStock supports anonymous access via x402 payment " +
          "at the MCP layer, but this REST SDK does not implement x402.)",
        401,
      );
    }
    return this.run<GenerateStockResearchReportResult>(
      "POST",
      `/api/stock_report/${encodeURIComponent(clean)}/research_report`,
      {
        refresh: options.refresh ? "true" : undefined,
        force_images: options.forceImages ? "true" : undefined,
      },
    );
  }
}
