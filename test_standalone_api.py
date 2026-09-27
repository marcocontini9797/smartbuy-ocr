"""The OCR repository must run without its former parent checkout."""

import subprocess
import sys
from pathlib import Path

import pytest

from document_engine.ingestion import MAX_FILE_SIZE, validate_file


def test_main_api_imports_from_this_repository_only():
    root = Path(__file__).resolve().parent
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(root)!r}); "
        "from main_api import app; "
        "from smartbuy import profile, risk, validation, document_facts_loader; "
        f"assert all(str(Path(module.__file__).resolve()).startswith({str(root)!r}) "
        "for module in (profile, risk, validation, document_facts_loader)); "
        "assert app.title == 'SmartBuy AI API'"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", "from pathlib import Path; " + code],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_upload_limit_matches_legacy_ocr_limit():
    assert MAX_FILE_SIZE == 20_000_000
    validate_file("documento.pdf", b"x" * MAX_FILE_SIZE)
    with pytest.raises(ValueError, match="20 MB"):
        validate_file("documento.pdf", b"x" * (MAX_FILE_SIZE + 1))
