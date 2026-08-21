import re
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "database"
    / "migrations"
    / "0006_dual_gate_message_provenance.sql"
)
DATA_CONTROL_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "database"
    / "migrations"
    / "0007_user_data_control.sql"
)


def test_dual_gate_migration_backfills_existing_turns_as_legacy() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "add column if not exists review_contract_version text" in sql
    assert "add column if not exists verification_contract_version text" in sql
    assert "add column if not exists bounded_response_kind text" in sql
    assert "review_contract_version = 'legacy'" in sql
    assert "verification_contract_version = 'legacy'" in sql
    assert "review_contract_version is null" in sql
    assert "verification_contract_version is null" in sql


def test_dual_gate_shape_is_null_safe_and_limits_current_bounded_kinds() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    for comparison in (
        "response_source is not distinct from 'review'",
        "support_mode is not distinct from 'reflection'",
        "risk_level is not distinct from 'none'",
        "review_contract_version is not distinct from '2'",
        # v1 is retained only as historical provenance; v2 is current.
        "verification_contract_version is not distinct from '1'",
        "verification_contract_version is not distinct from '2'",
    ):
        assert comparison in sql

    for bounded_kind in (
        "third_party_private_state",
        "single_chat_diagnostic_request",
        "personal_lifespan_conversion",
        "unavailable_cross_chat_context",
    ):
        assert f"'{bounded_kind}'" in sql

    # User and system rows must never carry release provenance.
    assert sql.count("and review_contract_version is null") >= 4
    assert sql.count("and verification_contract_version is null") >= 4
    assert sql.count("and bounded_response_kind is null") >= 3


def test_cross_chat_bounded_kind_exists_only_in_the_current_v2_pair() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    def kinds_for_verifier(version: str) -> set[str]:
        match = re.search(
            r"review_contract_version is not distinct from '2'\s+"
            rf"and verification_contract_version is not distinct from '{version}'\s+"
            r"and\s*\(\s*bounded_response_kind is null\s+"
            r"or bounded_response_kind in\s*\((?P<kinds>[^)]*)\)",
            sql,
            flags=re.DOTALL,
        )
        assert match is not None
        return {
            item.strip().strip("'")
            for item in match.group("kinds").split(",")
        }

    legacy_kinds = kinds_for_verifier("1")
    current_kinds = kinds_for_verifier("2")
    assert legacy_kinds == {
        "third_party_private_state",
        "single_chat_diagnostic_request",
        "personal_lifespan_conversion",
    }
    assert current_kinds == legacy_kinds | {"unavailable_cross_chat_context"}


def test_authenticated_reads_only_the_public_message_projection() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert (
        "revoke select on table public.messages from anon, authenticated;"
        in sql
    )
    private_revoke = re.search(
        r"revoke\s+select\s*\((?P<columns>.*?)\)\s*"
        r"on\s+table\s+public\.messages\s+from\s+anon,\s*authenticated\s*;",
        sql,
        flags=re.DOTALL,
    )
    assert private_revoke is not None
    assert {
        column.strip()
        for column in private_revoke.group("columns").split(",")
    } == {
        "review_contract_version",
        "verification_contract_version",
        "bounded_response_kind",
    }
    assert re.search(
        r"grant\s+select\s+on\s+table\s+public\.messages\s+to\s+authenticated",
        sql,
    ) is None
    assert re.search(
        r"grant\s+all(?:\s+privileges)?\s+on\s+(?:table\s+)?"
        r"public\.messages\s+to\s+authenticated",
        sql,
    ) is None
    match = re.search(
        r"grant\s+select\s*\((?P<columns>.*?)\)\s*"
        r"on\s+table\s+public\.messages\s+to\s+authenticated\s*;",
        sql,
        flags=re.DOTALL,
    )
    assert match is not None
    granted_columns = {
        column.strip()
        for column in match.group("columns").split(",")
    }
    assert granted_columns == {
        "id",
        "conversation_id",
        "client_turn_id",
        "role",
        "content",
        "response_source",
        "support_mode",
        "risk_level",
        "created_at",
    }
    assert granted_columns.isdisjoint(
        {
            "review_contract_version",
            "verification_contract_version",
            "bounded_response_kind",
        }
    )


