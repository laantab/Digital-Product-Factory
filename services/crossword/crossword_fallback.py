"""Verified local vocabulary + clue fallback library for crossword generation.

This module is the last-resort fallback when all repair attempts have failed.
It is NOT used when a local vocabulary pack successfully matches the user's topic.

Rules:
  - Never use computer words as a universal/general fallback.
  - Always select fallback content according to the user's theme/audience.
  - Provide enough variety to fill a 10-puzzle book without repeating words.
  - Every word has a verified real clue — never placeholder text.

Category routing (in priority order for "everyday/general" fallback):
  1. Detect audience: children → use CHILDREN_FALLBACK
  2. Detect theme keywords → use closest category pack
  3. Default for "general/everyday" → use EVERYDAY_LIFE pack
"""

from __future__ import annotations

import random
import re
from typing import Iterator

# ---------------------------------------------------------------------------
# Vocabulary packs — each pack has 30-50 words for variety across puzzles
# ---------------------------------------------------------------------------

# Format: (word, clue) tuples — all verified, all crossword-appropriate
# Difficulty: EASY=3-7 letters, MEDIUM=4-9 letters, HARD=5-12 letters

EVERYDAY_LIFE: list[tuple[str, str]] = [
    # Home & Living
    ("KITCHEN", "Room where meals are prepared."),
    ("BEDROOM", "Room where you sleep."),
    ("BATHROOM", "Room used for washing and grooming."),
    ("GARAGE", "Attached building for parking vehicles."),
    ("BACKYARD", "Outdoor space behind a home."),
    ("WINDOWS", "Glass panels that let in light."),
    ("CURTAINS", "Fabric hung to cover windows."),
    ("PILLOW", "Soft cushion for resting your head."),
    ("BLANKET", "Warm covering used on beds."),
    ("TOWELS", "Absorbent cloths for drying."),
    # Food & Kitchen
    ("BREAKFAST", "First meal of the day."),
    ("LUNCH", "Midday meal between breakfast and dinner."),
    ("DINNER", "Evening meal, often the largest of the day."),
    ("SANDWICH", "Food with filling between two slices of bread."),
    ("SALAD", "Cold mixture of vegetables."),
    ("SOUP", "Liquid dish often served as a starter."),
    ("PASTA", "Italian food made from wheat flour."),
    ("RICE", "Grain commonly served as a side dish."),
    ("COFFEE", "Hot caffeinated morning drink."),
    ("JUICE", "Drink made from pressed fruit."),
    # Family & People
    ("MOTHER", "Female parent."),
    ("FATHER", "Male parent."),
    ("SISTER", "Female sibling."),
    ("BROTHER", "Male sibling."),
    ("GRANDMA", "Informal name for grandmother."),
    ("GRANDPA", "Informal name for grandfather."),
    ("AUNT", "Sister of your mother or father."),
    ("UNCLE", "Brother of your mother or father."),
    ("NEIGHBOR", "Person who lives nearby."),
    ("FRIEND", "Person you like and trust."),
    # Nature & Weather
    ("SUNSHINE", "Light and warmth from the sun."),
    ("RAINBOW", "Colorful arc that appears after rain."),
    ("THUNDER", "Loud sound that follows lightning."),
    ("SNOWFLAKE", "Single crystal of frozen water."),
    ("SUNFLOWER", "Tall yellow flower that follows the sun."),
    ("PINEAPPLE", "Tropical fruit with spiky skin."),
    ("WATERFALL", "Water falling from a height."),
    ("MOUNTAIN", "Very high landform rising above surroundings."),
    ("RIVER", "Large natural stream of flowing water."),
    ("FOREST", "Large area covered with trees."),
    # Animals
    ("DOLPHIN", "Intelligent sea mammal known for jumping."),
    ("PENGUIN", "Bird that cannot fly but swims well."),
    ("GIRAFFE", "Tall animal with a very long neck."),
    ("BUTTERFLY", "Insect with colorful wings."),
    ("RABBIT", "Small animal with long ears and a cotton tail."),
    ("TURTLE", "Reptile with a shell on its back."),
    ("KOALA", "Australian marsupial that lives in eucalyptus trees."),
    ("ZEBRA", "African animal with black and white stripes."),
    ("PANDA", "Black and white bear from China."),
    ("FALCON", "Bird of prey known for speed."),
    # Daily activities
    ("MORNING", "Early part of the day."),
    ("EVENING", "Time of day just before night."),
    ("WEEKEND", "Saturday and Sunday, days off from work."),
    ("HOLIDAY", "Day of celebration or vacation."),
    ("GARDEN", "Area where flowers or vegetables are grown."),
    ("COOKING", "Preparing food by heating it."),
    ("CLEANING", "Making a place tidy and free of dirt."),
    ("READING", "Looking at written words to understand them."),
    ("EXERCISE", "Physical activity to stay healthy."),
    ("SHOPPING", "Going to stores to buy things."),
    # Clothing
    ("JACKET", "Garment worn over other clothes for warmth."),
    ("GLOVES", "Coverings for the hands."),
    ("SCARF", "Long piece of fabric worn around the neck."),
    ("BOOTS", "Sturdy shoes that cover the ankle."),
    ("SKIRT", "Garment that hangs from the waist."),
    ("DRESS", "One-piece garment worn by women."),
    ("SOCKS", "Foot coverings worn inside shoes."),
    ("BELT", "Strip of leather worn around the waist."),
    # Places
    ("LIBRARY", "Place where books are borrowed and read."),
    ("HOSPITAL", "Place where sick people receive care."),
    ("STADIUM", "Large venue for sporting events."),
    ("CASTLE", "Fortified building from medieval times."),
    ("VILLAGE", "Small settlement smaller than a town."),
    # Time & Seasons
    ("SPRING", "Season after winter, when flowers bloom."),
    ("AUTUMN", "Season when leaves change color."),
    ("WINTER", "Coldest season of the year."),
    ("SUMMER", "Warmest season of the year."),
    ("DECEMBER", "The twelfth and last month of the year."),
    ("OCTOBER", "The tenth month, known for Halloween."),
    # School & Work
    ("TEACHER", "Person who helps students learn."),
    ("OFFICE", "Room or building for professional work."),
    ("SCHOOL", "Place where children go to learn."),
    ("HOMEWORK", "Schoolwork done at home."),
    ("PROJECTS", "Planned pieces of work or research."),
    # Body & Health
    ("SHOULDER", "Joint connecting the arm to the body."),
    ("STOMACH", "Organ that digests food."),
    ("MUSCLES", "Tissues that help the body move."),
    ("HEALTHY", "In good physical and mental condition."),
    ("SLEEPING", "Resting with eyes closed in a dream state."),
    ("DREAMING", "Experiencing images and ideas while asleep."),
    # Time & Seasons (additional)
    ("JANUARY", "The first month of the year."),
    ("FEBRUARY", "The second month of the year."),
    ("MARCH", "The third month of the year."),
    ("APRIL", "The fourth month of the year."),
    ("MAY", "The fifth month of the year."),
    ("JUNE", "The sixth month of the year."),
    ("JULY", "The seventh month of the year."),
    ("AUGUST", "The eighth month of the year."),
    ("SEPTEMBER", "The ninth month of the year."),
    ("NOVEMBER", "The eleventh month of the year."),
    # Additional home & living
    ("FRIDGE", "Appliance used to keep food cold."),
    ("OVEN", "Appliance used for baking and roasting food."),
    ("STOVE", "Cooking appliance with burners on top."),
    ("DISHES", "Plates, bowls, and cups used for eating."),
    ("SINK", "Basin for washing dishes and hands."),
    ("LAUNDRY", "Clothes that need to be washed."),
    ("VACUUM", "Appliance used to clean floors."),
    # Additional daily activities
    ("WALKING", "Moving on foot at a steady pace."),
    ("BIKING", "Riding a bicycle for transport or exercise."),
    ("PLAYING", "Engaging in a game or recreational activity."),
    ("STUDYING", "Reading and learning for school or work."),
    # Additional nature & weather
    ("SUNRISE", "Time in the morning when the sun comes up."),
    ("SUNSET", "Time in the evening when the sun goes down."),
    ("CLOUD", "White or gray shape in the sky made of water vapor."),
    ("BREEZE", "Gentle light wind."),
    ("STORM", "Violent weather with thunder and rain."),
    # Missing everyday items — verified specific clues (was: generic "Crossword answer" placeholder)
    ("COMB", "A toothed tool used to arrange your hair."),
    ("WAKE", "To stop sleeping in the morning."),
    ("SOAP", "Something used with water for washing."),
    ("FORK", "An eating utensil with several pointed prongs."),
    ("BOWL", "A round deep dish used for food."),
    ("LAMP", "A household object that provides light."),
    ("KEYS", "Small objects used to open locks."),
    ("TOOTHBRUSH", "A small brush used to clean your teeth."),
    ("ALARM", "A sound or device that warns or wakes you."),
    ("TOAST", "Bread browned by heat."),
    ("SPOON", "An eating utensil with a small rounded bowl."),
    ("PLATE", "A flat dish used for serving food."),
    ("SHIRT", "Clothing worn on the upper body."),
    ("SHOES", "Footwear worn for walking."),
    ("PHONE", "A device used to call or message someone."),
    ("PANTS", "Clothing that covers the legs."),
    ("COUCH", "A long padded seat for several people."),
    ("RADIO", "A device used to receive audio broadcasts."),
    ("MONEY", "What people use to pay for goods and services."),
    ("TRASH", "Things thrown away because they are no longer wanted."),
    ("BROOM", "A cleaning tool used to sweep floors."),
    ("STORE", "A place where goods are sold."),
    ("KNIFE", "A sharp blade used for cutting food."),
    ("BLENDER", "An appliance used to mix or puree foods."),
    ("BATHTUB", "A large container used for bathing."),
    ("BLINDS", "Window coverings made of horizontal slats."),
    ("CHAIR", "A piece of furniture for sitting."),
    ("CLOCK", "A device that shows the time of day."),
    ("FAN", "A device with rotating blades that creates airflow."),
    ("IRON", "An appliance used to remove wrinkles from clothing."),
    ("MOP", "A cleaning tool with a absorbent head for washing floors."),
    ("RAZOR", "A tool with a sharp blade used for shaving."),
    ("SHAMPOO", "A liquid product used to wash hair."),
    ("SPONGE", "A soft porous material used for cleaning."),
    ("TOWEL", "A cloth used for drying after washing."),
    ("UMBRELLA", "A device used to protect against rain or sun."),
    ("WALLET", "A small folding case for carrying money and cards."),
]

