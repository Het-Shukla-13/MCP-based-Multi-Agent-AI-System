from app.enums import EvidenceType, MemoryType, TemporalScope


def test_enum_str_is_plain_value():
    # Regression: with (str, Enum), Python 3.11+ makes str(MemoryType.fact) ==
    # "MemoryType.fact", which silently broke memory promotion after the 3.12 upgrade.
    assert str(MemoryType.fact) == "fact"
    assert str(EvidenceType.explicit) == "explicit"
    assert f"{TemporalScope.durable}" == "durable"
