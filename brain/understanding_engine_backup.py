import re


SHORT_FORM_MAP = {
    "u": "you",
    "ur": "your",
    "r": "are",
    "plz": "please",
    "pls": "please",
    "bcz": "because",
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
    "vid": "video"
}


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def expand_short_forms(text: str) -> str:
    words = text.split()
    expanded = []

    for word in words:
        key = re.sub(r"[^\w']", "", word.lower())
        if key in SHORT_FORM_MAP:
            replacement = SHORT_FORM_MAP[key]
            punctuation = ""
            if word and not word[-1].isalnum():
                punctuation = word[-1]
            expanded.append(replacement + punctuation)
        else:
            expanded.append(word)

    return " ".join(expanded)


def normalize_common_phrases(text: str) -> str:
    text = text.strip()

    replacements = {
        "what's": "what is",
        "whats": "what is",
        "who's": "who is",
        "wheres": "where is",
        "where's": "where is",
        "how's": "how is",
        "im ": "i am ",
        "i m ": "i am ",
        "dont ": "don't ",
        "cant ": "can't ",
        "wont ": "won't "
    }

    lowered = text.lower()
    for old, new in replacements.items():
        lowered = lowered.replace(old, new)

    return lowered


def clean_user_input(text: str) -> str:
    text = normalize_whitespace(text)
    text = expand_short_forms(text)
    text = normalize_common_phrases(text)
    text = normalize_whitespace(text)
    return text


def split_multi_intent(text: str):
    text = clean_user_input(text)

    separators = [
        " and then ",
        " then ",
        " also ",
        " as well as ",
        " plus ",
        " and ",
        "&"
    ]

    parts = [text]

    for sep in separators:
        new_parts = []
        for part in parts:
            split_parts = [p.strip(" ,.?") for p in part.split(sep) if p.strip(" ,.?")]
            new_parts.extend(split_parts)
        parts = new_parts

    cleaned = []
    for part in parts:
        if part and part not in cleaned:
            cleaned.append(part)

    return cleaned[:3]


def estimate_input_quality(text: str) -> dict:
    original = str(text)
    cleaned = clean_user_input(original)

    return {
        "original": original,
        "cleaned": cleaned,
        "changed": original.strip() != cleaned.strip(),
        "word_count": len(cleaned.split())
    }