CHILDREN_EASY: list[tuple[str, str]] = [
    # Basic animals — pets
    ("DOG", "A common pet that barks and wags its tail."),
    ("CAT", "A common pet that meows and purrs."),
    ("BIRD", "Animal with feathers that can fly."),
    ("FISH", "Animal that lives and swims in water."),
    ("RABBIT", "Small animal with long ears and a cotton tail."),
    ("HAMSTER", "Small furry pet that runs on a wheel."),
    ("GUINEAPIG", "Small furry pet from South America."),
    ("PARROT", "Colorful bird that can copy sounds and words."),
    ("TURTLE", "Slow-moving reptile that carries its home on its back."),
    # Farm animals
    ("COW", "Farm animal that gives milk."),
    ("PIG", "Pink farm animal that says oink."),
    ("SHEEP", "Farm animal with thick woolly fleece."),
    ("HORSE", "Animal used for riding and pulling carts."),
    ("GOAT", "Farm animal that says baa and eats almost anything."),
    ("CHICKEN", "Farm bird that lays eggs."),
    ("DUCK", "Bird that lives near water and says quack."),
    ("GOOSE", "Large bird that honks and lives near water."),
    ("DONKEY", "Animal used for carrying loads, related to horses."),
    # Wild animals
    ("BEAR", "Large furry animal found in forests."),
    ("LION", "Big wild cat called the king of the jungle."),
    ("ELEPHANT", "Very large gray animal with a long trunk."),
    ("MONKEY", "Animal that often lives in trees and swings."),
    ("GIRAFFE", "Tall animal with a very long neck."),
    ("ZEBRA", "African animal with black and white stripes."),
    ("KANGAROO", "Australian animal that hops on strong back legs."),
    ("PENGUIN", "Bird that cannot fly but swims very well."),
    ("DOLPHIN", "Sea mammal known for jumping and playing."),
    ("WHALE", "Very large sea mammal that lives in the ocean."),
    ("SHARK", "Large fish with sharp teeth."),
    ("OCTOPUS", "Sea creature with eight arms."),
    ("CRAB", "Sea animal that walks sideways on ten legs."),
    ("LOBSTER", "Sea animal with claws and a hard shell."),
    ("BUTTERFLY", "Insect with colorful wings."),
    ("BEE", "Flying insect that makes honey."),
    ("SPIDER", "Eight-legged creature that spins webs."),
    ("FROG", "Amphibian that jumps and lives near water."),
    ("SNAKE", "Long reptile with no legs that slides."),
    ("LIZARD", "Reptile with four legs that basks in the sun."),
    ("TURTLE", "Reptile that carries its home on its back."),
    ("MOUSE", "Small rodent with a long tail."),
    ("SQUIRREL", "Small furry animal that climbs trees."),
    # Colors
    ("RED", "Color of fire trucks and apples."),
    ("BLUE", "Color of the sky on a clear day."),
    ("GREEN", "Color of grass and leaves."),
    ("YELLOW", "Bright color like the sun and bananas."),
    ("ORANGE", "Color of oranges and carrots."),
    ("PURPLE", "Color of grapes and eggplant."),
    ("PINK", "Light red color."),
    ("BROWN", "Color of chocolate and tree bark."),
    ("BLACK", "Darkest color with no light."),
    ("WHITE", "Lightest color like fresh snow."),
    # Shapes
    ("CIRCLE", "Round shape with no corners."),
    ("SQUARE", "Shape with four equal sides and four corners."),
    ("TRIANGLE", "Shape with three sides and three corners."),
    ("STAR", "Shape with five or more points."),
    ("HEART", "Shape like a valentine, symbol of love."),
    ("OVAL", "Shape like an elongated circle."),
    # Family
    ("MOM", "Female parent, also called mother."),
    ("DAD", "Male parent, also called father."),
    ("GRANDMA", "Mother of your mom or dad."),
    ("GRANDPA", "Father of your mom or dad."),
    ("AUNT", "Sister of your mom or dad."),
    ("UNCLE", "Brother of your mom or dad."),
    ("BABY", "Very young child, just born or a few months old."),
    ("KID", "Another word for a child or young person."),
    ("SISTER", "Female sibling."),
    ("BROTHER", "Male sibling."),
    ("COUSIN", "Child of your aunt or uncle."),
    # Body parts
    ("EYE", "Part of the face used for seeing."),
    ("NOSE", "Part of the face used for smelling."),
    ("MOUTH", "Part of the face used for eating and speaking."),
    ("EAR", "Part of the face used for hearing."),
    ("HAND", "Part of the arm used for grabbing and holding."),
    ("FOOT", "Bottom part of the leg you walk on."),
    ("HEAD", "Top part of the body where the brain is."),
    ("ARM", "Body part used for reaching and holding things."),
    ("LEG", "Body part used for standing and walking."),
    # Food
    ("MILK", "White drink from cows."),
    ("BREAD", "Food made from baked dough."),
    ("APPLE", "Red or green fruit that grows on trees."),
    ("BANANA", "Long yellow fruit that grows on trees."),
    ("ORANGE", "Round citrus fruit that is orange."),
    ("GRAPE", "Small round fruit that grows in bunches."),
    ("STRAWBERRY", "Red fruit with tiny seeds on the outside."),
    ("CARROT", "Orange vegetable that grows in the ground."),
    ("CAKE", "Sweet baked dessert often served at birthdays."),
    ("COOKIE", "Sweet flat snack baked in the oven."),
    ("CANDY", "Sweet treat made with sugar."),
    ("CHIPS", "Thin slices of potato fried until crispy."),
    ("PEanutbutter", "Thick spread made from peanuts."),
    ("JELLY", "Sweet fruit spread made from juice."),
    ("HONEY", "Sweet sticky substance made by bees."),
    # Everyday actions and things
    ("BALL", "Round toy used in many games."),
    ("BOOK", "Pages with words that you read."),
    ("TOY", "Something children play with."),
    ("GAME", "Fun activity with rules."),
    ("PLAY", "What children do for fun."),
    ("SING", "Making music with your voice."),
    ("DRAW", "Making pictures with crayons or pencils."),
    ("RUN", "Moving fast on your feet."),
    ("JUMP", "Pushing off the ground with your legs."),
    ("SWIM", "Moving through water using arms and legs."),
    ("RIDE", "Sitting on and traveling with an animal or vehicle."),
    ("CLIMB", "Going up using hands and feet."),
    ("DANCE", "Moving your body to music."),
    ("SLEEP", "Resting with your eyes closed at night."),
    ("EAT", "Putting food in your mouth and chewing."),
    ("DRINK", "Putting liquid in your mouth and swallowing."),
    ("WRITE", "Putting letters and words on paper."),
    ("READ", "Looking at words and understanding them."),
    ("PLAY", "Doing fun things with toys or other children."),
    ("HELP", "Assisting someone with a task."),
    ("SHARE", "Giving part of what you have to others."),
    ("BRUSH", "Cleaning with a brush, like teeth or hair."),
    ("WASH", "Cleaning with water and soap."),
    ("DRESS", "Putting on clothes each morning."),
]

FOOD_PACK: list[tuple[str, str]] = [
    # Breakfast
    ("PANCAKES", "Thin round cakes cooked on a griddle."),
    ("WAFFLES", "Light crispy cakes from a waffle iron."),
    ("CEREAL", "Grain served in a bowl with milk."),
    ("BACON", "Thin strips of salted pork."),
    ("EGGS", "Breakfast food from chickens."),
    ("TOAST", "Bread browned by heating."),
    ("OMELETTE", "Eggs beaten and fried with fillings."),
    ("HASH", "Diced potatoes fried with other ingredients."),
    ("SAUSAGE", "Ground meat stuffed into a casing."),
    ("GRANOLA", "Crunchy oat mixture often eaten with milk."),
    ("BISCUIT", "Soft bread roll often served with breakfast."),
    # Meals
    ("BREAKFAST", "First meal eaten in the morning."),
    ("LUNCH", "Midday meal between breakfast and dinner."),
    ("DINNER", "Evening meal, often the largest of the day."),
    ("SALAD", "Cold mixture of vegetables."),
    ("PASTA", "Italian food made from wheat flour."),
    ("RICE", "Grain commonly served as a side dish."),
    ("STEAK", "Thick cut of beef grilled or fried."),
    ("BURGER", "Ground beef patty in a bread bun."),
    ("CHICKEN", "Poultry often served grilled or fried."),
    ("TURKEY", "Large bird served roasted, especially at holidays."),
    ("VEGGIES", "Vegetables, the healthy parts of plants."),
    ("CURRY", "Spiced dish originating from Indian cuisine."),
    ("STEW", "Slow-cooked dish with meat and vegetables."),
    ("SOUP", "Liquid dish often served as a starter."),
    ("FISH", "Seafood often served grilled or fried."),
    ("SHRIMP", "Small shellfish often served as an appetizer."),
    ("LOBSTER", "Large sea animal with claws, served as a delicacy."),
    ("HAM", "Salted and smoked pork from the leg."),
    ("RIBS", "Meat on bones, often grilled or braised."),
    # Produce
    ("TOMATO", "Red fruit used in salads and sauces."),
    ("LETTUCE", "Leafy green used in salads."),
    ("POTATO", "Starchy root vegetable."),
    ("CARROT", "Orange root vegetable."),
    ("ONION", "Vegetable with a strong flavor."),
    ("MUSHROOM", "Fungus with a cap and stem, used in cooking."),
    ("PEPPER", "Vegetable available in sweet or hot varieties."),
    ("SPINACH", "Dark leafy green rich in iron."),
    ("BROCCOLI", "Green vegetable with a tree-like appearance."),
    ("CELERY", "Crisp vegetable often used in salads."),
    ("CUCUMBER", "Cool green vegetable often in salads."),
    ("GARLIC", "Pungent bulb used to flavor food."),
    ("GINGER", "Spicy root used in cooking and baking."),
    # Dairy
    ("CHEESE", "Dairy product made from milk."),
    ("BUTTER", "Yellow dairy spread made from cream."),
    ("YOGURT", "Thick dairy snack, often flavored."),
    ("MILK", "White drink from cows."),
    ("CREAM", "Dairy product with a high fat content."),
    ("SOURCREAM", "Dairy product with a tangy flavor."),
    # Snacks
    ("COOKIES", "Sweet baked snacks."),
    ("MUFFINS", "Individual-sized quick breads."),
    ("DONUTS", "Fried dough often topped with frosting."),
    ("PRETZEL", "Knot-shaped baked snack."),
    ("CHIPS", "Thin slices of potato fried until crispy."),
    ("CRACKERS", "Thin crisp crackers often eaten with cheese."),
    ("PEANUTS", "Nut often eaten as a snack or in butter."),
    ("POPCORN", "Snack made from heated corn kernels."),
    ("CHOCOLATE", "Sweet candy made from cacao."),
    ("CANDY", "Sweet treat made with sugar."),
    ("CARAMEL", "Sweet syrup made from heated sugar and milk."),
    # International
    ("PIZZA", "Flat bread with sauce, cheese, and toppings."),
    ("TACOS", "Folded tortillas with savory fillings."),
    ("NACHOS", "Tortilla chips with melted cheese."),
    ("SUSHI", "Japanese dish with rice and fish or vegetables."),
    ("NOODLES", "Long thin pasta made from wheat."),
    ("RAMEN", "Japanese noodle soup."),
    ("SALSA", "Spicy tomato-based dip."),
    ("GUACAMOLE", "Mexican dip made from mashed avocado."),
    ("TORTILLA", "Round flatbread used in Mexican cuisine."),
    ("BURRITO", "Large tortilla rolled around a savory filling."),
    ("Fajita", "Mexican dish of grilled meat with peppers."),
    ("Kebab", "Meat grilled on a skewer."),
    ("Dumpling", "Small piece of dough filled with meat or vegetables."),
    ("Friedrice", "Rice stir-fried with vegetables and often egg or meat."),
    # Desserts & drinks
    ("ICECREAM", "Frozen dessert made from dairy and sugar."),
    ("SUNDAE", "Ice cream with toppings and sauce."),
    ("COOKIE", "Sweet flat snack baked in the oven."),
    ("BROWNIE", "Dense chocolate square dessert."),
    ("CUPCAKE", "Small individual cake with frosting."),
    ("PIE", "Baked dish with a pastry crust and filling."),
    ("CAKE", "Sweet baked dessert often served at celebrations."),
    ("PUDDING", "Sweet dessert with a creamy texture."),
    ("TART", "Pastry shell filled with fruit or custard."),
    ("GINGERBREAD", "Spiced cookie often shaped into figures."),
    ("CROISSANT", "Flaky crescent-shaped French pastry."),
    ("BAGEL", "Ring-shaped bread roll."),
    ("WAFFLE", "Crispy grid-patterned cake from a waffle iron."),
    ("SHAKE", "Cold drink made by blending milk and ice cream."),
    ("LEMONADE", "Sweet and sour drink made from lemons."),
    ("TEA", "Hot or cold drink made from steeped leaves."),
    ("COFFEE", "Hot caffeinated morning drink."),
    ("JUICE", "Drink made from pressed fruit."),
    ("WATER", "Clear drink essential for life."),
    ("SMOOTHIE", "Thick blended drink made from fruit."),
    # Fruit
    ("APPLE", "Red or green fruit that grows on trees."),
    ("ORANGE", "Citrus fruit that is round and orange."),
    ("GRAPES", "Small round fruit that grow in bunches."),
    ("MANGO", "Sweet tropical stone fruit."),
    ("PEACH", "Fuzzy fruit with a large pit."),
    ("PLUM", "Small round fruit with smooth skin."),
    ("CHERRY", "Small red or black fruit with a pit."),
    ("LEMON", "Yellow sour citrus fruit."),
    ("BANANA", "Long yellow fruit."),
    ("STRAWBERRY", "Red berry with tiny seeds on the outside."),
    ("BLUEBERRY", "Small blue fruit popular in muffins."),
    ("WATERMELON", "Large green melon with red flesh."),
    ("PINEAPPLE", "Tropical fruit with spiky skin."),
    ("KIWI", "Small brown fruit with green flesh."),
    ("GRAPEFRUIT", "Large sour citrus fruit."),
    ("AVOCADO", "Creamy green fruit used in guacamole."),
    ("PAPAYA", "Tropical fruit with orange flesh."),
    ("PEAR", "Sweet fruit with a rounded bottom."),
    ("POMEGRANATE", "Fruit with many edible seeds inside."),
]

