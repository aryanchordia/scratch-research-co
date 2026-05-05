"""
courses.py — shared tournament/course name mappings for the pipeline.

fetch_data.py and fetch_datagolf.py both import from here so venue
resolution is consistent across all steps.
"""

# DataGolf's exact option values for each course
COURSE_NAME_MAP: dict[str, str] = {
    "harbour town": "Harbour Town Golf Links",
    "harbour town golf links": "Harbour Town Golf Links",
    "augusta national": "Augusta National Golf Club",
    "augusta": "Augusta National Golf Club",
    "pebble beach": "Pebble Beach Golf Links",
    "muirfield village": "Muirfield Village Golf Club",
    "congressional": "Congressional CC (Blue)",
    "colonial": "Colonial Country Club",
    "east lake": "East Lake Golf Club",
    "tpc sawgrass": "TPC Sawgrass (Stadium)",
    "tpc scottsdale": "TPC Scottsdale (Stadium)",
    "tpc louisiana": "TPC Louisiana",
    "bay hill": "Arnold Palmer's Bay Hill Club & Lodge",
    "riviera": "Riviera Country Club",
    "torrey pines": "Torrey Pines (South Course)",
    "quail hollow": "Quail Hollow Club",
    "southern hills": "Southern Hills Country Club",
    "oak hill": "Oak Hill Country Club (East)",
    "valhalla": "Valhalla Golf Club",
    "bethpage": "Bethpage Black",
    "shinnecock": "Shinnecock Hills Golf Club",
    "winged foot": "Winged Foot Golf Club (West)",
    "carnoustie": "Carnoustie Golf Links",
    "st andrews": "St Andrews Links (Old Course)",
    "royal troon": "Royal Troon Golf Club (Old)",
    "muirfield": "Muirfield",
    "royal portrush": "Royal Portrush Golf Club (Dunluce)",
    "trump national doral": "Trump National Doral (Blue Monster)",
    "doral": "Trump National Doral (Blue Monster)",
    "blue monster": "Trump National Doral (Blue Monster)",
    "tpc river highlights": "TPC River Highlights",
    "castle pines": "Castle Pines Golf Club",
    "hamilton golf": "Hamilton Golf & Country Club",
    "the renaissance club": "The Renaissance Club",
    "waialae": "Waialae Country Club",
    "plantation course": "Plantation Course at Kapalua",
    "detroit golf": "Detroit Golf Club",
    "tpc deere run": "TPC Deere Run",
    "tpc southwind": "TPC Southwind",
    "oakmont": "Oakmont Country Club",
}

# Tournament name keywords → resolved DataGolf course name
# Key: lowercase keyword that appears in the ESPN tournament name
# Value: DataGolf's exact course option string
TOURNAMENT_TO_COURSE: dict[str, str] = {
    "zurich classic": "TPC Louisiana",
    "wells fargo": "Quail Hollow Club",
    "pga championship": "Quail Hollow Club",
    "charles schwab": "Colonial Country Club",
    "memorial": "Muirfield Village Golf Club",
    "us open": "Oakmont Country Club",
    "u.s. open": "Oakmont Country Club",
    "travelers": "TPC River Highlights",
    "rocket mortgage": "Detroit Golf Club",
    "john deere": "TPC Deere Run",
    "genesis scottish": "The Renaissance Club",
    "genesis invitational": "Riviera Country Club",
    "the open": "Royal Troon Golf Club (Old)",
    "british open": "Royal Troon Golf Club (Old)",
    "fedex st. jude": "TPC Southwind",
    "bmw championship": "Castle Pines Golf Club",
    "tour championship": "East Lake Golf Club",
    "arnold palmer": "Arnold Palmer's Bay Hill Club & Lodge",
    "players championship": "TPC Sawgrass (Stadium)",
    "waste management": "TPC Scottsdale (Stadium)",
    "farmers insurance": "Torrey Pines (South Course)",
    "sony open": "Waialae Country Club",
    "sentry": "Plantation Course at Kapalua",
    "rbc canadian": "Hamilton Golf & Country Club",
    "rbc heritage": "Harbour Town Golf Links",
    "masters": "Augusta National Golf Club",
    "cadillac championship": "Trump National Doral (Blue Monster)",
    "wgc-cadillac": "Trump National Doral (Blue Monster)",
    "mexico open": "Vidanta Vallarta",
    "valero texas open": "TPC San Antonio (Oaks)",
    "texas open": "TPC San Antonio (Oaks)",
    "valspar": "Innisbrook Resort (Copperhead)",
    "cognizant classic": "PGA National Resort (The Champion)",
    "pga national": "PGA National Resort (The Champion)",
    "att pebble": "Pebble Beach Golf Links",
    "pebble beach pro-am": "Pebble Beach Golf Links",
    "phoenix open": "TPC Scottsdale (Stadium)",
    "american express": "Pete Dye Stadium Course",
    "the american express": "Pete Dye Stadium Course",
    "sanderson farms": "Country Club of Jackson",
    "shriners": "TPC Summerlin",
    "zozo": "Narashino Country Club",
    "fortinet": "Silverado Resort (North Course)",
    "nitto": "Shadow Creek Golf Course",
    "butterfield bermuda": "Port Royal Golf Course",
    "bermuda championship": "Port Royal Golf Course",
    "houston open": "Memorial Park Golf Course",
    "world wide technology": "El Cardonal at Diamante",
    "mayakoba": "El Camaleon",
    "rsm classic": "Sea Island (Seaside Course)",
    "hero world challenge": "Albany Golf Club",
    "the match": "",
    "cj cup": "Doral Resort",
    "scottish open": "The Renaissance Club",
    "irish open": "Royal County Down",
    "aon swing5": "",
}


def resolve_course(tournament_name: str, venue_hint: str = "") -> str:
    """
    Return the DataGolf course name for a given tournament/venue.

    Checks venue_hint first (ESPN sometimes does return a venue string),
    then falls back to keyword matching on tournament_name.
    Returns "" when no match found.
    """
    if venue_hint:
        key = venue_hint.lower().strip()
        if key in COURSE_NAME_MAP:
            return COURSE_NAME_MAP[key]

    normalized = tournament_name.lower().strip()
    # Direct key match
    if normalized in TOURNAMENT_TO_COURSE:
        return TOURNAMENT_TO_COURSE[normalized]
    # Keyword scan
    for keyword, course in TOURNAMENT_TO_COURSE.items():
        if keyword in normalized:
            return course

    return ""
