"""These modules call the production Supabase project or OpenAI at import time
and may write rows (e.g. facts attached to property 16 / document 2).
They run only when explicitly requested: SMARTBUY_LIVE_TESTS=1 pytest
"""

import os

LIVE_TEST_MODULES = [
    "test_classifier.py",
    "test_extraction_engine.py",
    "test_fact_mapper.py",
    "test_fact_repository_v2.py",
    "test_facts_repository.py",
    "test_knowledge_links.py",
    "test_knowledge_repository.py",
    "test_properties.py",
    "test_supabase.py",
    "test_supabase_raw.py",
    "test_supabase_sync.py",
]

# Script-style tests of prototype modules that main_api does not load
# (agent_core, auth_service, fascicolo/evaluation engines, llm_gateway).
# They target older signatures of those prototypes; revive them together
# with the module when it is wired into the API.
PROTOTYPE_TEST_MODULES = [
    "test_agent_core.py",
    "test_authentication.py",
    "test_fascicolo_engine.py",
    "test_issue_priority_engine.py",
    "test_llm_gateway.py",
]

collect_ignore = PROTOTYPE_TEST_MODULES + ([] if os.getenv("SMARTBUY_LIVE_TESTS") == "1" else LIVE_TEST_MODULES)
