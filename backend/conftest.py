"""Pytest bootstrap: put the backend/ dir on sys.path so the flat top-level
modules (agent, tools, llm, ...) import cleanly when tests run from anywhere.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
