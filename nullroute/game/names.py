"""Word lists for procedural generation. Everything here is fictional."""

FIRST = [
    "Anna", "Ben", "Clara", "David", "Elin", "Felix", "Greta", "Hugo", "Ines",
    "Jonas", "Karin", "Leo", "Maja", "Nils", "Olivia", "Pavel", "Quinn", "Rosa",
    "Simon", "Tove", "Ulf", "Vera", "Walter", "Yara", "Zoe", "Amir", "Bianca",
    "Carlos", "Dana", "Erik", "Fatima", "Gustav", "Hanna", "Ivan", "Julia",
    "Kenji", "Lina", "Marco", "Nora", "Oscar", "Priya", "Rafael", "Sara",
]

LAST = [
    "Andersson", "Becker", "Castillo", "Dahl", "Ekberg", "Fischer", "Garcia",
    "Holm", "Ito", "Jansen", "Kowalski", "Lindqvist", "Moreau", "Novak",
    "Okafor", "Petrov", "Quist", "Rossi", "Sandberg", "Tanaka", "Ulrich",
    "Varga", "Weber", "Young", "Zimmer", "Berg", "Carter", "Dubois", "Engel",
]

CORP_A = ["Meridian", "Halcyon", "Vantage", "Northwind", "Corvid", "Obsidian",
          "Lumen", "Arcadia", "Silverline", "Pinnacle", "Kestrel", "Bluefin",
          "Ironbark", "Solace", "Tessera", "Quantis", "Helix", "Orrery",
          "Zenith", "Cobalt", "Nimbus", "Vesper"]
CORP_B = ["Dynamics", "Biotech", "Robotics", "Aerospace", "Cybernetics",
          "Synthetics", "Genomics", "Systems", "Industries", "Labs",
          "Orbital", "Neural", "Fusion", "Materials"]

CITIES = {
    # name: (x, y) on the ascii world map (72 x 20)
    "Reykjavik": (25, 2), "Oslo": (36, 2), "Tallinn": (40, 3), "London": (32, 4),
    "Berlin": (37, 4), "Zurich": (35, 5), "Montreal": (16, 4), "New York": (15, 6),
    "Chicago": (11, 5), "Seattle": (4, 4), "Lima": (17, 13), "Sao Paulo": (21, 14),
    "Lagos": (32, 11), "Cairo": (39, 8), "Nairobi": (40, 12), "Mumbai": (49, 9),
    "Singapore": (57, 11), "Osaka": (64, 6), "Seoul": (61, 5), "Perth": (59, 15),
    "Sydney": (67, 15), "Cape Town": (36, 15), "Dubai": (46, 8), "Anchorage": (2, 2),
}

RELAY_CITIES = ["Reykjavik", "Tallinn", "Osaka", "Lagos", "Lima", "Perth",
                "Montreal", "Zurich", "Nairobi", "Seoul", "Anchorage", "Cape Town"]

CORP_CITIES = ["London", "New York", "Chicago", "Seattle", "Berlin", "Sao Paulo",
               "Mumbai", "Singapore", "Sydney", "Dubai", "Cairo", "Seoul"]

PROJECTS = ["Aurora", "Basilisk", "Chimera", "Daybreak", "Ember", "Fathom",
            "Gossamer", "Halo", "Icarus", "Juniper", "Kraken", "Lodestar",
            "Monolith", "Nightjar", "Obelisk", "Paragon", "Quicksilver",
            "Riptide", "Sable", "Tempest", "Umbra", "Vanguard", "Wraith"]

DATA_KINDS = ["schematics", "prototype", "research", "simulation", "genome",
              "firmware", "blueprint", "telemetry"]

PASSPHRASE_WORDS = ["amber", "beacon", "cinder", "drift", "echo", "fable",
                    "garnet", "harbor", "indigo", "jasper", "kelvin", "lunar",
                    "marrow", "nova", "onyx", "pylon", "quartz", "raven",
                    "sierra", "tundra", "umber", "vortex", "willow", "xenon"]

MEMO_SUBJECTS = ["Quarterly targets", "Lunch rota", "Server room access",
                 "Coffee machine (again)", "Lab safety reminder", "Team offsite",
                 "Parking permits", "New hire onboarding", "Budget freeze",
                 "Holiday schedule"]
