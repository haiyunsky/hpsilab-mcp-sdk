/** Free tool. Run: `HPSILAB_API_KEY=hpsi_... npx tsx examples/iv-radar.ts` */
import { HPSILabClient } from "@hpsilab/sdk";

const client = new HPSILabClient({ apiKey: process.env.HPSILAB_API_KEY });

const iv = await client.getIvRadar("SPY");
for (const row of iv.results) {
  console.log(`${row.symbol}: regime=${row.regime} squeeze_score=${row.squeeze_score} atm_iv=${row.atm_iv}`);
}
