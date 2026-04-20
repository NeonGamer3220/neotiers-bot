import os
import random

# =========================
# APRIL FOOLS' DAY MODE (Disabled)
# =========================

APRIL_FOOLS_MODE = False  # Enable April Fools' mode by setting to True

def should_april_fools_glitch() -> bool:
    """Determine if April Fools' glitch should occur (5% chance when mode is enabled)"""
    return APRIL_FOOLS_MODE and random.random() < 0.05

def get_april_fools_message() -> str:
    """Get a random April Fools' message"""
    messages = [
        "🎪 A cirkusz ma nyitva! 🎪",
        "🤡 A bohóc elárulta a titkát! 🤡",
        "🎭 A színházban ma előadás van! 🎭",
        "🃏 A kártyák újra keverve! 🃏",
    ]
    return random.choice(messages)

def get_funny_rank(rank: str) -> str:
    """Get a funny alternative rank name for April Fools' mode"""
    funny_ranks = {
        "Unranked": "🎪 Cirkuszban",
        "LT5": "🤡 Bohóc",
        "HT5": "🎭 Színész",
        "LT4": "🃏 Kártyás",
        "HT4": "🎪 Cirkuszos",
        "LT3": "🤡 Főbohóc",
        "HT3": "🎭 Főszínész",
        "LT2": "🃏 Főkártya",
        "HT2": "🎪 Cirkuszkapitány",
        "LT1": "🤡 Cirkuszdirigens",
        "HT1": "🎭 Színházigazgató",
    }
    return funny_ranks.get(rank, rank)


def truncate_message(text: str, max_length: int = 1900) -> str:
    """Truncate a message to fit Discord's 2000 character limit with safety margin"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."

def format_cooldown(seconds: int) -> str:
    """Format cooldown time nicely"""
    if seconds <= 0:
        return "0"
    days = seconds // (24 * 60 * 60)
    hours = (seconds % (24 * 60 * 60)) // (60 * 60)
    minutes = (seconds % (60 * 60)) // 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}ó")
    if minutes > 0:
        parts.append(f"{minutes}p")
    return " ".join(parts) if parts else "<1p"

def is_lt3_or_above(rank: str) -> bool:
    """Check if rank is LT3 or above"""
    rank_points = POINTS.get(rank, 0)
    return rank_points >= 6  # LT3 = 6 points

def is_under_lt3(rank: str) -> bool:
    """Check if rank is under LT3"""
    rank_points = POINTS.get(rank, 0)
    return rank_points < 6


# =========================
# ENV / CONFIG
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "0"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))
EXTRA_STAFF_ROLE_IDS = [int(os.getenv("EXTRA_STAFF_ROLE_IDS", "0"))] if os.getenv("EXTRA_STAFF_ROLE_IDS") else []
ALLOWED_USER_IDS = [int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()]
DEBUG_ALLOWED_USERS = []
DEBUG_ALLOWED_ROLES = [1483822408182796418]

WEBSITE_URL = os.getenv("WEBSITE_URL", "").rstrip("/")
BOT_API_KEY = os.getenv("BOT_API_KEY", "")

MINECRAFT_API_URL = os.getenv("MINECRAFT_API_URL", "http://localhost:8080").rstrip("/")

WIPE_GLOBAL_COMMANDS = os.getenv("WIPE_GLOBAL_COMMANDS", "0") == "1"

COOLDOWN_SECONDS = 14 * 24 * 60 * 60
DATA_FILE = "data.json"
HTTP_TIMEOUT_SECONDS = 10

LINK_CODE_LENGTH = 8
LINK_CODE_EXPIRY_MINUTES = 10

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "")
SUPABASE_PG_URL = os.getenv("SUPABASE_PG_URL", "")

USE_SUPABASE_API = bool(SUPABASE_URL and SUPABASE_KEY)


# =========================
# CONSTANTS
# =========================
TICKET_TYPES = [
    ("Vanilla", "vanilla", 1469763891226480926),
    ("UHC", "uhc", 1469765994988704030),
    ("Pot", "pot", 1469763780593324032),
    ("NethPot", "nethpot", 1469763817218117697),
    ("SMP", "smp", 1469764274955223161),
    ("Sword", "sword", 1469763677141074125),
    ("Axe", "axe", 1469763738889486518),
    ("Mace", "mace", 1469763612452196375),
    ("Cart", "cart", 1469763920871952435),
    ("Creeper", "creeper", 1469764200812249180),
    ("DiaSMP", "diasmp", 1469763946968911893),
    ("OGVanilla", "ogvanilla", 1469764329460203571),
    ("ShieldlessUHC", "shieldlessuhc", 1469766017243807865),
    ("SpearMace", "spearmace", 1469968704203788425),
    ("SpearElytra", "spearelytra", 1469968762575912970),
]

TICKET_ROUNDS = {
    "vanilla": ("FT4", "FT3", None),
    "diasmp": ("FT4", "FT3", "FT2"),
    "ogvanilla": ("FT4", "FT2", None),
    "nethpot": ("FT4", "FT2", None),
    "mace": ("FT4", "FT2", None),
    "smp": ("FT4", "FT3", "FT2"),
    "cart": ("FT4", "FT3", "FT2"),
    "sword": ("FT10", "FT6", None),
    "uhc": ("FT6", "FT3", None),
    "pot": ("FT10", "FT6", None),
    "creeper": ("FT6", "FT4", "FT3"),
    "shieldlessuhc": ("FT6", "FT4", None),
    "axe": ("FT20", "FT10", None),
    "spearmace": ("FT6", "FT3", None),
    "spearelytra": ("FT6", "FT3", None),
}

def get_ticket_rounds_display(mode_key: str) -> str:
    """Get the display string for required rounds based on gamemode"""
    rounds = TICKET_ROUNDS.get(mode_key.lower())
    if not rounds:
        return "FT4"

    default_ft, lt3_ft, loss_ft = rounds

    if loss_ft:
        return f"{default_ft}, LT3 alatt {lt3_ft}, ha nem nyersz a teszter ellen kört akkor {loss_ft}"
    else:
        return f"{default_ft}, LT3 alatt {lt3_ft}"

MODE_LIST = [t[0] for t in TICKET_TYPES]

RANKS = [
    "Unranked",
    "LT5", "HT5",
    "LT4", "HT4",
    "LT3", "HT3",
    "LT2", "HT2",
    "LT1", "HT1",
]

POINTS = {
    "Unranked": 0,
    "LT5": 1, "HT5": 2,
    "LT4": 3, "HT4": 4,
    "LT3": 6, "HT3": 8,
    "LT2": 10, "HT2": 12,
    "LT1": 14, "HT1": 18,
}

GAMEMODE_ALIASES = {
    "ogv": "ogvanilla",
    "ogvanilla": "ogvanilla",
    "nethpot": "nethpot",
    "uhc": "uhc",
    "shieldlessuhc": "shieldlessuhc",
    "spearmace": "spearmace",
    "spearelytra": "spearelytra",
}

GAMEMODE_DISPLAY_NAMES = {
    "vanilla": "Vanilla",
    "uhc": "UHC",
    "pot": "Pot",
    "nethpot": "NethPot",
    "smp": "SMP",
    "sword": "Sword",
    "axe": "Axe",
    "mace": "Mace",
    "cart": "Cart",
    "creeper": "Creeper",
    "diasmp": "DiaSMP",
    "ogvanilla": "OGVanilla",
    "shieldlessuhc": "ShieldlessUHC",
    "spearmace": "SpearMace",
    "spearelytra": "SpearElytra",
}

def normalize_gamemode(mode: str) -> str:
    """Normalize gamemode name to bot's TICKET_TYPES key format"""
    if not mode:
        return mode
    normalized = mode.lower().strip()
    return GAMEMODE_ALIASES.get(normalized, normalized)

