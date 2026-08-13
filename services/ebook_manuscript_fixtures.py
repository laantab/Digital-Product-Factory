"""Deterministic professional-quality manuscript fixture for validator tests.

This is local verification copy for the event-photography chapter contract.
It is not a live customer book and must not be exported as a finished product.
"""
from __future__ import annotations


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def build_event_photo_strong_manuscript() -> str:
    """Return a contract-satisfying 10-chapter manuscript with tables and workflows."""
    ch1 = f"""## What This Business Actually Looks Like

Event photography with optional on-site prints is a service business. The product is not a camera body. The product is coverage, communication, file handling, and, when sold, a physical print guests can hold before they leave. Weddings, birthday parties, school functions, church celebrations, reunions, and community festivals all pay for that service, but they do not pay for the same workflow.

A wedding usually needs a planning meeting, a family-group list, tighter timing, and a higher expectation of completeness. A birthday party needs candids, a cake moment, and a flexible end time. A school banquet needs volume, a defined start and stop, and organizer approval. A church event needs respectful movement and a program-aware shooting plan. A reunion needs large groups, changing light, and fast guest flow. A community festival may need a booth, a queue, and a print station that does not block the aisle.

On-site prints change the offer because guests leave with an object, not only a promise of a gallery. That can raise perceived value at parties, reunions, and school nights. It also adds a second operation: media, power, table space, queue control, and a pickup rule. If the host thinks “unlimited instant prints” and you planned one 4×6 with a cap, the night fails even if the photographs are strong.

This guide will not claim guaranteed earnings, guaranteed booking volume, or a guaranteed startup timeline. Published averages are signals. Printer specifications are used only where manufacturer documentation supports them. Keepsakes such as mugs and shirts are possible, but they are a separate production system.

{_table(
    ["Event type", "Planning load", "Typical coverage focus", "On-site print fit"],
    [
        ["Wedding (limited coverage)", "High: meeting, family list, timeline", "Ceremony, couples, groups", "Optional add-on at cocktail hour only"],
        ["Birthday / family party", "Medium: shot list, end time", "Candids, groups, cake", "Strong if host funds a capped print run"],
        ["School banquet or dance", "Medium-high: organizer rules", "Portraits, program, volume", "Strong with a defined booth and queue"],
        ["Church celebration", "Medium: program order, respect", "Speakers, congregation, groups", "Use only with leadership approval"],
        ["Reunion", "Medium: group boards, flow", "Class groups, candids", "Strong; guests expect a takeaway"],
        ["Community festival", "High: booth, power, staffing", "Candid + booth portraits", "Requires print-station staffing"],
    ],
)}

**Example scenario (planning only):** A school PTA asks for two hours of portraits plus 4×6 prints. The photographer quotes coverage and a capped print add-on as separate lines, names the print size, and writes that leftover prints are not an open gift shop. That is the difference between a photography job and a booth job.

What this guide will do: walk from first booking to a tested print station. What it will not do: invent Lonnie Brown clients, quote live street prices as facts, or treat mugs as if they were 4×6 dye-sub prints.
"""

    ch2 = f"""## Startup Reality Check: Budget, Legal Basics, and Insurance

Most beginners budget for a camera and forget the operating system: registration, insurance, a portfolio, a website, invoices, and a way to track deposits. Event work is public-facing. Venues ask for proof of insurance. If you cannot produce a certificate of insurance (COI), the booking can die after the contract is signed.

Research notes used for this manuscript cite lean photography startups in a planning range of about $2,000 to $5,000 and more event-focused or wedding-oriented setups in a planning range of about $10,000 to $25,000 (startcosts.com; photographylaunchpad.com; zenfolio.com/blog/startup-costs-photography-business). Those figures are planning ranges, not guarantees. What you already own, whether you buy used, and whether you rent specialty glass will move the number.

A lean launch might be one reliable body, one workhorse zoom, one flash, a computer that can cull, editing software, registration, liability insurance, and a simple site. An event-focused launch adds a backup body, a second zoom role, more lighting, and the cash to float a dye-sub printer and media if prints are part of the offer. Printing is not “a little extra.” It is another capital and insurance conversation.

{_table(
    ["Line item", "Lean planning range (hypothetical)", "Event-focused planning range (hypothetical)", "Notes"],
    [
        ["Camera body + backup path", "$800–$2,000", "$2,500–$6,000", "Used bodies allowed; test before event one"],
        ["Lenses (wide/medium/tele roles)", "$400–$1,500", "$2,000–$6,000", "Rent 70-200 until demand is real"],
        ["Flash / lighting", "$120–$400", "$400–$1,500", "Stands need cable and insurance thought"],
        ["Computer + software", "$400–$1,200", "$1,200–$2,500", "Subscriptions are recurring overhead"],
        ["Insurance + registration", "$300–$800", "$500–$1,500", "COI for venues is an operating requirement"],
        ["Website / portfolio / bookkeeping", "$0–$400", "$200–$800", "Invoices and deposits must be trackable"],
        ["Print station (if offered)", "$0 until tested", "$1,000–$4,000+", "Verify current supplier quotes"],
    ],
)}

**Insurance and COI checklist**
- General liability appropriate for guest-facing event work
- Equipment coverage for bodies, glass, and printers you actually carry
- Ability to issue a COI naming a venue or school as additional interest when asked
- Confirm whether an assistant or second shooter is covered
- Confirm whether a print table and stanchions change the venue’s vendor rules
- Store policy numbers and agent contact in the event folder, not only in email
- Do not treat a homeowner policy as event liability without a professional review

Registration and bookkeeping are not optional upgrades. Separate business money from personal money. Track invoices, deposits, travel, software, media, and gear. Without that, every price is a guess and tax season becomes archaeology. A one-page site that states the event types you serve, the cities you cover, and how to inquire is enough to start. Elaborate branding can wait until event one is on the calendar.

This chapter does not provide legal, tax, or insurance advice. Use a local professional for entity choice, contract review, and policy selection. The table above is a hypothetical planning worksheet, not a current market-price list.
"""

    ch3 = f"""## Core Camera Kit, Printing Equipment, and Backup Gear

Build the kit around roles, not shopping lists. Event work happens once. A dead battery or a full card is not a creative choice. The research notes treat a camera body, lenses, flash or lighting, a computer, and editing software as the core, and they treat a backup body, extra batteries, and extra memory cards as operational priorities.

Think in coverage roles. Wide coverage handles room, dance floor, and large groups. Medium coverage (a 24-70mm f/2.8 is a common recommendation in the research) handles most storytelling. Telephoto coverage (a 70-200mm f/2.8 is the common event recommendation) handles ceremonies, speakers, and distance without walking into the aisle. You do not need those exact lenses on day one, but you do need those roles covered by something you can operate in mixed light.

Lighting starts with a speedlight you can use on-camera without blinding a sanctuary. Larger strobes wait until you have a second pair of hands and a venue that allows stands. A computer that can ingest, back up, and cull is part of the kit. If the laptop cannot finish a two-hour job overnight, your turnaround promise is fiction.

Printing equipment is a second station, not a lens. At kit level you need a dedicated table plan, a laptop or ingest device, manufacturer-supported printer software, spare media, and a cable-safe power path. Model-level comparison of DS-RX1HS, DS620A, and QW410 belongs in Chapter 8 and must use manufacturer documentation. Do not skip backup thinking for the print laptop.

{_table(
    ["Role", "Starter kit (planning)", "Event kit (planning)", "Print-station add-on"],
    [
        ["Body", "One reliable body", "Primary + backup body", "Not a substitute for a camera backup"],
        ["Medium zoom", "24-70mm or equivalent zoom", "24-70mm f/2.8 or equivalent", "—"],
        ["Telephoto", "Rent 70-200mm for ceremonies", "Owned or dedicated rental 70-200mm f/2.8", "—"],
        ["Flash", "One speedlight + spare batteries", "Speedlight + fallback unit", "—"],
        ["Computer", "Laptop that can cull", "Laptop + ingest backup drive", "Print laptop or same laptop with a queue rule"],
        ["Printer", "Do not buy until a test event", "Only after a dry run", "Dye-sub photo printer + media + spare kit"],
    ],
)}

**Event backup kit checklist**
- Primary camera body
- Backup camera body, or a written rental plan that arrives before call time
- Main lens plus an alternate that can finish the job
- More charged batteries than the event hours
- More memory cards than you expect to fill, labeled in/out
- Backup flash or a no-flash exposure plan
- Card reader and a backup drive for ingest
- Print-station spare media and a documented stop quantity if prints are sold

Used gear and rentals are cost-control tools, not a shopping personality. Treat the next block as a hypothetical planning example, not current market prices.

**Hypothetical planning example: Buy vs. Rent vs. Used**

Use all three choices before you spend. These dollar figures are labeled planning numbers, not live asking prices.

{_table(
    ["Choice", "When it is the planning lean", "Hypothetical planning number", "Decision criteria"],
    [
        ["Buy", "Daily-driver coverage you will use at every paid event (24-70mm role)", "$1,800 planning allowance", "Buy when the item is on every shot list and a rental would repeat for the next three booked dates"],
        ["Rent", "Specialty telephoto for one ceremony", "$120 hypothetical weekend rental", "Rent the 70-200mm when you need it for a single date and do not yet have a second paid ceremony on the calendar"],
        ["Used", "Backup batteries, second body, spare flash", "$250 planning allowance", "Buy used when the item is backup-critical, has a service history you can inspect, and a rental would not already be in the bag if the primary fails"],
    ],
)}

Decision criteria: if you would rent the same 70-200mm three times this season, the planning lean is buy (new or used). If you need it once, rent. If it must already be in the bag at call time, used is the planning lean. Do not invent or quote current market prices. The research notes say used purchases or rentals can reduce startup cost substantially; treat any percentage as one source’s claim, not a law. Stage upgrades around actual demand.
"""

    ch4 = f"""## Finding Clients and Turning Inquiries into Signed Bookings

Packages do not find clients. People find clients. Beginners get first paid events from people who already gather: PTAs, church coordinators, reunion chairs, venue coordinators, and friends who host parties. A clear one-page site and a short inquiry reply matter more than a new lighting modifier.

Lead sources to work in parallel: ask past portrait clients whether they have an event this year; offer a defined school-night package to one PTA; introduce yourself to two venues with insurance already in hand; post one sample gallery from a practice event with written permission; keep a weekly follow-up list. Do not wait for a marketplace algorithm to invent a wedding.

Every inquiry should move through the same sequence. If you skip steps, you get a maybe and a date collision.

**Inquiry-to-signed-booking workflow**
1. Reply within one business day with event-type questions: date, venue, hours, guest count, indoor/outdoor, and whether prints are requested.
2. Send two package options with hours, deliverables, turnaround, and travel radius. Keep print add-ons on a separate line.
3. Hold the date only after a written hold policy (for example, 48 hours) or a deposit.
4. Send the contract with hours, deliverables, payment schedule, cancellation, and print rules if any.
5. Collect the deposit and signed contract before the planning call.
6. Confirm the remaining balance due date and the shot-list / timeline request.
7. Log the booking in the same spreadsheet you use for insurance COI requests.
8. Send a one-page confirmation: arrival window, parking, on-site contact, and print-station yes/no.

**Example scenario (planning only):** A reunion chair emails on Monday. Tuesday you send questions and two options. Wednesday they choose the four-hour package without prints. Thursday the contract and deposit link go out. Friday the signed contract and deposit return. The date is then actually booked. An inquiry that never reaches step 5 is not a booking.

Follow-up is part of the workflow. If there is no reply after the options email, send one reminder three days later and one final note a week later. Then close the file. Chasing forever trains people to treat you as an unpaid hold.

Do not hide print complexity inside a vague “full experience” sentence. If prints are not offered yet, say so. If they are offered, the contract must say size, cap, who pays, and when pickup ends. That is how an inquiry becomes a signed booking instead of an argument at 9 p.m.
"""

    ch5 = f"""## Packages and Pricing Scenarios That Protect Your Margin

A package clients can understand names hours, deliverables, a planning meeting if any, turnaround, and what is not included. A birthday package and a limited wedding package should not share a vague “event coverage” label. Print add-ons sit beside the core offer; they do not swallow it.

Published averages in the research notes are signals, not your price list. Beginner photographers are often described around $50 to $150 per hour. Beginner event or small wedding coverage is commonly cited around $500 to $1,500. Some sources describe many professional event photographers around $100 to $250 hourly (aftershoot.com/blog/photography-pricing-guide). Your city, demand, and speed will disagree with those bands. Use them to sanity-check, then build from a cost stack.

The cost stack is planning, communication, travel, setup, coverage, editing, delivery, software, storage, insurance, taxes, gear recovery, and profit. If you price only the hours you hold a camera, the rest of the job is a donation.

{_table(
    ["Package (planning example)", "Hours on site", "Deliverables", "Hypothetical price", "Notes"],
    [
        ["Community / birthday", "2", "Highlight gallery, 75+ edited images, 10-day turnaround", "$450", "No prints unless add-on"],
        ["School / church program", "3", "Program coverage + group board, 14-day turnaround", "$700", "COI required"],
        ["Limited wedding coverage", "4", "Planning call, timeline, 200+ images, 21-day turnaround", "$1,200", "Prints quoted separately"],
        ["Print add-on (host-funded)", "n/a", "One size, capped quantity, pickup before teardown", "See margin table", "Not blended into core fee"],
    ],
)}

**Hypothetical dollar-margin scenario only — not a current market-price claim**

{_table(
    ["Cost stack item", "Small community event", "Limited wedding", "Event + print add-on"],
    [
        ["Labor hours (plan/travel/shoot/edit)", "6 hrs", "12 hrs", "15 hrs"],
        ["Labor at a $60 planning rate", "$360", "$720", "$900"],
        ["Travel / parking / meals", "$25", "$60", "$60"],
        ["Insurance / software share", "$20", "$40", "$55"],
        ["Media / print labor (hypothetical)", "$0", "$0", "$90"],
        ["Gear recovery share", "$15", "$30", "$45"],
        ["Taxes set-aside (planning 20%)", "$84", "$170", "$230"],
        ["Hypothetical price charged", "$450", "$1,200", "$1,450"],
        ["Planning remainder after costs", "$−74 to refine", "$180", "$70"],
    ],
)}

The small-community row is the lesson: a $450 fee can lose money if six hours of real work sit underneath two hours of coverage. Raise the fee, shorten the edit promise, or decline the job. Do not “make it up on prints” unless the print add-on has its own media, labor, and teardown math.

Gear recovery belongs in the stack. Bodies, flashes, drives, and printers wear out. If prices never contribute to replacement, the business is slowly liquidating equipment. Label every dollar table in this chapter as a hypothetical planning scenario and verify current supplier and local market numbers before you publish a real price list.
"""

    ch6 = f"""## Planning the Event: Contracts, Timelines, Space, Power, and Staffing

Event day is downstream of paperwork. The contract should already have defined hours, deliverables, payment, cancellation, and print rules. The planning pass then turns that contract into a timeline, a floor plan, and a staffing list.

Lead questions that still belong here, even after booking: indoor/outdoor, sunset, where you may stand, flash restrictions, load-in door, parking, on-site contact, whether a second shooter is allowed, and whether a print table is allowed. School and church events often need a named organizer and a written stop time. Reunions need a group-board order. Weddings need a family-group list with a handler who is not you.

{_table(
    ["When", "Planning action", "Owner", "Done?"],
    [
        ["21 days out", "COI sent if the venue asked; remaining balance date confirmed", "Photographer", ""],
        ["14 days out", "Shot list and family/group order requested in writing", "Client / organizer", ""],
        ["7 days out", "Timeline drafted: arrival, first shot, key moments, print open/close, teardown", "Photographer", ""],
        ["5 days out", "Power and table location confirmed; cable path sketched", "Photographer + venue", ""],
        ["3 days out", "Staff roles assigned; backup body and media packed on paper", "Photographer", ""],
        ["1 day out", "Batteries charged; cards formatted; print dry-run if offering prints", "Photographer", ""],
        ["Call time", "Walk the floor, tape cable corners, confirm on-site contact number", "All staff", ""],
    ],
)}

**Space, power, cable-safety, and staffing checklist**
- Table location that does not block exits, food lines, or the dance floor
- Dedicated circuit or a tested outlet; no daisy-chained power strips across walkways
- Cable covers or taped corners on every guest path
- Printer and laptop on a stable surface away from drinks
- One person who can stay at the print station if prints are offered
- One person whose only job is coverage if guest count or ceremony timing is tight
- Guest-facing signage: what is for sale or included, size, and pickup end time
- A written stop quantity so the queue cannot outrun media
- Rain or indoor fallback if any part of the station is outdoors
- Teardown owner and a 15-minute buffer before venue overtime

**Pre-event planning workflow**
1. Re-read the contract hours and print clause.
2. Build the timeline from the organizer’s program, not from hope.
3. Place the print station on a sketch with power and queue direction.
4. Assign names to coverage, assist, and print roles.
5. Send the timeline and station sketch to the organizer for one confirmation.
6. Pack to the backup checklist in Chapter 3.

Setting print expectations before event day is cheaper than explaining them in a line. Clients should know size, cap, host-funded vs guest-pay, and that pickup ends when the station tears down. If those sentences are missing, do not take the printer.
"""

    ch7 = f"""## Event-Day Operations: From Photograph to Guest Delivery

Run the day in three phases: before, during, and after. Before is confirmation and a floor walk. During is coverage discipline plus, if sold, a print queue that does not steal the primary shooter. After is ingest, backup, and a clean teardown. Guest delivery of prints happens before teardown, not in the parking lot.

**Event-day run-of-show workflow**
1. Before doors: confirm contact, walk exits, test the outlet, tape cables, format cards, and shoot a test frame.
2. If printing: print one test image, confirm color/finish, and post the pickup rule.
3. First hour: wide establishing frames, then medium storytelling; do not camp on one lens.
4. Key program moments: telephoto for speakers, vows, or awards; flash only where allowed.
5. Mid-event: rotate cards before they fill; bag used cards separately from empty cards.
6. Print window: assistant runs queue, payment if any, and pickup; primary stays on coverage.
7. Last 20 minutes: final groups, station close, leftover-print rule, and a last backup if time allows.
8. After last guest pickup: teardown in reverse order, then ingest in the car or a quiet room before driving tired.

Wide, medium, and telephoto roles still matter on the day, but the new work is timing. A run-of-show on paper beats a vague intention to “get everything.” Flash discipline means matching the room: no-flash during a solemn program, careful bounce when the room is a cave, never firing into a choir loft because the LCD looked dull.

**File-backup procedure checklist**
- Label cards A/B and in/out before call time
- Change cards on a schedule, not only when the camera yells
- Immediately bag used cards; never format a used card on site
- Ingest to laptop and a second drive before long driving
- Verify file counts match the camera’s shot count
- Keep the second drive physically separate from the laptop bag
- Do not start a heavy edit until the backup verify step is checked
- After delivery, keep the backup until the client confirms the gallery

Staffing is role-based. One person cannot honestly run a busy print queue and a first dance at the same time. If the budget cannot staff both, drop prints for that event. Guest flow needs a single line, a pickup corner that does not cross the dance floor, and a posted wait expectation. After the event, files are not done until they are backed up. Prints are not done until leftovers are counted and the station is off the floor.
"""

    ch8 = f"""## Dye-Sublimation Printing: Setup, Queue, Ordering, Payment, and Pickup

Dye-sublimation photo printers are used for fast take-home prints because the process is built around photographic output with a protective overlay. DNP states that dye-sub prints are sealed into the paper and protected against UV light, fingerprints, and water (https://www.dnpphoto.com/about). That is why they appear in event booths. It is not a reason to invent prices or to treat every DNP page as a business plan.

Use only source-supported specifications for the three approved models, and verify firmware, media, and current supplier pricing before you buy or quote. Equipment and media prices vary.

{_table(
    ["Documented point", "DS-RX1HS", "DS620A", "QW410"],
    [
        ["Source", "dnpphoto.com/products/printers/rx1hs", "dnpphoto.com/products/printers/ds620a", "dnpphoto.com/products/printers/qw410"],
        ["Speed (documented)", "4×6 in 12.4 seconds; up to 290 4×6/hour", "4×6 in under 9 seconds; 5×7 ~15 seconds", "Event/mobile class; verify current speed listing"],
        ["Sizes (documented)", "2×6 strips, 4×6, 5×7, 6×6, 6×8 depending on media", "4×6, 5×7, 6×8 media listed", "4×3 through 4.5×8 including 4×4"],
        ["Media capacity (documented)", "700 4×6 or 350 6×8 per media set", "400 4×6 per roll (800/case); 230 5×7; 200 6×8", "Verify current media listing; IDW520 notes 150 images/roll on 4.5×6"],
        ["Physical / power notes", "USB iSerial multi-printer; Windows Status App", "10.8” W × 14.4” D × 6.7” H; standby <0.5 W", "Under 13 lbs; 8” W × 7.75” H × 9.5” D; mobility/battery-oriented"],
        ["Finish / other", "300×300 or 300×600 dpi; glossy/matte", "Advanced Exchange warranty listed", "Smallest/lightest DNP dye-sub photo printer as marketed"],
    ],
)}

DNP Hot Folder Print is documented as a Windows utility for automated photo printing and can distribute jobs across two or more compatible connected printers in one-to-many mode. Compatible families listed by DNP include DS620A, QW410, DS-RX1HS, and others (https://www.dnpphoto.com/hot-folder-print). Status monitoring on DS-RX1HS is documented via a Windows Status App showing media type, prints remaining, and printer status. Verify the exact combination you own; do not assume every accessory ships in the box.

**Setup → queue → ordering → payment → pickup workflow**
1. Place the printer on a stable table with taped power and a guest-safe cable path.
2. Load documented media; print one test image; confirm finish (glossy/matte) against the host agreement.
3. Connect the ingest laptop; enable Hot Folder Print only if that software is installed and documented for your model.
4. Define the order method: host-funded tally sheet or guest-pay SKU list with one size.
5. Queue files by dropping selected images into the hot folder or the manufacturer-supported print path.
6. If two printers are connected and the software supports one-to-many, split the queue; otherwise do not invent a custom spooler.
7. Take payment only if the contract says guests pay; otherwise tally against the host cap.
8. Hand the print at a pickup corner; do not make guests reach over cables.
9. Stop at the contracted quantity; do not keep printing because the line looks sad.
10. Log spoilage, remaining media, and teardown time before leaving.

**Hypothetical media-planning scenario only:** Host wants 150 4×6 prints. You plan 150 + 10% spoilage = 165. Against a DS-RX1HS media set documented at 700 4×6, one set is enough capacity, but you still price labor, setup, breakdown, and a spare set because a jam on Saturday night is not a theory. Do not publish a per-print retail number in this book as if it were a current supplier quote.

Multi-printer distribution and status monitoring matter because a single jammed unit can freeze a reunion line. If you cannot see prints remaining, you cannot keep the cap honest. Verify those features from current DNP documentation for the exact hardware and software you will stand up.
"""

    ch9 = f"""## Keepsakes Beyond Photo Prints: Separate Equipment and Workflow

A 4×6 dye-sub print and a mug are not the same product. Fast photo printing may fit the Chapter 8 station. Mugs, buttons, shirts, plates, and similar items usually need separate equipment, different materials, different cycle times, different staffing, and different safety planning. The printer-manufacturer sources used for DS-RX1HS, DS620A, and QW410 do not verify those keepsake systems. This chapter will not invent press temperatures, platen times, or shirt-ink recipes.

That does not mean keepsakes are impossible. It means they are a second line of business. If one person is already covering a first dance, they cannot also babysit a heat press at the same table. Heat, pressure, and public access require a barrier, a trained operator, and a venue that agreed in writing.

**Keepsake go / no-go, staffing, and safety checklist**
- Go only if a named operator who is not the primary shooter is staffed
- Go only if the venue approved the extra footprint, power, and heat/press equipment in writing
- Go only after a full dry run of the exact item, not a YouTube thumbnail
- No-go if the only “spec” you have is a guess about cycle time
- No-go if guests would stand inside a heat or pressure zone
- No-go if media, blanks, or inks were not counted for the guest cap
- Staffing: one coverage role, one keepsake operator, one person for money/queue if guest-pay
- Safety: cord covers, no drinks on the press table, cooling space, first-aid location known
- Safety: keep children from touching equipment; use a table lip or barrier
- After-event: leftover blanks counted; hot equipment fully cooled before load-out
- Pricing: separate line item; never bundled as “prints and stuff”
- Claims: do not quote dye-sub photo-printer pages as mug-press documentation

If the answer is no-go, sell the photo-print add-on or sell nothing extra. A clean 4×6 line beats a scorch mark on a tablecloth. If the answer is go, write a separate mini-contract: item list, production time, pickup rule, and a statement that production specs come from that system’s manufacturer, not from this book.

Test keepsakes at a low-stakes practice, not at a wedding. Until that test exists, the honest offer is photography plus optional photo prints.
"""

    ch10 = f"""## Common Mistakes and Your 30-Day First Paid Event Plan

The expensive mistakes are predictable. Underpricing by counting only event hours. Launching without backup batteries, cards, or a body plan. Selling “coverage” with no hours or image count. Promising live prints without a size, cap, power plan, or operator. Buying a fourth lens before a first inquiry. Skipping insurance until a venue asks at noon on Friday. Treating bookkeeping as a winter project.

Overbuying feels like progress because gear is tangible. A package, an inquiry script, and a COI are less photogenic and more useful. Weak print planning is its own failure mode: a memorable booth that cannot explain who pays will be remembered for the wrong reason.

**30-day first-paid-event checklist**

**Days 1–7**
- Choose one or two event types from Chapter 1, not all six
- Inventory bodies, lenses, flash, computer, and insurance gaps
- Write a lean budget using Chapter 2 ranges as planning numbers only
- Call an insurance professional about liability, equipment, and COI
- Confirm business registration steps for your state without using this book as legal advice

**Days 8–14**
- Publish a one-page site with event types, area, and an inquiry email
- Put ten practice images in a gallery you have permission to show
- Open a bookkeeping method that can record deposits
- Draft two packages with hours, deliverables, and turnaround
- Write the eight-step inquiry workflow from Chapter 4 on one card

**Days 15–21**
- Build a hypothetical dollar stack from Chapter 5 and set a floor price
- Place contract and deposit tools in the same folder as the COI request template
- Pack the backup kit and label cards
- Decide prints: not offered / simple host-funded add-on / delayed until a dry run
- If prints are offered, complete one Chapter 8 dry run with test media

**Days 22–30**
- Rehearse the Chapter 7 run-of-show in an empty room
- Time ingest and backup on a sample card
- Ask five real people for introductions to one PTA, church, venue, or reunion chair
- Send three inquiries using the workflow; log them
- After the first paid event, record actual hours, actual wait times, and actual questions — then adjust. Do not invent a case study.

After event one, refinement is a notebook, not a myth. If the print line blocked the cake, move the table. If six hours of editing hid under a two-hour fee, change the fee. If nobody asked for mugs, do not buy a press. That is how a beginner kit becomes a stable event business without fictional testimonials.
"""

    back = """**Disclaimer** This guide is for practical planning and general educational use. It does not provide legal, tax, insurance, or financial advice. Use qualified local professionals for business registration, contract review, insurance selection, and tax decisions. Any pricing, margin, or media examples in this manuscript are hypothetical planning scenarios only, not current market-price claims or income promises. Printer specifications are summarized from manufacturer materials available at the time of research and must be verified against current documentation and suppliers before purchase or quoting.

**Sources**
- https://startcosts.com/photography
- https://aftershoot.com/blog/photography-pricing-guide
- https://www.photographylaunchpad.com/photography-business-startup-costs
- https://www.format.com/online-portfolio-website/event-photography/guide
- https://zenfolio.com/blog/startup-costs-photography-business
- https://www.dnpphoto.com/products/printers/rx1hs
- https://www.dnpphoto.com/products/printers/ds620a
- https://www.dnpphoto.com/products/printers/qw410
- https://www.dnpphoto.com/hot-folder-print
- https://www.dnpphoto.com/about
"""

    return "\n\n".join(
        [
            "# From First Booking to On-Site Prints",
            "*Lonnie Brown*",
            "*A Practical Guide to Equipment, Pricing, Client Workflow, Event-Day Operations, and Dye-Sublimation Printing*",
            ch1,
            ch2,
            ch3,
            ch4,
            ch5,
            ch6,
            ch7,
            ch8,
            ch9,
            ch10,
            back,
        ]
    )
