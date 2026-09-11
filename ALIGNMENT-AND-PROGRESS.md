# Where We Are vs. The FMCG Hub Platform Vision

**A plain-English progress & alignment document**
Covers both the backend (`parcel-track`) and the mobile app (`parcel-track-mobile`), measured against the *FMCG Hub – Tech Team Briefing v4* PDF.

---

## How to read this document

There are two things in play:

1. **What we've built** — a backend API plus a mobile app. Together they run one complete workflow really well: a sea-freight order, from purchase order → container on a ship → arrival → payment → delivery, for our current reality (one Morocco supplier, soft drinks, mostly GBP/USD).
2. **What the PDF describes** — a much bigger "operating platform" for the whole business: many suppliers, many product categories, many currencies, customer/partner/investor portals, an email client inside the app, AI that reads documents, and live vessel tracking.

So the honest one-line summary is:

> **We have built a deep, high-quality *vertical slice*. The PDF describes a wide *platform*. Most of the hard engineering plumbing is done; most of the breadth is still ahead.**

This document sorts everything we've built into three buckets, in plain language:

- **Section 1 — Keep as-is** (built correctly, no change needed, and *why*)
- **Section 2 — Needs adjustment** (built, but subtly wrong or too narrow for the bigger platform, and *why*)
- **Section 3 — Missing** (not built yet — what each thing is and *what job it does in the app*)

A short **glossary** at the end explains every technical term in simple words. Terms that appear in the text are marked like *(see glossary)* the first time.

> **A note on the numbers.** Against the PDF's full vision there are ~96 distinct requirements. Roughly: **2 fully built, ~22 partially built, ~8 built-but-different, ~64 not started.** That sounds harsh, but it's measuring against the *finished platform* — not against "is the current app good." The current app is good. The platform is just big.

---

## Section 1 — Implementations that need NO adjustment

These are built correctly, are production-grade, and match the *intent* of the PDF. Changing them would be wasted effort ("churn"). Reasoning is given for each.

### Backend

**1.1 — Login, accounts & permissions (auth + roles).**
The full sign-in system works: inviting a user, logging in, staying logged in safely, locking out after too many bad attempts, and making sure each person only sees the data they're allowed to.
*Why keep it:* The PDF's core security ask is "multi-user with roles + partner light access." This is exactly that, and it's done to a high standard (passwords are properly hashed, sessions refresh safely, a known data-leak between bookings was already fixed). Everything else — portals, audit, approvals — builds on top of this, so it being solid is a big deal.

**1.2 — The container status is *calculated*, not *typed in* (derived state).**
A container's stage ("on water," "at port," "delivered," etc.) is worked out automatically from the real events that happened to it, rather than someone manually setting a status that can drift out of sync.
*Why keep it:* The PDF explicitly wants "a real state machine, not free status writes." Calculating the status from facts is the most reliable way to do that — it can't lie. This is the *right* architectural choice and rare to get right early. *(see glossary: derived state, state machine)*

**1.3 — File uploads go straight to cloud storage the safe way (presigned uploads to R2).**
When a document or photo is uploaded, the app gets a temporary, single-use link and sends the file *directly* to cloud storage — the server never has to handle the heavy file itself. The server then double-checks the file really arrived.
*Why keep it:* This is the modern, scalable, secure pattern, and it's fully done. Every future intake channel (email, WhatsApp, AI) can reuse it. *(see glossary: presigned upload)*

**1.4 — Talking to outside services without falling over (resilience layer).**
All calls to outside companies (vessel tracking, push notifications, and later XE rates / AI / WhatsApp) go through one shared piece of code that adds timeouts, automatic retries, and a "circuit breaker" that backs off when a service is down instead of hammering it.
*Why keep it:* Outside services *will* be flaky. This protects us, and it's the correct foundation for every integration the PDF lists. Reuse it; don't reinvent it per service. *(see glossary: circuit breaker)*