NATURE_PACK: list[tuple[str, str]] = [
    # Weather conditions
    ("WEATHER", "Day-to-day conditions of the atmosphere."),
    ("SUNNY", "Clear and bright with plenty of sunshine."),
    ("CLOUDY", "Sky covered with clouds."),
    ("RAINY", "Having a lot of rain falling."),
    ("STORM", "Violent weather with thunder and lightning."),
    ("WINDY", "Having strong moving air."),
    ("FOGGY", "Weather with thick cloud near the ground."),
    ("SNOW", "Frozen precipitation falling as white flakes."),
    ("HAIL", "Ice balls that fall from clouds during storms."),
    ("SLEET", "Partly frozen rain."),
    ("MISTY", "Fine water droplets in the air making visibility low."),
    ("TEMPERATURE", "How hot or cold the air is, measured in degrees."),
    ("HUMIDITY", "Amount of moisture in the air."),
    ("FORECAST", "Prediction of what the weather will be."),
    ("MELTDOWN", "Snow and ice turning to water as it warms."),
    # Severe weather
    ("HURRICANE", "Large powerful tropical storm with very strong winds."),
    ("TORNADO", "Violently rotating column of air reaching the ground."),
    ("BLIZZARD", "Severe snowstorm with very strong winds."),
    ("AVALANCHE", "Mass of snow sliding rapidly down a mountain."),
    ("LIGHTNING", "Flash of bright light in the sky during a storm."),
    ("THUNDER", "Loud sound that follows lightning."),
    ("FLOOD", "Overflow of water onto normally dry land."),
    ("DROUGHT", "Extended period of abnormally low rainfall."),
    ("HEATWAVE", "Period of unusually hot weather."),
    ("MONSOON", "Seasonal wind bringing heavy rainfall."),
    # Land environments
    ("ECOSYSTEM", "Community of living things and their environment."),
    ("RAINFOREST", "Dense tropical forest with heavy rainfall."),
    ("SAVANNA", "Grassland with scattered trees in a warm region."),
    ("DESERT", "Very dry area with little rainfall."),
    ("TUNDRA", "Flat frozen Arctic region with little vegetation."),
    ("MEADOW", "Open grassy field, often with wildflowers."),
    ("SWAMP", "Wetland dominated by trees and standing water."),
    ("MARSH", "Wetland with grasses and shallow water."),
    ("GLACIER", "Massive body of slow-moving ice in cold regions."),
    ("VOLCANO", "Mountain that can erupt with lava and ash."),
    ("EARTHQUAKE", "Shaking of the ground caused by shifting rocks."),
    ("OASIS", "Green area in a desert where water is found."),
    ("VALLEY", "Low area between hills or mountains."),
    ("CANYON", "Deep narrow valley with steep rocky sides."),
    # Plants
    ("TREE", "Tall plant with a trunk, branches, and leaves."),
    ("OAK", "Large sturdy tree with acorns."),
    ("PINE", "Cone-bearing evergreen tree with needle-like leaves."),
    ("MAPLE", "Tree known for maple syrup and colorful fall leaves."),
    ("PALM", "Tropical tree with large fronds at the top."),
    ("BAMBOO", "Tall fast-growing plant with hollow stems."),
    ("GRASS", "Green plants that cover lawns and fields."),
    ("MOSS", "Small soft plant that grows in damp and shady places."),
    ("FERN", "Green plant with feather-like fronds and no flowers."),
    ("MUSHROOM", "Fungus with a cap and stem, often growing in shade."),
    ("CACTUS", "Desert plant with spines instead of leaves."),
    ("SUNFLOWER", "Tall flower that tracks the sun across the sky."),
    ("ROSE", "Fragrant flower often given as a gift."),
    ("DAISY", "Simple white flower with a yellow center."),
    ("DAFFODIL", "Yellow spring flower shaped like a trumpet."),
    ("TULIP", "Cup-shaped spring flower in many bright colors."),
    ("LILAC", "Shrub with fragrant purple or white flowers."),
    ("IVY", "Climbing plant with lobed dark green leaves."),
    ("BLOSSOM", "Flower appearing on a plant in spring."),
    ("ACORN", "Nutmeg-sized seed of the oak tree."),
    ("POLLEN", "Fine powder produced by flowers to fertilize seeds."),
    ("SEED", "Small object produced by a plant that grows into a new plant."),
    ("ROOTS", "Part of a plant that grows underground and absorbs water."),
    ("PETAL", "Colored leaf of a flower."),
    ("PINEAPPLE", "Tropical fruit with spiky skin on the outside."),
    # Insects
    ("BUTTERFLY", "Insect with colorful patterned wings."),
    ("DRAGONFLY", "Insect with two pairs of transparent wings."),
    ("HONEYBEE", "Insect that makes honey in a hive."),
    ("GRASSHOPPER", "Insect that jumps using its long legs."),
    ("MOSQUITO", "Small flying insect that bites and drinks blood."),
    ("LADYBUG", "Small red beetle with black spots."),
    ("BEETLE", "Insect with a hard shell covering its wings."),
    ("CATERPILLAR", "Worm-like larva of a butterfly or moth."),
    ("EARTHWORM", "Worm that lives in soil and helps plants grow."),
    ("ANTS", "Small insects that live in large organized groups."),
    ("WORM", "Long boneless creature that lives in soil."),
    ("SNAIL", "Mollusk with a spiral shell that moves slowly."),
    ("SLUG", "Mollusk similar to a snail but without a shell."),
    # Sea life
    ("OCTOPUS", "Sea creature with eight arms and a soft body."),
    ("SEAHORSE", "Small fish with a horse-shaped head."),
    ("CORAL", "Marine organism that builds reefs in warm seas."),
    ("JELLYFISH", "Sea creature with a jelly-like body and stinging tentacles."),
    ("STARFISH", "Sea creature with five arms shaped like a star."),
    ("CRAB", "Sea animal that walks sideways on ten legs."),
    ("LOBSTER", "Sea animal with large claws and a long body."),
    ("WHALE", "Very large sea mammal that breathes air."),
    ("DOLPHIN", "Intelligent sea mammal known for jumping."),
    ("SHARK", "Large fish with sharp teeth."),
    ("PENGUIN", "Flightless bird that lives in cold waters."),
    ("SEAL", "Sea mammal with flippers that comes ashore to rest."),
    ("WALRUS", "Large sea mammal with long tusks."),
    ("TURTLE", "Sea reptile with a shell that swims in the ocean."),
    # Land wildlife
    ("ELEPHANT", "Very large gray animal with a long trunk."),
    ("TIGER", "Large wild cat with orange coat and black stripes."),
    ("MONKEY", "Primate that often lives in trees and swings."),
    ("GIRAFFE", "Tallest land animal with a very long neck."),
    ("ZEBRA", "African animal with black and white stripes."),
    ("KANGAROO", "Australian animal that hops on strong back legs."),
    ("GORILLA", "Large powerful African ape with dark fur."),
    ("PANDA", "Black and white bear from China."),
    ("KOALA", "Australian marsupial that lives in eucalyptus trees."),
    ("SNAKE", "Long reptile with no legs that slides along the ground."),
    ("LIZARD", "Reptile with four legs that basks in the sun."),
    ("FROG", "Amphibian that jumps and lives near water."),
    ("TOAD", "Bumpier amphibian that lives mostly on land."),
    ("SPIDER", "Eight-legged creature that spins silk webs."),
    ("BAT", "Flying mammal that is active at night."),
    ("FOX", "Wild dog-like animal with a bushy pointed tail."),
    ("DEER", "Wild animal with antlers, found in forests."),
    ("WOLF", "Wild dog that lives and hunts in a group called a pack."),
    ("BEAR", "Large furry animal found in forests."),
    ("RABBIT", "Small animal with long ears that hops."),
    ("SQUIRREL", "Small furry animal that climbs trees and stores nuts."),
    ("BIRD", "Animal with feathers that can fly."),
    ("EAGLE", "Large bird of prey with a hooked beak."),
    ("OWL", "Night bird with large eyes that hunts at night."),
    ("PARROT", "Colorful bird that can copy sounds."),
    ("PELICAN", "Large water bird with a big pouch for catching fish."),
    ("SALMON", "Fish that swims upstream to lay eggs."),
    ("TROUT", "Freshwater fish popular for fishing."),
]

