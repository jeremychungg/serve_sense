"""
Serve Sense label definitions.

9-class classification system for tennis serve technique analysis.
"""

# All valid serve labels
SERVE_LABELS = [
    "flat_good_mechanics",
    "flat_low_toss",
    "flat_low_racket_speed",
    "slice_good_mechanics",
    "slice_low_toss",
    "slice_low_racket_speed",
    "kick_good_mechanics",
    "kick_low_toss",
    "kick_low_racket_speed",
]

# Human-readable display names
LABEL_DISPLAY_NAMES = {
    "flat_good_mechanics": "Flat – Good Mechanics",
    "flat_low_toss": "Flat – Low Toss",
    "flat_low_racket_speed": "Flat – Low Racket Speed",
    "slice_good_mechanics": "Slice – Good Mechanics",
    "slice_low_toss": "Slice – Low Toss",
    "slice_low_racket_speed": "Slice – Low Racket Speed",
    "kick_good_mechanics": "Kick – Good Mechanics",
    "kick_low_toss": "Kick – Low Toss",
    "kick_low_racket_speed": "Kick – Low Racket Speed",
}

# Reverse mapping: display name -> internal label
DISPLAY_TO_LABEL = {v: k for k, v in LABEL_DISPLAY_NAMES.items()}


def get_label_display_name(label: str) -> str:
    """Get human-readable name for a label."""
    return LABEL_DISPLAY_NAMES.get(label, label)


def is_valid_label(label: str) -> bool:
    """Check if a label is valid."""
    return label in SERVE_LABELS or label in DISPLAY_TO_LABEL


def normalize_label(label: str) -> str:
    """Convert display name to internal label format."""
    if label in DISPLAY_TO_LABEL:
        return DISPLAY_TO_LABEL[label]
    return label

