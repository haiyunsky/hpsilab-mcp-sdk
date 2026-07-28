/** Free tool. Run: `HPSILAB_API_KEY=hpsi_... npx tsx examples/monte-carlo.ts` */
import { HPSILabClient } from "@hpsilab/sdk";

const client = new HPSILabClient({ apiKey: process.env.HPSILAB_API_KEY });

const mc = await client.getMonteCarlo("AAPL");
console.log(`Mean projected close: $${mc.mean_price} (median $${mc.median_price})`);
console.log(`${(mc.ci * 100).toFixed(0)}% range: $${mc.lower_bound} to $${mc.upper_bound}`);
console.log(`Simulated paths: ${mc.final_prices.length}`);
