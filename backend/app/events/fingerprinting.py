"""
hi.myrepo - Error Fingerprinting

Deterministic fingerprinting normalizes errors to prevent alert storms.
182 identical errors → 1 error group → 1 incident.

Fingerprint = hash(normalized_exception + normalized_stack + route + context)
"""

import hashlib
import re
from typing import Optional

from pydantic import BaseModel


class ErrorInput(BaseModel):
    """Raw error data to be fingerprinted."""
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    file_location: Optional[str] = None
    line_number: Optional[int] = None
    function_name: Optional[str] = None
    route: Optional[str] = None
    release: Optional[str] = None
    environment: Optional[str] = None


class FingerprintResult(BaseModel):
    """Result of fingerprinting an error."""
    fingerprint: str
    normalized_message: str
    normalized_stack: str
    error_type: str
    route: Optional[str] = None
    file_location: Optional[str] = None


class FingerprintEngine:
    """
    Creates deterministic fingerprints from error data.
    Normalizes messages by removing variable parts (IDs, timestamps, UUIDs, etc.)
    """

    # Patterns to normalize in error messages
    NORMALIZATION_PATTERNS = [
        # UUIDs
        (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "<UUID>"),
        # Long hex strings
        (re.compile(r"[0-9a-f]{16,}", re.I), "<HEX>"),
        # Integer IDs
        (re.compile(r"\b\d{6,}\b"), "<ID>"),
        # Timestamps
        (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"), "<TIMESTAMP>"),
        # IP addresses
        (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "<IP>"),
        # Email addresses
        (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "<EMAIL>"),
        # URLs
        (re.compile(r"https?://[^\s]+"), "<URL>"),
        # File paths (absolute)
        (re.compile(r"/[\w/.-]+\.\w+"), "<PATH>"),
        # Windows paths
        (re.compile(r"[A-Z]:\\[\w\\.]+"), "<PATH>"),
        # Numbers in common variable patterns
        (re.compile(r"(?:count|size|length|offset|limit|page|total)\s*[:=]\s*\d+", re.I), lambda m: re.sub(r"\d+", "<N>", m.group())),
    ]

    # Stack trace patterns to normalize (applied in _normalize_stack)
    STACK_NORMALIZATION_PATTERNS = [
        # Generic line:col
        (re.compile(r":(\d+):(\d+)"), ":<N>:<N>"),
    ]

    def _normalize_path(self, path: str) -> str:
        """Normalize a file path by removing project-specific prefixes."""
        # Keep the last few meaningful path components
        parts = path.replace("\\", "/").split("/")
        if len(parts) > 3:
            return "/".join(["..."] + parts[-3:])
        return path

    def fingerprint(self, error: ErrorInput) -> FingerprintResult:
        """
        Create a deterministic fingerprint from an error.
        The same logical error always produces the same fingerprint.
        """
        # Normalize the error message
        normalized_message = self._normalize_text(error.error_message)

        # Normalize the stack trace
        normalized_stack = ""
        if error.stack_trace:
            normalized_stack = self._normalize_stack(error.stack_trace)

        # Build the fingerprint input
        fingerprint_input = "|".join([
            error.error_type.lower().strip(),
            normalized_message,
            normalized_stack,
            (error.route or "").lower().strip(),
            (error.file_location or "").lower().strip(),
        ])

        # Generate deterministic hash
        fingerprint = hashlib.sha256(
            fingerprint_input.encode("utf-8")
        ).hexdigest()[:16]  # 16 chars is sufficient for collision avoidance

        return FingerprintResult(
            fingerprint=fingerprint,
            normalized_message=normalized_message,
            normalized_stack=normalized_stack,
            error_type=error.error_type,
            route=error.route,
            file_location=error.file_location,
        )

    def _normalize_text(self, text: str) -> str:
        """Normalize variable parts of text."""
        normalized = text.lower().strip()
        for pattern, replacement in self.NORMALIZATION_PATTERNS:
            if callable(replacement):
                normalized = pattern.sub(replacement, normalized)
            else:
                normalized = pattern.sub(replacement, normalized)
        return normalized

    def _normalize_stack(self, stack: str) -> str:
        """Normalize a stack trace."""
        lines = stack.strip().split("\n")
        normalized_lines = []
        node_pattern = re.compile(r"at\s+.*\s+\(([^)]+)\)")
        python_pattern = re.compile(r'File "([^"]+)", line (\\d+)')

        for line in lines:
            normalized = line.strip()

            # Node.js style: at Function (file:line:col)
            m = node_pattern.match(normalized)
            if m:
                normalized = f"at <FUNC> ({self._normalize_path(m.group(1))})"
            else:
                # Python style: File "path", line N
                m2 = python_pattern.match(normalized)
                if m2:
                    normalized = f'File "{self._normalize_path(m2.group(1))}", line <N>'

            # Apply remaining patterns (generic line:col)
            for pattern, replacement in self.STACK_NORMALIZATION_PATTERNS:
                if callable(replacement):
                    normalized = pattern.sub(replacement, normalized)
                else:
                    normalized = pattern.sub(replacement, normalized)
            normalized_lines.append(normalized)
        # Only keep the meaningful part of the stack (first 10 lines)
        return "\n".join(normalized_lines[:10])


# Global fingerprint engine singleton
fingerprint_engine = FingerprintEngine()
