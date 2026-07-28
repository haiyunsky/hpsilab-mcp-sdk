/** Free tool. Run: `HPSILAB_API_KEY=hpsi_... npx tsx examples/option-pressure.ts` */
import { HPSILabClient } from "@hpsilab/sdk";

const client = new HPSILabClient({ apiKey: process.env.HPSILAB_API_KEY });

const pressure = await client.getOptionPressure("SPY");
console.log(`Max Pain: $${pressure.max_pain}`);
console.log(`Gamma Wall: $${pressure.gamma_wall}`);
console.log(`Likely weekly high: $${pressure.expected_high}`);
