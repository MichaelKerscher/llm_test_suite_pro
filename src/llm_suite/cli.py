import argparse
from llm_suite.config import load_config
from llm_suite.pipeline import run_pipeline

def main():
    p = argparse.ArgumentParser(description="Generalized LLM Test Suite")
    p.add_argument("--tests", required=True, help="Path to CSV testcases file")
    p.add_argument("--mode", choices=["incident", "testcase"], default=None, help="Run mode")
    p.add_argument("--case", default=None, help="Filter by testcase_id")
    p.add_argument("--incident", default=None, help="Filter by incident_id")
    p.add_argument("--no-judge", action="store_true", help="Disable judge for this run")
    p.add_argument("--enable-strategy-hook", action="store_true", help="Enable strategy hook (default off)")
    p.add_argument("--strategy", default=None, help="Force strategy when hook enabled (e.g., S2)")
    args = p.parse_args()

    cfg = load_config(args)
    run_pipeline(cfg)