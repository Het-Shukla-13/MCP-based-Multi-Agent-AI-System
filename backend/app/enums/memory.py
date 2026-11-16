from enum import StrEnum

class MemoryType(StrEnum):
    preference = "preference"
    fact = "fact"
    decision = "decision"
    task = "task"


class EvidenceType(StrEnum):
    explicit = "explicit"
    repeated = "repeated"
    inferred = "inferred"


class TemporalScope(StrEnum):
    durable = "durable"
    ongoing = "ongoing"
    temporary = "temporary"


class SourceKind(StrEnum):
    statement = "statement"
    question = "question"
    request = "request"
    assistant_claim = "assistant_claim"
    hypothetical = "hypothetical"
    unclear = "unclear"


class ValueSpecificity(StrEnum):
    concrete = "concrete"
    vague = "vague"


class OverwriteRisk(StrEnum):
    none = "none"
    low = "low"
    high = "high"


class ProfileCategory(StrEnum):
    identity = "identity"
    preference = "preference"
    project = "project"
    relationship = "relationship"
    wellbeing = "wellbeing"
    other = "other"