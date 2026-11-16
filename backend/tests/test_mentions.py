from app.agent_layer.core.mentions import parse_agent_mention

AGENTS = {"general", "code", "data", "research", "document", "image"}


def test_leading_mention_selects_agent_and_is_removed():
    assert parse_agent_mention("@code reverse a list", AGENTS) == ("code", "reverse a list")


def test_mention_in_middle_and_case_insensitive():
    assert parse_agent_mention("please @Data summarise sales.csv", AGENTS) == ("data", "please summarise sales.csv")


def test_email_address_is_not_a_mention():
    assert parse_agent_mention("mail me at het@code.dev", AGENTS) == (None, "mail me at het@code.dev")


def test_unknown_name_is_ignored():
    assert parse_agent_mention("ask @john about it", AGENTS) == (None, "ask @john about it")


def test_first_known_agent_wins():
    assert parse_agent_mention("@john @research latest news", AGENTS)[0] == "research"


def test_mention_only_keeps_text():
    assert parse_agent_mention("@image", AGENTS) == ("image", "@image")
