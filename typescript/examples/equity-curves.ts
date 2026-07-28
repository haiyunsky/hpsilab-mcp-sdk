/** Free tool. Run: `HPSILAB_API_KEY=hpsi_... npx tsx examples/equity-curves.ts` */
import { HPSILabClient } from "@hpsilab/sdk";

const client = new HPSILabClient({ apiKey: process.env.HPSILAB_API_KEY });

const curves = await client.getEquityCurves("IONQ");
for (const row of curves.summary) {
  console.log(`${row.ticker}: Sharpe ${row.sharpe}, max drawdown ${row.maxDrawdown}, win rate ${row.winRate}`);
}
