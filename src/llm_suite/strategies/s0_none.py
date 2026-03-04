from llm_suite.strategies.base import StrategyHook
from llm_suite.models import TestCase

class S0None(StrategyHook):
    name = "S0"
    def apply(self, tc: TestCase) -> TestCase:
        return tc