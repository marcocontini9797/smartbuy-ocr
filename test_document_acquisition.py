from document_engine.document_acquisition import build_document_packages, persist_request_drafts


def items(plan):
    return {i["document_type"]: i for g in plan["packages"] for i in g["items"]}


def test_conditional_and_existing_documents():
    plan = build_document_packages({"id":16,"purpose":"sale","is_condominium":True},
        [{"document_type":"ape_energy_certificate"}],
        [{"document_type":"visura_catastale","status":"sent","request_id":"r1"}])
    result = items(plan)
    assert result["ape"]["status"] == "present"
    assert result["visura_catastale"]["status"] == "sent"
    assert "verbali_assembleari" in result
    assert "successione" not in result
    assert "contratto_locazione" not in result
    assert plan["delivery_status"] == "not_sent"


def test_unknown_condominium_requests_clarification():
    plan = build_document_packages({"id":16,"purpose":"rent"}, [], [])
    assert "titoli_edilizi" not in items(plan)
    assert "regolamento_condominiale" not in items(plan)
    assert any(c["condition"] == "condominium" for c in plan["applicability_checks"])


def test_retry_does_not_overwrite_received_or_cancelled():
    saved = []
    class Client:
        def table(self, name):
            assert name == "smartbuy_document_requests"
            return self
        def upsert(self, rows, **options):
            assert options["ignore_duplicates"] is True
            saved.extend(rows)
            return self
        def execute(self): pass
    plan = build_document_packages({"id":16}, [], [
        {"document_type":"ape","status":"received","request_id":"r1"},
        {"document_type":"visura_catastale","status":"cancelled","request_id":"r2"}])
    persist_request_drafts(Client(), plan)
    assert all(r["document_type"] not in {"ape","visura_catastale"} for r in saved)
    assert len({r["request_id"] for r in saved}) == len(saved)