**1.5 — Vessel tracking is built (just switched off).**
Live ship positions and ETAs from VesselFinder, including arrival alerts, are written and tested. It's currently disabled only because we haven't plugged in the paid account credentials.
*Why keep it:* It's a flip-the-switch, not a build. Matches the PDF's "Vessel Tracker" screen.

### Mobile app (frontend)

**1.6 — The app's overall structure is excellent.**
Every screen talks to the real backend (the inventory found **zero fake/placeholder screens**). All network calls go through one well-organised layer, data is cached and refreshed sensibly, the navigation adapts to the user's role, login tokens are stored in the phone's secure vault, and there are **277 automated tests**.
*Why keep it:* This is the difference between a demo and a real app. It's clean, consistent, and easy to extend. The stack choices (Expo, React Native, TanStack Query, TypeScript) are all sound.

**1.7 — Push notifications work end-to-end.**
The app registers for push, receives notifications, and tapping one jumps you straight to the relevant booking. *(Note: actually *sending* push to a real installed app needs a production build setup — see 3.x.)*

**1.8 — Camera/photo/file upload from the phone works.**
You can snap a photo or pick a file and it uploads to cloud storage with a progress bar, using the safe direct-upload method (1.3).
*Why keep it:* This is exactly the PDF's "snap a doc on mobile" requirement, already working.

**1.9 — Money is handled carefully, and payments can't be double-counted.**
Money values are kept as exact text (never as rough decimals that can introduce rounding errors), and payment actions carry an "idempotency key" so a flaky connection that retries can't accidentally record the same payment twice.
*Why keep it:* These two habits prevent the worst class of bug in a finance app — wrong numbers. The PDF is all about money correctness; this is the right discipline. *(see glossary: idempotency, money-as-text)*

**1.10 — Forms, validation, and the visual design system.**
Data-entry forms validate input before sending; there's a consistent, branded look-and-feel built from reusable pieces.
*Why keep it:* Solid, finished, on-brand. No reason to touch it.

> **Bottom line for Section 1:** The engine, the wiring, and the app shell are done and done well. The remaining work is mostly *new rooms on top of a good foundation*, not *re-pouring the foundation*.

---

## Section 2 — Implementations that NEED adjustment

These exist and often *look* finished, but they're either subtly incorrect or too narrow for the full platform. Left alone, several would produce **wrong money numbers** or **legal/compliance gaps**. Each has the problem, why it matters, and the fix.

### Backend

**2.1 — The "audit trail" only covers a few actions, not all of them.**
*What's there:* An audit log *(see glossary)* exists, but it's only filled in by hand in about 5 places. Most actions — logins, customer payments, most record creation — leave **no trace**.
*Why it matters:* The PDF's #1 non-negotiable is "audit log on day 1, every write, no exceptions." Right now that promise isn't kept.
*The fix:* Route every change through one shared "record this" helper so coverage is automatic and complete, instead of remembered case-by-case. *(Medium effort.)*

**2.2 — The "who owes us money and how late" report is wrong in four ways.**
*What's there:* A receivables-aging report *(see glossary)*.
*Why it matters:* It (a) uses the wrong age brackets vs the PDF, (b) measures lateness from the wrong date (any small edit resets the clock), (c) shows the **full** invoice as outstanding even after partial payments have arrived, and (d) adds up different currencies as if they were the same. If the MD makes chasing/credit decisions off this, the numbers mislead.
*The fix:* Correct the brackets, anchor the clock to the real delivery/due date, subtract money already received, and make it currency-aware (this ties into the FX work in Section 3). *(Medium effort.)*

**2.3 — "Delivery type" is being confused with "sale type" — and sale type is the legally important one.**
*What's there:* A field that records *how* goods move (direct vs via-warehouse).
*Why it matters:* The PDF needs a *different* distinction: **ex-bond pickup vs delivered** — which determines who is the legal importer and underpins the whole UAE tax structure. These are two separate questions, and right now only the less-important one is captured.
*The fix:* Add an explicit "sale type: ex-bond / delivered" field per deal. *(Small effort, high importance.)*

