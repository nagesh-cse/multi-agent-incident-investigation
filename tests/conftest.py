import os
import pytest

# Ensure unit tests and test suites always run deterministically offline
os.environ["USE_MOCK_LLM"] = "true"