TECHNOLOGY_PACK: list[tuple[str, str]] = [
    # Input & Output Devices
    ("KEYBOARD", "Input device with keys for typing."),
    ("MONITOR", "Screen that displays computer output."),
    ("MOUSE", "Handheld device that controls the cursor."),
    ("PRINTER", "Machine that produces printed copies."),
    ("SPEAKER", "Device that produces sound."),
    ("WEBCAM", "Camera that sends live video over the internet."),
    ("HEADPHONES", "Wearables that play audio privately."),
    ("SCANNER", "Device that digitizes printed documents."),
    ("PROJECTOR", "Device that projects images onto a screen."),
    ("TOUCHSCREEN", "Display that responds to finger contact."),
    ("MICROPHONE", "Device that captures sound for recording or calls."),
    ("WEBCAMERA", "Camera for live video on a computer."),
    ("PLOTTER", "Printer that draws lines using pens."),
    # Computing Hardware
    ("LAPTOP", "Portable personal computer that folds shut."),
    ("DESKTOP", "Stationary computer that sits on a desk."),
    ("TABLET", "Flat touchscreen computer."),
    ("SMARTPHONE", "Mobile phone with internet and apps."),
    ("PROCESSOR", "Chip that performs calculations."),
    ("MEMORY", "Temporary space where the computer holds active data."),
    ("STORAGE", "Space to save files and data."),
    ("HARDWARE", "Physical parts of a computer."),
    ("MOTHERBOARD", "Main circuit board inside a computer."),
    ("GRAPHICS", "Hardware that renders images and video."),
    ("FAN", "Cooling component inside a computer."),
    ("POWER", "Supply unit that distributes electricity to components."),
    ("BATTERY", "Device that stores and provides electrical power."),
    ("CHARGING", "Restoring power to a battery."),
    ("CABLE", "Wire used to connect devices together."),
    ("ADAPTER", "Device that converts one connection type to another."),
    ("CHIP", "Small piece of silicon with electronic circuits."),
    ("CIRCUIT", "Path that electricity flows through."),
    # Software & Applications
    ("SOFTWARE", "Programs and applications on a computer."),
    ("PROGRAM", "Set of instructions that tells a computer what to do."),
    ("CODING", "Writing instructions for computers."),
    ("DEBUGGING", "Finding and fixing errors in code."),
    ("ALGORITHM", "Step-by-step instructions for solving a problem."),
    ("FIRMWARE", "Software permanently stored in hardware."),
    ("BROWSER", "App used to view websites."),
    ("WEBSITE", "Collection of pages on the internet."),
    ("DATABASE", "Organized collection of stored information."),
    ("MALWARE", "Software designed to harm or spy on computers."),
    ("ANTIVIRUS", "Software that detects and removes malware."),
    ("FIREWALL", "Security system that monitors network traffic."),
    ("BACKUP", "Copy of data kept for safekeeping."),
    ("UPDATE", "New version of software that adds features or fixes bugs."),
    ("UPGRADE", "Better version of hardware or software."),
    # Internet & Networking
    ("INTERNET", "Global network connecting computers worldwide."),
    ("EMAIL", "Electronic messages sent over the internet."),
    ("WIRELESS", "Using radio signals instead of wires."),
    ("BLUETOOTH", "Short-range wireless technology."),
    ("ETHERNET", "Wired network connection."),
    ("ROUTER", "Device that directs internet traffic."),
    ("MODEM", "Device that connects a network to the internet."),
    ("WIFI", "Wireless local area network technology."),
    ("BANDWIDTH", "Amount of data that can be transmitted per second."),
    ("SERVER", "Computer that provides data to other computers."),
    ("CLOUD", "Remote storage and services accessed over the internet."),
    ("STREAMING", "Playing audio or video over the internet."),
    ("PODCAST", "Audio series available for download."),
    ("DOWNLOAD", "Transferring data from the internet to your device."),
    ("UPLOAD", "Sending data from your device to the internet."),
    ("BROADBAND", "High-speed internet connection."),
    # User Accounts & Security
    ("PASSWORD", "Secret word or phrase used to access accounts."),
    ("USERNAME", "Unique name used to identify an account."),
    ("AVATAR", "Picture representing a user online."),
    ("LOGIN", "Process of signing into an account."),
    ("LOGOUT", "Process of signing out of an account."),
    ("ENCRYPT", "Converting data into a secure format."),
    ("DECRYPT", "Converting encrypted data back to readable form."),
    ("HACKER", "Person who tries to break into computer systems."),
    ("SPAM", "Unwanted or junk messages sent in bulk."),
    ("PHISHING", "Fraudulent attempt to steal personal information."),
    # Digital Media
    ("PIXEL", "Smallest unit of a digital image."),
    ("RESOLUTION", "Number of pixels in a display or image."),
    ("CAMERA", "Device that captures still or video images."),
    ("PHOTO", "Digital image taken with a camera."),
    ("VIDEO", "Moving visual content."),
    ("AUDIO", "Sound content in digital form."),
    ("MUSIC", "Sound organized as melody and rhythm."),
    ("PODCAST", "Digital audio file series available online."),
    ("SCREENSHOT", "Image captured of what is shown on a screen."),
    # Mobile & Apps
    ("APP", "Application software on a phone or tablet."),
    ("NOTIFICATION", "Alert sent by an app on a device."),
    ("BATTERY", "Stored power source in a mobile device."),
    ("SCREEN", "Display surface of a device."),
    ("BLUETOOTH", "Wireless technology for short-range connections."),
    ("TEXTING", "Sending written messages from a phone."),
    ("VOICEMAIL", "Recorded audio message left on a phone."),
    ("CALENDAR", "Digital schedule showing dates and events."),
    ("CLOCK", "Digital timekeeping feature on a device."),
    ("ALARM", "Alert set to go off at a specific time."),
    # Data & Files
    ("FOLDER", "Container for organizing files on a computer."),
    ("FILE", "Named collection of data stored on a computer."),
    ("DOCUMENT", "File containing text or formatted content."),
    ("SPREADSHEET", "File with data organized in rows and columns."),
    ("PRESENTATION", "File showing slides for a talk or lecture."),
    ("ARCHIVE", "Compressed collection of stored files."),
    ("COMPRESS", "Reducing the size of a file."),
    ("EXTRACT", "Removing files from a compressed archive."),
    # Miscellaneous
    ("ARTIFICIAL", "Made by human skill rather than occurring naturally."),
    ("MACHINE", "Device with moving parts that performs work."),
    ("ROBOT", "Machine that can be programmed to carry out tasks."),
    ("AUTOMATION", "Use of machines to perform tasks without human input."),
    ("SATELLITE", "Object orbiting Earth that relays communications."),
    ("SIGNAL", "Electrical or radio wave that carries information."),
    ("BROADCAST", "Sending content to many receivers at once."),
    ("DIGITAL", "Using electronic signals for data."),
    ("ONLINE", "Connected to the internet."),
    ("OFFLINE", "Not connected to the internet."),
    ("REBOOT", "Restarting a computer or device."),
    ("SHUTDOWN", "Turning off a computer or device."),
    ("STARTUP", "Initial loading of a computer system."),
    ("NETWORK", "Group of connected computers and devices."),
    ("SYNC", "Synchronizing data between devices."),
]

ACTIVITIES_PACK: list[tuple[str, str]] = [
    # Outdoor & Adventure
    ("HIKING", "Walking in nature for pleasure along trails."),
    ("CAMPING", "Sleeping outdoors in a tent for recreation."),
    ("FISHING", "Catching fish with a rod and line."),
    ("CYCLING", "Riding a bicycle for sport or transport."),
    ("JOGGING", "Running at a steady gentle pace for exercise."),
    ("SKIING", "Sliding over snow on long narrow boards."),
    ("SNOWBOARDING", "Gliding down snowy slopes on a single board."),
    ("SURFING", "Riding ocean waves on a board."),
    ("SWIMMING", "Moving through water using arms and legs."),
    ("DIVING", "Plunging into water headfirst with control."),
    ("SAILING", "Propelling a boat using wind in the sails."),
    ("ROWING", "Propelling a boat using oars."),
    ("KAYAKING", "Paddling a small boat through water."),
    ("CLIMBING", "Going upward using hands and feet."),
    ("ROCKCLIMBING", "Ascending rock faces using specialized equipment."),
    ("SKATING", "Moving on ice or hard surfaces wearing blade shoes."),
    ("ICE-skating", "Skating on a frozen rink or pond."),
    ("SKATEBOARDING", "Riding a board with wheels for tricks or transport."),
    ("BIRDING", "Observing and identifying wild birds."),
    ("STARGAZING", "Observing stars and planets in the night sky."),
    ("ASTRONOMY", "Study of celestial objects and space."),
    ("TREKKING", "Long-distance walking through natural terrain."),
    ("SAFARI", "Trip to observe wild animals in their natural habitat."),
    ("RAFTING", "Navigating rapids in an inflatable boat."),
    ("SPELUNKING", "Exploring caves as a hobby."),
    ("PARAGLIDING", "Flying through the air using a parachute-like wing."),
    ("SCUBADIVING", "Diving underwater using a breathing apparatus."),
    ("WILDLIFE", "Watching and photographing wild animals."),
    # Team Sports
    ("BASEBALL", "Team sport played with a bat and ball."),
    ("BASKETBALL", "Team sport shooting a ball through a hoop."),
    ("FOOTBALL", "Team sport involving carrying and throwing an oval ball."),
    ("SOCCER", "Team sport played by kicking a ball into a goal."),
    ("VOLLEYBALL", "Team sport hitting a ball over a net."),
    ("TENNIS", "Racket sport played on a court with a net."),
    ("BADMINTON", "Racket sport played with a shuttlecock."),
    ("HOCKEY", "Team sport played with sticks and a puck or ball."),
    ("RUGBY", "Team sport involving carrying an oval ball."),
    ("CRICKET", "Team bat-and-ball sport played with wickets."),
    ("LACROSSE", "Team sport using nets on sticks to score goals."),
    ("GOLF", "Game of hitting a ball into a series of holes."),
    ("BOWLING", "Rolling a heavy ball toward pins to knock them down."),
    ("DARTS", "Game of throwing missiles at a circular target."),
    ("ARCHERY", "Sport of shooting arrows at a target."),
    ("BOXING", "Combat sport using fists in padded gloves."),
    ("WRESTLING", "Combat sport of grappling and pinning."),
    ("JUDO", "Japanese martial art and Olympic sport."),
    ("KARATE", "Japanese martial art emphasizing strikes."),
    ("TAEKWONDO", "Korean martial art emphasizing kicks."),
    ("FENCING", "Sport of fighting with swords."),
    ("SOFTBALL", "Team sport similar to baseball with a larger ball."),
    ("HANDBALL", "Team sport throwing a ball into a goal with hands."),
    ("PINGPONG", "Table tennis game played with small paddles."),
    ("RACQUETBALL", "Indoor racquet sport played in a room."),
    # Arts & Crafts
    ("PAINTING", "Creating art using colors on a surface."),
    ("DRAWING", "Making pictures with pencils, pens, or charcoal."),
    ("SCULPTING", "Creating three-dimensional art from material."),
    ("POTTERY", "Making ceramic objects on a potter's wheel."),
    ("CROCHETING", "Making fabric using a hooked needle."),
    ("KNITTING", "Making fabric by interlocking loops of yarn."),
    ("WEAVING", "Interlacing threads to make fabric."),
    ("ORIGAMI", "Art of folding paper into shapes."),
    ("CALLIGRAPHY", "Beautiful and decorative handwriting."),
    ("LEATHERCRAFT", "Making items from leather."),
    ("MOSAIC", "Art of creating images from small colored pieces."),
    # Music & Performance
    ("SINGING", "Making music with the voice."),
    ("DANCING", "Moving rhythmically to express or for exercise."),
    ("KARAOKE", "Singing along to recorded music for fun."),
    ("GUITAR", "Playing a stringed musical instrument."),
    ("PIANO", "Playing a keyboard instrument with black and white keys."),
    ("DRUMS", "Playing a percussion instrument."),
    ("VIOLIN", "Playing a string instrument held against the shoulder."),
    ("TRUMPET", "Playing a brass wind instrument."),
    ("THEATER", "Acting and performing on a stage."),
    ("MAGIC", "Performing illusions and tricks for entertainment."),
    ("BAND", "Group of musicians playing together."),
    ("CHORUS", "Large group of singers performing together."),
    ("FLUTE", "Woodwind instrument played by blowing across a hole."),
    # Games & Puzzles
    ("BOARDGAMES", "Games played on a flat surface with pieces and rules."),
    ("CHESS", "Strategy board game played by two players."),
    ("CHECKERS", "Board game of jumping pieces diagonally."),
    ("CARDS", "Playing card games for fun or competition."),
    ("PUZZLES", "Games that test thinking and problem-solving."),
    ("CROSSWORD", "Word puzzle with clues for answers."),
    ("SUDOKU", "Number puzzle on a grid."),
    ("VIDEOGAMES", "Electronic games played on a screen."),
    ("MONOPOLY", "Classic board game about buying property."),
    ("SCRABBLE", "Word game forming words from letter tiles."),
    # Domestic & Practical
    ("COOKING", "Preparing food by applying heat."),
    ("BAKING", "Cooking using dry heat in an oven."),
    ("GRILLING", "Cooking food over an open flame or hot coals."),
    ("BREWING", "Making beer or other beverages by fermentation."),
    ("GARDENING", "Growing and tending plants and flowers."),
    ("CLEANING", "Making a place tidy and free of dirt."),
    ("REPAIR", "Fixing something that is broken."),
    ("WOODWORK", "Craft of making things from wood."),
    ("JEWELRY", "Making decorative items to wear."),
    ("CANDLE", "Handcraft of pouring wax into a mold to produce lights."),
    ("PAPERCRAFT", "Creating art and decorations from paper."),
    ("SEWING", "Stitching fabric together to make clothing."),
    # Relaxation & Wellness
    ("YOGA", "Discipline combining breath, meditation, and physical poses."),
    ("MEDITATION", "Practice of focusing the mind for relaxation."),
    ("MASSAGE", "Rubbing muscles to relieve tension and pain."),
    ("READING", "Looking at written words to understand them."),
    ("WRITING", "Putting thoughts into written form."),
    ("JOURNALING", "Writing personal thoughts and experiences in a diary."),
    ("FISHING", "Catching fish as a hobby or food source."),
    ("PICNICKING", "Eating a meal outdoors in a scenic place."),
    ("GEOCACHING", "Treasure-hunting game using GPS coordinates."),
    ("BIKING", "Riding a bicycle for fun or exercise."),
    ("WALKING", "Moving on foot at a relaxed pace."),
    ("RELAXING", "Resting and unwinding after activity."),
]

