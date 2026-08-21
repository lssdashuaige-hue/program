import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { PGlite } from "@electric-sql/pglite";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";
import { pgDump } from "@electric-sql/pglite-tools";

const rehearsalDir = dirname(fileURLToPath(import.meta.url));
const migrationsDir = resolve(rehearsalDir, "../migrations");
const bootstrapSql = await readFile(join(rehearsalDir, "bootstrap.sql"), "utf8");
const forwardFreezeSql = await readFile(
  join(rehearsalDir, "forward_freeze_after_0007.sql"),
  "utf8",
);
const resumeSql = await readFile(
  join(rehearsalDir, "resume_after_forward_freeze.sql"),
  "utf8",
);
const preflightSql = await readFile(
  join(rehearsalDir, "preflight_before_0006_0007.sql"),
  "utf8",
);
const postflightSql = await readFile(
  join(rehearsalDir, "postflight_after_0006_0007.sql"),
  "utf8",
);

const EXPECTED_MIGRATIONS = [
  "0001_initial_schema.sql",
  "0002_confirmed_memory_writes.sql",
  "0003_conversation_history.sql",
  "0004_conversation_owner_fk_index.sql",
  "0005_backend_only_conversation_writes.sql",
  "0006_dual_gate_message_provenance.sql",
  "0007_user_data_control.sql",
];

const IDS = Object.freeze({
  userA: "11111111-1111-4111-8111-111111111111",
  userB: "22222222-2222-4222-8222-222222222222",
  conversationA: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  conversationB: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  sourceA: "a1000000-0000-4000-8000-000000000001",
  sourceB: "b1000000-0000-4000-8000-000000000001",
  assistantLegacy: "a2000000-0000-4000-8000-000000000001",
  assistantRollback: "a2000000-0000-4000-8000-000000000002",
  turnLegacy: "a3000000-0000-4000-8000-000000000001",
  turnRollback: "a3000000-0000-4000-8000-000000000002",
  historicalMemory: "a4000000-0000-4000-8000-000000000001",
  unconfirmedMemory: "a4000000-0000-4000-8000-000000000002",
  exactMemory: "a4000000-0000-4000-8000-000000000003",
  rollbackMemory: "a4000000-0000-4000-8000-000000000004",
  tamperedMemory: "a4000000-0000-4000-8000-000000000005",
  crossUserMemory: "b4000000-0000-4000-8000-000000000001",
  resumeMemory: "a4000000-0000-4000-8000-000000000006",
});

const report = {
  evidence_schema: "pas-local-database-rehearsal/v1",
  scope: {
    local_only: true,
    hosted_supabase_contacted: false,
    deepseek_contacted: false,
    deployment_performed: false,
  },
  engine: {
    package: "@electric-sql/pglite",
    package_version: "0.5.5",
    pg_dump_package: "@electric-sql/pglite-tools@0.4.5",
  },
  migrations: [],
  checks: [],
  summary: {},
};

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function cleanError(error) {
  const message = String(error?.message ?? error ?? "unknown error")
    .replaceAll(rehearsalDir, "<rehearsal>")
    .slice(0, 500);
  return {
    code: error?.code ?? null,
    message,
    detail: error?.detail ?? null,
    table: error?.table ?? null,
    constraint: error?.constraint ?? null,
    position: error?.position ?? null,
  };
}

function addCheck(id, status, summary, details = {}) {
  report.checks.push({ id, status, summary, details });
}

async function checked(id, summary, callback) {
  try {
    const details = (await callback()) ?? {};
    addCheck(id, "pass", summary, details);
    return details;
  } catch (error) {
    addCheck(id, "fail", summary, { error: cleanError(error) });
    return null;
  }
}

