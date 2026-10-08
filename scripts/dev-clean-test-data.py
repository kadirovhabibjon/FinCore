#!/usr/bin/env python3
"""Removes test accounts, and what they did, from a development stack.

A stack that the end-to-end and load suites have run against for weeks
holds thousands of accounts nobody owns; the admin dashboard then counts
them as customers. This removes them and keeps the real ones.

    ./scripts/dev-clean-test-data.py            # show what would go, ask, then do it
    ./scripts/dev-clean-test-data.py --dry-run  # only show

Whose data goes: every account whose email is at a domain reserved for
tests and documentation (example.com, example.org, *.test - RFC 2606).
Nobody can own such an address, which is what makes the rule safe; every
suite in this repository registers its users there.

What goes with them, per database, each in one transaction:

  identity_db      the accounts (sessions, roles, reset codes cascade)
  payment_db       their transfers, payments, refunds, exchanges, limits,
                   merchants, and the outbox rows and idempotency keys of
                   those; a merchant a real customer has paid is kept
  notification_db  their notifications, support conversations, read marks
  fraud_db         their risk checks
  webhook_db       their endpoints and deliveries

What is deliberately left alone:

  ledger_db   Deleting a wallet's entries would unbalance the postings
              they are half of. The test wallets stay, owned by nobody.
  audit_db    An audit log that can be edited is not one.

Before anything is deleted the five databases are dumped next to the
repository (../db-backup-<date>-<time>/). Restore one with:

    docker compose exec -T postgres pg_restore -U postgres --clean -d <db> < <db>.dump

For a development machine only. It talks to the `postgres` service of
this repository's docker compose stack and nothing else.
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATABASES = ["identity_db", "payment_db", "notification_db", "fraud_db", "webhook_db"]
# Reserved for tests and documentation: nobody can receive mail there.
TEST = "(email like '%@example.com' or email like '%@example.org' or email like '%.test')"
# The merchants of the service providers belong to FinCore itself.
SYSTEM_OWNER = "00000000-0000-4000-8000-00000000b111"


def psql(database: str, sql: str) -> str:
    """Runs `sql` in the stack's postgres; a failure rolls the transaction back."""
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "postgres", "-At",
         "-v", "ON_ERROR_STOP=1", "-d", database],
        input=sql, capture_output=True, text=True, cwd=REPO,
    )
    if result.returncode:
        sys.exit(f"{database}: failed, nothing in it was changed.\n{result.stderr[-800:]}")
    return result.stdout.strip()


def loaded(ids: list[str]) -> str:
    """SQL that puts the test accounts' ids in a temp table `t`."""
    return "create temp table t(id uuid primary key);\ncopy t from stdin;\n" + "\n".join(ids) + "\n\\.\n"


def counts(database: str, queries: dict[str, str], ids: list[str]) -> dict[str, int]:
    sql = "begin;\n" + loaded(ids) + "".join(
        f"select '{name}='||count(*) from {source};\n" for name, source in queries.items()
    ) + "rollback;\n"
    rows = [line for line in psql(database, sql).split("\n") if "=" in line]
    return {name: int(value) for name, value in (row.split("=") for row in rows)}


IN_T = "(select id from t)"
# What would be deleted, as `from` clauses - also what is counted first.
DOOMED = {
    "payment_db": {
        "transfers": f"transfers where initiator_user_id in {IN_T}",
        "payments": f"payments where initiator_user_id in {IN_T}",
        "exchanges": f"exchanges where initiator_user_id in {IN_T}",
        "money requests": f"money_requests where requester_user_id in {IN_T} and payer_user_id in {IN_T}",
        "merchants": f"merchants m where owner_user_id in {IN_T} and not exists "
                     f"(select 1 from payments p where p.merchant_id = m.id "
                     f"and p.initiator_user_id not in {IN_T})",
    },
    "notification_db": {
        "notifications": f"notifications where recipient_user_id in {IN_T}",
        "support conversations": f"support_threads where user_id in {IN_T}",
    },
    "fraud_db": {"risk checks": f"fraud_checks where user_id in {IN_T}"},
    "webhook_db": {"webhook endpoints": f"webhook_endpoints where owner_user_id in {IN_T}"},
}