PLACES_PACK: list[tuple[str, str]] = [
    # Travel & Transportation Hubs
    ("AIRPORT", "Place where airplanes take off and land."),
    ("HARBOR", "Place where ships anchor and load or unload cargo."),
    ("TRAINSTATION", "Building where trains stop to pick up passengers."),
    ("BUSSTATION", "Central location for bus routes and passengers."),
    ("SUBWAY", "Underground railway system in a city."),
    ("STADIUM", "Large venue for sporting events and concerts."),
    ("ARENA", "Indoor venue for sports and entertainment."),
    ("PLAYGROUND", "Outdoor area with equipment for children's play."),
    ("PARKINGLOT", "Paved area where vehicles are left temporarily."),
    ("GASSTATION", "Place where vehicles refuel with gasoline or diesel."),
    ("TERMINAL", "Building at an airport or station for passengers."),
    ("DOCK", "Platform at a harbor for loading and unloading ships."),
    # Buildings & Institutions
    ("LIBRARY", "Place where books are stored and borrowed."),
    ("MUSEUM", "Building where artifacts and art are displayed."),
    ("HOSPITAL", "Place where sick people receive medical care."),
    ("CLINIC", "Medical facility for outpatient treatment."),
    ("SCHOOL", "Place where children go to learn."),
    ("UNIVERSITY", "Higher education institution with many faculties."),
    ("COLLEGE", "Post-secondary school offering degrees."),
    ("LIGHTHOUSE", "Tower that emits light to guide ships at sea."),
    ("CASTLE", "Fortified residence from medieval times."),
    ("TOWER", "Tall narrow building or structure."),
    ("SKYSCRAPER", "Very tall office or apartment building."),
    ("CATHEDRAL", "Large important Christian church."),
    ("MOSQUE", "Islamic place of worship."),
    ("SYNAGOGUE", "Jewish place of worship."),
    ("CHURCH", "Christian place of worship."),
    ("TEMPLE", "Sacred building used for worship."),
    ("TOWNHALL", "Building where local government conducts business."),
    ("PRISON", "Building where convicted people serve sentences."),
    ("COURTHOUSE", "Building where legal trials take place."),
    ("FIREHOUSE", "Station where firefighters and their equipment are based."),
    ("POLICESTATION", "Building where police officers work and are based."),
    ("POSTOFFICE", "Place where mail is collected and distributed."),
    ("BANK", "Building where money is stored and financial services offered."),
    ("GYMNASIUM", "Building with equipment for physical exercise."),
    # Shops & Markets
    ("RESTAURANT", "Place where meals are prepared and served to customers."),
    ("CAFETERIA", "Self-service restaurant in schools or offices."),
    ("CAFE", "Small restaurant serving coffee and light meals."),
    ("BAKERY", "Shop that makes and sells bread and pastries."),
    ("BUTCHER", "Shop that sells meat."),
    ("GROCERY", "Store selling food and household items."),
    ("SUPERMARKET", "Large self-service store selling food and goods."),
    ("CONVENIENCESTORE", "Small store open long hours for quick purchases."),
    ("DRUGSTORE", "Pharmacy that also sells toiletries and medicines."),
    ("BOOKSTORE", "Shop that sells books and magazines."),
    ("TOYSTORE", "Shop that sells games and toys."),
    ("CLOTHINGSTORE", "Shop selling garments and accessories."),
    ("HARDWARESTORE", "Shop selling tools and building supplies."),
    ("FLORIST", "Shop that sells flowers and plants."),
    ("JEWELRYSTORE", "Shop that sells jewelry and watches."),
    ("MARKET", "Open area where vendors sell goods."),
    # Nature & Outdoor Locations
    ("BEACH", "Sandy or pebbly shore beside the sea."),
    ("ISLAND", "Land area surrounded entirely by water."),
    ("MOUNTAIN", "Very high landform rising steeply above surroundings."),
    ("VALLEY", "Low area between hills or mountains."),
    ("CANYON", "Deep narrow valley with steep sides."),
    ("DESERT", "Dry region with very little rainfall."),
    ("JUNGLE", "Dense tropical forest with heavy vegetation."),
    ("VILLAGE", "Small settlement, smaller than a town."),
    ("TOWN", "Settlement larger than a village but smaller than a city."),
    ("CITY", "Large populated urban area."),
    ("CAPITAL", "City where a government's officials work."),
    ("FOREST", "Large area covered with trees."),
    ("MEADOW", "Open grassy field with wildflowers."),
    ("SWAMP", "Wetland dominated by trees and standing water."),
    ("LAKE", "Large body of freshwater surrounded by land."),
    ("POND", "Small body of still freshwater."),
    # Recreation & Entertainment
    ("CINEMA", "Place where movies are shown to audiences."),
    ("THEATER", "Building where plays and live performances are shown."),
    ("CONCERTHALL", "Specially designed building for musical performances."),
    ("ZOO", "Place where wild animals are kept for public viewing."),
    ("AQUARIUM", "Building where aquatic animals and plants are displayed."),
    ("AMUSEMENTPARK", "Large park with rides and entertainment attractions."),
    ("WATERPARK", "Park featuring water slides and swimming pools."),
    ("GALLERY", "Room or building where art is displayed and sold."),
    ("LIBRARY", "Public building with books available to borrow."),
    ("STADIUM", "Large venue for sporting events and concerts."),
    ("RINK", "Ice arena for skating and hockey."),
    # Nature & Landmarks
    ("BRIDGE", "Structure built to span a physical obstacle."),
    ("TUNNEL", "Underground passage through an obstacle."),
    ("CROSSWALK", "Marked path for pedestrians crossing a road."),
    ("INTERSECTION", "Place where two or more roads meet."),
    ("HIGHWAY", "Major road connecting cities."),
    ("BOULEVARD", "Wide city street often with trees."),
    ("ALLEY", "Narrow passageway between or behind buildings."),
    ("SIDEWALK", "Paved path for pedestrians alongside a road."),
    ("MONUMENT", "Structure built to commemorate a person or event."),
    ("FOUNTAIN", "Water feature built for decoration."),
    # Accommodation
    ("HOTEL", "Building where travelers pay for lodging."),
    ("MOTEL", "Roadside hotel designed for drivers."),
    ("HOSTEL", "Low-cost shared accommodation for travelers."),
    ("INN", "Small hotel or tavern providing lodging."),
    ("RESORT", "Vacation facility with amenities and activities."),
    ("CAMPGROUND", "Designated area for pitching tents and camping."),
    ("VACATION", "Place where people go for rest and recreation."),
    # Agricultural & Industrial
    ("GREENHOUSE", "Building with glass walls for growing plants."),
    ("STABLE", "Building where horses are kept."),
    ("BARN", "Farm building used for storing grain and housing animals."),
    ("FARM", "Land used for growing crops and raising animals."),
    ("ORCHARD", "Planted area of fruit trees."),
    ("VINEYARD", "Farm where grapes are grown for wine."),
    ("FACTORY", "Building where goods are manufactured."),
    ("WAREHOUSE", "Large building for storing goods."),
    ("POWERPLANT", "Facility that generates electricity."),
    ("RECYCLINGCENTER", "Place where recyclable materials are processed."),
    ("LANDFILL", "Designated site for disposing of waste."),
    ("QUARRY", "Place where stone is extracted from the ground."),
    # Medical & Emergency
    ("AMBULANCE", "Vehicle that transports sick people to hospital."),
    ("PHARMACY", "Shop where medicines are prepared and sold."),
    ("REHABILITATION", "Center where people recover from illness or injury."),
    ("CEMETERY", "Place where dead bodies are buried."),
    ("CHAPEL", "Small church or room for private worship."),
]

