/**
 * Pro tool (signed-in plans free within monthly quota). REQUIRES an API key —
 * unlike getPretradeRiskScan, this endpoint has no anonymous REST fallback
 * (see README "Authentication"). Run:
 * `HPSILAB_API_KEY=hpsi_... npx tsx examples/research-report.ts`
 */
import { HPSILabClient } from "@hpsilab/sdk";

const client = new HPSILabClient({ apiKey: process.env.HPSILAB_API_KEY });

const report = await client.generateStockResearchReport("RXRX", { forceImages: true });
console.log(`Direction: ${report.direction} (score ${report.direction_score}/100)`);
console.log(report.report_markdown);
