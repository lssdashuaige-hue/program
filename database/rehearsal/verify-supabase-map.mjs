import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rehearsalDir = dirname(fileURLToPath(import.meta.url));
const siteRoot = resolve(rehearsalDir, "../..");
const sourceDir = join(siteRoot, "database", "migrations");
const deploymentDir = join(siteRoot, "supabase", "migrations");

const mapping = [
  ["20260727034958_confirmed_memory_writes.sql", "0002_confirmed_memory_writes.sql", "91941bb25d7d805a1ba4eb8bc7c58ed1d9e14e8773c3c9d4f82378caf6130251"],
  ["20260814091709_conversation_history.sql", "0003_conversation_history.sql", "5d9b6c62065a0b1aeb551ef7d4054aa613879ac3ca55b704665b669e69ad4859"],
  ["20260814091937_conversation_owner_fk_index.sql", "0004_conversation_owner_fk_index.sql", "a302fcf6c3a6330150348d5656ec110a2ed99d282b9a0151a9acdd9cbd5abbdb"],
  ["20260814093334_backend_only_conversation_writes.sql", "0005_backend_only_conversation_writes.sql", "f6f7ef1d9972ae24bd12ec834a486835a0b27e68b74d7be997de8eb557ca1545"],
  ["20260821094736_dual_gate_message_provenance.sql", "0006_dual_gate_message_provenance.sql", "024217bca725e2f8c76904a03092076672fe15326a96341a2ee19991ae898d33"],
  ["20260821094738_user_data_control.sql", "0007_user_data_control.sql", "d0d0144a6ec77401f11246ef3eef24ed3efc8c6d46c4d87179d5430b7e0268e2"],
];

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function invariant(condition, message) {
  if (!condition) throw new Error(message);
}

const actualDeploymentFiles = (await readdir(deploymentDir))
  .filter((name) => name.endsWith(".sql"))
  .sort();
const expectedDeploymentFiles = mapping.map(([deploymentName]) => deploymentName);

invariant(
  JSON.stringify(actualDeploymentFiles) === JSON.stringify(expectedDeploymentFiles),
  `deployment migration set drifted: ${actualDeploymentFiles.join(", ")}`,
);
invariant(
  actualDeploymentFiles.every((name) => !name.includes("initial_schema")),
  "hosted deployment mapping must exclude the untracked 0001 baseline",
);

const checks = [];
for (const [deploymentName, sourceName, expectedHash] of mapping) {
  const source = await readFile(join(sourceDir, sourceName));
  const deployment = await readFile(join(deploymentDir, deploymentName));
  const sourceHash = sha256(source);
  const deploymentHash = sha256(deployment);
  invariant(sourceHash === expectedHash, `${sourceName} hash drifted`);
  invariant(deploymentHash === expectedHash, `${deploymentName} hash drifted`);
  invariant(source.equals(deployment), `${deploymentName} is not byte-identical to ${sourceName}`);
  checks.push({ deployment_name: deploymentName, source_name: sourceName, sha256: expectedHash });
}

const config = await readFile(join(siteRoot, "supabase", "config.toml"), "utf8");
invariant(config.includes('project_id = "pas-site-alpha"'), "Supabase project_id drifted");
const seedSection = config.match(/\[db\.seed\]([\s\S]*?)(?=\r?\n\[|$)/)?.[1] ?? "";
invariant(/(?:^|\r?\n)enabled = false(?:\r?\n|$)/.test(seedSection), "Supabase seed execution must remain disabled");

console.log(JSON.stringify({
  evidence_schema: "pas-supabase-deployment-map/v1",
  scope: {
    local_only: true,
    hosted_supabase_contacted: false,
    deployment_performed: false,
  },
  hosted_0001_policy: "schema-present-ledger-absent-excluded",
  checks,
  summary: { pass: checks.length, fail: 0, overall: "pass" },
}, null, 2));
