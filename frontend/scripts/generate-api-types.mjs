// Generates TypeScript types for every public API the SPA calls from the
// committed OpenAPI contracts (contracts/openapi, spec Section 22), so a
// backend contract change shows up as a type error here instead of a
// runtime surprise. CI regenerates and fails on any diff.
import { writeFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const contracts = join(root, "..", "contracts", "openapi");
const out = join(root, "src", "api", "schema");
const services = [
  "identity-service",
  "ledger-service",
  "payment-service",
  "webhook-service",
  "assistant-service",
];

await mkdir(out, { recursive: true });
for (const service of services) {
  const source = new URL(`file://${join(contracts, `${service}.json`)}`);
  const ast = await openapiTS(source);
  const banner = `// Generated from contracts/openapi/${service}.json by scripts/generate-api-types.mjs.\n// Do not edit by hand: run \`npm run gen:api\`.\n\n`;
  await writeFile(join(out, `${service}.ts`), banner + astToString(ast));
  console.log(`wrote src/api/schema/${service}.ts`);
}
