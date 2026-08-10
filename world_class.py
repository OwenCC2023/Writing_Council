"""World classification tiers and the capabilities each one buys.

The pipeline used to ask one question — is this Earth? — and hang the whole alien
harness on the answer. That put a wands-in-contemporary-Britain world in the same tier
as an ammonia sea: a world bible, an Opus writer on every pass, and two reviewers pushing
for more strangeness, on material whose sensory ground the model already knows.

Three tiers, split on sensory ground rather than rule count. Every gate reads a predicate
here rather than comparing strings, so a tier's capabilities are defined once.
"""

EARTH = "EARTH"
SECONDARY = "SECONDARY"
NON_EARTH = "NON-EARTH"
CLASSES = (EARTH, SECONDARY, NON_EARTH)

AUTO = "auto"  # let the planner classify; the default for every entry point

_ALIASES = {
    "": AUTO,
    "auto": AUTO,
    "earth": EARTH,
    "secondary": SECONDARY,
    "non-earth": NON_EARTH,
    "non_earth": NON_EARTH,
    "nonearth": NON_EARTH,
}


def normalize(value: str) -> str:
    """User input → a canonical class or AUTO. Raises ValueError on anything else."""
    key = (value or "").strip().lower()
    if key not in _ALIASES:
        raise ValueError(
            f"Unknown world_class {value!r}; expected one of "
            f"{(AUTO,) + CLASSES}."
        )
    return _ALIASES[key]


def parse_tag(value: str) -> str:
    """A tag the planner emitted → a canonical class. Unknown text falls back to EARTH,
    matching the pre-tier behavior of a missing or unreadable tag."""
    key = (value or "").strip().lower()
    resolved = _ALIASES.get(key, EARTH)
    return EARTH if resolved == AUTO else resolved


def wants_canon(world_class: str) -> bool:
    """A canon sheet — the short list of load-bearing rules. Both non-Earth tiers get
    one: a secondary world's departure set is exactly what is worth precomputing."""
    return world_class in (SECONDARY, NON_EARTH)


def wants_bible(world_class: str) -> bool:
    """A world bible — the dense sensory detail bank, plus the plan revision that
    exploits it. Only for worlds whose sensory texture the writer cannot assume."""
    return world_class == NON_EARTH


def wants_opus_writer(world_class: str) -> bool:
    """Opus on every write pass, not just the first."""
    return world_class == NON_EARTH


def wants_strangeness_reviewers(world_class: str) -> bool:
    """StrangenessReviewerAgent + SensoryQuotaAgent in the Inner fan-out. Both push
    toward more world-surface, which a secondary world does not need."""
    return world_class == NON_EARTH


def wants_smaller_sections(world_class: str) -> bool:
    """More, smaller sections so the writer holds less world-state per section."""
    return world_class == NON_EARTH


def is_non_earth(world_class: str) -> bool:
    """Back-compat for the boolean the API used to return."""
    return world_class == NON_EARTH
