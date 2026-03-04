from llm_suite.strategies.s0_none import S0None

_STRATEGIES = {
    "S0": S0None,
}

def make_strategy(name: str):
    name = (name or "S0").strip().upper()
    cls = _STRATEGIES.get(name, S0None)
    return cls()