function invariant(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function createDatabase(options = {}) {
  const pg = await PGlite.create({
    extensions: { pgcrypto },
    ...options,
  });
  await pg.exec(bootstrapSql);
  return pg;
}

async function closeDatabase(pg) {
  if (pg) {
    await pg.close();
  }
}

async function applyMigrations(pg, from = 0, through = migrations.length) {
  for (const migration of migrations.slice(from, through)) {
    await pg.exec(migration.sql);
    const version = migration.name.slice(0, 4);
    const name = migration.name.slice(5, -4);
    await pg.query(
      `insert into supabase_migrations.schema_migrations (version, name)
       values ($1, $2)`,
      [version, name],
    );
  }
}

async function beginAs(pg, role, userId) {
  invariant(
    role === "authenticated" || role === "anon" || role === "service_role",
    `unsupported rehearsal role: ${role}`,
  );
  await pg.exec("begin");
  await pg.exec(`set local role ${role}`);
  if (userId) {
    await pg.query(
      "select pg_catalog.set_config('request.jwt.claim.sub', $1, true)",
      [userId],
    );
  }
}

async function queryAs(pg, role, userId, sql, params = []) {
  await beginAs(pg, role, userId);
  try {
    const result = await pg.query(sql, params);
    await pg.exec("commit");
    return result;
  } catch (error) {
    await pg.exec("rollback").catch(() => {});
    throw error;
  }
}

async function probeAs(pg, role, userId, sql, params = []) {
  await beginAs(pg, role, userId);
  try {
    const result = await pg.query(sql, params);
    await pg.exec("rollback");
    return { succeeded: true, rows: result.rows };
  } catch (error) {
    await pg.exec("rollback").catch(() => {});
    return { succeeded: false, error: cleanError(error) };
  }
}

async function probeSuperuser(pg, sql, params = []) {
  await pg.exec("begin");
  try {
    const result = await pg.query(sql, params);
    await pg.exec("rollback");
    return { succeeded: true, rows: result.rows };
  } catch (error) {
    await pg.exec("rollback").catch(() => {});
    return { succeeded: false, error: cleanError(error) };
  }
}

async function expectRejectedAs(pg, role, userId, sql, params, reason) {
  const outcome = await probeAs(pg, role, userId, sql, params);
  invariant(!outcome.succeeded, reason);
  return outcome.error;
}

async function seedUsers(pg) {
  await pg.query(
    `insert into auth.users (id, email) values
       ($1, 'local-a@example.invalid'),
       ($2, 'local-b@example.invalid')`,
    [IDS.userA, IDS.userB],
  );
}

async function seedUpgradeFixture(pg, { includeUnconfirmed = false } = {}) {
  await seedUsers(pg);
  await pg.query(
    `insert into public.profiles (id, display_name, memory_enabled) values
       ($1, 'Local A', true),
       ($2, 'Local B', true)`,
    [IDS.userA, IDS.userB],
  );
  await pg.query(
    `insert into public.conversations (id, user_id, title) values
       ($1, $2, 'Synthetic A'),
       ($3, $4, 'Synthetic B')`,
    [IDS.conversationA, IDS.userA, IDS.conversationB, IDS.userB],
  );
  await pg.query(
    `insert into public.messages (
       id, conversation_id, user_id, role, content
     ) values
       ($1, $2, $3, 'user', 'I choose gardening to settle down.'),
       ($4, $5, $6, 'user', 'I choose walking to settle down.')`,
    [
      IDS.sourceA,
      IDS.conversationA,
      IDS.userA,
      IDS.sourceB,
      IDS.conversationB,
      IDS.userB,
    ],
  );
  await pg.query(
    `insert into public.messages (
       id, conversation_id, user_id, role, content, client_turn_id,
       response_source, support_mode, risk_level
     ) values ($1, $2, $3, 'assistant', 'A legacy reviewed response.', $4,
       'review', 'reflection', 'none')`,
    [IDS.assistantLegacy, IDS.conversationA, IDS.userA, IDS.turnLegacy],
  );
  await pg.query(
    `insert into public.memories (
       id, user_id, source_message_id, kind, content, confidence, confirmed
     ) values ($1, $2, $3, 'experience', 'I choose gardening to settle down.',
       'medium', true)`,
    [IDS.historicalMemory, IDS.userA, IDS.sourceA],
  );
  if (includeUnconfirmed) {
    await pg.query(
      `insert into public.memories (
         id, user_id, source_message_id, kind, content, confidence, confirmed
       ) values ($1, $2, $3, 'reflection', 'I choose gardening to settle down.',
         'low', false)`,
      [IDS.unconfirmedMemory, IDS.userA, IDS.sourceA],
    );
  }
}

async function canonicalRows(pg) {
  const tables = [
    "auth.users",
    "public.profiles",
    "public.conversations",
    "public.messages",
    "public.memories",
    "public.themes",
  ];
  const result = {};
  for (const table of tables) {
    const rows = await pg.query(
      `select row_to_json(t)::text as row_json from ${table} t order by id`,
    );
    result[table] = rows.rows.map((row) => row.row_json);
  }
  return result;
}

const names = (await readdir(migrationsDir))
  .filter((name) => /^\d{4}_.+\.sql$/.test(name))
  .sort();
invariant(
  JSON.stringify(names) === JSON.stringify(EXPECTED_MIGRATIONS),
  `migration set drifted: found ${names.join(", ")}`,
);
const migrations = await Promise.all(
  names.map(async (name) => {
    const sql = await readFile(join(migrationsDir, name), "utf8");
    return { name, sql, sha256: sha256(sql) };
  }),
);
report.migrations = migrations.map(({ name, sha256: digest }) => ({
  name,
  sha256: digest,
}));

await checked(
  "blank-replay-0001-0007",
  "A blank local PostgreSQL database accepts bootstrap plus migrations 0001-0007 in order.",
  async () => {
    const pg = await createDatabase();
    try {
      await applyMigrations(pg);
      const version = (await pg.query("select version() as version")).rows[0].version;
      const tables = await pg.query(
        `select count(*)::int as count
         from pg_catalog.pg_class c
         join pg_catalog.pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public' and c.relkind = 'r'`,
      );
      invariant(tables.rows[0].count === 5, "expected five public tables");
      report.engine.postgresql_version = version;
      return { public_table_count: tables.rows[0].count };
    } finally {
      await closeDatabase(pg);
    }
  },
);

let canonicalPg = null;
await checked(
  "upgrade-confirmed-fixture-0001-0005-to-0007",
  "A representative confirmed-memory fixture upgrades from 0001-0005 through 0006-0007 without data loss.",
  async () => {
    const pg = await createDatabase();
    try {
      await applyMigrations(pg, 0, 5);
      await seedUpgradeFixture(pg);
      await applyMigrations(pg, 5, 7);
      const legacy = (
        await pg.query(
          `select review_contract_version, verification_contract_version
           from public.messages where id = $1`,
          [IDS.assistantLegacy],
        )
      ).rows[0];
      const memory = (
        await pg.query(
          `select lineage_id, original_content, status, version,
                  version_origin, confirmed
           from public.memories where id = $1`,
          [IDS.historicalMemory],
        )
      ).rows[0];
      const profiles = await pg.query(
        "select count(*)::int as count from public.profiles where memory_enabled = false and memory_enabled_at is null",
      );
      invariant(
        legacy.review_contract_version === "legacy" &&
          legacy.verification_contract_version === "legacy",
        "0006 did not label the legacy reviewed response",
      );
      invariant(memory.lineage_id === IDS.historicalMemory, "memory lineage was not backfilled");
      invariant(memory.status === "active" && memory.version === 1, "memory control fields were not backfilled");
      invariant(memory.version_origin === "source_quote" && memory.confirmed, "memory origin/confirmation drifted");
      invariant(profiles.rows[0].count === 2, "0007 did not conservatively disable existing profiles");
      canonicalPg = pg;
      return {
        legacy_contract: "legacy/legacy",
        backfilled_memory_version: memory.version,
        profiles_reset_to_opt_out: profiles.rows[0].count,
      };
    } catch (error) {
      await closeDatabase(pg);
      throw error;
    }
  },
);

await checked(
  "upgrade-negative-historical-unconfirmed-memory",
  "Migration 0007 fails closed and atomically when a historical confirmed=false memory row is present.",
  async () => {
    const pg = await createDatabase();
    try {
      await applyMigrations(pg, 0, 5);
      await seedUpgradeFixture(pg, { includeUnconfirmed: true });
      await applyMigrations(pg, 5, 6);
      let failure = null;
      try {
        await applyMigrations(pg, 6, 7);
      } catch (error) {
        failure = cleanError(error);
      }
      await pg.exec("rollback").catch(() => {});
      invariant(failure, "0007 accepted a historical confirmed=false memory");
      invariant(
        failure.code === "23514",
        `0007 rejected the row with an unexpected SQLSTATE: ${failure.code}`,
      );
      const remaining = await pg.query(
        `select confirmed,
                exists (
                  select 1 from information_schema.columns
                  where table_schema = 'public' and table_name = 'memories'
                    and column_name = 'lineage_id'
                ) as new_column_exists
         from public.memories where id = $1`,
        [IDS.unconfirmedMemory],
      );
      invariant(remaining.rows.length === 1, "historical unconfirmed memory disappeared");
      invariant(
        remaining.rows[0].confirmed === false,
        "failed 0007 mutated the historical confirmation state",
      );
      invariant(
        remaining.rows[0].new_column_exists === false,
        "failed 0007 left data-control DDL behind",
      );
      return { rejection: failure, preserved_legacy_row: remaining.rows[0] };
    } finally {
      await closeDatabase(pg);
    }
  },
);

if (!canonicalPg) {
  addCheck(
    "permissions-rls-rpc",
    "blocked",
    "Permission, RLS, and RPC checks require the canonical upgraded fixture.",
  );
} else {
  await checked(
    "permissions-rls-rpc",
    "RLS, column grants, and SECURITY DEFINER RPC boundaries match the 0007 contract.",
    async () => {
      const rls = await canonicalPg.query(
        `select c.relname, c.relrowsecurity
         from pg_catalog.pg_class c
         join pg_catalog.pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public'
           and c.relname in ('profiles','conversations','messages','memories','themes')
         order by c.relname`,
      );
      invariant(rls.rows.length === 5 && rls.rows.every((row) => row.relrowsecurity), "RLS is not enabled on every user table");

      const grants = (
        await canonicalPg.query(
          `select
             has_table_privilege('authenticated', 'public.messages', 'select') as message_table_select,
             has_column_privilege('authenticated', 'public.messages', 'content', 'select') as message_content_select,
             has_column_privilege('authenticated', 'public.messages', 'review_contract_version', 'select') as internal_review_select,
             has_column_privilege('authenticated', 'public.profiles', 'display_name', 'update') as display_name_update,
             has_column_privilege('authenticated', 'public.profiles', 'memory_enabled', 'update') as memory_flag_update,
             has_column_privilege('authenticated', 'public.memories', 'status', 'update') as memory_status_update,
             has_column_privilege('authenticated', 'public.memories', 'content', 'update') as memory_content_update`,
        )
      ).rows[0];
      invariant(grants.message_table_select === false, "authenticated retained table-wide message SELECT");
      invariant(grants.message_content_select === true, "authenticated lost public message content SELECT");
      invariant(grants.internal_review_select === false, "internal review provenance is column-readable");
      invariant(grants.display_name_update === true && grants.memory_flag_update === false, "profile column grants are not narrow");
      invariant(grants.memory_status_update === true && grants.memory_content_update === false, "memory update grants are not narrow");

      const functions = await canonicalPg.query(
        `select p.proname, p.prosecdef, p.proconfig,
                has_function_privilege('authenticated', p.oid, 'execute') as authenticated_execute,
                has_function_privilege('anon', p.oid, 'execute') as anon_execute
         from pg_catalog.pg_proc p
         join pg_catalog.pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public'
           and p.proname in (
             'set_memory_enabled',
             'is_exact_owned_user_message',
             'revise_memory',
             'delete_memory_lineage'
           )
         order by p.proname`,
      );
      invariant(functions.rows.length === 4, "expected four data-control functions");
      for (const fn of functions.rows) {
        invariant(fn.prosecdef === true, `${fn.proname} is not SECURITY DEFINER`);
        invariant(fn.authenticated_execute === true, `${fn.proname} is not executable by authenticated`);
        invariant(fn.anon_execute === false, `${fn.proname} is executable by anon/PUBLIC`);
        invariant(
          Array.isArray(fn.proconfig) && fn.proconfig.includes("search_path=\"\""),
          `${fn.proname} does not pin an empty search_path`,
        );
      }

      const deniedUpdate = await expectRejectedAs(
        canonicalPg,
        "authenticated",
        IDS.userA,
        "update public.profiles set memory_enabled = true where id = $1 returning id",
        [IDS.userA],
        "authenticated could directly update memory_enabled",
      );
      const enabled = await queryAs(
        canonicalPg,
        "authenticated",
        IDS.userA,
        "select * from public.set_memory_enabled(true)",
      );
      invariant(enabled.rows[0]?.memory_enabled === true, "set_memory_enabled did not enable the owner");
      return {
        rls_tables: rls.rows.map((row) => row.relname),
        rpc_names: functions.rows.map((row) => row.proname),
        direct_memory_flag_update_error: deniedUpdate,
      };
    },
  );

  await checked(
    "memory-exact-source-and-tamper-negative",
    "An opted-in owner can save an exact source quote, while altered content is rejected.",
    async () => {
      const inserted = await queryAs(
        canonicalPg,
        "authenticated",
        IDS.userA,
        `insert into public.memories (
           id, user_id, lineage_id, source_message_id, kind, content,
           original_content, confidence, confirmed, status, version,
           version_origin, confirmed_at
         ) values ($1, $2, $1, $3, 'experience', $4, $4, 'medium', true,
                   'active', 1, 'source_quote', now())
         returning id`,
        [
          IDS.exactMemory,
          IDS.userA,
          IDS.sourceA,
          "I choose gardening to settle down.",
        ],
      );
      invariant(inserted.rows[0]?.id === IDS.exactMemory, "exact source memory was not inserted");
      const rejected = await expectRejectedAs(
        canonicalPg,
        "authenticated",
        IDS.userA,
        `insert into public.memories (
           id, user_id, lineage_id, source_message_id, kind, content,
           original_content, confidence, confirmed, status, version,
           version_origin, confirmed_at
         ) values ($1, $2, $1, $3, 'experience', 'I definitely garden every day.',
                   'I definitely garden every day.', 'medium', true,
                   'active', 1, 'source_quote', now())
         returning id`,
        [IDS.tamperedMemory, IDS.userA, IDS.sourceA],
        "altered content was accepted as a source quote",
      );
      return { exact_memory_id: IDS.exactMemory, tamper_error: rejected };
    },
  );

  await checked(
    "revise-memory-null-expected-version-negative",
    "revise_memory rejects expected_version=NULL instead of bypassing optimistic concurrency.",
    async () => {
      const outcome = await probeAs(
        canonicalPg,
        "authenticated",
        IDS.userA,
        "select id, version from public.revise_memory($1, $2, $3)",
        [IDS.historicalMemory, null, "A user-authored corrected memory."],
      );
      invariant(
        !outcome.succeeded,
        "revise_memory accepted expected_version=NULL and created a new version",
      );
      return { rejection: outcome.error };
    },
  );

  await checked(
    "two-user-isolation-and-cross-lineage-negative",
    "User B cannot read, revise, delete, or attach a new memory to user A's lineage.",
    async () => {
      await queryAs(
        canonicalPg,
        "authenticated",
        IDS.userB,
        "select * from public.set_memory_enabled(true)",
      );
      const visible = await queryAs(
        canonicalPg,
        "authenticated",
        IDS.userB,
        "select id from public.memories where id = $1",
        [IDS.exactMemory],
      );
      invariant(visible.rows.length === 0, "user B can read user A's memory");
      const revised = await queryAs(
        canonicalPg,
        "authenticated",
        IDS.userB,
        "select id from public.revise_memory($1, 1, 'cross-user revision')",
        [IDS.exactMemory],
      );
      invariant(revised.rows.length === 0, "user B revised user A's memory");
      const deleted = await queryAs(
        canonicalPg,
        "authenticated",
        IDS.userB,
        "select public.delete_memory_lineage($1) as deleted",
        [IDS.exactMemory],
      );
      invariant(deleted.rows[0]?.deleted === 0, "user B deleted user A's lineage");
      const crossLineageError = await expectRejectedAs(
        canonicalPg,
        "authenticated",
        IDS.userB,
        `insert into public.memories (
           id, user_id, lineage_id, source_message_id, kind, content,
           original_content, confidence, confirmed, status, version,
           version_origin, confirmed_at
         ) values ($1, $2, $3, $4, 'experience', $5, $5, 'low', true,
                   'active', 1, 'source_quote', now()) returning id`,
        [
          IDS.crossUserMemory,
          IDS.userB,
          IDS.exactMemory,
          IDS.sourceB,
          "I choose walking to settle down.",
        ],
        "user B attached a memory to user A's lineage",
      );
      const ownerConstraints = await canonicalPg.query(
        `select conname, cardinality(conkey)::int as local_column_count,
                cardinality(confkey)::int as referenced_column_count
         from pg_catalog.pg_constraint
         where conrelid = 'public.memories'::regclass
           and conname in ('memories_lineage_fk', 'memories_supersedes_fk')
         order by conname`,
      );
      invariant(
        ownerConstraints.rows.length === 2 &&
          ownerConstraints.rows.every(
            (row) => row.local_column_count === 2 && row.referenced_column_count === 2,
          ),
        "composite memory owner foreign keys are missing",
      );
      const databaseCrossOwner = await probeSuperuser(
        canonicalPg,
        `insert into public.memories (
           id, user_id, lineage_id, source_message_id, supersedes_id, kind,
           content, original_content, confidence, confirmed, status, version,
           version_origin, confirmed_at
         ) values ($1, $2, $3, $4, $3, 'experience', 'Cross-owner revision.',
                   'I choose walking to settle down.', 'low', true, 'active', 2,
                   'user_revision', now()) returning id`,
        [
          IDS.crossUserMemory,
          IDS.userB,
          IDS.historicalMemory,
          IDS.sourceB,
        ],
      );
      invariant(
        !databaseCrossOwner.succeeded && databaseCrossOwner.error.code === "23503",
        "database constraints accepted a cross-user lineage/supersedes reference",
      );
      return {
        user_b_visible_rows: visible.rows.length,
        user_b_deleted_rows: deleted.rows[0].deleted,
        cross_lineage_error: crossLineageError,
        composite_owner_constraints: ownerConstraints.rows.map((row) => row.conname),
        database_cross_owner_error: databaseCrossOwner.error,
      };
    },
  );
}

await checked(
  "runbook-preflight-and-postflight-sql",
  "The read-only hosted preflight and postflight checklists execute against their matching local schema boundaries.",
  async () => {
    const pg = await createDatabase();
    try {
      await applyMigrations(pg, 0, 5);
      await seedUpgradeFixture(pg);
      await pg.exec(preflightSql);
      await applyMigrations(pg, 5, 7);
      await pg.exec(postflightSql);
      const ledger = await pg.query(
        "select version, name from supabase_migrations.schema_migrations order by version",
      );
      invariant(ledger.rows.length === 7, "local migration ledger does not contain 0001-0007");
      return {
        preflight_boundary: "0005",
        postflight_boundary: "0007",
        local_ledger_entries: ledger.rows.length,
      };
    } finally {
      await closeDatabase(pg);
    }
  },
);

await checked(
  "migration-0006-failure-atomicity",
  "A forced failure inside migration 0006 rolls back its DDL, data labels, and privilege changes.",
  async () => {
    const pg = await createDatabase();
    try {
      await applyMigrations(pg, 0, 5);
      await seedUpgradeFixture(pg);
      const failingSql = migrations[5].sql.replace(
        /commit;\s*$/i,
        "select 1 / 0;\ncommit;",
      );
      invariant(failingSql !== migrations[5].sql, "could not inject the 0006 failure probe");
      let failure = null;
      try {
        await pg.exec(failingSql);
      } catch (error) {
        failure = cleanError(error);
      }
      await pg.exec("rollback").catch(() => {});
      invariant(failure, "forced 0006 failure unexpectedly succeeded");
      const state = (
        await pg.query(
          `select
             exists (
               select 1 from information_schema.columns
               where table_schema = 'public' and table_name = 'messages'
                 and column_name = 'review_contract_version'
             ) as new_column_exists,
             has_table_privilege('authenticated', 'public.messages', 'select') as old_table_select,
             (select response_source from public.messages where id = $1) as response_source`,
          [IDS.assistantLegacy],
        )
      ).rows[0];
      invariant(state.new_column_exists === false, "0006 DDL survived a failed transaction");
      invariant(state.old_table_select === true, "0006 privilege revocation survived a failed transaction");
      invariant(state.response_source === "review", "0006 mutated legacy message data after rollback");
      return { forced_error: failure, preserved_state: state };
    } finally {
      await closeDatabase(pg);
    }
  },
);

await checked(
  "migration-0007-failure-atomicity",
  "A forced failure inside migration 0007 rolls back all of 0007 and preserves the pre-migration state.",
  async () => {
    const pg = await createDatabase();
    try {
      await applyMigrations(pg, 0, 6);
      await seedUsers(pg);
      await pg.query(
        "insert into public.profiles (id, display_name, memory_enabled) values ($1, 'Atomic A', true)",
        [IDS.userA],
      );
      const failingSql = migrations[6].sql.replace(
        /commit;\s*$/i,
        "select 1 / 0;\ncommit;",
      );
      invariant(failingSql !== migrations[6].sql, "could not inject the 0007 failure probe");
      let failure = null;
      try {
        await pg.exec(failingSql);
      } catch (error) {
        failure = cleanError(error);
      }
      await pg.exec("rollback").catch(() => {});
      invariant(failure, "forced 0007 failure unexpectedly succeeded");
      const state = (
        await pg.query(
          `select
             exists (
               select 1 from information_schema.columns
               where table_schema = 'public' and table_name = 'profiles'
                 and column_name = 'memory_enabled_at'
             ) as new_column_exists,
             (select memory_enabled from public.profiles where id = $1) as memory_enabled,
             (select column_default
                from information_schema.columns
               where table_schema = 'public' and table_name = 'profiles'
                 and column_name = 'memory_enabled') as memory_default`,
          [IDS.userA],
        )
      ).rows[0];
      invariant(state.new_column_exists === false, "0007 DDL survived a failed transaction");
      invariant(state.memory_enabled === true, "0007 data reset survived a failed transaction");
      invariant(state.memory_default === "true", "0007 default change survived a failed transaction");
      return { forced_error: failure, preserved_state: state };
    } finally {
      await closeDatabase(pg);
    }
  },
);

await checked(
  "pre-migration-physical-snapshot-disaster-restore",
  "A physical snapshot taken at 0005 restores into an independent local instance after a simulated 0006-0007 upgrade.",
  async () => {
    const source = await createDatabase();
    let restored = null;
    try {
      await applyMigrations(source, 0, 5);
      await seedUpgradeFixture(source);
      const before = await canonicalRows(source);
      const snapshot = await source.dumpDataDir("gzip");
      const snapshotBytes = new Uint8Array(await snapshot.arrayBuffer());
      invariant(snapshotBytes.byteLength > 0, "PGlite returned an empty pre-migration snapshot");

      await applyMigrations(source, 5, 7);
      const upgraded = (
        await source.query(
          `select
             exists (
               select 1 from information_schema.columns
               where table_schema = 'public' and table_name = 'messages'
                 and column_name = 'review_contract_version'
             ) as migration_0006_present,
             exists (
               select 1 from information_schema.columns
               where table_schema = 'public' and table_name = 'memories'
                 and column_name = 'lineage_id'
             ) as migration_0007_present`,
        )
      ).rows[0];
      invariant(upgraded.migration_0006_present && upgraded.migration_0007_present, "simulated upgrade did not reach 0007");

      restored = await PGlite.create({
        extensions: { pgcrypto },
        loadDataDir: snapshot,
      });
      const after = await canonicalRows(restored);
      invariant(JSON.stringify(after) === JSON.stringify(before), "physical disaster restore changed pre-migration rows");
      const restoredState = (
        await restored.query(
          `select
             exists (
               select 1 from information_schema.columns
               where table_schema = 'public' and table_name = 'messages'
                 and column_name = 'review_contract_version'
             ) as migration_0006_present,
             exists (
               select 1 from information_schema.columns
               where table_schema = 'public' and table_name = 'memories'
                 and column_name = 'lineage_id'
             ) as migration_0007_present`,
        )
      ).rows[0];
      invariant(
        restoredState.migration_0006_present === false &&
          restoredState.migration_0007_present === false,
        "disaster restore did not return to the 0005 schema boundary",
      );
      return {
        snapshot_bytes: snapshotBytes.byteLength,
        snapshot_sha256: sha256(snapshotBytes),
        restored_schema_boundary: "0005",
        restored_table_counts: Object.fromEntries(
          Object.entries(after).map(([table, rows]) => [table, rows.length]),
        ),
      };
    } finally {
      await closeDatabase(restored);
      await closeDatabase(source);
    }
  },
);

if (!canonicalPg) {
  addCheck(
    "forward-freeze-and-resume",
    "blocked",
    "Forward freeze/resume requires the canonical upgraded fixture.",
  );
  addCheck(
    "logical-backup-and-restore",
    "blocked",
    "Logical backup/restore requires the canonical upgraded fixture.",
  );
} else {
  await checked(
    "forward-freeze-and-resume",
    "A safe forward freeze blocks every authenticated memory mutation, preserves reads/data, and resumes only exact 0007 privileges with opt-in still off.",
    async () => {
      const freezePg = await createDatabase();
      try {
        await applyMigrations(freezePg, 0, 5);
        await seedUpgradeFixture(freezePg);
        await applyMigrations(freezePg, 5, 7);
        await queryAs(
          freezePg,
          "authenticated",
          IDS.userA,
          "select * from public.set_memory_enabled(true)",
        );
        const before = (
          await freezePg.query(
            `select
               (select count(*)::int from public.memories) as memory_count,
               (select count(*)::int from information_schema.columns
                 where table_schema = 'public' and table_name = 'memories') as memory_column_count,
               (select count(*)::int from pg_catalog.pg_constraint
                 where conrelid = 'public.memories'::regclass) as memory_constraint_count`,
          )
        ).rows[0];

        await freezePg.exec(forwardFreezeSql);
        const frozenProfiles = await freezePg.query(
          "select count(*)::int as count from public.profiles where memory_enabled = false and memory_enabled_at is null",
        );
        invariant(frozenProfiles.rows[0].count === 2, "forward freeze did not opt out every profile");

        const frozenInsert = await expectRejectedAs(
          freezePg,
          "authenticated",
          IDS.userA,
          `insert into public.memories (
             id, user_id, lineage_id, source_message_id, kind, content,
             original_content, confidence, confirmed, status, version,
             version_origin, confirmed_at
           ) values ($1, $2, $1, $3, 'experience', $4, $4, 'medium', true,
                     'active', 1, 'source_quote', now()) returning id`,
          [
            IDS.resumeMemory,
            IDS.userA,
            IDS.sourceA,
            "I choose gardening to settle down.",
          ],
          "forward freeze allowed an authenticated memory INSERT",
        );
        const frozenUpdate = await expectRejectedAs(
          freezePg,
          "authenticated",
          IDS.userA,
          "update public.memories set status = 'paused', paused_at = now() where id = $1 returning id",
          [IDS.historicalMemory],
          "forward freeze allowed an authenticated memory UPDATE",
        );
        const frozenToggle = await expectRejectedAs(
          freezePg,
          "authenticated",
          IDS.userA,
          "select * from public.set_memory_enabled(true)",
          [],
          "forward freeze allowed set_memory_enabled",
        );
        const frozenHelper = await expectRejectedAs(
          freezePg,
          "authenticated",
          IDS.userA,
          "select public.is_exact_owned_user_message($1, $2) as exact",
          [IDS.sourceA, "I choose gardening to settle down."],
          "forward freeze allowed the exact-source helper",
        );
        const frozenRevise = await expectRejectedAs(
          freezePg,
          "authenticated",
          IDS.userA,
          "select id from public.revise_memory($1, 1, 'Frozen revision')",
          [IDS.historicalMemory],
          "forward freeze allowed revise_memory",
        );
        const frozenDelete = await expectRejectedAs(
          freezePg,
          "authenticated",
          IDS.userA,
          "select public.delete_memory_lineage($1) as deleted",
          [IDS.historicalMemory],
          "forward freeze allowed delete_memory_lineage",
        );
        const readable = await queryAs(
          freezePg,
          "authenticated",
          IDS.userA,
          "select id, content from public.memories where id = $1",
          [IDS.historicalMemory],
        );
        invariant(readable.rows.length === 1, "forward freeze blocked owner reads/export");
        const afterFreeze = (
          await freezePg.query(
            `select
               (select count(*)::int from public.memories) as memory_count,
               (select count(*)::int from information_schema.columns
                 where table_schema = 'public' and table_name = 'memories') as memory_column_count,
               (select count(*)::int from pg_catalog.pg_constraint
                 where conrelid = 'public.memories'::regclass) as memory_constraint_count`,
          )
        ).rows[0];
        invariant(JSON.stringify(afterFreeze) === JSON.stringify(before), "forward freeze changed schema or memory rows");

        await freezePg.exec(resumeSql);
        const stillOff = (
          await freezePg.query(
            "select memory_enabled from public.profiles where id = $1",
            [IDS.userA],
          )
        ).rows[0].memory_enabled;
        invariant(stillOff === false, "resume silently re-enabled memory");
        const beforeOptIn = await expectRejectedAs(
          freezePg,
          "authenticated",
          IDS.userA,
          `insert into public.memories (
             id, user_id, lineage_id, source_message_id, kind, content,
             original_content, confidence, confirmed, status, version,
             version_origin, confirmed_at
           ) values ($1, $2, $1, $3, 'experience', $4, $4, 'medium', true,
                     'active', 1, 'source_quote', now()) returning id`,
          [
            IDS.resumeMemory,
            IDS.userA,
            IDS.sourceA,
            "I choose gardening to settle down.",
          ],
          "resume allowed a write before explicit opt-in",
        );
        await queryAs(
          freezePg,
          "authenticated",
          IDS.userA,
          "select * from public.set_memory_enabled(true)",
        );
        const resumedInsert = await queryAs(
          freezePg,
          "authenticated",
          IDS.userA,
          `insert into public.memories (
             id, user_id, lineage_id, source_message_id, kind, content,
             original_content, confidence, confirmed, status, version,
             version_origin, confirmed_at
           ) values ($1, $2, $1, $3, 'experience', $4, $4, 'medium', true,
                     'active', 1, 'source_quote', now()) returning id`,
          [
            IDS.resumeMemory,
            IDS.userA,
            IDS.sourceA,
            "I choose gardening to settle down.",
          ],
        );
        invariant(resumedInsert.rows[0]?.id === IDS.resumeMemory, "resume did not restore exact-source INSERT");
        const resumedHelper = await probeAs(
          freezePg,
          "authenticated",
          IDS.userA,
          "select public.is_exact_owned_user_message($1, $2) as exact",
          [IDS.sourceA, "I choose gardening to settle down."],
        );
        const resumedRevise = await probeAs(
          freezePg,
          "authenticated",
          IDS.userA,
          "select id from public.revise_memory($1, 1, 'Resumed revision')",
          [IDS.resumeMemory],
        );
        const resumedDelete = await probeAs(
          freezePg,
          "authenticated",
          IDS.userA,
          "select public.delete_memory_lineage($1) as deleted",
          [IDS.resumeMemory],
        );
        invariant(resumedHelper.succeeded && resumedHelper.rows[0]?.exact === true, "resume did not restore exact-source helper");
        invariant(resumedRevise.succeeded && resumedRevise.rows.length === 1, "resume did not restore revise_memory");
        invariant(resumedDelete.succeeded && resumedDelete.rows[0]?.deleted === 1, "resume did not restore delete_memory_lineage");
        return {
          frozen_profiles: frozenProfiles.rows[0].count,
          frozen_mutation_errors: {
            insert: frozenInsert.code,
            update: frozenUpdate.code,
            toggle: frozenToggle.code,
            helper: frozenHelper.code,
            revise: frozenRevise.code,
            delete: frozenDelete.code,
          },
          owner_read_rows_while_frozen: readable.rows.length,
          resume_kept_default_off: !stillOff,
          pre_opt_in_error: beforeOptIn.code,
          resumed_exact_write: resumedInsert.rows[0].id,
        };
      } finally {
        await closeDatabase(freezePg);
      }
    },
  );

  await checked(
    "logical-backup-and-restore",
    "A pg_dump logical data backup restores into a fresh 0001-0007 schema with identical synthetic rows.",
    async () => {
      const before = await canonicalRows(canonicalPg);
      let dump;
      try {
        dump = await pgDump({
          pg: canonicalPg,
          args: [
            "--data-only",
            "--schema=auth",
            "--schema=public",
            "--no-owner",
            "--no-privileges",
          ],
        });
      } catch (error) {
        throw new Error(
          `pgDump API is unavailable; recovery rehearsal is blocked: ${cleanError(error).message}`,
        );
      }
      const dumpSql = await dump.text();
      invariant(dumpSql.length > 0, "pgDump returned an empty logical backup");

      const restored = await createDatabase();
      try {
        await applyMigrations(restored);
        // The message insert trigger intentionally advances a conversation's
        // updated_at. Disable only that derived-field trigger while replaying
        // the already-complete logical snapshot so row identity is exact.
        try {
          await restored.exec(
            "alter table public.messages disable trigger messages_touch_conversation_after_insert",
          );
        } catch (error) {
          throw new Error(`could not disable the derived-field trigger: ${cleanError(error).message}`);
        }
        try {
          try {
            await restored.exec(dumpSql);
          } catch (error) {
            throw new Error(`logical dump replay failed: ${cleanError(error).message}`);
          }
        } finally {
          try {
            // pg_dump deliberately emits `SET row_security = off` so a dump
            // cannot silently omit rows. Restore the ordinary session setting
            // before post-restore verification queries.
            await restored.exec("reset role; reset session authorization; set row_security = on");
            await restored.exec(
              "alter table public.messages enable trigger messages_touch_conversation_after_insert",
            );
          } catch (error) {
            throw new Error(`could not re-enable the derived-field trigger: ${cleanError(error).message}`);
          }
        }
        const after = await canonicalRows(restored);
        invariant(
          JSON.stringify(after) === JSON.stringify(before),
          "restored synthetic rows differ from the backup source",
        );
        const isolated = await queryAs(
          restored,
          "authenticated",
          IDS.userB,
          "select id from public.memories where user_id = $1",
          [IDS.userA],
        );
        invariant(isolated.rows.length === 0, "RLS isolation failed after logical restore");
        return {
          dump_bytes: Buffer.byteLength(dumpSql, "utf8"),
          dump_sha256: sha256(dumpSql),
          restored_table_counts: Object.fromEntries(
            Object.entries(after).map(([table, rows]) => [table, rows.length]),
          ),
          post_restore_user_b_cross_read_rows: isolated.rows.length,
        };
      } finally {
        await closeDatabase(restored);
      }
    },
  );
}

await closeDatabase(canonicalPg);

const statusCounts = report.checks.reduce(
  (counts, check) => {
    counts[check.status] = (counts[check.status] ?? 0) + 1;
    return counts;
  },
  { pass: 0, fail: 0, blocked: 0 },
);
report.summary = {
  ...statusCounts,
  overall: statusCounts.fail === 0 && statusCounts.blocked === 0 ? "pass" : "not_ready",
};

process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
if (report.summary.overall !== "pass") {
  process.exitCode = 1;
}