def test_server_permissions_and_existing_rls_policy_are_preserved() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "grant select, insert on table public.messages to service_role;" in sql
    assert "row level security" not in sql
    assert "create policy" not in sql
    assert "drop policy" not in sql


def test_data_control_migration_makes_memory_explicit_opt_in() -> None:
    sql = DATA_CONTROL_MIGRATION.read_text(encoding="utf-8").lower()

    assert "alter column memory_enabled set default false" in sql
    assert "function public.set_memory_enabled(boolean)" in sql
    assert "rpc/set_memory_enabled" not in sql
    assert "revoke insert, update, delete on table public.profiles" in sql
    assert "grant update (display_name) on table public.profiles" in sql
    assert "memory_enabled_at = excluded.memory_enabled_at" in sql
    assert "set memory_enabled = false" in sql
    assert "add column if not exists memory_enabled_at timestamptz" in sql
    assert "p.memory_enabled = true" in sql
    assert "memories_insert_opted_in_source_quote" in sql
    assert "function public.is_exact_owned_user_message" in sql
    assert "source.role = 'user'" in sql
    assert "source.content = p_content" in sql
    assert "public.is_exact_owned_user_message(source_message_id, content)" in sql


def test_data_control_migration_preserves_source_and_version_lineage() -> None:
    sql = DATA_CONTROL_MIGRATION.read_text(encoding="utf-8").lower()

    for column in (
        "lineage_id",
        "supersedes_id",
        "original_content",
        "version_origin",
        "confirmed_at",
        "paused_at",
        "superseded_at",
    ):
        assert f"add column if not exists {column}" in sql
    assert "memories_lineage_version_key unique (lineage_id, version)" in sql
    assert "memories_id_user_id_key unique (id, user_id)" in sql
    assert "foreign key (lineage_id, user_id)" in sql
    assert "foreign key (supersedes_id, user_id)" in sql
    assert sql.count("references public.memories(id, user_id) on delete cascade") == 2
    assert "version_origin = 'source_quote'" in sql
    assert "version_origin = 'user_revision'" in sql
    assert "content = original_content" in sql
    assert "original_content = current_row.original_content" not in sql
    assert "current_row.original_content" in sql
    assert "current_row.id" in sql
    assert "current_row.version + 1" in sql


def test_data_control_revision_is_narrow_and_owner_checked() -> None:
    sql = DATA_CONTROL_MIGRATION.read_text(encoding="utf-8").lower()

    assert "security definer" in sql
    assert "set search_path = ''" in sql
    assert sql.count("user_id = (select auth.uid())") >= 3
    assert (
        "revoke all on function public.revise_memory(uuid, integer, text) "
        "from public"
    ) in sql
    assert (
        "grant execute on function public.revise_memory(uuid, integer, text)"
        in sql
    )
    assert (
        "revoke insert, update, delete on table public.memories from authenticated"
        in sql
    )
    assert "grant update (status, paused_at, updated_at)" in sql
    assert "function public.delete_memory_lineage(uuid)" in sql
    assert "p_expected_version is null" in sql
    assert "current_row.version is distinct from p_expected_version" in sql


def test_data_control_migration_rejects_unverifiable_legacy_memories() -> None:
    sql = DATA_CONTROL_MIGRATION.read_text(encoding="utf-8").lower()

    assert "memory.confirmed is distinct from true" in sql
    assert "source.id is null" in sql
    assert "source.user_id is distinct from memory.user_id" in sql
    assert "source.role is distinct from 'user'" in sql
    assert "source.content is distinct from memory.content" in sql
    assert "using errcode = '23514'" in sql
