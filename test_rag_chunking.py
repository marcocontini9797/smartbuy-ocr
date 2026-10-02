"""Chunking for retrieval: pages, structure, size limits, coverage (offline)."""
import pytest

from document_engine.rag_chunking import MAX_SIZE, MIN_SIZE, TARGET_SIZE, chunk_document, split_pages


def paragraph(topic, sentences=6):
    return " ".join(f"La clausola {topic} stabilisce l'obbligo numero {n} per le parti contraenti." for n in range(sentences))


def test_pages_come_from_the_ocr_markers():
    text = f"--- PAGINA 1 ---\nPrima pagina.\n\n--- PAGINA 2 ---\nSeconda pagina.\n\n--- PAGINA 3 ---\nTerza."
    assert [(page, body.strip()) for page, body in split_pages(text)] == [
        (1, "Prima pagina."), (2, "Seconda pagina."), (3, "Terza.")]


def test_text_without_markers_is_one_page():
    assert [page for page, _ in split_pages("solo testo")] == [1]
    assert split_pages("   \n ") == []
    assert chunk_document("") == [] and chunk_document(None) == []


def test_a_chunk_reports_the_pages_it_spans():
    text = ("--- PAGINA 1 ---\n" + "Riga della prima pagina con dati catastali. " * 5 +
            "\n\n--- PAGINA 2 ---\n" + "Riga della seconda pagina con altri dati. " * 5)
    chunks = chunk_document(text)
    assert chunks[0].page_start == 1 and chunks[-1].page_end == 2
    assert all(c.page_start <= c.page_end for c in chunks)


def test_each_section_starts_a_new_chunk_with_its_heading():
    text = "\n\n".join(f"Art. {n} - Oggetto {n}\n{paragraph(n)}" for n in range(1, 4))
    chunks = chunk_document(text)
    assert len(chunks) >= 3
    assert [c.heading for c in chunks[:3]] == ["Art. 1 - Oggetto 1", "Art. 2 - Oggetto 2", "Art. 3 - Oggetto 3"]
    assert all(c.text.startswith("Art.") for c in chunks[:3])


def test_tiny_sections_are_merged_instead_of_becoming_heading_only_chunks():
    text = "Art. 1 - Oggetto\nBreve.\nArt. 2 - Durata\nAnche questa breve.\nArt. 3 - Prezzo\nEuro 100.000."
    chunks = chunk_document(text)
    assert len(chunks) == 1 and "Euro 100.000." in chunks[0].text


def test_the_heading_in_effect_is_carried_across_pages():
    text = ("--- PAGINA 1 ---\nREGOLAMENTO DI CONDOMINIO\n" + paragraph("uso", 12) +
            "\n\n--- PAGINA 2 ---\n" + paragraph("parti comuni", 12))
    chunks = chunk_document(text)
    assert {c.heading for c in chunks} == {"REGOLAMENTO DI CONDOMINIO"}
    assert max(c.page_end for c in chunks) == 2


def test_a_long_block_is_split_with_overlap_and_nothing_is_lost():
    sentences = [f"Dichiarazione numero {n} resa dalla parte venditrice nel presente atto." for n in range(80)]
    chunks = chunk_document(" ".join(sentences))
    assert len(chunks) > 3
    assert all(len(c.text) <= MAX_SIZE for c in chunks)
    joined = "\n".join(c.text for c in chunks)
    assert all(s in joined for s in sentences)
    # consecutive chunks share their boundary sentence (overlap)
    assert set(chunks[0].text.split("\n")) & set(chunks[1].text.split("\n"))


def test_short_lines_with_identifiers_are_never_cut():
    lines = [f"Foglio {n} Particella {n + 30} Subalterno {n % 5} Categoria A/{n % 4 + 2} Rendita 1.{n:03d},00 euro" for n in range(60)]
    chunks = chunk_document("\n".join(lines))
    joined = "\n".join(c.text for c in chunks)
    assert all(line in joined for line in lines)
    assert all(piece in lines for c in chunks for piece in c.text.split("\n"))     # no line was cut


@pytest.mark.parametrize("text", [
    "Un testo molto breve.",
    "--- PAGINA 1 ---\nCiao\n--- PAGINA 2 ---\nMondo",
    "ELENCO\n" + "voce molto lunga " * 200,
])
def test_every_line_of_the_input_ends_up_in_some_chunk(text):
    body = "\n".join(c.text for c in chunk_document(text))
    for line in text.splitlines():
        if line.strip() and not line.startswith("---"):
            assert line.strip()[:40] in body


def test_chunking_is_deterministic_and_indexes_are_sequential():
    text = "\n\n".join(f"Art. {n}\n{paragraph(n)}" for n in range(1, 8))
    first, second = chunk_document(text), chunk_document(text)
    assert first == second
    assert [c.index for c in first] == list(range(len(first)))


def test_chunks_stay_near_the_target_size():
    text = "\n\n".join(f"Art. {n} - Titolo\n{paragraph(n, 10)}" for n in range(1, 10))
    sizes = [len(c.text) for c in chunk_document(text)]
    assert max(sizes) <= MAX_SIZE
    assert sum(size >= MIN_SIZE for size in sizes) >= len(sizes) - 1       # at most one small tail
    assert max(sizes) <= TARGET_SIZE * 2