def get_gamemode_display_name(mode_key: str) -> str:
    """Get proper display name for a gamemode key"""
    if not mode_key:
        return mode_key
    if mode_key in GAMEMODE_DISPLAY_NAMES:
        return GAMEMODE_DISPLAY_NAMES[mode_key]
    return GAMEMODE_DISPLAY_NAMES.get(mode_key.lower().strip(), mode_key)

QUEUE_CHANNELS = {
    "sword": 1495038486120632410,
    "axe": 1495038602751774730,
    "mace": 1495038625719783586,
    "uhc": 1495038706103484487,
    "pot": 1495038741465792553,
    "nethpot": 1495038766769897482,
    "smp": 1495038799800176660,
    "vanilla": 1495038839591534834,
    "creeper": 1495038857597681818,
    "cart": 1495038915453779982,
    "diasmp": 1495038938640027760,
    "spearelytra": 1495038976988545206,
    "spearmace": 1495038999876600008,
    "shieldlessuhc": 1495039115119296572,
    "ogvanilla": 1495039145330872341,
}

QUEUE_PING_ROLES = {
    "sword": 1495043729017278525,
    "axe": 1495043913583558758,
    "mace": 1495043981959237752,
    "uhc": 1495044042612805754,
    "pot": 1495044102730022942,
    "nethpot": 1495044163194847322,
    "smp": 1495044237551472893,
    "vanilla": 1495044315272052929,
    "creeper": 1495044383425171506,
    "cart": 1495044436403556443,
    "diasmp": 1495044514992095333,
    "shieldlessuhc": 1495044593211670711,
    "ogvanilla": 1495044664502386698,
    "spearelytra": 1495044732680667247,
    "spearmace": 1495044798472781944,
}

TICKET_CREATE_CATEGORY_ID = 1495038336744689674