DELETE = {
    "payment_db": f"""
create temp table dp as select id from payments where initiator_user_id in {IN_T};
create temp table dt as select id from transfers where initiator_user_id in {IN_T};
create temp table de as select id from exchanges where initiator_user_id in {IN_T};
create temp table dr as select id from refunds where payment_id in (select id from dp);
delete from refunds where id in (select id from dr);
delete from payments where id in (select id from dp);
delete from transfers where id in (select id from dt);
delete from exchanges where id in (select id from de);
delete from money_requests where requester_user_id in {IN_T} and payer_user_id in {IN_T};
delete from wallet_limits where owner_user_id in {IN_T};
delete from merchants m where owner_user_id in {IN_T}
  and not exists (select 1 from payments p where p.merchant_id = m.id);
delete from outbox_events where aggregate_id in (
  select id::text from dp union all select id::text from dt
  union all select id::text from de union all select id::text from dr);
delete from idempotency_keys k where user_id in {IN_T}
  and not exists (select 1 from transfers where idempotency_key_id = k.id)
  and not exists (select 1 from payments where idempotency_key_id = k.id)
  and not exists (select 1 from refunds where idempotency_key_id = k.id)
  and not exists (select 1 from exchanges where idempotency_key_id = k.id);
""",
    "notification_db": f"""
delete from notifications where recipient_user_id in {IN_T};
delete from support_messages where user_id in {IN_T};
delete from support_threads where user_id in {IN_T};
delete from announcement_reads where user_id in {IN_T};
delete from news_reads where user_id in {IN_T};
""",
    "fraud_db": f"delete from fraud_checks where user_id in {IN_T};\n",
    "webhook_db": f"""
delete from webhook_attempts where delivery_id in (
  select d.id from webhook_deliveries d join webhook_endpoints e on e.id = d.endpoint_id
  where e.owner_user_id in {IN_T});
delete from webhook_deliveries where endpoint_id in (
  select id from webhook_endpoints where owner_user_id in {IN_T});
delete from webhook_endpoints where owner_user_id in {IN_T};
""",
}


def kept_fingerprint(real: list[str]) -> str:
    """How much the real accounts have, to compare before and after."""
    mine = ",".join(f"'{user_id}'" for user_id in real)
    return "|".join([
        psql("payment_db", f"""
select count(*) from transfers where initiator_user_id in ({mine});
select count(*) from payments where initiator_user_id in ({mine});
select count(*) from exchanges where initiator_user_id in ({mine});
select count(*) from merchants where owner_user_id in ({mine}) or owner_user_id = '{SYSTEM_OWNER}';
""").replace("\n", ","),
        psql("notification_db", f"""
select count(*) from notifications where recipient_user_id in ({mine});
select count(*) from support_threads where user_id in ({mine});
""").replace("\n", ","),
    ])


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]
    if set(sys.argv[1:]) - {"--dry-run"}:
        sys.exit(__doc__)

    test_ids = [line for line in psql("identity_db", f"select id from users where {TEST}").split("\n") if line]
    real = psql("identity_db", f"""
select id||'  '||first_name||' '||last_name||'  <'||left(email, 3)||'…@'||split_part(email, '@', 2)||'>'
from users where not {TEST} order by created_at""").split("\n")
    real_ids = [line.split("  ")[0] for line in real if line]

    print(f"\nKept - {len(real_ids)} account(s) at real addresses, with everything they did:")
    for line in real:
        if line:
            print("   ", line.split("  ", 1)[1])
    if not test_ids:
        print("\nThere are no test accounts. Nothing to do.")
        return

    print(f"\nRemoved - {len(test_ids)} test account(s) at reserved addresses, and their:")
    for database, queries in DOOMED.items():
        for name, count in counts(database, queries, test_ids).items():
            print(f"    {count:>7}  {name}")
    print("\nNot touched: ledger_db (wallets and postings) and audit_db.")

    if dry_run:
        print("\nDry run: nothing was changed.")
        return
    if not real_ids:
        sys.exit("\nNo real account would be left. That can't be right; stopping.")
    if input('\nType "yes" to back up and delete: ').strip().lower() != "yes":
        print("Nothing was changed.")
        return

    backup = REPO.parent / f"db-backup-{datetime.now():%Y-%m-%d-%H%M%S}"
    backup.mkdir(mode=0o700)
    for database in DATABASES:
        target = backup / f"{database}.dump"
        with target.open("wb") as out:
            done = subprocess.run(
                ["docker", "compose", "exec", "-T", "postgres", "pg_dump", "-U", "postgres", "-Fc", database],
                stdout=out, cwd=REPO,
            )
        target.chmod(0o600)
        if done.returncode or target.stat().st_size == 0:
            sys.exit(f"Could not back up {database}. Nothing was changed.")
    print(f"Backed up to {backup}")

    before = kept_fingerprint(real_ids)
    for database, statements in DELETE.items():
        psql(database, "begin;\n" + loaded(test_ids) + statements + "commit;\n")
        print(f"  cleaned {database}")
    # Last: the accounts are what every other step was keyed on, so a
    # failure above leaves them in place and the script can be run again.
    psql("identity_db", f"begin;\ndelete from users where {TEST};\ncommit;\n")
    print("  cleaned identity_db")

    if kept_fingerprint(real_ids) != before:
        sys.exit(f"\nThe real accounts' data changed, which it must not. Restore from {backup}.")
    left = psql("identity_db", "select count(*) from users")
    print(f"\nDone. {left} account(s) left; the real accounts' data is exactly as it was.")


if __name__ == "__main__":
    main()