SEASONS_PACK: list[tuple[str, str]] = [
    # The four seasons
    ("SPRING", "Season when flowers bloom and animals wake from hibernation."),
    ("SUMMER", "Warmest and longest season of the year."),
    ("AUTUMN", "Season when leaves fall and temperatures start to drop."),
    ("WINTER", "Coldest season of the year, often with snow."),
    # Solar events
    ("EQUINOX", "Day when day and night are equal in length."),
    ("SOLSTICE", "Day of maximum or minimum daylight in the year."),
    ("SUNRISE", "Time each morning when the sun comes up."),
    ("SUNSET", "Time each evening when the sun goes down."),
    ("TWILIGHT", "Soft light just before sunrise or just after sunset."),
    ("DAYLIGHT", "Natural light that comes from the sun."),
    ("MIDNIGHT", "Twelve oclock at night, in the middle of darkness."),
    ("NOON", "Twelve oclock in the middle of the day."),
    ("TIMEZONE", "Region of the world with a uniform standard time."),
    # Spring activities
    ("PLANTING", "Putting seeds or young plants into soil."),
    ("BLOSSOM", "Flower or spray of flowers appearing on a tree."),
    ("BLOOM", "Flower or the state of a plant being in flower."),
    ("POLLEN", "Fine yellow powder produced by flowers."),
    ("BEEKEEPER", "Person who keeps bees to collect honey."),
    ("RAINBOW", "Colorful arc that appears in the sky after rain."),
    ("TADPOLE", "Young frog that lives in water."),
    ("EGG", "Oval object laid by birds, associated with Easter."),
    ("BASKET", "Container often filled with treats at Easter."),
    # Summer activities
    ("SWIMMING", "Moving through water for sport or recreation."),
    ("PICNIC", "Meal eaten outdoors in a scenic location."),
    ("BBQ", "Cooking food outdoors on a grill."),
    ("BEACH", "Sandy or pebbly shore beside the sea."),
    ("VACATION", "Planned trip away from home for rest."),
    ("CAMPFIRE", "Fire built outdoors for warmth or cooking."),
    ("FERN", "Green plant with feather-like fronds found in forests."),
    ("DRAGONFLY", "Insect with two pairs of transparent wings near water."),
    ("FIREFLY", "Glowing insect that lights up at night."),
    ("SUNSCREEN", "Lotion that protects skin from sunburn."),
    ("OUTDOOR", "Activities and sports played in the open air."),
    # Autumn activities
    ("HARVEST", "Gathering of ripe crops from the fields."),
    ("RAKING", "Gathering fallen leaves into piles."),
    ("APPLE", "Red or green fruit often picked in autumn."),
    ("PUMPKIN", "Orange gourd often carved at Halloween."),
    ("SCARECROW", "Straw figure set up to scare birds away from crops."),
    ("MIGRATION", "Seasonal movement of birds from one region to another."),
    ("ACORN", "Nut of the oak tree, found in autumn."),
    ("MAPLE", "Tree known for autumn leaf colors and syrup."),
    ("LEAVES", "Foliage that changes color and falls in autumn."),
    ("COAT", "Warm outer garment worn in cold weather."),
    # Winter activities
    ("SKIING", "Sliding over snow on long narrow boards."),
    ("SNOWBOARDING", "Gliding down snowy slopes on a single wide board."),
    ("SLEDDING", "Sliding down a snow-covered hill on a sled."),
    ("TUBING", "Riding an inner tube down a snowy slope."),
    ("SKATING", "Moving on ice wearing ice-skate shoes."),
    ("SNOWMAN", "Figure made from packed snow with sticks and stones."),
    ("SNOWFORT", "Shelter built from snow blocks and walls."),
    ("ICEBERG", "Large floating piece of frozen fresh water in the sea."),
    ("FROST", "Ice crystals that form on cold surfaces overnight."),
    ("ICICLE", "Pointed piece of ice hanging from a surface."),
    ("SHOVEL", "Tool used to remove snow from paths and driveways."),
    ("SLEIGH", "Vehicle that slides over snow, pulled by horses."),
    ("HOTCOCOA", "Warm chocolate drink served in winter."),
    # Winter wildlife
    ("HIBERNATION", "Deep sleep some animals enter to survive winter."),
    ("REINDEER", "Arctic deer used to pull sleighs."),
    ("POLARBEAR", "Large white bear that lives in the Arctic."),
    ("PENGUIN", "Flightless bird that lives in cold southern waters."),
    ("ARCTIC", "Region around the North Pole."),
    ("ANTARCTIC", "Region around the South Pole."),
    # Holiday vocabulary
    ("CHRISTMAS", "Christian holiday celebrated on December twenty-fifth."),
    ("HALLOWEEN", "Holiday on October thirty-first with costumes and candy."),
    ("EASTER", "Spring holiday celebrating new beginnings."),
    ("THANKSGIVING", "Autumn holiday celebrating the harvest."),
    ("VALENTINE", "Holiday on February fourteenth celebrating love."),
    ("NEWYEAR", "Celebration on January first marking a new calendar year."),
    ("CANDLE", "Cylinder of wax with a wick that produces a flame."),
    ("ORNAMENT", "Decorative item hung on a Christmas tree."),
    ("WREATH", "Circular decoration hung on a door, especially at Christmas."),
    ("CAROL", "Christmas song sung by groups of people."),
    ("FIREWORKS", "Explosive displays of light in the sky."),
    ("PARADE", "Procession of people marching with music and banners."),
    ("FESTIVAL", "Celebration with special activities, food, and music."),
    ("CARNIVAL", "Festive season with rides and entertainment before Lent."),
    ("LANTERN", "Container with a light source, used in celebrations."),
    ("FIRECRACKER", "Small explosive used to make noise during celebrations."),
    ("GIFT", "Present given to someone, especially at holidays."),
    ("STOCKING", "Long sock hung by the fireplace for Santa to fill."),
    ("TURKEY", "Bird traditionally served at Thanksgiving dinner."),
    ("PUMPKINPIE", "Sweet dessert made from pumpkin and spices."),
    ("GINGERBREAD", "Spiced cookie often shaped into figures at Christmas."),
    ("EGGNOG", "Creamy holiday drink made with milk and eggs."),
    ("TRICKORTREAT", "Halloween tradition of children asking for candy."),
    ("COSTUME", "Special clothing worn for dress-up, especially at Halloween."),
    # Winter landscape
    ("GLACIER", "Slowly moving mass of ice in cold regions."),
    ("PERMAFROST", "Permanently frozen layer of soil in polar regions."),
    ("TUNDRA", "Treeless Arctic region with frozen ground."),
    ("ICE", "Frozen water, solid and cold."),
    ("SNOWFLAKE", "Single crystal of frozen water that falls as snow."),
    ("BLIZZARD", "Severe snowstorm with very strong winds."),
    ("AVALANCHE", "Mass of snow sliding rapidly down a mountain."),
    ("LAVENDER", "Purple flowering plant associated with summer fields."),
    ("SUNFLOWER", "Tall yellow flower that grows in summer."),
    ("CACTUS", "Desert plant that survives hot dry seasons."),
    ("ROSE", "Fragrant flower that blooms in spring and summer."),
    ("DAISY", "Simple white flower with a yellow center."),
    ("ICESTORM", "Storm with freezing rain that coats surfaces in ice."),
    ("SLEET", "Partly frozen rain that bounces on surfaces."),
    ("BONFIRE", "Large outdoor fire used for celebrations."),
    ("TOURNAMENT", "Competition with many participants and rounds."),
    ("SPRINGBREAK", "Vacation period during spring, especially for students."),
    ("MIDSUMMER", "The period around the longest day of the year."),
    ("LEAPYEAR", "Year with an extra day, occurring every four years."),
]

# ---------------------------------------------------------------------------
# Office Supplies pack — office stationery, school supplies, desk items,
# and technology peripherals used in an office or classroom setting.
# ---------------------------------------------------------------------------
OFFICE_SUPPLIES: list[tuple[str, str]] = [
    # Writing instruments
    ("PENCIL", "Wooden instrument with graphite used for writing and drawing."),
    ("ERASER", "Rubber tool used to remove pencil marks."),
    ("PEN", "Writing instrument that uses ink to make marks."),
    ("MARKER", "Thick felt-tip instrument for bold writing or coloring."),
    ("HIGHLIGHTER", "Bright translucent marker used to emphasize text."),
    ("CRAYON", "Wax coloring stick used by children and artists."),
    ("CHALK", "White writing stick used on blackboards."),
    ("PENS", "Ink writing instruments plural."),
    # Paper and notebooks
    ("PAPER", "Sheet material used for writing and printing."),
    ("NOTEBOOK", "Bound collection of blank pages for writing."),
    ("PAD", "Stack of paper sheets glued at one edge."),
    ("FOLDER", "Paper holder with a clasp for storing documents."),
    ("FILE", "Container for organizing papers in an office."),
    ("CLIPBOARD", "Portable writing surface with a clip at the top."),
    ("BINDER", "Cover that holds loose papers together."),
    ("ENVELOPE", "Paper container for mailing letters."),
    ("LABEL", "Small paper tag for identifying items."),
    ("STICKYNOTE", "Small adhesive note for reminders."),
    ("INDEXCARD", "Small card for recording and filing information."),
    ("TRANSPARENCY", "Clear sheet used on overhead projectors."),
    # Fasteners and adhesives
    ("STAPLER", "Device that pushes metal staples through paper."),
    ("STAPLES", "Small metal clips used to fasten papers together."),
    ("TAPE", "Adhesive strip used for sealing or mounting."),
    ("GLUE", "Liquid adhesive used to bond materials together."),
    ("SCISSORS", "Cutting tool with two pivoted blades."),
    ("RULER", "Straight measuring tool marked in inches or centimeters."),
    ("RUBBERBAND", "Elastic loop used to hold items together."),
    ("PUSHPIN", "Small pointed tack for attaching papers to boards."),
    ("PAPERCLIP", "Bent wire clip for holding papers together."),
    # Desk furniture
    ("DESK", "Table or workspace for writing and office work."),
    ("CHAIR", "Seating furniture used at a desk."),
    ("LAMP", "Household object that provides light for reading."),
    ("CLOCK", "Device that shows the current time."),
    ("CALENDAR", "Chart showing days, weeks, and months of a year."),
    ("WHITEBOARD", "Erasable board used for writing and presentations."),
    ("BULLETINBOARD", "Board for pinning notices and announcements."),
    ("EASEL", "Stand that holds a board or canvas upright."),
    ("CABINET", "Storage unit with shelves and doors."),
    ("SHREDDER", "Machine that cuts paper into strips for disposal."),
    ("LAMINATOR", "Machine that coats paper in protective plastic."),
    ("PROJECTOR", "Device that displays images onto a screen."),
    # School and learning
    ("BACKPACK", "Carrying bag worn on the shoulders to school."),
    ("TEXTBOOK", "Official book used for studying a subject."),
    ("TEXTBOOKS", "Official books used for studying academic subjects."),
    ("PROTRACTOR", "Semi-circular tool for measuring and drawing angles."),
    ("COMPASS", "Drawing tool used to make accurate circles."),
    ("STUDY", "Reading and learning for school or work."),
    ("GRADE", "Mark given to a student for schoolwork."),
    ("LESSON", "Period of teaching on a particular subject."),
    ("ASSIGNMENT", "Task given by a teacher to be completed."),
    ("HOMEWORK", "Schoolwork assigned to be done at home."),
    ("EXAM", "Formal test to assess knowledge of a subject."),
    ("RECESS", "Break time when children play outside at school."),
    ("BELL", "Sound that signals the end of a class period."),
    # Calculators and office tech
    ("CALCULATOR", "Electronic device for performing arithmetic."),
    ("KEYBOARD", "Device with keys used to type on a computer."),
    ("MONITOR", "Screen that displays computer output."),
    ("MOUSE", "Handheld device used to move the computer cursor."),
    ("PRINTER", "Machine that produces paper copies of digital documents."),
    ("SCANNER", "Device that converts paper documents into digital images."),
    ("WEBCAM", "Camera used for video calls on a computer."),
    ("ROUTER", "Device that distributes internet to multiple computers."),
    ("ROUTERS", "Devices that distribute internet to multiple computers."),
    ("USBDRIVE", "Small flash memory device for storing files."),
    ("FLASHDRIVE", "Portable memory device that plugs into a computer."),
    ("LAPTOP", "Portable personal computer that folds shut."),
    ("TABLET", "Touchscreen portable computing device."),
    ("SPEAKER", "Device that produces sound from electronic signals."),
    ("SPEAKERS", "Devices that produce sound from electronic signals."),
    ("HEADPHONES", "Audio device worn over the ears to listen privately."),
    ("HEADSET", "Headphones with a microphone attached."),
    ("CHARGER", "Device used to replenish battery power."),
    ("CHARGERCABLE", "Cable that connects a device to its charger."),
    ("POWERSTRIP", "Extension cord with multiple outlets."),
    ("BATTERY", "Small power source for portable electronic devices."),
    # Organizers and filing
    ("DIARY", "Personal book for recording daily events and thoughts."),
    ("JOURNAL", "Notebook for writing entries over time."),
    ("PLANNER", "Book for scheduling and organizing tasks."),
    ("AGENDA", "List of items to be discussed at a meeting."),
    ("CALENDAR", "Chart showing the days weeks and months of a year."),
    ("SCHEDULE", "Plan that lists times for planned activities."),
    # Supplies for art and craft
    ("PAINTBRUSH", "Tool with bristles used to apply paint."),
    ("WATERCOLOR", "Paint that uses water as a medium."),
    ("PALETTE", "Board on which an artist mixes paints."),
    ("CANVAS", "Stretched fabric used as a surface for painting."),
    ("SKETCHBOOK", "Book of blank pages for drawing."),
    ("CRAFTPAPER", "Colored paper used for arts and crafts."),
    ("RIBBON", "Narrow strip of fabric used for decoration."),
    # Miscellaneous office
    ("INBOX", "Tray for receiving incoming documents and mail."),
    ("OUTBOX", "Tray for documents ready to be sent out."),
    ("STAMP", "Rubber tool used to imprint a design or message."),
    ("INK", "Colored liquid used in pens and printers."),
    ("TONER", "Powder used in laser printers to form text and images."),
    ("WASTEBASKET", "Container for throwing away trash."),
    ("CLASSDESK", "Desk used by students in a classroom."),
    ("TEACHER", "Person who helps students learn."),
    ("STUDENT", "Person who is studying at a school or university."),
    ("OFFICE", "Room or building for professional work."),
    ("CLASSDESK", "Desk used by students in a school classroom."),
]