**2.4 — Delivery status can jump to any value with no rules.**
*What's there:* Delivery progress can be set freely, unlike the carefully-guarded container status (1.2).
*Why it matters:* The PDF wants a proper "booked → signed → proof-of-delivery photo" sequence. Without rules, statuses can go out of order, and there's no place yet to capture the signature/photo.
*The fix:* Give deliveries the same guarded, ordered status flow that containers have, and add photo/signature capture. *(Medium effort.)*

**2.5 — Supplier payments are *recorded* but the *workflow* around them is thin.**
*What's there:* You can log a payment to the supplier.
*Why it matters:* The PDF wants a weekly batch the MD approves in one go, plus proper bank-reference fields, plus an email confirmation — none of which exist (and there's no email system at all yet, see 3.x).
*The fix:* Add the weekly bundle + approval step + the missing reference fields. *(Medium effort.)*

**2.6 — Payments and invoices can be accidentally duplicated on a bad connection.**
*What's there:* Only the supplier-payment action is protected against accidental retries; customer payments, invoices, and BL uploads are **not**.
*Why it matters:* A phone on a weak signal can silently create two payments. In a finance system that's serious.
*The fix:* Add the same "idempotency key" protection (already used elsewhere) to every money-related action. *(Small–medium effort.)* *(see glossary: idempotency)*

**2.7 — Database-level access control is switched off; all protection is in the app code.**
*What's there:* The deeper "row-level security" *(see glossary)* safety net is deliberately disabled; every rule lives in the application instead. Some list endpoints already over-share (e.g. broker/company lists are visible to any logged-in user).
*Why it matters:* It works today, but it means **one forgotten check = a data leak** — and that risk multiplies the moment we add outside-facing portals.
*The fix:* Tighten the over-sharing now, and treat scoping as a first-class design task before any portal ships. *(Ongoing discipline + small fixes.)*

**2.8 — Adding a new currency or port still needs a developer + a deployment.**
*What's there:* Currencies and ports are baked into the code as fixed lists. (For example, the currency **AED is missing entirely**.)
*Why it matters:* The PDF's mantra is "config over code — a new currency/port/partner is a data row, not a code change." Today it's the opposite.
*The fix:* Short-term, add AED. Longer-term, move these lists into editable data tables (this overlaps with Section 3's master-data work). *(see glossary: config over code)*

**2.9 — Uploaded documents are saved separately from the record they belong to, and the size/format limits don't match the spec.**
*What's there:* A document is saved in its own step; the size limit is 50MB and some formats (phone photos in HEIC, email files) are rejected.
*Why it matters:* For the future "AI reads the document and files it automatically" feature, the document and the data it produces must be saved together (so a failure can't leave one without the other). And the PDF expects 25MB plus email-file support.
*The fix:* Make the document + its data save as one atomic step *(see glossary: atomic)*, and align the limits/formats. *(Small now; important before AI intake.)*

### Mobile app (frontend)

**2.10 — The app only *shows* a currency; it doesn't *convert* between currencies.**
*What's there:* Money is displayed in whatever currency the record uses (GBP/USD); supplier currency is hard-coded to USD.
*Why it matters:* The PDF wants a live multi-currency view (a rates strip on every screen, everything also shown in USD). That's a whole feature that depends on backend work in Section 3.
*The fix:* Build the currency display once the backend FX foundation lands. (Note: the PDF assumes "every page," but we only have a mobile app today, not a web app — worth flagging.)

**2.11 — A couple of small backend shortcuts the app is working around.**
*What's there:* The app rebuilds container detail on the phone because there's no dedicated "get one container" endpoint, and there's no "who am I" endpoint.
*Why it matters:* Minor now, but they're known shortcuts to clean up.
*The fix:* Add the two small endpoints. *(Small effort — already on the deferred list.)*

> **Bottom line for Section 2:** Most of these are *correctness and completeness* fixes, not rewrites. The money-related ones (2.1, 2.2, 2.6) and the legal one (2.3) are the priorities — they're the items most likely to cause real-world problems if shipped as-is.

---

## Section 3 — Missing implementations (what they are & what they'd do)

Not built yet. For each, here's **what it is** and **the job it does in the platform**. These are grouped by theme and roughly ordered by how much else depends on them.

### A. The data foundation (build this first — everything else needs it)

**3.1 — Master data / "config over code" tables.**
*What it is:* Proper editable lists for products (SKUs *(see glossary)* with both our code and the supplier's code), suppliers (with their bank details, terms, currencies), product categories, pack sizes (cases/trays/units), and warehouses.
*Its job:* Lets the business add a new product, supplier, or warehouse by filling in a form — no developer, no deployment. **Almost everything else references this**, which is why it comes first. Today products are just free typed text and there's no supplier list at all.

**3.2 — Multi-entity tagging.**
*What it is:* A label on every transaction saying which legal company it belongs to (the UAE entity today; a future Morocco sister-company later).
*Its job:* Lets reports be filtered per company and rolled up for investors, and keeps the tax structure clean. None exists today — the platform silently assumes one company.

### B. How orders and money really work

**3.3 — Blanket purchase orders with weekly draw-downs.**
*What it is:* One big standing order (e.g. "60 containers over the quarter") that gets pulled down in weekly batches, each with its own payment date (the "Thursday rotation") and shipment.
*Its job:* Matches how the business *actually* buys. Today the system only models one-off orders.

**3.4 — One shipment split across many ships / one ship carrying many orders.**
*What it is:* A flexible link between cargo batches and vessels (the PDF's "all permutations").
*Its job:* Reflects reality when a supplier is short and cargo gets spread across several sailings. **Caution:** this conflicts with a simplifying assumption currently baked deep into the system, so it's a meaningful rework, not a quick add — worth confirming it's truly needed before doing it.

**3.5 — Multi-currency holdings + live exchange rates (XE) + locked historical rates.**
*What it is:* The ability to hold balances in several currencies, value everything in USD using **live** rates, but **freeze** the rate used on each past transaction so history never changes. Plus a cashflow ledger showing the live position.
*Its job:* This is the financial heart of the PDF. Holding native currencies and timing payments is how the business protects its ~40-50% margins. "Locked historical rate" *(see glossary)* is what keeps past reports honest. Currently there's no rate feed and no USD-equivalent on transactions.

**3.6 — Landed cost per container.**
*What it is:* Adding up all the costs a container incurs (goods in USD, freight in EUR, UK fees in GBP…) into one true USD cost.
*Its job:* Shows real cost and profit margin *before* the goods even ship. Doesn't exist yet.

**3.7 — Customer payment SOP engine + damages handling.**
*What it is:* A standard playbook for every payment situation (paid on time, part-paid, late, short by a few pounds, asked for a discount, claimed damages) that suggests the right action and logs the MD's decision.
*Its job:* Turns ad-hoc chasing into a consistent, auditable process. Today payments are recorded but there's no playbook.

**3.8 — Automatic bank matching (Wio webhook).**
*What it is:* The bank notifies the platform of incoming transfers, which get matched to the right invoice automatically.
*Its job:* Removes manual reconciliation. Not built; treat the bank connection as a security-sensitive piece.

### C. The legal / customs backbone

**3.9 — Incoterms, importer-of-record, and origin certificates per deal.**
*What it is:* Recording, per deal, the trade terms (FOB/DAP/DDP), the fact that the **customer** becomes the UK importer at clearance, the exact point title transfers, and the EUR1 origin certificate.
*Its job:* This *is* the tax-efficiency structure the whole business rests on. Right now the EUR1 certificate doesn't exist in the system and the importer-of-record concept isn't modelled — so it must be built deliberately, not faked with a checkbox.

**3.10 — A "required documents per stage" checklist.**
*What it is:* A rule that each lifecycle stage must have its specific paperwork (loading sheet, bill of lading, customs C88, proof-of-delivery, etc.).
*Its job:* Stops containers progressing with missing documents. The 13 document types the PDF lists aren't all represented yet.

### D. The "intelligence" layer

**3.11 — Document AI (read-and-file).**
*What it is:* You drop in a PDF/photo/email; AI figures out what it is, pulls out the key fields, and files them automatically — sending anything it's unsure about to the MD to approve.
*Its job:* The PDF calls this "the platform's brain." It removes manual typing. **Recommendation:** at launch, have a human confirm *everything*; only let it auto-file once it's proven accurate (auto-filing customs/payment numbers on a guess is risky). This is the single biggest unbuilt piece.

**3.12 — Email living inside the platform.**
*What it is:* Reading and replying to partner/customer emails from within the app, with drafts auto-linked to the relevant job, and a `docs@` address that ingests forwarded documents.
*Its job:* The PDF's "never open the inbox app again." **Recommendation:** don't build a full mail server — use a service that forwards incoming mail in and sends outgoing mail, which covers the real needs far more cheaply.

**3.13 — WhatsApp ingest & share.**
*What it is:* Partners send documents via WhatsApp; the phone can share into the app.
*Its job:* Meets partners where they already are. Not built (and the share feature needs the production build setup, 3.18).

### E. The outside-facing surfaces

**3.14 — Partner portal** (suppliers / freight forwarders / hauliers).
*Its job:* Lets partners upload their own documents, confirm stock, raise invoices, and report problems — instead of emailing us to type in by hand.

**3.15 — Customer + broker portal.**
*Its job:* Customers browse available stock (including cargo still on the water), choose pickup-vs-delivery, request to book stock (MD approves), and see their own history.

**3.16 — Investor portal.**
*Its job:* Read-only live business KPIs with a currency toggle, replacing monthly PDF reports.

> **Important for B–E:** all three portals are **new outside-the-company login surfaces**, each needing its own strict "you can only see your own data" rules — and they likely imply a **web** version, which we don't have today (we only have the mobile app). This is a strategic decision to confirm early.

### F. Operational screens & tooling

**3.17 — Rate cards, incidents, and the morning dashboard.**
- **Rate cards:** the agreed price list per partner, so the system knows the *expected* cost and can flag when an invoice doesn't match. *Its job:* margin protection + the "why is this charge here?" check.
- **Incidents / open items:** a log of anything that costs time or money, tied to a job, requiring a resolution note. *Its job:* nothing falls through the cracks.
- **Today's actions dashboard:** the MD's prioritised morning to-do list, assembled from everything above. *Its job:* the home screen of the whole platform.

**3.18 — Mobile shipping & polish: production build (EAS), biometric unlock, offline mode.**
*What it is:* The setup needed to ship a *real* installable app (not just the Expo preview) and send real push notifications, plus fingerprint/Face unlock and a cached offline mode.
*Its job:* Gets the app out of "preview" and onto people's phones. **This should be scheduled early** — real push and any app-store install are blocked until it's done, and the credentials involved have external lead times.

**3.19 — Other later integrations.**
Companies House (auto-fill UK customer details), HMRC customs (Destin8 — the code path is mostly built, just needs credentials), and accounting export (Sage/Xero). *Their job:* onboarding speed, customs filing, and finance reconciliation. All later-phase.

---

## Where you are vs. the plan — and how to get aligned

### Your honest position

You have built **one workflow, all the way through, to a high standard, on both the backend and the phone**: order → container → ship → arrival → payment → delivery, for a single-supplier, mostly-single-currency world. The *hardest engineering* (security, the status engine, safe uploads, resilient integrations, a clean app architecture, money-safety habits) is **behind you**. What's ahead is mostly **breadth** — more data types, more currencies, more surfaces (portals, email, AI) — built *on top of* that foundation.

A useful mental model:

| | The PDF platform | Where you are |
|---|---|---|
| **Depth of one workflow** | Required | **Done well** ✅ |
| **Master data (products/suppliers/warehouses)** | Core | Not started |
| **Multi-currency / live FX** | Core | Display-only, no conversion |
| **Legal/customs (ex-bond, importer-of-record, EUR1)** | Critical | Barely modelled |
| **Document AI** | "The brain" | Not started |
| **Email inside the app** | Required | Not started |
| **Portals (partner/customer/investor)** | Required | Not started (and likely need web) |
| **Mobile app quality** | Required | **Strong** ✅ (needs production-build setup) |

### The key uncertainty: where is the *other* effort?

You said the PDF platform is being built but you don't know what stage it's at. That's the most important thing to resolve, because it changes everything. Before more building, get answers to these:

1. **Is the PDF platform the *same* codebase as this one, or a separate build?** (Are "they" extending your backend, or starting fresh?)
2. **Has anyone built the master-data layer (3.1) or the multi-currency model (3.5)?** These are the shared foundations — if two efforts build them differently, the projects won't fit together.
3. **Who owns the portals, the email system, and the Document AI?** These are big, separable chunks — ideal to divide, dangerous to duplicate.
4. **Web vs mobile:** the PDF assumes a web operating portal + portals; you have a mobile app. Who's building the web side?
5. **What phase ordering is the other side using?** The PDF's roadmap and the realistic ordering differ (e.g. Document AI and portals are written as if early, but really depend on the data foundation first).

### Recommended path to align

1. **Agree the data foundation first (3.1 + 3.2 + 3.5).** It's the shared backbone; nail down *one* version of it before parallel work diverges.
2. **Lock the legal/customs model (3.9)** early — it's small to add but expensive to retrofit, and the business depends on it.
3. **Divide the big independent chunks** (Document AI, email, each portal) clearly between efforts so nothing is built twice.
4. **Front-load the mobile production-build setup (3.18)** so the app you've already built can actually ship and send push.
5. **Keep everything in Section 1 as the shared standard** — the auth, the status engine, the upload pipeline, the resilience layer, the money-safety habits. New work should plug into these, not around them.

---

## Glossary (plain-English)

- **Audit log / audit trail** — an unchangeable history of who changed what, when. Needed for trust and compliance.
- **Atomic** — an all-or-nothing save: either every part succeeds together, or nothing is saved. Prevents half-finished records.
- **Circuit breaker** — code that notices an outside service is failing and stops calling it for a while, instead of repeatedly trying and making things worse.
- **Config over code** — being able to change the system by editing data (filling a form) rather than changing the program and re-deploying it.
- **Derived state** — a status that's *calculated* from the underlying facts, rather than typed in by hand. It can't get out of sync because it's recomputed from the truth.
- **Idempotency** — a safety feature so that if the same request is sent twice (e.g. a phone retries on a bad signal), it only takes effect once. Critical for payments.
- **Importer of Record (IoR)** — the legal party responsible for importing goods (paying duty/VAT). The PDF's whole tax structure relies on the *customer* being the IoR, not us.
- **Incoterms** — standard international shipping terms (FOB, DAP, DDP…) that define who pays for and is responsible for goods at each stage.
- **Landed cost** — the *total* cost to get goods to their destination, including purchase price + freight + fees, across all currencies, expressed in one currency.
- **Locked / historical rate** — the exchange rate frozen at the moment of a transaction, so past records keep their original value even as live rates move.
- **Master data** — the core reference lists everything else points to: products, suppliers, warehouses, categories.
- **Money-as-text** — storing money as exact text rather than as decimal numbers that can pick up tiny rounding errors.
- **Presigned upload** — a temporary, single-use link that lets the app send a file directly to cloud storage, so the server never has to carry the heavy file itself.
- **Receivables aging** — a report grouping unpaid customer invoices by how overdue they are (e.g. current / 31-45 days / 46-90 / 90+).
- **Row-level security (RLS)** — a database safety net that restricts which rows each user can see, *underneath* the application. Currently switched off here; all protection is in app code instead.
- **SKU** — a unique code for a specific product (e.g. "Pepsi 330ml can"). The PDF wants two codes per product: ours and the supplier's.
- **State machine** — a set of allowed statuses plus rules for which can follow which, so something can't jump to an invalid or out-of-order state.

---

*Generated from a verified, file-by-file gap analysis of `parcel-track` (backend) and `parcel-track-mobile` (frontend) against FMCG Hub Tech Team Briefing v4.*
