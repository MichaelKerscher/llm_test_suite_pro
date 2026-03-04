import os
import sys

# allow imports from src/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from llm_suite.cli import main

if __name__ == "__main__":
    main()