# ---------------------------------------------------------------------------
# California Gold Rush vocabulary (1848–1855)
# Historically accurate, Easy-level clues covering:
# gold/ore, mining tools, techniques, important people, CA locations,
# trails, migration, camps, boomtowns, commerce, statehood, historical events
# ---------------------------------------------------------------------------

GOLD_RUSH: list[tuple[str, str]] = [
    # --- Gold and Ore ---
    ("GOLD", "Precious yellow metal discovered in California in 1848."),
    ("NUGGET", "A rough lump of gold found in a river or mine."),
    ("RIVER", "A stream where prospectors panned for gold along its banks."),
    ("MINE", "An underground or open pit for removing gold-bearing rock."),
    ("MARSHALL", "The man who found gold at Sutter's Mill in January 1848."),
    ("ORE", "Rock containing enough gold or silver to be worth mining."),
    ("SILVER", "Precious metal also sought during the Gold Rush era."),
    ("BULLION", "Gold or silver in the form of bars or ingots."),
    # --- Mining Tools ---
    ("PICKAXE", "Heavy tool with a pointed head used to break rock."),
    ("SHOVEL", "Tool with a broad blade for lifting dirt and gravel."),
    ("PAN", "Shallow metal bowl used to swirl dirt and separate gold."),
    ("SLUICE", "Long wooden trough where gold settles as water flows through."),
    ("ROCKER", "Small gold-washing device rocked back and forth."),
    ("DREDGE", "Machine that scoops gold-bearing mud from a riverbed."),
    ("CROWBAR", "Long metal bar used to pry apart rocks."),
    ("SIEVE", "Tool with small holes used to sift dirt for gold particles."),
    ("BUCKET", "Metal or wooden container used to carry dirt and water."),
    ("WINCH", "Machine with a rotating drum for raising buckets from a shaft."),
    ("LADDER", "Runged device used to climb into and out of a mine shaft."),
    ("HAMMER", "Tool used to drive stakes and break rock."),
    ("MATTOCK", "Tool with a pick-like head for loosening soil around gold."),
    # --- Mining Techniques ---
    ("PANNING", "Swirling dirt in a pan to separate gold from gravel."),
    ("PLACER", "Deposit of gold found in river gravel and sand."),
    ("DRIFT", "Horizontal tunnel dug into the side of a hill or mountain."),
    ("SHAFT", "Vertical hole dug straight down into the earth."),
    ("VEIN", "A thin layer of gold or ore embedded in rock."),
    ("QUARTZ", "Hard white mineral often found with gold."),
    ("TAILINGS", "Rocks and dirt left behind after gold is extracted."),
    ("SEDIMENT", "Layers of dirt and rock deposited by flowing water."),
    # --- Important People ---
    ("PROSPECTOR", "Person who searches for gold or other valuable minerals."),
    ("FORTY-NINER", "Person who went to California in 1849 seeking gold."),
    ("MINER", "A worker who finds precious metals in the earth."),
    ("JAMES MARSHALL", "The man who discovered gold at Sutter's Mill in 1848."),
    ("SUTTER", "Swiss rancher whose workers discovered the first California gold."),
    ("BANCROFT", "Historian who documented California's Gold Rush era."),
    # --- California Locations ---
    ("SACRAMENTO", "City that became a supply hub during the Gold Rush."),
    ("COLOMA", "The valley where James Marshall found gold at Sutter's Mill."),
    ("SIERRA", "Mountain range where most California gold was found."),
    ("YUBACITY", "One of the richest gold mining areas in California."),
    ("YUBA", "River and county that yielded tons of gold."),
    ("CALAVERAS", "Sierra foothills county that boomed with Gold Rush mining camps."),
    ("TUOLUMNE", "County in the Sierra Nevada that was a rich mining area."),
    ("MARIPOSA", "Southern Mother Lode county known for early quartz mining."),
    ("AMADOR", "Mother Lode county named during the California Gold Rush."),
    ("EL DORADO", "Spanish name meaning 'the golden one' - also a CA gold county."),
    ("BUTTE", "Northern California gold-mining county in the Sierra foothills."),
    # --- Trails and Migration ---
    ("EMIGRANT", "A person who leaves one region to settle in another."),
    ("TRAIL", "A path worn by people traveling to the gold fields."),
    ("PACKMULE", "A mule used to carry supplies over mountain trails."),
    ("WAGON", "Large four-wheeled vehicle pulled by oxen or mules."),
    ("OXEN", "Castrated bulls used to pull heavy wagons."),
    ("STAGECOACH", "Horse-drawn vehicle that carried passengers over long routes."),
    ("FERRY", "Boat used to carry people and supplies across rivers."),
    ("BLAZE", "A mark made on a tree to mark a trail through the wilderness."),
    ("SUMMIT", "The highest point of a mountain, such as over the Sierra."),
    ("PASS", "A route through mountains used by gold seekers."),
    # --- Camps and Boomtowns ---
    ("CAMP", "A temporary settlement of miners near a gold deposit."),
    ("BOOMTOWN", "A town that grew very quickly during the Gold Rush."),
    ("TENT", "Portable canvas shelter used by miners in early camps."),
    ("SHACK", "A small, roughly built cabin or shelter."),
    ("LOG", "A length of cut timber used in building cabins."),
    ("STORES", "Buildings where miners bought food, tools, and supplies."),
    ("SALOON", "A bar or drinking establishment popular in gold camps."),
    ("HOTEL", "A building that offered lodging to travelers and miners."),
    ("BUSH", "A shop or crude store set up in a mining camp."),
    ("RIGGING", "Ropes and equipment used to operate mining machinery."),
    ("WATERPOWER", "The force of flowing water used to run machinery."),
    ("FLUME", "An artificial channel that carries water to a mining site."),
    # --- Commerce and Supplies ---
    ("TRADINGPOST", "A store in a remote mining area where goods were bartered."),
    ("SUPPLY", "Food, tools, and goods needed by the miners."),
    ("PROVISIONS", "Food and trail rations packed for mining camps."),
    ("BISCUIT", "Hard dry bread that kept well on the trail."),
    ("WHISKEY", "Strong alcoholic drink popular with miners and frontiersmen."),
    ("ROPE", "Strong cord used for climbing, hauling, and securing loads."),
    ("CANVAS", "Strong cloth used to make tents and wagon covers."),
    ("STOVE", "Iron device used for cooking and heating in cabins."),
    ("CANDLE", "Wax light used in mining camps before electricity."),
    # --- Historical Events ---
    ("DISCOVERY", "The moment James Marshall found gold at Sutter's Mill."),
    ("GOLDFEVER", "The intense excitement and urgency to find gold."),
    ("RUSH", "A rapid migration of people to a place where gold was found."),
    ("SETTLER", "A person who moved west to live and work near the diggings."),
    ("ARGONAUT", "Another word for a forty-niner seeking gold in California."),
    # --- Miscellaneous Gold Rush ---
    ("GHOSTTOWN", "An abandoned town left empty after the gold ran out."),
    ("WATERWAY", "A river, creek, or stream used for panning gold."),
    ("RIVERBED", "The ground at the bottom of a river where gold settles."),
    ("GRAVEL", "Loose mixture of small stones used in gold panning."),
    ("SAND", "Fine particles found in riverbeds where gold also settles."),
    ("CLAY", "Heavy sticky earth that had to be washed away to find gold."),
    ("BANK", "The side of a river or stream where miners worked."),
    ("CLAIM", "A piece of land marked off by a miner for gold digging."),
    ("MARKER", "A post or pile of stones marking the boundary of a claim."),
    ("PERMIT", "An official document allowing someone to mine in an area."),
    ("TRIBUTE", "A portion of gold paid to the owner of a mine."),
    ("LAW", "A rule made by miners to govern their camps and claims."),
    ("VIGILANCE", "A citizen committee that kept order in lawless camps."),
    ("COURT", "A place where judges decided disputes between miners."),
    ("DEPUTY", "An assistant to the sheriff in a mining town."),
    ("JAIL", "A building where prisoners were held in a mining town."),
    ("MULE", "A donkey-like animal valued for packing ore and supplies."),
    ("STAMPEDE", "A rapid rush of prospectors toward a new gold strike."),
    ("LEGEND", "A famous story passed down about the California Gold Rush."),
    ("STREAM", "A small river or creek where gold could be found."),
    ("CANYON", "A deep valley with steep sides carved by a river."),
    ("TUNNEL", "A long underground passage dug to reach gold deposits."),
    ("EXPLOSIVE", "Gunpowder used to break hard rock in deep mines."),
    ("FURNACE", "An enclosed fire used to melt ore and extract metal."),
    ("SMELTER", "A furnace where rock is melted to obtain gold and silver."),
    ("VIAL", "A small glass bottle used to store gold dust."),
    ("GOLDSCALE", "A precision scale for weighing gold dust."),
    ("FORGER", "A person who makes illegal copies of gold coins."),
    ("SWINDLER", "A dishonest person who tricked miners out of their gold."),
    ("CRADLE", "A rocking gold-washing device used on rivers."),
    ("DITCH", "A long narrow channel dug to bring water to a mine."),
    ("GATE", "A wooden valve that controls water flow in a sluice box."),
    ("DIVERT", "To change the direction of a stream to access the riverbed."),
    ("FLOOD", "An overflow of water that could destroy a mining camp."),
    ("MUD", "A wet mixture of earth and water common in mining."),
    ("CHUNK", "A thick solid piece of gold found in the earth."),
    ("FLAKE", "A thin flat piece of gold broken from a larger nugget."),
    ("DUST", "Fine gold particles, often saved in a leather pouch."),
    ("GOLDPOUCH", "A small leather bag for carrying gold dust and nuggets."),
    ("POUCH", "A small bag carried by miners to hold gold."),
    # --- Extra Mother Lode / camp vocabulary for 12-puzzle books ---
    ("LODE", "A rich vein of gold-bearing ore in rock."),
    ("MOTHERLODE", "The principal vein of gold in a mining district."),
    ("DIGGINGS", "A claim or site where miners dig for gold."),
    ("LONGTOM", "A long sluice-like trough used to wash gold-bearing dirt."),
    ("HYDRAULIC", "Mining method that blasts hillsides with high-pressure water."),
    ("NOZZLE", "Metal tip that directs water in hydraulic mining."),
    ("MONITOR", "Water cannon used in hydraulic gold mining."),
    ("BEDROCK", "Solid rock beneath gravel where heavy gold settles."),
    ("PAYDIRT", "Earth rich enough in gold to be worth washing."),
    ("COLOR", "Visible flecks of gold seen while panning."),
    ("ASSAY", "A test that measures how much gold is in a sample."),
    ("MINT", "Place where California gold was coined into money."),
    ("INGOT", "A cast bar of gold ready for trade or storage."),
    ("POKE", "A small bag used by miners to carry gold dust."),
    ("TAMP", "To pack blasting powder firmly into a drill hole."),
    ("ADIT", "A nearly horizontal entrance tunnel into a mine."),
    ("STOPE", "An underground excavation where ore is removed."),
    ("WINZE", "A steep underground passage between mine levels."),
    ("ARRASTRA", "A circular mill that crushed gold ore with stones."),
    ("STAMP", "Heavy iron weight that crushed quartz ore for gold."),
    ("AMALGAM", "Mixture of gold and mercury used in ore recovery."),
    ("MERCURY", "Liquid metal used to capture fine gold from crushed ore."),
    ("RETORT", "Device that heats amalgam to separate gold from mercury."),
    ("NUGGETS", "Several rough lumps of gold found in a diggings."),
    ("GRAVELBAR", "River deposit of stones where placer gold collects."),
    ("DRYDIGGINGS", "Gold claims worked away from a flowing stream."),
    ("WETCLAIM", "A mining claim located beside a river or creek."),
    ("OVERLAND", "The land route taken by gold seekers heading west."),
    ("CLIPPER", "Fast sailing ship that carried argonauts to California."),
    ("ISTHMUS", "Narrow land crossing used by some travelers to California."),
    ("COMSTOCK", "Famous silver strike that followed California's gold boom."),
]

