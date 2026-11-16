from functools import lru_cache

import tiktoken

# o200k_base is the tokenizer family used by our main model (gpt-oss). Gemini uses its
# own tokenizer, but o200k counts are a close, consistent estimate for budgeting.
# tiktoken is a pure tokenizer library: no ML model is downloaded or run locally.
TOKENIZER_ENCODING = "o200k_base"
FALLBACK_CHARS_PER_TOKEN = 4


@lru_cache(maxsize=1)
def get_tokenizer():
    return tiktoken.get_encoding(TOKENIZER_ENCODING)


def get_token_count(text: str) -> int:
    normalized_text = text or ""

    try:
        return len(get_tokenizer().encode(normalized_text, disallowed_special=()))
    except Exception:
        # Encoding files are fetched once and cached; stay usable if offline on first run.
        return max(1, (len(normalized_text) + FALLBACK_CHARS_PER_TOKEN - 1) // FALLBACK_CHARS_PER_TOKEN)
