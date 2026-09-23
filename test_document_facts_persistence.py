from api.document_routes import persist_document_facts


class FakeTable:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def insert(self, rows):
        self.store.setdefault(self.name, []).extend(rows if isinstance(rows, list) else [rows])
        return self

    def execute(self):
        return self


class FakeClient:
    def __init__(self):
        self.store = {}

    def table(self, name):
        return FakeTable(self.store, name)


def test_each_extracted_field_becomes_a_fact_linked_to_its_own_provenance():
    client = FakeClient()
    saved = persist_document_facts(
        client, property_id=16,
        document={"id": 41, "file_name": "ape.pdf", "document_type": "ape"},
        analysis={"id": "analysis-uuid"},
        extracted_fields={
            "tipo_documento": "ape", "note_incertezza": ["x"], "classe_energetica": "C",
            "superficie_utile_mq": {"valore": "78,5", "fonte": "Superficie utile: 78,5 m²", "confidence": 0.9},
            "riferimenti_catastali": [], "data_scadenza": None,
        },
        default_confidence=0.8, model_name="model-x",
    )
    assert saved == 2
    facts = {f["fact_name"]: f for f in client.store["property_facts"]}
    provenance = {p["id"]: p for p in client.store["fact_provenance"]}
    assert set(facts) == {"classe_energetica", "superficie_utile_mq"}
    surface = facts["superficie_utile_mq"]
    assert surface["fact_value"] == {"value": "78,5"} and surface["confidence_score"] == 0.9
    assert surface["source_document_id"] == 41
    assert provenance[surface["provenance_id"]]["source_text"] == "Superficie utile: 78,5 m²"
    assert facts["classe_energetica"]["confidence_score"] == 0.8
    assert all(p["property_id"] == 16 and p["document_id"] == 41 for p in provenance.values())


def test_no_facts_no_writes():
    client = FakeClient()
    assert persist_document_facts(client, property_id=1, document={"id": 1}, analysis={"id": "a"},
                                  extracted_fields={"tipo_documento": "ape"}, default_confidence=None, model_name=None) == 0
    assert client.store == {}
