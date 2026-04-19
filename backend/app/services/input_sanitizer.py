"""Input sanitization service for prompt injection detection."""

import re
import logging

logger = logging.getLogger(__name__)

# Patterns that indicate prompt injection attempts (English + Ukrainian)
_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Override system prompt
    (
        re.compile(
            r"(ignore|forget|disregard|override)\s+(all\s+)?(previous|above|prior|your)\s+"
            r"(instructions|rules|prompt|guidelines|system)",
            re.IGNORECASE,
        ),
        "prompt_override",
    ),
    (
        re.compile(
            r"(ігноруй|забудь|відкинь|не\s+зважай\s+на)\s+"
            r"(всі\s+)?(попередні|свої|минулі|системні)\s+"
            r"(інструкції|правила|промпт|вказівки)",
            re.IGNORECASE,
        ),
        "prompt_override_ua",
    ),
    (
        re.compile(
            r"new\s+system\s+(prompt|message|instruction)",
            re.IGNORECASE,
        ),
        "new_system_prompt",
    ),
    # Role-play attacks
    (
        re.compile(
            r"(you\s+are\s+now|act\s+as|pretend\s+(you\s+are|to\s+be)|"
            r"simulate\s+(being|a)|roleplay\s+as|behave\s+as)",
            re.IGNORECASE,
        ),
        "roleplay",
    ),
    (
        re.compile(
            r"(тепер\s+ти|уяви\s+(що\s+ти|себе)|поводь\s+себе\s+як|"
            r"грай\s+роль|будь\s+як)",
            re.IGNORECASE,
        ),
        "roleplay_ua",
    ),
    # Data exfiltration
    (
        re.compile(
            r"(repeat|show|print|output|reveal|display)\s+"
            r"(the\s+)?(above|system|your|initial)\s+"
            r"(prompt|message|instructions|text)",
            re.IGNORECASE,
        ),
        "data_exfiltration",
    ),
    (
        re.compile(
            r"what\s+are\s+your\s+(instructions|rules|system\s+prompt)",
            re.IGNORECASE,
        ),
        "data_exfiltration",
    ),
    (
        re.compile(
            r"(покажи|виведи|повтори|розкрий)\s+"
            r"(свій\s+)?(системний\s+)?(промпт|інструкції|правила)",
            re.IGNORECASE,
        ),
        "data_exfiltration_ua",
    ),
    # Delimiter injection — excessive delimiters used to "escape" the prompt
    (
        re.compile(r"(---){5,}|(\*\*\*){5,}|(###){5,}|(```){3,}"),
        "delimiter_injection",
    ),
]


class InputSanitizer:
    """Detects and sanitizes prompt injection attempts in user input."""

    def detect_injection(self, text: str) -> tuple[bool, str]:
        """Check text for known injection patterns.

        Returns:
            (is_injection, pattern_name) — ``True`` and the matched pattern
            category if an injection is detected, ``(False, "")`` otherwise.
        """
        for pattern, name in _INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning(
                    "Prompt injection detected (pattern=%s, length=%d)",
                    name,
                    len(text),
                )
                return True, name
        return False, ""

    def sanitize(self, text: str) -> str:
        """Remove excessive whitespace and normalize delimiters.

        This does *not* strip injection phrases — those are caught by
        ``detect_injection`` and should be rejected outright.
        """
        # Collapse runs of 4+ identical delimiter characters
        text = re.sub(r"(-){4,}", "---", text)
        text = re.sub(r"(\*){4,}", "***", text)
        text = re.sub(r"(#){4,}", "###", text)
        return text.strip()


input_sanitizer = InputSanitizer()
