/** Free tool. Run: `HPSILAB_API_KEY=hpsi_... npx tsx examples/ai-prediction.ts` */
import { HPSILabClient } from "@hpsilab/sdk";

const client = new HPSILabClient({ apiKey: process.env.HPSILAB_API_KEY });

const [row] = await client.getAiPrediction("TSLA");
if (row) {
  console.log(`Up probability: ${(row.ensemble_up_probability * 100).toFixed(1)}%`);
  console.log(`Last close ${row.last_close} as of ${row.last_date}`);
}
