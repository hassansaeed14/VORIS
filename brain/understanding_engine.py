import re


SHORT_FORM_MAP = {
    "u": "you",
    "ur": "your",
    "r": "are",
    "plz": "please",
    "pls": "please",
    "bcz": "because",
    "wht": "what",
    "wat": "what",
    "msg": "message",
    "cmd": "command",
    "abt": "about",
    "btw": "by the way",
    "idk": "i do not know",
    "dont": "don't",
    "cant": "can't",
    "wont": "won't",
    "im": "i am",
    "ive": "i have",
    "thx": "thanks",
    "ty": "thank you",
    "smth": "something",
    "govt": "government",
    "pic": "picture",
    "vid": "video",
    "insta": "instagram",
    "snap": "snapchat",
    "emailto": "email to",
}


TYPO_REPLACEMENTS = {
    "emailto": "email to",
    "facebokk": "facebook",
    "facebok": "facebook",
    "whats": "what is",
    "what's": "what is",
    "wheres": "where is",
    "where's": "where is",
    "hows": "how is",
    "how's": "how is",
    "wether": "weather",
    "remaind": "remind",
    "remine": "remind",
    "grammer": "grammar",
    "sumarize": "summarize",
    "summrize": "summarize",
    "transalte": "translate",
    "yotube": "youtube",
    "defination": "definition",
}


SAFE_MULTI_SEPARATORS = [
    " and then ",
    " then ",
    " also ",
    " as well as ",
    " plus ",
    "&",
]


ACTION_STARTERS = (
    "open", "search", "find", "show", "tell", "give", "set", "add", "delete",
    "remove", "create", "write", "send", "read", "analyze", "summarize",
    "translate", "calculate", "solve", "compare", "list", "take", "remind",
    "research", "study", "explain", "check", "fix"
)


PROTECTED_PATTERNS = [
    r"\bdifference between .+ and .+",
    r"\bcompare .+ and .+",
    r"\bbetween \d+ and \d+",
    r"\bbetween [a-zA-Z]+ and [a-zA-Z]+",
    r"\btranslate .+ in [a-zA-Z]+ and [a-zA-Z]+",
]


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def fix_common_typos(text: str) -> str:
    result = str(text)

    for old, new in TYPO_REPLACEMENTS.items():
        result = re.sub(rf"\b{re.escape(old)}\b", new, result, flags=re.IGNORECASE)

    return result


def expand_short_forms(text: str) -> str:
    words = text.split()
    expanded_words = []

    for word in words:
        prefix_match = re.match(r"^[^\w']*", word)
        suffix_match = re.search(r"[^\w']*$", word)

        prefix = prefix_match.group(0) if prefix_match else ""
        suffix = suffix_match.group(0) if suffix_match else ""

        core = word[len(prefix):]
        if suffix:
            core = core[:-len(suffix)]

        key = core.lower()
        replacement = SHORT_FORM_MAP.get(key, core)

        expanded_words.append(f"{prefix}{replacement}{suffix}")

    return " ".join(expanded_words)


def strip_conversation_fillers(text: str) -> str:
    patterns = [
        r"^\s*hi\s+",
        r"^\s*hey\s+",
        r"^\s*hello\s+",
        r"^\s*hi voris\s+",
        r"^\s*hey voris\s+",
        r"^\s*hello voris\s+",
        r"^\s*hi aura\s+",
        r"^\s*hey aura\s+",
        r"^\s*hello aura\s+",
        r"^\s*no\s+i\s+mean\s+",
        r"^\s*i\s+mean\s+",
    ]

    result = text

    for pattern in patterns:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    return result.strip()


def is_meaningful_text(text: str) -> bool:
    if not text:
        return False

    stripped = text.strip(" ,.?;:!-")
    return bool(stripped)


def is_protected_single_intent(text: str) -> bool:
    for pattern in PROTECTED_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def starts_with_action(text: str) -> bool:
    lowered = text.strip().lower()
    return lowered.startswith(ACTION_STARTERS)


def should_split_on_and(text: str) -> bool:
    lowered = text.lower()

    if " and " not in lowered:
        return False

    if is_protected_single_intent(lowered):
        return False

    parts = lowered.split(" and ", 1)
    if len(parts) != 2:
        return False

    left = parts[0].strip()
    right = parts[1].strip()

    if not left or not right:
        return False

    if starts_with_action(right):
        return True

    if starts_with_action(left) and len(right.split()) <= 4:
        return True

    return False


def clean_user_input(text: str) -> str:
    text = normalize_whitespace(text)
    text = fix_common_typos(text)
    text = expand_short_forms(text)
    text = strip_conversation_fillers(text)
    text = normalize_whitespace(text)
    return text


def split_multi_intent(text: str):
    from brain.command_splitter import split_commands

    return split_commands(text, max_commands=3)
