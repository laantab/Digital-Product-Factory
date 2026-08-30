"""Deterministic content banks for the Faith Planner and Budget Planner.

Everything here is written material, not a prompt. The Editor-in-Chief blocks
placeholder text, prompt leakage, and blank pages, so a planner cannot be a
stack of empty ruled boxes with a title on top: each section carries real
instructional copy that earns its page.

Two deliberate constraints:

  * Scripture appears as *references* (book, chapter, verse) and as original
    reflection prompts. No modern-translation verse text is reproduced, so
    nothing here depends on a copyright licence.
  * Budget material is educational structure — categories, arithmetic, and
    method explanations. It is not personalised financial advice, and the
    front matter says so in the customer's own copy.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Shared
# --------------------------------------------------------------------------- #
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


# --------------------------------------------------------------------------- #
# Faith Planner
# --------------------------------------------------------------------------- #
FAITH_HOW_TO_USE = [
    (
        "Start with one page, not the whole book",
        "This planner is built to be used unevenly. Some weeks you will fill "
        "every line; some weeks you will write two words in the gratitude box "
        "and close it again. Both count. The daily pages are undated on "
        "purpose so a gap never turns into a stack of blank spreads that make "
        "you want to quit.",
    ),
    (
        "Read first, write second",
        "Each weekly spread opens with a reading reference rather than a "
        "printed passage. Read it in whichever translation you already trust, "
        "then come back and answer the three questions. Writing before reading "
        "produces opinions; writing after reading produces notes you will "
        "actually return to.",
    ),
    (
        "Use the three-question method",
        "Every daily page asks the same three things: what does the passage "
        "say, what does it mean, and what will you do about it before "
        "tomorrow. The third question is the one that changes anything. Keep "
        "the answer small enough to finish today.",
    ),
    (
        "Keep the prayer log honest",
        "Record the date you started praying for something and the date "
        "something changed — including the times the answer was no or the "
        "situation simply ended. A prayer log that only records wins stops "
        "being a record and becomes a highlight reel.",
    ),
    (
        "Review monthly, not daily",
        "At the end of each month, read back through your own entries before "
        "you plan the next one. The monthly review page exists so that you are "
        "reacting to evidence rather than to how the last twenty-four hours "
        "happened to feel.",
    ),
]

# A 52-entry reading plan. References only — book and chapter ranges, which are
# structural facts about the text, not reproduced content.
FAITH_READING_PLAN = [
    ("Beginnings", "Genesis 1-3", "Creation, calling, and the first fracture"),
    ("Beginnings", "Genesis 12; 15; 17", "A promise made to one family"),
    ("Beginnings", "Genesis 22; 28", "Testing, and a promise repeated"),
    ("Beginnings", "Genesis 37; 39-41", "Betrayal, patience, and reversal"),
    ("Deliverance", "Exodus 1-3", "Oppression and an unexpected commission"),
    ("Deliverance", "Exodus 12-14", "Rescue at the edge of the sea"),
    ("Deliverance", "Exodus 19-20", "Covenant and the shape of a good life"),
    ("Deliverance", "Exodus 32-34", "Failure, intercession, and mercy"),
    ("Wilderness", "Numbers 13-14", "Fear as a decision-making method"),
    ("Wilderness", "Deuteronomy 6-8", "Remembering on purpose"),
    ("Wilderness", "Deuteronomy 30", "Choosing, plainly stated"),
    ("Wilderness", "Joshua 1; 24", "Courage and a household's decision"),
    ("Songs", "Psalms 1; 8; 19", "Delight, smallness, and order"),
    ("Songs", "Psalms 22-24", "Abandonment, shepherding, and welcome"),
    ("Songs", "Psalms 42-46", "Thirst, honesty, and refuge"),
    ("Songs", "Psalms 51; 32", "Confession without cosmetics"),
    ("Songs", "Psalms 73; 77", "Envy, doubt, and the long view"),
    ("Songs", "Psalms 90; 91", "Brevity of life, shelter in it"),
    ("Songs", "Psalms 103; 104", "Mercy, and a world full of it"),
    ("Songs", "Psalms 119:1-88", "A love letter to instruction"),
    ("Songs", "Psalms 139; 145", "Being fully known"),
    ("Wisdom", "Proverbs 1-4", "Wisdom as a skill you practise"),
    ("Wisdom", "Proverbs 10-13", "Speech, work, and consequence"),
    ("Wisdom", "Proverbs 15-17", "Anger, humility, and correction"),
    ("Wisdom", "Proverbs 30-31", "Limits, and a life of substance"),
    ("Wisdom", "Ecclesiastes 1-3", "Meaning under the sun"),
    ("Wisdom", "Ecclesiastes 11-12", "Sowing without guarantees"),
    ("Prophets", "Isaiah 6; 40", "Holiness, and comfort for the tired"),
    ("Prophets", "Isaiah 43; 53", "Belonging, and a suffering servant"),
    ("Prophets", "Isaiah 55; 58", "Invitation, and the fast God wants"),
    ("Prophets", "Jeremiah 1; 29", "Calling, and settling into exile"),
    ("Prophets", "Micah 6; Habakkuk 3", "What is required; joy without harvest"),
    ("Gospel", "Matthew 5-7", "The sermon that reorders everything"),
    ("Gospel", "Matthew 13; 18", "Parables and the arithmetic of forgiveness"),
    ("Gospel", "Mark 1-4", "Urgency, authority, and soil"),
    ("Gospel", "Mark 8-10", "Cost, ambition, and service"),
    ("Gospel", "Luke 10; 15", "Neighbour, and three things lost"),
    ("Gospel", "Luke 22-24", "Table, trial, and the third day"),
    ("Gospel", "John 1; 3", "Word made flesh; being born again"),
    ("Gospel", "John 13-15", "Basin, towel, vine, and friendship"),
    ("Gospel", "John 17; 20-21", "Prayer for us; breakfast on a beach"),
    ("Church", "Acts 1-2", "Wind, fire, and a new community"),
    ("Church", "Acts 9; 16", "Interruption and open doors"),
    ("Letters", "Romans 5-8", "Peace, struggle, and no condemnation"),
    ("Letters", "Romans 12", "Ordinary life as worship"),
    ("Letters", "1 Corinthians 12-13", "Gifts, and the more excellent way"),
    ("Letters", "Galatians 5; Ephesians 4", "Freedom, fruit, and getting along"),
    ("Letters", "Philippians 1-4", "Joy written from a prison cell"),
    ("Letters", "Colossians 3; 1 Thessalonians 5", "New clothes; steady habits"),
    ("Letters", "Hebrews 11-12", "Faith as a long line of witnesses"),
    ("Letters", "James 1-3", "Doing, not only hearing"),
    ("Letters", "1 John 3-4; Revelation 21-22", "Love, and everything made new"),
]

FAITH_DAILY_PROMPTS = (
    "What does this passage actually say?",
    "What does it mean — for the first readers, and for me?",
    "What will I do about it before tomorrow?",
)

FAITH_PRAYER_CATEGORIES = (
    "Family and household",
    "Friends and neighbours",
    "Church and leaders",
    "Work and provision",
    "Health and healing",
    "The overwhelmed and grieving",
    "Those far from faith",
    "My own character",
)

FAITH_HABITS = (
    "Read the day's passage",
    "Pray for someone by name",
    "Practise gratitude",
    "Serve one person",
    "Rest without guilt",
    "Give (time or money)",
    "Confess honestly",
)

FAITH_REFLECTION_PROMPTS = (
    "Where did I see grace this month, including in something I did not choose?",
    "Which prayer changed me rather than the circumstance?",
    "What did I say I would do and not do? What made it hard?",
    "Who needs something from me next month that I can actually give?",
    "What am I carrying that I was never asked to carry?",
)

FAITH_SERMON_FIELDS = (
    "Date", "Speaker", "Passage", "Main point",
)

FAITH_MEMORY_METHOD = [
    (
        "Choose one verse for the whole month",
        "One verse a month, held properly, beats fifty verses skimmed and "
        "forgotten. Pick a single verse on the first of the month, write the "
        "reference on the memory card page in this planner, and do not add a "
        "second verse until the month is over. Twelve verses a year that you "
        "can still say in December is a genuinely good year.",
    ),
    (
        "Write the verse out by hand three times",
        "Handwriting drags you through every word at the pace of a slow "
        "reader, which is exactly the pace memory works at. Write the verse "
        "out on day one, again on day three, and again on day seven. Do not "
        "copy it in one sitting; the gaps between the three attempts are what "
        "moves the verse from the page into your head.",
    ),
    (
        "Say it out loud before you check it",
        "Recall is the practice. Re-reading the card is not, however much "
        "more comfortable it feels. Try to say the verse from memory first, "
        "get it wrong, and only then look at the card to correct the part you "
        "actually missed. The struggle is the mechanism, not a sign that the "
        "method is failing.",
    ),
    (
        "Attach the verse to something you already do",
        "Say your verse while the kettle boils, at the same traffic light "
        "every morning, or in the thirty seconds before you open your laptop. "
        "A verse attached to an existing habit survives a chaotic week. A "
        "verse attached only to good intentions does not survive a Tuesday.",
    ),
    (
        "Expect to lose it, and plan the recovery",
        "Most people forget a verse somewhere around week three, decide they "
        "are bad at memorising, and stop. You are not bad at it; three weeks "
        "is simply when the first serious decay happens. Keep the old cards "
        "in the planner and cycle one previous verse back through each week "
        "alongside the current one.",
    ),
]

FAITH_CONTEXT_METHOD = [
    (
        "Ask who wrote this passage, and to whom",
        "Almost every confusing passage becomes clearer once you know who was "
        "speaking and who was listening. A letter written to a specific "
        "church under pressure reads differently from a song written for "
        "public worship, and a promise made to one named person is not "
        "automatically a promise made to you. Write the answer in the margin "
        "of your daily page before you write anything else.",
    ),
    (
        "Ask what kind of writing it is",
        "The Bible is a library, not a single book, and its shelves do not "
        "all work the same way. Poetry exaggerates on purpose. Narrative "
        "describes what happened without necessarily approving of it. Law was "
        "given to a particular nation at a particular moment. Proverbs are "
        "reliable patterns, not cast-iron guarantees. Reading a proverb as a "
        "promise is one of the fastest routes to disappointment with God.",
    ),
    (
        "Read the paragraphs on either side",
        "A verse lifted out of its paragraph can be made to say almost "
        "anything, which is why so many memorable verses are quoted to mean "
        "the opposite of what they meant. Before you decide what a verse "
        "means, read the ten verses before it and the ten after. This costs "
        "two minutes and prevents most misreadings.",
    ),
    (
        "Ask what it meant then before you ask what it means now",
        "The passage did not begin its life addressed to you, and it does not "
        "become useful by pretending otherwise. Work out what it meant to its "
        "first readers, then ask what carries across to your situation. That "
        "order protects you from making the text a mirror that only ever "
        "shows you your own opinions back.",
    ),
    (
        "Let the hard passages stay hard",
        "Some passages will not resolve on a Tuesday morning with a coffee "
        "and this planner. Write the question down on the weekly spread "
        "rather than inventing an answer to make the discomfort stop. A "
        "recorded honest question is worth more to your faith a year from now "
        "than a tidy answer you did not believe when you wrote it.",
    ),
]

FAITH_PRAYER_METHOD = [
    (
        "Pray when you do not feel like praying",
        "Feeling is a poor scheduler. If prayer only happens when you are "
        "moved to pray, it will happen during crises and holidays and almost "
        "never in the ordinary weeks that make up most of a life. Keep the "
        "appointment first and let the feeling arrive late, or not at all.",
    ),
    (
        "Use a structure when words run out",
        "On the days you have nothing to say, borrow a shape: thank, confess, "
        "ask, listen. Two sentences in each is a complete prayer. Structure is "
        "not a lack of sincerity; it is the handrail that gets you through the "
        "days when sincerity is exactly what you cannot summon.",
    ),
    (
        "Pray for people by name, and write the names down",
        "Praying for 'everyone who is struggling' costs nothing and changes "
        "no one, including you. Praying for four named people, week after "
        "week, changes how you treat them when you next meet. The prayer log "
        "in this planner exists to keep the names in front of you.",
    ),
    (
        "Say the honest thing, including the angry thing",
        "A third of the Psalms are complaints, and several of them are furious. "
        "Editing your prayers into something polite produces a relationship "
        "with a version of yourself you have invented for the occasion. Say "
        "the actual thing. The tradition has room for it.",
    ),
    (
        "Keep it short enough to repeat tomorrow",
        "Five honest minutes every day beats forty minutes once a fortnight "
        "followed by three weeks of guilt. Set a length you could keep during "
        "your busiest week of the year, and treat anything beyond that as a "
        "bonus rather than the standard you are failing to meet.",
    ),
]


# --------------------------------------------------------------------------- #
# Budget Planner
# --------------------------------------------------------------------------- #
BUDGET_DISCLAIMER = (
    "This planner is an educational worksheet system. It does not provide "
    "personalised financial, tax, investment, or legal advice, and it does not "
    "know your circumstances. For decisions with real consequences — debt "
    "settlement, retirement accounts, tax treatment, insolvency — speak with a "
    "qualified professional who can see your full picture."
)

BUDGET_HOW_TO_USE = [
    (
        "Fill the snapshot before you plan anything",
        "The Financial Snapshot page asks for balances you may not enjoy "
        "writing down. Do it anyway, once, in pencil. Every later page is "
        "arithmetic performed on those numbers, and arithmetic performed on a "
        "guess produces a plan you will quietly abandon in week three.",
    ),
    (
        "Budget the month you are actually in",
        "Each Monthly Budget spread is planned before the month starts and "
        "reconciled after it ends. Planned and Actual sit side by side on "
        "purpose: the gap between them is the only number that teaches you "
        "anything.",
    ),
    (
        "Give every pound or dollar a job",
        "Income minus every planned category should equal zero — not because "
        "you spend everything, but because savings and debt payments are "
        "categories too. Money without an assigned job gets spent by default.",
    ),
    (
        "Track for two weeks, then stop guessing",
        "Use the Expense Log honestly for fourteen days before you decide what "
        "your variable categories should be. Most people are wrong about "
        "groceries and eating out by thirty percent or more in their own "
        "favour.",
    ),
    (
        "Expect to revise, not to fail",
        "A category you overspend three months running is not a discipline "
        "problem, it is a mis-set number. Move it up, move something else "
        "down, and keep the total honest.",
    ),
]

BUDGET_METHODS = [
    (
        "The 50 / 30 / 20 budget",
        "This budget splits take-home pay three ways: half to needs, thirty "
        "percent to wants, twenty percent to savings and extra debt payments. "
        "It is the best starting shape when your income is steady and you want "
        "a rule of thumb rather than a system to maintain. Its weakness is "
        "that the 'needs' bucket quietly expands to swallow whatever you let "
        "it, until a budget that looked disciplined on paper is really just "
        "your existing spending with better labels on it.",
    ),
    (
        "The zero-based budget",
        "Here every unit of income is assigned to a budget category before the "
        "month starts, until nothing is left unassigned — savings and debt "
        "payments included. This is the budget to use when money keeps "
        "disappearing and you genuinely cannot say where it went. Its weakness "
        "is maintenance: it needs a real sit-down at the start of each month, "
        "and if you skip two months in a row the budget stops describing your "
        "actual life.",
    ),
    (
        "Pay yourself first",
        "Savings and debt payments leave the account automatically on payday, "
        "and you budget only what is left. This works well when your income is "
        "reliable but your willpower is not, because the important transfers "
        "happen before you get a vote. Its weakness is that overspending hides "
        "inside the leftover pot, so the budget looks healthy right up until "
        "the account is empty on the twenty-third.",
    ),
    (
        "The envelope budget",
        "Each variable budget category — groceries, eating out, impulse buys — "
        "gets a fixed amount in cash or in a separate digital pot, and spending "
        "in that category stops when the envelope is empty. This is the most "
        "effective method for the categories that leak. Its weakness is "
        "friction, which is also precisely the point: the awkwardness at the "
        "till is the budget doing its job.",
    ),
    (
        "Which budget should you actually pick",
        "If you have never budgeted before, start with 50 / 30 / 20 for two "
        "months to learn the shape of your own spending, then move to a "
        "zero-based budget once you know your real numbers. Add envelopes only "
        "for the two or three categories that keep breaking. Running every "
        "category as an envelope from day one is the most common reason people "
        "abandon budgeting inside a month.",
    ),
]

BUDGET_EMERGENCY_FUND = [
    (
        "Start with one month of essential costs, not six",
        "The standard advice to save six months of expenses is correct and "
        "almost useless as a starting point, because the number is so large "
        "that most people never begin. Add up only your essential monthly "
        "costs — housing, utilities, food, transport, minimum debt payments — "
        "and make that single month your first savings target. It is the "
        "difference between a bad week and a new credit card balance.",
    ),
    (
        "Keep the emergency fund boring and slightly inconvenient",
        "This money should sit in a separate savings account you can reach "
        "within a day or two, not in your current account where it will be "
        "spent by accident, and not in investments where its value moves. "
        "Boring and accessible beats clever every time for an emergency fund; "
        "you are buying certainty, not returns.",
    ),
    (
        "Decide in advance what counts as an emergency",
        "Write the definition down while nothing is going wrong, because your "
        "judgement is worst in the moment you need it. A broken boiler, a car "
        "you need for work, an unexpected trip for a funeral: yes. A sale, a "
        "holiday, a phone upgrade: no. An emergency fund with a vague "
        "definition is a savings account that empties every few months.",
    ),
    (
        "Refill it before you resume anything else",
        "When you spend from the fund, refilling it becomes the first line of "
        "the next budget, ahead of extra debt payments and ahead of any new "
        "savings goal. Use the sinking-fund pages to route the money back. A "
        "fund that is used but never refilled is a one-time rescue, not a "
        "system.",
    ),
]

BUDGET_CUTTING = [
    (
        "Cut the recurring costs before the small pleasures",
        "One renegotiated insurance renewal, one cancelled subscription you "
        "forgot about, and one switched utility tariff can save more in a year "
        "than eliminating every coffee you buy — and unlike the coffee, you "
        "only have to do it once. Start with the money that leaves your "
        "account automatically, because that is the money you are least aware "
        "of spending.",
    ),
    (
        "Reduce a category by a quarter, not to zero",
        "Cutting a spending category to zero is a decision you will reverse "
        "within six weeks, and the reversal usually takes the whole budget "
        "with it. Cut it by twenty-five percent instead, live there for two "
        "months, and cut again only if it was genuinely comfortable. Slow "
        "reductions survive; dramatic ones become evidence that budgeting does "
        "not work for you.",
    ),
    (
        "Attack the three biggest numbers first",
        "Housing, transport, and food are the largest lines in almost every "
        "household budget, and a five percent change in any of them usually "
        "beats a fifty percent change further down the list. These are also "
        "the hardest to move, which is exactly why they get skipped in favour "
        "of satisfying but trivial cuts.",
    ),
    (
        "Keep one category you refuse to cut",
        "Name one thing you spend money on that makes your life noticeably "
        "better and protect it explicitly in the budget. A plan with nothing "
        "enjoyable in it is a plan you are secretly waiting to fail, and the "
        "failure usually costs more than the category you were protecting.",
    ),
]

BUDGET_INCOME_ROWS = (
    "Primary take-home pay",
    "Second job / side income",
    "Partner's take-home pay",
    "Benefits / support payments",
    "Interest and dividends",
    "Refunds and rebates",
    "Other income",
)

BUDGET_FIXED_ROWS = (
    "Rent / mortgage",
    "Council tax / property tax",
    "Utilities - electricity & gas",
    "Water",
    "Internet and mobile",
    "Insurance - home / contents",
    "Insurance - vehicle",
    "Insurance - health / life",
    "Loan repayment",
    "Credit card minimum",
    "Childcare / school fees",
    "Transport - season ticket / fuel",
    "Subscriptions",
    "Savings transfer",
)

BUDGET_VARIABLE_ROWS = (
    "Groceries",
    "Eating out and takeaway",
    "Household and cleaning",
    "Clothing",
    "Personal care",
    "Medical and prescriptions",
    "Pets",
    "Fuel / travel top-up",
    "Gifts",
    "Entertainment",
    "Hobbies",
    "Charity and giving",
    "Miscellaneous",
)

BUDGET_SINKING_FUNDS = (
    "Car service and repairs",
    "Home maintenance",
    "Christmas and birthdays",
    "Holiday / travel",
    "Annual insurance renewal",
    "Tax bill",
    "Replacement tech",
    "Emergency fund top-up",
)

BUDGET_DEBT_METHODS = [
    (
        "Snowball — smallest balance first",
        "Order debts from smallest balance to largest, pay minimums on all of "
        "them, and put every spare unit against the smallest. You clear whole "
        "debts quickly, which is motivating. You pay slightly more interest "
        "overall.",
    ),
    (
        "Avalanche — highest rate first",
        "Same minimums, but the spare money goes to the highest interest rate. "
        "Mathematically cheapest. It can feel like nothing is happening for "
        "months, which is why people abandon it.",
    ),
    (
        "Choosing between them",
        "If you have abandoned a payoff plan before, use snowball — the "
        "finished lines are the feature. If you have never abandoned one and "
        "the rate gap is wide, use avalanche. The method you keep doing beats "
        "the method that is theoretically optimal.",
    ),
]

BUDGET_REVIEW_PROMPTS = (
    "Which category was furthest from plan, and was the number wrong or the month unusual?",
    "What did I buy that I cannot now remember or justify?",
    "Which single change would have had the biggest effect this month?",
    "What is coming next month that this month did not have?",
    "What went right that I should keep doing without thinking about it?",
)

BUDGET_HABITS = (
    "Logged today's spending",
    "No unplanned purchase",
    "Checked account balance",
    "Packed lunch / cooked at home",
    "Moved money to savings",
    "Reviewed a subscription",
    "Talked money with partner",
)

BUDGET_SNAPSHOT_ASSETS = (
    "Current account",
    "Savings account",
    "Emergency fund",
    "Cash on hand",
    "Pension / retirement",
    "Investments",
    "Vehicle value",
    "Property value",
)

BUDGET_SNAPSHOT_DEBTS = (
    "Mortgage balance",
    "Vehicle loan",
    "Credit card 1",
    "Credit card 2",
    "Personal loan",
    "Student loan",
    "Overdraft",
    "Family / informal",
)
