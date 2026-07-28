/** Free tool. Run: `HPSILAB_API_KEY=hpsi_... npx tsx examples/stock-images.ts` */
import { HPSILabClient } from "@hpsilab/sdk";

const client = new HPSILabClient({ apiKey: process.env.HPSILAB_API_KEY });

const result = await client.generateStockImages("RXRX", {
  force: true,
  types: ["ai_prediction", "iv_radar"],
});
for (const image of result.images) {
  console.log(`${image.type}: ${image.status} — ${image.url}`);
}
