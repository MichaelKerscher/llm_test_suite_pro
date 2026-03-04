from llm_suite.models import TestCase

class StrategyHook:
    name = "base"
    def apply(self, tc: TestCase) -> TestCase:
        return tc