# ---------------------------------------------------------------------------
# Category registry
# ---------------------------------------------------------------------------

_ALL_PACKS: dict[str, list[tuple[str, str]]] = {
    # gold_rush first so its entries take priority in the fallback clue cache
    # when the same word exists in multiple packs (e.g. BISCUIT, CANDLE).
    "gold_rush": GOLD_RUSH,
    "everyday_life": EVERYDAY_LIFE,
    "children": CHILDREN_EASY,
    "food": FOOD_PACK,
    "nature": NATURE_PACK,
    "technology": TECHNOLOGY_PACK,
    "activities": ACTIVITIES_PACK,
    "office_supplies": OFFICE_SUPPLIES,
    "places": PLACES_PACK,
    "seasons": SEASONS_PACK,
}


def _normalize_theme(theme: str) -> str:
    """Convert a user theme string to a pack key.

    Routing rules (checked in order):
      - food-related → FOOD_PACK
      - nature/animals/weather → NATURE_PACK
      - technology → TECHNOLOGY_PACK
      - activities/hobbies/sports → ACTIVITIES_PACK
      - gold rush / forty-niner / california gold → GOLD_RUSH
      - food-related → FOOD_PACK
      - nature/animals/weather → NATURE_PACK
      - technology → TECHNOLOGY_PACK
      - activities/hobbies/sports → ACTIVITIES_PACK
      - office supplies/school supplies/stationery → OFFICE_SUPPLIES
      - places/travel → PLACES_PACK
      - seasons/holidays → SEASONS_PACK
      - children/young audience → CHILDREN_EASY
      - general/everyday → EVERYDAY_LIFE
    """
    t = str(theme or "").lower().strip()

    # Gold Rush — checked FIRST because it is very specific and must not
    # fall through to the everyday_life default (the root cause of the
    # "Goal Rush" broken-output bug).
    # Targeted near-match: "Goal Rush" is a common misspelling/OCR of "Gold Rush".
    # Do NOT treat the standalone word "goal" as a match.
    if (
        "goal rush" in t
        or any(w in t for w in [
            "gold rush", "gold rush days", "california gold rush",
            "california gold", "forty-niner", "49ers gold", "49er", "prospector",
            "prospector's gold", "prospectors", "panning for gold",
        ])
    ):
        return "gold_rush"

    # Food: singular + plural forms
    # NOTE: keywords must be long enough to avoid false substring matches.
    # Removed: "ea" (matched "weather", "seasons"), "eat"/"eating" (matched "weather").
    if any(w in t for w in ["food", "foods", "recipe", "cooking", "meal", "meals", "snack", "snacks", "dessert", "desserts", "kitchen", "bakery", "breakfast", "lunch", "dinner", "brunch"]):
        return "food"
    # Nature: includes animals (singular + plural), weather, outdoors
    # NOTE: "sea" removed (matched "seasons"); use longer distinctive keywords only.
    if any(w in t for w in ["nature", "natural", "weather", "animal", "animals", "plant", "plants", "forest", "forests", "ocean", "oceans", "river", "rivers", "mountain", "mountains", "garden", "gardening", "jungle", "rainforest", "outdoor", "outdoors", "wildlife", "bird", "birds", "fish", "lake", "stream", "climate"]):
        return "nature"
    # Technology
    # NOTE: "app"/"apps" removed (matched "appliances"); use distinctive keywords.
    if any(w in t for w in ["technolog", "computer", "computers", "internet", "coding", "code", "software", "digital", "phone", "device", "devices", "electronic", "electronics", "robot", "robotic", "gadget", "tech", "laptop", "tablet"]):
        return "technology"
    # Places: travel, buildings, locations
    # Check for exact standalone "travel" (not "traveling") and other place keywords.
    # Use word-boundary-style checks: the keyword must appear as the full token,
    # not as part of a longer word. For multi-char keywords, `w in t` is safe.
    # Short keywords (<=3 chars) are checked via explicit conditions to avoid
    # false substring matches (e.g., "daily" in "traveling", "home" in "traveling").
    if (
        any(w in t for w in [
            "place", "places", "vacation", "city", "cities", "country", "countries",
            "building", "buildings", "destination", "island", "beach", "park",
            "museum", "restaurant", "hotel", "airport", "stadium", "theater",
            "theatre", "temple", "shrine",
        ])
        or "traveling" in t
        or ("travel" in t and not t.endswith("ing"))  # "travel" but not "traveling"
    ):
        return "places"
    # Activities: hobbies, sports, games, exercise
    # Note: "travel" routes to places (above), not activities.
    if any(w in t for w in [
        "sport", "sports", "game", "games", "hobby", "hobbies",
        "activity", "activities", "play", "playing",
        "outdoor", "outdoors", "exercise", "fitness",
        "dance", "dancing", "music", "musical",
        "craft", "crafts", "collect", "collecting",
        "transport", "trip", "vehicle", "vehicles",
        "car", "cars", "bus", "train", "plane",
    ]):
        return "activities"
    # Office supplies: stationery, school supplies, desk items
    if any(w in t for w in [
        "office supply", "office supplies", "supply", "supplies",
        "stationery", "desk supply", "desk supplies",
        "school supply", "school supplies",
        "pencil", "pencils", "paper", "notebook", "notebooks",
        "teacher supply", "teacher supplies",
        "classroom supply", "classroom supplies",
    ]):
        return "office_supplies"
    # Seasons and holidays
    if any(w in t for w in ["season", "seasons", "spring", "summer", "autumn", "winter", "holiday", "holidays", "christmas", "halloween", "easter", "thanksgiving", "valentine", "newyear", "solstice", "equinox"]):
        return "seasons"
    # Children and young learners
    if any(w in t for w in ["child", "children", "childrens", "kids", "kid", "baby", "babies", "toddler", "preschool", "young", "younger", "elementary", "kindergarten", "beginner"]):
        return "children"
    # Everyday / household: only when the theme explicitly asks for it.
    # Short keywords (<=3 chars) excluded to avoid false substring matches.
    # Unmatched specific topics must NOT silently receive this pack.
    if any(w in t for w in [
        "household", "appliance", "appliances", "everyday life",
        "everyday", "daily life", "home life",
    ]):
        return "everyday_life"
    # No confident pack match — fail closed (callers must not invent vocabulary).
    return ""


def select_fallback_pack(theme: str, *, random_seed: int | None = None) -> str:
    """Return the best pack key for a given theme."""
    return _normalize_theme(theme)


def get_fallback_words_and_clues(
    theme: str,
    *,
    count: int = 10,
    exclude_words: set[str] | None = None,
    random_seed: int | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Return fallback vocabulary and clues for a theme.

    Returns (words, clues_map) where:
      - words: list of answer words (uppercase, no spaces)
      - clues_map: {ANSWER: clue_text} for every word

    exclude_words: words already used in this book (prevents repetition)
    random_seed: if provided, shuffles deterministically so the same seed
                 always produces the same order for reproducibility
    """
    pack_key = _normalize_theme(theme)
    if not pack_key or pack_key not in _ALL_PACKS:
        return [], {}
    pool = list(_ALL_PACKS[pack_key])

    if random_seed is not None:
        rng = random.Random(random_seed)
        rng.shuffle(pool)
    else:
        pool = list(pool)  # copy before shuffle

    exclude = {w.upper().strip() for w in (exclude_words or set())}
    words: list[str] = []
    clues_map: dict[str, str] = {}

    for word, clue in pool:
        answer = re.sub(r"\s+", "", word.upper()).strip()
        if answer in exclude:
            continue
        if len(answer) < 2:
            continue
        words.append(answer)
        clues_map[answer] = clue
        exclude.add(answer)
        if len(words) >= count:
            break

    return words, clues_map


def get_fallback_book_vocabulary(
    theme: str,
    *,
    puzzle_count: int = 10,
    words_per_puzzle: int = 10,
    random_seed: int | None = None,
) -> list[tuple[list[str], dict[str, str]]]:
    """Return vocabulary and clues for a full book of puzzles.

    Produces puzzle_count separate word sets, each drawn from the same pack
    but without overlap between sets, ensuring variety across the book.
    """
    pack_key = _normalize_theme(theme)
    if not pack_key or pack_key not in _ALL_PACKS:
        return []
    pool = list(_ALL_PACKS[pack_key])

    if random_seed is not None:
        rng = random.Random(random_seed)
        rng.shuffle(pool)
    else:
        pool = list(pool)

    exclude: set[str] = set()
    puzzles: list[tuple[list[str], dict[str, str]]] = []

    for _ in range(puzzle_count):
        words: list[str] = []
        clues_map: dict[str, str] = {}
        for word, clue in pool:
            answer = re.sub(r"\s+", "", word.upper()).strip()
            if answer in exclude or len(answer) < 2:
                continue
            words.append(answer)
            clues_map[answer] = clue
            exclude.add(answer)
            if len(words) >= words_per_puzzle:
                break
        if words:
            puzzles.append((words, clues_map))
        if len(exclude) >= len(pool) * 0.9:
            # Pool nearly exhausted — refill from full pack without the exclude set
            # but start fresh for remaining puzzles
            break

    return puzzles
