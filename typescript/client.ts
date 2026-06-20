export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export type JsonObject = { [key: string]: JsonValue };

export interface HpsiMcpClientOptions {
  serverUrl?: string;
  timeoutMs?: number;
  headers?: Record<string, string>;
}

export interface ToolCallRequest<TArguments extends JsonObject = JsonObject> {
  tool: string;
  arguments: TArguments;
}

export class HpsiMcpError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "HpsiMcpError";
  }
}

export class HpsiMcpClient {
  private readonly serverUrl?: string;
  private readonly timeoutMs: number;
  private readonly headers: Record<string, string>;

  constructor(options: HpsiMcpClientOptions = {}) {
    this.serverUrl = options.serverUrl;
    this.timeoutMs = options.timeoutMs ?? 30_000;
    this.headers = options.headers ?? {};
  }

  async callTool<TArguments extends JsonObject = JsonObject, TResult = unknown>(
    name: string,
    args: TArguments = {} as TArguments,
  ): Promise<TResult> {
    if (!name) {
      throw new HpsiMcpError("Tool name is required.");
    }

    const request: ToolCallRequest<TArguments> = {
      tool: name,
      arguments: args,
    };

    return this.request<TResult>(request);
  }

  async getAiPrediction<TResult = unknown>(symbol: string): Promise<TResult> {
    return this.callTool("get_ai_prediction", { symbol });
  }

  async getIvRadar<TResult = unknown>(symbol: string): Promise<TResult> {
    return this.callTool("get_iv_radar", { symbol });
  }

  async getOptionPressure<TResult = unknown>(
    symbol: string,
  ): Promise<TResult> {
    return this.callTool("get_option_pressure", { symbol });
  }

  async getEquityCurves<TResult = unknown>(symbol: string): Promise<TResult> {
    return this.callTool("get_equity_curves", { symbol });
  }

  async getMonteCarlo<TResult = unknown>(symbol: string): Promise<TResult> {
    return this.callTool("get_monte_carlo", { symbol });
  }

  protected async request<TResult>(
    _payload: ToolCallRequest,
  ): Promise<TResult> {
    void this.serverUrl;
    void this.timeoutMs;
    void this.headers;

    throw new HpsiMcpError(
      "Connect this skeleton to an MCP transport before calling tools.",
    );
  }
}
