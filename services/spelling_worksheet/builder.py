"""Spelling Worksheet Builder — 100% local spelling practice sheet generator.

No OpenAI, no chat_json, no Tavily. All word generation is from built-in
topic banks and grade-level word banks. The only external dependency removed
is the AI word-generation path.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Grade-level word banks (used when no topic bank matches)
# ---------------------------------------------------------------------------
_GRADE_BANKS: dict[str, list[str]] = {
    "1": ["cat", "dog", "sun", "run", "hop", "map", "red", "blue", "big", "little",
          "play", "jump", "milk", "fish", "book", "ball", "tree", "hand", "foot", "nose"],
    "2": ["fish", "bird", "cake", "walk", "look", "hand", "play", "jump", "read", "write",
          "house", "green", "happy", "friend", "water", "light", "night", "sleep", "dream", "smile"],
    "3": ["animal", "garden", "teacher", "pencil", "window", "basket", "summer", "winter",
          "forest", "planet", "feather", "market", "silver", "river", "flower", "castle",
          "desert", "island", "ocean", "valley"],
    "4": ["harbor", "palace", "temple", "meadow", "canyon", "glacier", "horizon", "storm",
          "weather", "climate", "ancient", "modern", "culture", "citizen", "country",
          "captain", "soldier", "journey", "mystery", "kingdom"],
    "5": ["explain", "compare", "fraction", "decimal", "climate", "energy", "habitat", "history",
          "culture", "journey", "pattern", "measure", "system", "project", "science",
          "citizen", "volcano", "economy", "balance", "compass"],
    "6": ["paragraph", "conclusion", "paragraph", "estimate", "accurate", "practice", "benefit",
          "evidence", "research", "strategy", "organize", "describe", "community", "continent",
          "population", "government", "traditional", "remarkable", "independent", "environment"],
    "7": ["analyze", "evidence", "conclusion", "strategy", "accurate", "process", "evaluate",
          "structure", "academic", "resource", "complex", "function", "variable", "specific",
          "solution", "principle", "theory", "concept", "method", "approach"],
    "8": ["hypothesis", "phenomenon", "interpretation", "methodology", "investigate", "significance",
          "perspective", "criterion", "sufficient", "demonstrate", "substantiate", "comprehensive",
          "analytical", "implication", "substantive", "formulate", "synthesis", "evaluation"],
    "9": ["articulate", "comprehensive", "substantial", "hypothesis", "interpretation",
          "methodology", "significant", "perspective", "criterion", "phenomenon",
          "synthesis", "analytical", "implication", "sufficient", "demonstrate",
          "substantiate", "substantive", "formulate", "evaluation", "principle"],
    "10": ["substantiate", "substantive", "comprehensive", "methodology", "interpretation",
           "hypothesis", "phenomenon", "criterion", "analytical", "perspective",
           "significance", "articulate", "synthesis", "implication", "sufficient",
           "demonstrate", "formulate", "principle", "comprehensive", "methodology"],
    "11": ["substantiate", "methodology", "interpretation", "hypothesis", "phenomenon",
           "criterion", "analytical", "perspective", "significance", "comprehensive",
           "substantive", "principle", "synthesis", "implication", "sufficient",
           "demonstrate", "articulate", "formulate", "evaluation", "theoretical"],
    "12": ["substantiate", "methodology", "interpretation", "hypothesis", "phenomenon",
           "criterion", "analytical", "perspective", "significance", "comprehensive",
           "substantive", "principle", "synthesis", "implication", "sufficient",
           "demonstrate", "articulate", "formulate", "evaluation", "theoretical"],
}


def _get_grade_bank(grade: str) -> list[str]:
    """Return the word bank for a grade level. Gracefully falls back to grade 3."""
    g = str(grade or "3").strip()
    # Strip "Grade " prefix if present
    g = re.sub(r"^Grade\s*", "", g, flags=re.IGNORECASE).strip()
    # Handle "3-4" or "3,4" range
    g = re.split(r"[-,]", g)[0].strip()
    return _GRADE_BANKS.get(g, _GRADE_BANKS.get("3", []))


# ---------------------------------------------------------------------------
# Topic word banks (matched by whole-token or common phrase)
# ---------------------------------------------------------------------------
_TOPIC_BANKS: dict[str, list[str]] = {
    "farm animals": [
        "chicken", "rooster", "cow", "horse", "sheep", "goat", "pig", "duck",
        "turkey", "donkey", "rabbit", "barn", "pasture", "farmer", "tractor",
        "hen", "pony", "goose", "lamb", "calf",
    ],
    "animals": [
        "elephant", "giraffe", "tiger", "lion", "zebra", "monkey", "turtle", "dolphin",
        "rabbit", "fox", "bear", "whale", "eagle", "frog", "snake", "penguin",
        "owl", "shark", "kangaroo", "leopard",
    ],
    "school": [
        "pencil", "paper", "teacher", "student", "classroom", "lesson", "notebook",
        "library", "recess", "homework", "desk", "marker", "ruler", "folder", "eraser",
        "chalkboard", "backpack", "textbook", "compass", "globe",
    ],
    "weather": [
        "cloudy", "sunny", "rainy", "thunder", "lightning", "storm", "windy", "snowflake",
        "rainbow", "forecast", "temperature", "drizzle", "hurricane", "climate", "breeze",
        "frost", "tornado", "humidity", "atmosphere", "precipitation",
    ],
    "technology": [
        "keyboard", "mouse", "monitor", "screen", "printer", "laptop", "desktop", "speaker",
        "cable", "router", "webcam", "processor", "memory", "motherboard", "harddrive",
        "software", "hardware", "wireless", "bluetooth", "broadband",
    ],
    "computer parts": [
        "keyboard", "mouse", "monitor", "screen", "printer", "laptop", "desktop", "speaker",
        "cable", "router", "webcam", "processor", "memory", "motherboard", "harddrive",
        "software", "hardware", "wireless", "bluetooth", "broadband",
    ],
    "plants": [
        "flower", "stem", "leaf", "root", "seed", "soil", "garden", "branch", "petal",
        "sprout", "trunk", "fruit", "pollen", "sunlight", "water", "forest", "tree",
        "vine", "blossom", "harvest",
    ],
    "food": [
        "apple", "banana", "carrot", "sandwich", "cheese", "potato", "tomato", "orange",
        "cereal", "chicken", "rice", "bread", "pasta", "salad", "yogurt", "butter",
        "celery", "broccoli", "lettuce",
    ],
    "sports": [
        "soccer", "baseball", "tennis", "football", "basketball", "swimming", "running",
        "skating", "volleyball", "coach", "player", "helmet", "whistle", "trophy",
        "practice", "stadium", "referee", "champion", "tournament", "fitness",
    ],
    "transportation": [
        "bicycle", "airplane", "train", "subway", "scooter", "tractor", "truck", "boat",
        "rocket", "bus", "taxi", "highway", "driver", "engine", "station", "airport",
        "passenger", "platform", "conductor", "cargo",
    ],
    "ocean": [
        "whale", "shark", "dolphin", "coral", "tide", "wave", "shell", "anchor", "sailor",
        "captain", "voyage", "reef", "current", "lighthouse", "harbor", "krill", "octopus",
        "seahorse", "starfish", "jellyfish",
    ],
    "space": [
        "planet", "rocket", "astronaut", "galaxy", "comet", "orbit", "asteroid", "nebula",
        "satellite", "telescope", "meteor", "cosmic", "gravity", "starlight", "spaceship",
        "crater", "sunlight", "atmosphere", "voyage", "eclipse",
    ],
}


def _match_topic_bank(theme: str) -> list[str] | None:
    """Return the matching topic bank, or None if no match.

    SPELLING WORKSHEET RELEASE (2026-09-09): the substring scan used to
    return the FIRST key (in dict-insertion order) that appeared as a
    substring of the theme, rather than the most specific one -- e.g.
    "Ocean Animals" contains both "animals" (a generic safari-word bank,
    defined earlier in the dict) and "ocean" (a real, specific ocean-word
    bank, defined later) as substrings, so the generic one always won
    regardless of relevance. Now picks the LONGEST matching key, the same
    "longest alias wins" principle the shared Universal Topic Vocabulary
    Engine already uses (services/factory/topic_vocabulary.py), so a more
    specific bank always beats a more generic one that happens to also
    match. This function is only reached for themes the shared engine
    itself doesn't cover (see _select_words) -- most common topics resolve
    through the shared engine first now.
    """
    if not theme:
        return None
    theme_lower = str(theme).lower().strip()
    # Exact match beats everything.
    if theme_lower in _TOPIC_BANKS:
        return _TOPIC_BANKS[theme_lower]
    # Substring match: prefer the longest (most specific) matching key.
    best_key = None
    for key in _TOPIC_BANKS:
        if key in theme_lower or theme_lower in key:
            if best_key is None or len(key) > len(best_key):
                best_key = key
    return _TOPIC_BANKS[best_key] if best_key else None


# ---------------------------------------------------------------------------
# Local dictation sentence bank (maps words to sentences)
# ---------------------------------------------------------------------------
_DICTATION_BANK: dict[str, str] = {
    # Farm Animals
    "chicken": "The farmer collects eggs from the chicken every morning.",
    "rooster": "The rooster crows loudly to wake up the farm.",
    "cow": "The cow gives fresh milk for the whole family.",
    "horse": "The children ride the horse around the paddock.",
    "sheep": "The sheep grow thick wool to stay warm in winter.",
    "goat": "The goat jumps onto the rock to eat the leaves.",
    "pig": "The pig rolls in the mud to cool down on hot days.",
    "duck": "The duck swims gracefully across the pond.",
    "turkey": "The turkey struts around the barnyard proudly.",
    "donkey": "The donkey carries heavy bags of grain to the barn.",
    "rabbit": "The rabbit hops quickly through the tall grass.",
    "barn": "The red barn protects the animals from rain and wind.",
    "pasture": "The green pasture has plenty of grass for the animals.",
    "farmer": "The farmer works hard every day to care for the animals.",
    "tractor": "The big tractor plows the field before planting season.",
    # Animals
    "elephant": "The elephant uses its trunk to drink water from the river.",
    "giraffe": "The giraffe eats leaves from the tallest trees.",
    "tiger": "The tiger hunts quietly through the tall jungle grass.",
    "lion": "The lion roars to warn other animals away from its pride.",
    "zebra": "The zebra runs very fast when it senses danger nearby.",
    "monkey": "The monkey swings from branch to branch in the rainforest.",
    "turtle": "The turtle moves slowly but never gives up on its journey.",
    "dolphin": "The dolphin leaps out of the water to breathe fresh air.",
    "eagle": "The eagle soars high above the mountains searching for prey.",
    "frog": "The frog sits by the pond and catches flies with its long tongue.",
    # School
    "pencil": "Please write your name at the top of the page with your pencil.",
    "paper": "The student drew a picture on a piece of white paper.",
    "teacher": "The teacher explains the lesson clearly to all the students.",
    "student": "The student finishes the math homework before dinner.",
    "classroom": "The bright classroom has many books and maps on the walls.",
    "notebook": "I write my ideas in a notebook every morning.",
    "library": "The library has thousands of books for students to read.",
    "homework": "The student completes the homework before watching television.",
    "desk": "The desk holds all of the books and supplies for the class.",
    "ruler": "Use the ruler to draw a straight line across the page.",
    # Weather
    "cloudy": "It is cloudy today, so we might not see the sun at all.",
    "sunny": "It is sunny and warm, a perfect day to play outside.",
    "rainy": "It is rainy and cold, so we will stay inside today.",
    "thunder": "Thunder booms loudly when a storm approaches quickly.",
    "lightning": "Lightning flashes across the dark sky before the rain starts.",
    "storm": "The strong storm knocked down many trees in the forest.",
    "windy": "It is very windy today, so hold onto your hat tightly.",
    "snowflake": "Each snowflake is unique and has a beautiful crystal shape.",
    "rainbow": "A bright rainbow appeared after the rainstorm passed.",
    "temperature": "The temperature drops at night even in the summer months.",
    # Technology
    "keyboard": "I type quickly on the keyboard to finish my report.",
    "mouse": "The computer mouse helps me click and move around the screen.",
    "monitor": "The large monitor displays clear and colorful pictures.",
    "screen": "The screen glows brightly in the dark room.",
    "printer": "The printer makes a copy of every document I need.",
    "laptop": "I carry my laptop to school to take notes in class.",
    "speaker": "The speaker plays music loudly for the whole party.",
    "cable": "The cable connects the computer to the internet.",
    "router": "The router sends the wireless signal throughout the house.",
    "webcam": "I use the webcam to talk to my grandmother on video.",
    # Plants
    "flower": "The flower opens its petals each morning when the sun rises.",
    "stem": "The stem carries water from the roots up to the leaves.",
    "leaf": "The green leaf makes food for the plant using sunlight.",
    "root": "The root holds the plant firmly in the soil underground.",
    "seed": "We plant the seed in the soil and water it every day.",
    "soil": "Rich dark soil is the best place to grow healthy vegetables.",
    "garden": "We grow tomatoes and peppers in our backyard garden.",
    "branch": "A bird builds its nest on a branch of the oak tree.",
    "petal": "The pink petal fell gently from the rose flower.",
    "trunk": "The elephant rubbed its back against the rough tree trunk.",
    # Food
    "apple": "I eat an apple every day for a healthy snack.",
    "banana": "The banana is yellow and ripe, ready to eat.",
    "carrot": "The rabbit loves to eat crunchy orange carrots.",
    "sandwich": "I pack a sandwich with cheese and lettuce for lunch.",
    "cheese": "The cheese melts beautifully on top of the hot pizza.",
    "potato": "The baked potato is soft and delicious with butter.",
    "tomato": "The red tomato is ripe and ready to pick from the vine.",
    "orange": "I squeeze an orange to make fresh juice for breakfast.",
    "cereal": "I pour cold cereal and milk into a bowl each morning.",
    "chicken": "The roast chicken is golden brown and smells wonderful.",
    # Sports
    "soccer": "We play soccer on the big field every Saturday morning.",
    "baseball": "The baseball player swings the bat and hits a home run.",
    "tennis": "I hit the tennis ball over the net to win the point.",
    "football": "The football player runs fast to score a touchdown.",
    "basketball": "The basketball bounces on the court with a loud thud.",
    "swimming": "I go swimming at the pool to cool off on hot days.",
    "coach": "The coach teaches the team how to play fairly and well.",
    "player": "The basketball player jumps high to block the shot.",
    "helmet": "Always wear a helmet when you ride your bicycle.",
    "trophy": "The team proudly displays the trophy in the hallway.",
    # Transportation
    "bicycle": "I ride my bicycle to school along the safe path.",
    "airplane": "The airplane flies through the clouds at a great height.",
    "train": "The train travels on the tracks across the countryside.",
    "subway": "The subway carries many passengers under the busy city.",
    "truck": "The delivery truck brings packages to the store every morning.",
    "boat": "The sailboat glides smoothly across the calm blue water.",
    "rocket": "The rocket launches into space with a burst of flame.",
    "bus": "The school bus picks up students at the corner every morning.",
    "taxi": "We take a taxi to the airport when we travel on vacation.",
    "engine": "The engine powers the train to move along the tracks.",
    # Ocean
    "whale": "The blue whale is the largest animal that has ever lived.",
    "shark": "The shark swims quietly beneath the surface of the ocean.",
    "dolphin": "The dolphin plays in the waves alongside the boat.",
    "coral": "Colorful coral reefs are home to many sea creatures.",
    "tide": "The rising tide covers the sandcastle we built on the beach.",
    "wave": "The strong wave pushed the boat closer to the shore.",
    "anchor": "The captain drops the anchor to keep the boat from drifting.",
    "sailor": "The brave sailor navigates the ship through the stormy sea.",
    # Space
    "planet": "Earth is the only planet in our solar system with life.",
    "rocket": "The rocket blasts off from the launchpad with great speed.",
    "astronaut": "The astronaut floats weightlessly inside the space station.",
    "galaxy": "Our galaxy contains billions of stars and solar systems.",
    "orbit": "The satellite travels in orbit around the Earth every ninety minutes.",
    "comet": "A bright comet appeared in the night sky last week.",
    "asteroid": "An asteroid passed safely by the Earth last month.",
    "nebula": "The colorful nebula is a cloud of gas and dust in space.",
    "satellite": "The weather satellite sends pictures of cloud patterns.",
    "telescope": "We use a telescope to see stars that are very far away.",
    # Ocean animals (2026-09-09, added alongside the shared topic engine
    # integration so words drawn from the shared "ocean_animals" category
    # get a real dictation sentence instead of the generic fallback).
    "octopus": "The octopus squeezed its soft body through a tiny gap in the rocks.",
    "squid": "The squid shot a cloud of ink to escape from a hungry shark.",
    "starfish": "The starfish can slowly regrow an arm that it loses.",
    "jellyfish": "The jellyfish drifted through the water, trailing its long tentacles.",
    "seahorse": "The tiny seahorse wrapped its tail around a piece of coral.",
    "crab": "The crab scuttled sideways across the wet sand.",
    "lobster": "The lobster used its large claws to crack open a shell.",
    "shrimp": "A school of shrimp darted along the sandy ocean floor.",
    "clam": "The clam closed its two shells tightly when the tide went out.",
    "oyster": "Inside the oyster, a grain of sand slowly became a pearl.",
    "seal": "The seal barked and clapped its flippers on the rocky shore.",
    "walrus": "The walrus used its long tusks to haul itself onto the ice.",
    "otter": "The otter floated on its back and cracked open a shell with a rock.",
    "penguin": "The penguin waddled across the ice before diving into the cold water.",
    "turtle": "The sea turtle swam gracefully through the warm ocean current.",
    "eel": "The eel slithered out from a crack between the coral rocks.",
    "stingray": "The stingray glided silently over the sandy sea floor.",
    "anemone": "The clownfish hid safely among the stinging arms of the anemone.",
    "tuna": "The tuna swam swiftly through the open ocean in a large school.",
    "salmon": "Every year, the salmon swims upstream to lay its eggs.",
    "clownfish": "The bright orange clownfish darted between the anemone's arms.",
    "manatee": "The gentle manatee grazed slowly on grass at the bottom of the bay.",
    "plankton": "Tiny plankton floats near the ocean's surface, feeding many larger animals.",
    "barnacle": "A barnacle attached itself firmly to the bottom of the old boat.",
    "pelican": "The pelican dove into the water and scooped up a fish in its pouch.",
    "krill": "A humpback whale can eat millions of tiny krill in a single day.",
}


def _get_dictation_sentence(word: str) -> str:
    """Return a dictation sentence for a word, or a generic one."""
    w = str(word).lower().strip()
    if w in _DICTATION_BANK:
        return _DICTATION_BANK[w]
    return f"The word {word} is spelled {word}."


# ---------------------------------------------------------------------------
# Activity generators (local — no AI required)
# ---------------------------------------------------------------------------

def _scramble_word(word: str) -> str:
    """Return a scrambled version of a word (first/last letter fixed)."""
    if len(word) <= 1:
        return word
    if len(word) <= 3:
        return word
    middle = list(word[1:-1])
    attempts = 0
    while "".join(middle) == word[1:-1] and attempts < 10:
        random.shuffle(middle)
        attempts += 1
    return word[0] + "".join(middle) + word[-1]


def _activity_word_list(words: list[str]) -> list[dict]:
    return [{"word": w, "scrambled": "", "hint": ""} for w in words]


def _activity_unscramble(words: list[str]) -> list[dict]:
    return [
        {"word": w, "scrambled": _scramble_word(w),
         "hint": "Unscramble the letters to spell the word correctly."}
        for w in words
    ]


def _activity_missing_letters(words: list[str]) -> list[dict]:
    result = []
    for w in words:
        idx = random.randint(1, len(w) - 2) if len(w) >= 3 else random.randint(0, len(w) - 1)
        hint_word = w[:idx] + "_" + w[idx + 1:]
        result.append({
            "word": w,
            "scrambled": hint_word,
            "hint": f"Fill in the missing letter. The word has {len(w)} letters.",
        })
    return result


_FILL_BLANK_SENTENCES: dict[str, str] = {
    "problem": "The math ________ took us 20 minutes to finish.",
    "minute": "We have five ________ to get to recess.",
    "under": "The dog is hiding ________ the table.",
    "friend": "My best ________ lives next door to me.",
    "people": "Many ________ attended the school play.",
    "school": "I walk to ________ every morning.",
    "thought": "She had a quiet ________ about the story.",
    "answer": "Raise your hand when you know the ________.",
    "story": "This ________ has three main characters.",
    "different": "These two shapes are ________ in size.",
    "important": "It is ________ to do your homework every night.",
    "together": "The twins like to play ________ after school.",
    "beautiful": "The sunset over the lake is very ________.",
    "everything": "She packed ________ she needed for the trip.",
    "everyone": "________ in the class did well on the test.",
    "always": "I ________ brush my teeth before bed.",
    "often": "We ________ go to the park on weekends.",
    "sometimes": "It rains here, but only ________.",
    "never": "I have ________ been to a baseball game.",
    "really": "I am ________ excited about the field trip.",
    "truly": "This is a ________ wonderful surprise party.",
    "finally": "After waiting, she ________ got her turn.",
    "meant": "The note she left ________ a lot to me — it was very kind.",
    "beginning": "Every story has a ________ and an ending.",
    "opinion": "In my ________, this is the best book of the year.",
    "condition": "The old house was in poor ________ and needed many repairs.",
    "ordinary": "Today felt like an ________ Tuesday, nothing special happened.",
    "women": "Many ________ from our community volunteered at the shelter.",
    "disappear": "If you do not water the plant, it will begin to ________.",
    "taught": "The teacher ________ us how to write a complete sentence.",
    "because": "I stayed home ________ I was feeling sick.",
    "bought": "She ________ a new backpack for school.",
    "caught": "The cat ________ the ball in its paws.",
    "eight": "There are ________ planets in our solar system.",
    "which": "________ book would you like to read?",
    "where": "________ is the library located?",
    "their": "The dogs wagged ________ tails happily.",
    "there": "The book is right ________ on the shelf.",
    "through": "The rabbit ran ________ the garden quickly.",
    "experience": "The class trip was an amazing ________ through the woods.",
    "neighbor": "Our ________ brought us fresh cookies.",
    "exercise": "Running laps is my favorite form of ________.",
    "heard": "I ________ a strange noise outside last night.",
    "certain": "I am ________ that this is the right answer.",
    "believe": "I ________ that every child can learn.",
    "weight": "The package's ________ is more than five pounds.",
    "quiet": "Please be ________ in the library.",
    "quite": "The movie was ________ good and worth watching.",
    "while": "I read a book ________ my brother played video games.",
    "information": "She did some ________ to find the best answer.",
    "certainly": "I will ________ help you with your homework.",
    "describe": "Can you ________ what happened yesterday?",
    "example": "This math problem is an ________ of addition.",
    "machine": "The washing ________ hums quietly in the basement.",
    "maybe": "I will ________ go to the store after school.",
    "notice": "Did you ________ anything strange in the picture?",
    "often": "I ________ see birds flying south in winter.",
    "separate": "Please ________ the red socks from the white ones.",
    "straight": "Please sit ________ up in your chair.",
    "strength": "It takes a lot of ________ to lift that heavy box.",
    "suppose": "I ________ we should leave now.",
    "surprise": "The party was a complete ________.",
    "woman": "The ________ walked down the street alone.",
    "wonderful": "We had a ________ time at the amusement park.",
    "yesterday": "________ was my birthday!",
    "bought": "She ________ a beautiful dress for the dance.",
    "caught": "The fisherman ________ a huge fish this morning.",
    "brought": "Dad ________ us ice cream after dinner.",
    "sugar": "Pass the ________, please.",
    "machine": "The copy ________ broke down this morning.",
    "different": "This cake recipe is ________ from that one.",
    "library": "We go to the ________ every Tuesday.",
    "country": "What is your favorite ________ to visit?",
    "early": "We woke up ________ to catch the sunrise.",
    "easy": "That math problem was very ________ to solve.",
    "earth": "Our ________ goes around the sun once a year.",
    "eight": "My little brother is ________ years old.",
    "enough": "I have had ________ to eat at dinner.",
    "float": "Wood will ________ on top of water.",
    "fruit": "An apple is a type of ________.",
    "guess": "Can you ________ how many jellybeans are in the jar?",
    "happen": "What will ________ if we miss the bus?",
    "heart": "The human ________ pumps blood through the body.",
    "hundred": "There are ________ days in a school year.",
    "idea": "That is a great ________ for a science project.",
    "important": "It is ________ to brush your teeth every day.",
    "island": "Hawaii is a beautiful ________ in the ocean.",
    "learn": "Children ________ to read in school.",
    "minute": "I will be ready in just one ________.",
    "money": "We use ________ to buy things at the store.",
    "mountain": "The tall ________ was covered in snow.",
    "nothing": "There is ________ in the box.",
    "often": "We ________ play soccer after school.",
    "parent": "My ________ dropped me off at school today.",
    "people": "Many ________ came to the concert.",
    "piece": "I ate a large ________ of birthday cake.",
    "possible": "Is it ________ to finish all this homework tonight?",
    "probable": "It is ________ that we will have homework over the weekend.",
    "promise": "I ________ to clean my room tomorrow.",
    "question": "Can you answer this ________ about the story?",
    "quite": "The movie was ________ interesting.",
    "really": "I am ________ happy about my grades.",
    "remember": "Please ________ to turn off the lights.",
    "said": "She ________ the book was her favorite.",
    "school": "I have five classes at ________ today.",
    "sentence": "Please write each vocabulary word in a ________.",
    "separate": "Can you ________ the shirts from the pants?",
    "special": "Today is a ________ day because it is my birthday.",
    "strange": "That was a very ________ noise we heard last night.",
    "strength": "You need a lot of ________ to carry that backpack.",
    "study": "I need to ________ for my science test tomorrow.",
    "sugar": "Too much ________ is not good for your teeth.",
    "sure": "I am ________ that I finished my homework.",
    "though": "________ it was raining, we went outside to play.",
    "thought": "That was a very nice ________ you had.",
    "together": "The twins like to do everything ________.",
    "tomorrow": "I have a dentist appointment ________.",
    "toward": "We walked ________ the big red barn.",
    "trouble": "I got in ________ for talking in class.",
    "truly": "I am ________ sorry for what happened.",
    "turn": "Please take ________s when you read aloud.",
    "understand": "I finally ________ how to solve the equation.",
    "usual": "My ________ bedtime is 8 o'clock.",
    "wait": "Please ________ for the bus at the stop.",
    "weather": "The ________ today is sunny and warm.",
    "whether": "I am not sure ________ to walk or ride my bike.",
    "woman": "The ________ who works at the bakery makes great cookies.",
    "women": "The ________ in the meeting all agreed on the plan.",
    "wonderful": "We had a ________ time at the party.",
    "write": "I need to ________ a letter to my grandmother.",
}


def _activity_fill_blank(words: list[str]) -> list[dict]:
    results = []
    for w in words:
        w_lower = w.lower()
        blank = "_" * len(w)
        if w_lower in _FILL_BLANK_SENTENCES:
            # Sentence from bank — use it with blanks
            sentence = _FILL_BLANK_SENTENCES[w_lower]
            student_sentence = sentence.replace("________", blank)
        else:
            # Generic fallback — sentence shows the blank only, answer stays hidden
            student_sentence = f"Fill in the blank (word has {len(w)} letters):  {blank}"
        results.append({"word": w, "scrambled": "", "hint": "", "sentence": student_sentence})
    return results


_ACTIVITY_GENERATORS: dict[str, callable] = {
    "word list": _activity_word_list,
    "unscramble": _activity_unscramble,
    "missing letters": _activity_missing_letters,
    "fill in the blank": _activity_fill_blank,
}

_ACTIVITY_LABELS: dict[str, str] = {
    "word list": "Practice writing each word correctly. Use the guide words to help you.",
    "unscramble": "Each word below has its letters scrambled. Figure out the correct spelling and write it on the line.",
    "missing letters": "Each word below has one letter missing. Fill in the blank with the correct letter.",
    "fill in the blank": "Read each sentence below. Fill in the blank with the correct spelling of the word listed. Check your spelling carefully!",
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class SpellingWord:
    word: str
    sentence: str = ""
    definition: str = ""
    difficulty: str = "medium"
    scrambled: str = ""
    hint: str = ""

    def as_dict(self) -> dict:
        return {
            "word": self.word,
            "sentence": self.sentence,
            "definition": self.definition,
            "difficulty": self.difficulty,
            "scrambled": self.scrambled,
            "hint": self.hint,
        }


@dataclass
class SpellingSection:
    label: str
    instruction: str
    words: list[SpellingWord]
    dictation_text: str = ""
    activity_type: str = "word list"

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "instruction": self.instruction,
            "words": [w.as_dict() for w in self.words],
            "dictation_text": self.dictation_text,
            "activity_type": self.activity_type,
        }


@dataclass
class SpellingWorksheetResult:
    title: str
    theme: str
    grade: str = ""
    sections: list[SpellingSection] = field(default_factory=list)
    dictation_sentences: list[str] = field(default_factory=list)
    answer_key: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def all_words(self) -> list[str]:
        return [w.word for s in self.sections for w in s.words if w.word]

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "theme": self.theme,
            "grade": self.grade,
            "sections": [s.as_dict() for s in self.sections],
            "dictation_sentences": self.dictation_sentences,
            "answer_key": self.answer_key,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def _capitalize_word(word: str) -> str:
    """Capitalize a word: lowercase → title case, else preserve as-is."""
    w = word.strip()
    if w.islower():
        return w.capitalize()
    return w


def _grade_max_word_length(grade: str) -> int:
    """Deterministic, explainable per-grade word-length ceiling.

    Only applied to topic/shared-engine vocabulary, which has no inherent
    grade tier of its own (unlike _GRADE_BANKS, which is already hand-
    curated per grade). A simple length cap is enough to keep "Grade 2"
    from getting the same word complexity as "Grade 8" without building an
    elaborate linguistic/readability system.
    """
    g = re.sub(r"^Grade\s*", "", str(grade or "3").strip(), flags=re.IGNORECASE)
    g = re.split(r"[-,]", g)[0].strip()
    try:
        n = int(g)
    except ValueError:
        n = 3
    if n <= 2:
        return 6
    if n <= 4:
        return 8
    if n <= 6:
        return 10
    return 99  # Grades 7+ : no practical cap.


def _filter_topic_words_for_grade(words: list[str], grade: str, word_count: int) -> list[str]:
    """Clean, dedupe, and grade-length-filter a topic word list.

    Never lets grade filtering starve the worksheet: if the cap would
    leave fewer than a small usable minimum, it relaxes back to the full
    deduplicated pool rather than under-deliver on the customer's
    requested word count. Never pads with unrelated words -- a topic pool
    smaller than word_count simply returns fewer words.
    """
    max_len = _grade_max_word_length(grade)
    cleaned: list[str] = []
    seen: set[str] = set()
    for w in words:
        wl = re.sub(r"[^A-Za-z]", "", str(w or "")).lower()
        if not wl or wl in seen:
            continue
        seen.add(wl)
        cleaned.append(wl)
    filtered = [w for w in cleaned if len(w) <= max_len]
    pool = filtered if len(filtered) >= min(4, word_count) else cleaned
    return pool[:word_count]


def _looks_like_real_topic(theme: str) -> bool:
    """Local, deterministic nonsense-topic guard for the grade-bank
    fallback (Step 12 of the 2026-09-09 Spelling Worksheet release: a
    theme that matches no pack must not silently receive random
    grade-level words that have nothing to do with what the customer
    typed -- "the Factory must not pretend it understands nonsense").

    A theme containing any bare number/symbol token, or where most of its
    alphabetic tokens don't look like real words (too short or no vowel),
    is treated as nonsense. A real topic phrase not covered by any pack
    (e.g. "Medieval History") still passes this check and keeps the
    existing graceful grade-bank fallback -- this guard is deliberately
    narrow, not a general profanity/quality filter.
    """
    tokens = re.findall(r"[A-Za-z]+|[0-9]+", str(theme or ""))
    if not tokens:
        return False
    if any(t.isdigit() for t in tokens):
        return False
    alpha_tokens = [t for t in tokens if t.isalpha()]
    if not alpha_tokens:
        return False
    real_looking = [t for t in alpha_tokens if len(t) >= 3 and re.search(r"[aeiouAEIOU]", t)]
    return len(real_looking) >= max(1, (len(alpha_tokens) + 1) // 2)


def _select_words(
    theme: str,
    grade: str,
    word_count: int,
    custom_words: str,
) -> tuple[list[str], list[str]]:
    """
    Select words using ONLY local banks and the shared topic engine — no
    AI, no network calls.

    Priority:
      1. custom_words (user-supplied list, local)
      2. the shared Universal Topic Vocabulary Engine (services.factory.
         topic_vocabulary) -- the SAME resolver Crossword and Word Search
         use, so all three products agree on what a topic means. Falls
         through unchanged when the theme isn't one of its categories.
      3. local topic bank (theme matched to this module's own bank, for
         topics outside the shared engine's current category list)
      4. grade-level bank (local fallback) -- but a genuinely nonsense
         theme fails safely here instead (see _looks_like_real_topic)

    Returns (selected_words, dictation_sentences).
    """
    # 1. Custom word list — fully local
    if custom_words and custom_words.strip():
        words = [
            _capitalize_word(w)
            for w in re.split(r"[\n\s]+", custom_words)
            if w.strip()
        ]
        return words[:word_count], []

    # 2. Shared Universal Topic Vocabulary Engine — fully local, zero-cost.
    from services.factory.topic_vocabulary import resolve_topic_vocabulary

    shared = resolve_topic_vocabulary(theme, max(word_count * 3, 30))
    if shared.matched:
        selected = _filter_topic_words_for_grade(shared.words, grade, word_count)
        if selected:
            sentences = [_get_dictation_sentence(w) for w in selected]
            return selected, sentences

    # 3. Local topic bank match — fully local
    topic_words = _match_topic_bank(theme)
    if topic_words:
        selected = _filter_topic_words_for_grade(topic_words, grade, word_count)
        if selected:
            sentences = [_get_dictation_sentence(w) for w in selected]
            return selected, sentences

    # 4. No topic match at all. A genuinely nonsense theme must not
    # silently fall through to random grade-level words.
    if theme and theme.strip() and not _looks_like_real_topic(theme):
        return [], []

    # 5. Grade-level bank — fully local fallback (no theme given, or a
    # real-looking topic phrase with no matching pack).
    grade_words = _get_grade_bank(grade)
    selected = grade_words[:word_count]
    sentences = [_get_dictation_sentence(w) for w in selected]
    return selected, sentences


def build_spelling_worksheet(
    *,
    theme: str = "",
    grade: str = "3",
    word_count: int = 10,
    custom_words: str = "",
    include_answer_key: bool = True,
    difficulty: str = "Medium",
    activity_type: str = "word list",
) -> SpellingWorksheetResult:
    """
    Generate a spelling worksheet with themed vocabulary words — 100% local.

    No OpenAI, no chat_json, no network calls. Words come from:
      1. User-supplied custom_words list (highest priority)
      2. Local topic word bank (theme matched)
      3. Local grade-level word bank (fallback)

    Supports activity types: word list, unscramble, missing letters, fill in the blank.
    """
    title = str(theme or "Spelling Practice").strip()
    theme_val = str(theme or "Spelling").strip()
    grade_val = str(grade or "3").strip()
    activity = activity_type if activity_type in _ACTIVITY_GENERATORS else "word list"
    generator = _ACTIVITY_GENERATORS.get(activity, _activity_word_list)
    instruction = _ACTIVITY_LABELS.get(activity, _ACTIVITY_LABELS["word list"])

    # Select words locally — no AI call
    raw_words, dictation_sentences = _select_words(theme_val, grade_val, word_count, custom_words)

    if not raw_words:
        return SpellingWorksheetResult(
            title=title,
            theme=theme_val,
            grade=grade_val,
            errors=[
                f'We could not build a strong enough word set for "{theme_val}" yet. '
                "Try a broader topic or add your own words."
            ],
        )

    # Apply activity transformation
    activity_rows = generator(raw_words)

    spelling_word_objs = [
        SpellingWord(
            word=row["word"],
            scrambled=row.get("scrambled", ""),
            hint=row.get("hint", ""),
            sentence=row.get("sentence", ""),
        )
        for row in activity_rows
    ]

    answer_key = [w.word for w in spelling_word_objs]

    section = SpellingSection(
        label=f"{activity.title()} Practice",
        instruction=instruction,
        words=spelling_word_objs,
        activity_type=activity,
    )

    # Trim dictation sentences to 5 max
    dictation = [s.strip() for s in dictation_sentences[:5] if s.strip()]

    return SpellingWorksheetResult(
        title=title,
        theme=theme_val,
        grade=grade_val,
        sections=[section],
        dictation_sentences=dictation,
        answer_key=answer_key,
    )
