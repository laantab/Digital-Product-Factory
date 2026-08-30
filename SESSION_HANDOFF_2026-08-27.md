# Session Handoff — 2026-08-27 (supersedes 2026-08-26)

**Start a new session with:** "Read flask_app/SESSION_HANDOFF_2026-08-27.md and continue."

---

## PICK UP HERE — domain registered, nameservers just switched, waiting on propagation

Continuing the 2026-08-26 thread (Lemon Squeezy live-payment activation paused
at the "website location" field because the Factory had no stable public
URL). This session the owner registered a real domain and got it about
halfway wired to a stable Cloudflare Tunnel. **Nothing on the app/repo side
changed yet** — this was all done through the Namecheap and Cloudflare
dashboards in the browser, walked through interactively with the owner (who
had never used Cloudflare before).

### What's done

1. **Domain registered**: `digitalproductfactorypro.com`, via **Namecheap**
   (confirmed active, expires Aug 27 2027, WithheldForPrivacy protection on).
2. **Cloudflare account created** (free plan), domain added as a site there.
   Hit a transient "Authentication error" on first attempt adding the site —
   resolved itself on retry (likely an extension/session hiccup, not
   diagnosed further since it cleared).
3. **DNS records page**: intentionally left empty — no records added, since
   the tunnel (next step) will create what's needed. Ignore Cloudflare's
   "visitors cannot reach www..." recommendation nagging, not relevant yet.
4. **Nameservers switched at Namecheap**: Domain List → Manage →
   NAMESERVERS → changed from "Namecheap BasicDNS" to **Custom DNS**, entered:
   ```
   lilith.ns.cloudflare.com
   thomas.ns.cloudflare.com
   ```
   Saved (owner confirmed clicking the checkmark). **These are this domain's
   specific two nameservers — Cloudflare assigns them per-domain, don't
   assume they're reusable for anything else.**
5. Cloudflare's domain overview was showing **"Pending setup" / "Waiting for
   your registrar to propagate your new nameservers"** as of the save. Typical
   propagation is 1–2 hours, can take up to 24h. Cloudflare emails when done
   and the status flips to Active.

### Next steps, once the owner confirms Cloudflare shows the domain as Active

1. Confirm `cloudflared` is still at `C:\Program Files (x86)\cloudflared\cloudflared.exe`
   (already installed, v2026.8.2 as of 2026-08-27, not yet logged into any
   Cloudflare account — no `~/.cloudflared/cert.pem` exists yet).
2. Run `cloudflared tunnel login` — opens a browser, **owner must click
   Authorize** themselves (don't do this step without them present).
3. Create a named tunnel (e.g. `cloudflared tunnel create factory`), which
   writes a credentials JSON.
4. Write a tunnel config (`config.yml`) with ingress rules pointing the
   chosen hostname (root domain or a subdomain like
   `app.digitalproductfactorypro.com` — ask the owner which they want) at
   `http://localhost:5055` (the owner's `_run_factory_5055.py`, per
   [SESSION_HANDOFF_2026-08-25.md](SESSION_HANDOFF_2026-08-25.md) — do not
   collide with it, same rule as before).
5. `cloudflared tunnel route dns factory <hostname>` to create the DNS
   record automatically.
6. Run the tunnel (foreground first to confirm, then decide with the owner
   whether to run it as a background process or install as a Windows
   service so it survives reboots — quick tunnels never had this problem
   since they were started ad hoc each session, but a named tunnel is meant
   to be always-on).
7. Update `.env`: `FACTORY_PUBLIC_URL=https://<chosen-hostname>`.
8. Update the Lemon Squeezy webhook URL to match (via API — see
   `services/billing/providers.py`, no helper script yet) and confirm with
   the same verification snippet from
   [SESSION_HANDOFF_2026-08-25.md](SESSION_HANDOFF_2026-08-25.md) (`_lemon_request('GET', '/webhooks?filter[store_id]=397800')`).
9. Restart the app.
10. **Then** the owner goes back to Lemon Squeezy's business-details form and
    finishes it with a real, stable website URL.

No code was touched this session — this is purely infrastructure/account
setup done in the browser. Everything from
[SESSION_HANDOFF_2026-08-25.md](SESSION_HANDOFF_2026-08-25.md) (billing
status, planners, repo state 1 commit ahead of origin/main, standing open
items) remains accurate and unchanged.
