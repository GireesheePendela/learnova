"""Read-aloud with Amazon Polly, for students who are more comfortable listening than reading.

Uses the same AWS credentials as Bedrock. Languages without a Polly voice simply get no
Listen button. READ_ALOUD=on/off overrides the default (on with Bedrock, off with Ollama).
"""

import os
import re
from functools import lru_cache

from .config import provider

# Polly voices per language, best first. Neural voices sound more natural but are not offered
# in every region, so each language falls back to a standard voice.
VOICES: dict[str, list[tuple[str, str, str]]] = {
    "Hindi": [("Kajal", "neural", "hi-IN"), ("Aditi", "standard", "hi-IN")],
    "Arabic": [("Hala", "neural", "ar-AE"), ("Zeina", "standard", "arb")],
    "Spanish": [("Lupe", "neural", "es-US"), ("Lupe", "standard", "es-US")],
    "Portuguese": [("Camila", "neural", "pt-BR"), ("Camila", "standard", "pt-BR")],
    "Chinese (Simplified)": [("Zhiyu", "neural", "cmn-CN"), ("Zhiyu", "standard", "cmn-CN")],
    "English": [("Joanna", "neural", "en-US"), ("Joanna", "standard", "en-US")],
}

# Polly bills at most 3000 characters per request; one explanation or quiz fits well within it.
MAX_CHARS = 2900


def enabled() -> bool:
    return os.getenv("READ_ALOUD", "on" if provider() == "bedrock" else "off").lower() == "on"


def available(language: str) -> bool:
    return enabled() and language in VOICES


def speakable(text: str) -> str:
    """Strip Markdown and the invisible direction marks so Polly reads only the words."""
    text = re.sub(f"[{chr(0x2066)}-{chr(0x2069)}]", "", text)  # direction isolates added by app.term()
    text = re.sub(r"[*_#`>|]+", " ", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_CHARS]


@lru_cache(maxsize=256)
def synthesize(text: str, language: str) -> bytes:
    """MP3 audio of text read in the student's language. Cached, so replaying costs nothing."""
    import boto3
    from botocore.exceptions import ClientError

    polly = boto3.client("polly", region_name=os.getenv("AWS_REGION") or None)
    error: Exception | None = None
    for voice, engine, code in VOICES[language]:
        try:
            response = polly.synthesize_speech(Text=speakable(text), OutputFormat="mp3", VoiceId=voice,
                                               Engine=engine, LanguageCode=code)
            return response["AudioStream"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] in ("AccessDeniedException", "UnrecognizedClientException"):
                raise  # no access to Polly at all: another voice won't help
            error = e  # e.g. this engine is not offered in the region: try the next voice
    raise error or RuntimeError(f"No Polly voice for {language}")
