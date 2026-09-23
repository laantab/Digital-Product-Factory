# Backup and recovery

Plain steps for getting the Factory back if something is lost. Written to be
followed by the person who runs it, not by a database administrator.

If you are reading this in a hurry, go straight to **"Something has gone
wrong"** at the bottom.

---

## What there is to lose

The Factory keeps customer work in three separate places. Losing any one of
them loses something different, and they are backed up in different ways.

| What | Where it lives | What is lost if it goes |
|---|---|---|
| **Projects database** | PostgreSQL on Render (`DATABASE_URL`). Locally, `projects.db`. | Every project: titles, manuscripts, approvals, the paid-call ledger, who owns what. This is the one that matters most. |
| **Finished files** | Cloudflare R2 bucket (`FACTORY_R2_BUCKET`). | Customers' PDFs and ZIPs. |
| **The code** | GitHub, `laantab/Digital-Product-Factory`. | Nothing, as long as GitHub is intact — this is already three copies (GitHub, your computer, each Render service). |

The local disk on a Render service is **not** in that list on purpose. Both
services are built fresh on every deploy and the builder starts each run with an
empty disk. Nothing that only exists on a service's disk survives, and nothing
is supposed to.

---

## What is NOT a backup

`/admin/backup-db` copies the database file next to itself, on the same disk,
on the same machine. It is useful before a risky bulk operation and useless in
any failure that takes the disk or the machine. Do not count it as a backup.

A copy on your own computer that you have never tested restoring is also not a
backup. Do the restore rehearsal below once, so you know it works.

---

## The three backups to have

### 1. The projects database — Render PostgreSQL

Render takes daily backups of a PostgreSQL instance automatically and keeps them
for a period that depends on the plan. To check yours:

1. Open the Render dashboard and click the PostgreSQL instance.
2. Open **Backups**. You should see a list with today's date at the top.
3. If the list is empty or the newest entry is old, that is a problem to fix
   today — nothing else in this document will help you without it.

To take one yourself before a risky change, use **Backups → Create backup**.

### 2. The finished files — Cloudflare R2

Turn on **object versioning** on the bucket in the Cloudflare dashboard
(R2 → your bucket → Settings). With versioning on, a file that is overwritten or
deleted can be recovered. Without it, a delete is final.

### 3. A copy you hold yourself

Once a month, download one database backup from Render and keep it somewhere
that is not Render and not the same computer you work on. This is the copy that
survives losing the account itself.

**To restore from that copy**, when Render is not available to restore it for
you: the file you downloaded is a PostgreSQL dump. Create an empty PostgreSQL
database wherever you are rebuilding — a new Render instance, or one on your own
machine — and load the dump into it:

```
pg_restore --clean --if-exists --no-owner --dbname "<connection string of the empty database>" "<the file you downloaded>"
```

Then point the Factory at it by setting `FACTORY_DB_BACKEND=postgres` and
`DATABASE_URL` to that connection string, exactly as in the rehearsal above. If
`pg_restore` says the file is not a dump it can read, it is a plain SQL file
instead — use `psql --dbname "<connection string>" --file "<the file>"`.

---

## Restore rehearsal — do this once, before you need it

Nobody's backup works until it has been restored once.

1. In Render, create a **new** PostgreSQL instance (not the live one).
2. Restore yesterday's backup into it.
3. Copy its connection string.
4. On your own computer, open a terminal in the Factory folder and run the
   Factory against it, in a throwaway window:

   ```
   set FACTORY_DB_BACKEND=postgres
   set DATABASE_URL=<the new instance's connection string>
   python app.py
   ```

5. Open the site it prints, sign in, and check that Saved Projects lists the
   books you expect.
6. Delete the temporary instance. It costs money for as long as it exists.

If step 5 shows your projects, your backups work. Write the date you did this
at the bottom of this file.

---

## Something has gone wrong

### "Projects have disappeared from Saved Projects"

Most likely they are hidden, not gone. This has a known cause: before v1.9.1,
a book whose title contained a word like "test", "QA" or "debug" was stamped as
a test record when it was created and hidden from its owner.

```
python scripts/review_hidden_books.py
```

That lists candidates and changes nothing. To bring one back:

```
python scripts/review_hidden_books.py --unhide <id>
```

Only restore a project if you recognise it as a real customer book.

### "The whole database is gone or corrupt"

1. **Stop deploying.** Do not push anything; a new deploy will not help and may
   make the picture harder to read.
2. Render dashboard → the PostgreSQL instance → **Backups** → pick the newest
   backup from **before** the problem started → **Restore**.
3. Render will tell you when the restore is done. The website reconnects on its
   own; if it does not, use **Manual Deploy → Deploy latest commit** on the web
   service.
4. Open the site and check Saved Projects.
5. Anything created between the backup and the failure is gone. Write down what
   that window was, so you can tell any affected customer honestly.

### "A customer's PDF or ZIP will not download"

The Factory already recovers a missing file from storage on its own. If it
still fails, the file is missing from R2 as well.

1. Cloudflare dashboard → R2 → the bucket → find the object.
2. If versioning is on and the object was overwritten or deleted, restore the
   previous version.
3. If it is genuinely gone, the book can be exported again from the project —
   the manuscript, cover and design all live in the database, not in the file.

### "The site answers 503 and says it is not accepting visitors"

That is the access-control guard, and it is working as intended: the live
service has neither `FACTORY_INVITE_CODE` nor `FACTORY_OPEN_ACCESS` set. Set one
of them in Render → Environment. A deploy is not needed; the service restarts on
an environment change.

**Prefer `FACTORY_INVITE_CODE`**, set to your beta code. Only use
`FACTORY_OPEN_ACCESS=1` if you mean the site to be open to anyone who finds the
address.

### "The site is down and I do not know why"

1. Render dashboard → the web service → **Logs**. Read the last twenty lines
   before the failure.
2. Render dashboard → the web service → **Events**. If the newest deploy failed,
   use **Rollback** on the last deploy that succeeded.
3. Rolling back is safe: it changes the code the site runs, not the database.
   Any book built while the newer code was live is still in the database and can
   be exported again once you are back up.

---

## Things to be careful with

- `/admin/delete-test-projects` deletes rows permanently. It now needs an admin
  account **and** `FACTORY_DELETE_TEST_PROJECTS_TOKEN` set on the host. Leave
  that variable unset except during the few minutes you are using it.
- Restoring a database backup replaces everything. Never restore into the live
  instance to "have a look" — restore into a new one.
- `.env` is not in the repository and never should be. If you lose it, the
  values are all in the Render dashboard; `.env.example` lists what they are.

---

Restore rehearsal last completed: _not yet — do this._
