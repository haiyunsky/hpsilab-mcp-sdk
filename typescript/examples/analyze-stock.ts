/** Free tool, recommended starting point. Run: `HPSILAB_API_KEY=hpsi_... npx tsx examples/analyze-stock.ts` */
import { HPSILabClient } from "@hpsilab/sdk";

const client = new HPSILabClient({ apiKey: process.env.HPSILAB_API_KEY });

const result = await client.analyzeStock("NVDA");
console.log(`${result.symbol}: ${result.signal} (${result.confidence_score}/100)`);
console.log(result.summary);
