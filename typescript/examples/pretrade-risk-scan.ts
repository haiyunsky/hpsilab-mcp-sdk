/**
 * Pro tool (signed-in plans free within quota). Run:
 * `HPSILAB_API_KEY=hpsi_... npx tsx examples/pretrade-risk-scan.ts`
 *
 * This one call currently also works with no API key at all (the REST route
 * accepts the SDK's default anonymous-readonly header) — but that anonymous
 * path is documented backend-side as temporary, so don't build on it. See
 * README "Authentication" and the getPretradeRiskScan JSDoc in src/client.ts.
 */
import { HPSILabClient } from "@hpsilab/sdk";

const client = new HPSILabClient({ apiKey: process.env.HPSILAB_API_KEY });

const scan = await client.getPretradeRiskScan("NVDA");
console.log(`Regime: ${scan.regime} (confidence ${scan.regimeConfidence})`);
for (const check of scan.sizingChecks) {
  console.log(`- ${check.label}: ${check.status} — ${check.detail}`);
}
if (scan.exposure.available) {
  console.log(`Post-trade concentration flag: ${scan.exposure.concentrationFlag}`);
} else {
  console.log(`Exposure unavailable: ${scan.exposure.reason}`);
}
