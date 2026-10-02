"""A harder, more realistic fascicolo: rag_corpus.py plus near-duplicates and long documents.

Real pratiche have the same minutes every year, quotes that repeat the figures of the
minutes, and acts and regulations full of boilerplate. There the question is often
"which document?", not just "which sentence?", and a fixed-size chunker has many more
ways to cut the answer or bury it. Still synthetic, still no personal data.
"""

from __future__ import annotations

from evaluation import rag_corpus as base

_ATTO_CONDIZIONI = """
--- PAGINA 5 ---
Art. 11 - Possesso e godimento
Il possesso giuridico e il godimento dell'immobile sono trasferiti alla parte acquirente da oggi, con tutti gli effetti utili ed onerosi.

Art. 12 - Garanzia per evizione e vizi
La parte venditrice presta la garanzia per evizione e dichiara che l'immobile e' venduto a corpo, nello stato di fatto e di diritto in cui si trova, con ogni accessione, pertinenza e diritto di condominio sulle parti comuni dell'edificio.

Art. 13 - Imposte
Ai fini fiscali le parti dichiarano che la presente vendita e' soggetta ad imposta di registro nella misura del 2% sul valore catastale, oltre imposta ipotecaria di Euro 50,00 e imposta catastale di Euro 50,00.

Art. 14 - Cancellazione dell'ipoteca
Le spese per la cancellazione dell'ipoteca sono a carico della parte venditrice, che si obbliga a consegnare la quietanza della banca entro trenta giorni.

--- PAGINA 6 ---
Art. 15 - Trattamento dei dati personali
Le parti prendono atto dell'informativa sul trattamento dei dati personali resa dal notaio ai sensi del Regolamento UE 2016/679.

Art. 16 - Mediazione
La parte acquirente dichiara che per la presente vendita si e' avvalsa dell'opera dell'agenzia "Casa Diretta S.r.l." e si impegna a corrispondere una provvigione di Euro 8.550,00 oltre IVA, gia' versata con le modalita' indicate all'articolo 3.

Art. 17 - Dichiarazioni sugli impianti
La parte venditrice dichiara che le dichiarazioni di conformita' degli impianti elettrico e di riscaldamento sono state consegnate alla parte acquirente, che dichiara di averle ricevute.

Art. 18 - Antiriciclaggio
Le parti dichiarano di conoscere le conseguenze civili e penali delle dichiarazioni mendaci rese ai sensi della normativa antiriciclaggio e confermano le modalita' di pagamento indicate nel presente atto.

Art. 19 - Trascrizione e voltura
Il notaio e' autorizzato ad eseguire le formalita' di trascrizione e di voltura catastale a favore della parte acquirente.
"""

_REGOLAMENTO_EXTRA = """
--- PAGINA 4 ---
Art. 10 - Rifiuti e raccolta differenziata
I rifiuti devono essere conferiti negli appositi contenitori, nel rispetto della raccolta differenziata, dalle ore 20:00 alle ore 7:00.

Art. 11 - Biciclette e cortile
E' vietato depositare biciclette nell'androne e sulle scale; e' consentito l'uso del cortile interno solo per il ricovero di biciclette.

Art. 12 - Balconi e terrazzi
E' vietato stendere panni sulle facciate prospicienti la via. I vasi devono essere assicurati in modo da evitarne la caduta.

Art. 13 - Condizionatori e antenne
Le unita' esterne dei condizionatori sono ammesse solo sul lato cortile, previa comunicazione all'amministratore. Le antenne televisive sono collettive.

Art. 14 - Sanzioni
La violazione delle norme del presente regolamento comporta una sanzione fino a Euro 200,00 a favore del fondo comune.

Art. 15 - Modifica del regolamento
Il regolamento puo' essere modificato con la maggioranza degli intervenuti che rappresenti almeno la meta' del valore dell'edificio.
"""


def _verbale(year, day_month, present, millesimi, rendiconto_year, result_word, result_amount, works, works_amount,
             company, morosi):
    return f"""--- PAGINA 1 ---
VERBALE DI ASSEMBLEA ORDINARIA DEL CONDOMINIO "PALAZZO ZAMBONI"
Bologna, {day_month} {year}
Sono presenti {present} condomini su 12 che rappresentano {millesimi} millesimi su 1000.

Punto 1 - Approvazione del rendiconto consuntivo {rendiconto_year}
Il rendiconto consuntivo {rendiconto_year} viene approvato all'unanimita' dei presenti. L'{result_word} di gestione e' di Euro {result_amount}.

Punto 2 - Lavori
L'assemblea delibera {works}, per un importo complessivo di Euro {works_amount} oltre IVA, affidati all'impresa {company}.

--- PAGINA 2 ---
Punto 3 - Morosita'
{morosi}

Punto 4 - Varie ed eventuali
Non essendovi altro da deliberare la seduta e' sciolta.
"""


DOCUMENTS = [dict(d) for d in base.DOCUMENTS]
for _doc in DOCUMENTS:
    if _doc["id"] == 3:
        _doc["text"] += _ATTO_CONDIZIONI
    if _doc["id"] == 4:
        _doc["text"] += _REGOLAMENTO_EXTRA

DOCUMENTS += [
    {"id": 8, "name": "verbale_assemblea_2022.pdf", "type": "verbale_assemblea_condominio", "text": _verbale(
        2022, "12 aprile", 9, 702, 2021, "avanzo", "1.045,00", "il rifacimento della copertura del tetto", "96.200,00",
        "Copertura Bologna S.r.l.", "Risultano morosi tre condomini per un totale di Euro 5.120,00.")},
    {"id": 9, "name": "verbale_assemblea_2023.pdf", "type": "verbale_assemblea_condominio", "text": _verbale(
        2023, "18 aprile", 7, 590, 2022, "disavanzo", "1.870,00",
        "la sostituzione dell'impianto citofonico e di videosorveglianza", "18.400,00", "Elettrosistemi S.r.l.",
        "Risulta moroso un condomino per un totale di Euro 1.240,00.")},
    {"id": 10, "name": "verbale_assemblea_2024.pdf", "type": "verbale_assemblea_condominio", "text": _verbale(
        2024, "16 aprile", 8, 655, 2023, "avanzo", "3.050,00",
        "la messa a norma dell'impianto antincendio dell'autorimessa", "27.300,00", "Sicurezza Emilia S.r.l.",
        "Risultano morosi due condomini per un totale di Euro 2.015,00.")},
    {"id": 11, "name": "estratto_conto_condominiale.pdf", "type": "estratto_conto", "text": """--- PAGINA 1 ---
ESTRATTO CONTO CONDOMINIALE ESERCIZIO 2025
Condominio "Palazzo Zamboni" - Unita' Foglio 12 Particella 34 Subalterno 3 - Condomino ROSSI MARIO
Millesimi di proprieta': 82,5 Millesimi di riscaldamento: 71,0

Rate ordinarie
Rata 1 scadenza 31/01/2025 Euro 612,00 pagata
Rata 2 scadenza 30/04/2025 Euro 612,00 pagata
Rata 3 scadenza 31/07/2025 Euro 612,00 da pagare
Rata 4 scadenza 31/10/2025 Euro 612,00 da pagare

Quota straordinaria lavori facciata
Prima rata 40% alla firma del contratto Euro 4.620,00 scadenza 15/09/2025
Saldo a debito al 31/12/2024: Euro 0,00
"""},
    {"id": 12, "name": "preventivo_edilbo.pdf", "type": "preventivo", "text": """--- PAGINA 1 ---
PREVENTIVO N. 2025/118 - EDILBO S.R.L.
Oggetto: ripristino e tinteggiatura della facciata e rifacimento del cornicione - Palazzo Zamboni, Via Zamboni 33

Ponteggi e opere provvisionali Euro 21.800,00
Ripristino degli intonaci e tinteggiatura Euro 58.400,00
Rifacimento del cornicione lato strada Euro 52.300,00
Oneri della sicurezza Euro 3.600,00
Imprevisti e lavori in economia Euro 12.400,00
Totale preventivo Euro 148.500,00 oltre IVA

Validita' dell'offerta: 90 giorni. Durata dei lavori: 120 giorni lavorativi dalla consegna.
"""},
]

QUESTIONS = list(base.QUESTIONS) + [
    # near-duplicate documents: the right year / the right document must be found
    ("t1", "which", "Quanto fu l'avanzo del rendiconto 2021?", "avanzo di gestione e' di euro 1.045,00"),
    ("t2", "which", "Che lavori furono deliberati nell'assemblea del 2022?", "rifacimento della copertura del tetto"),
    ("t3", "which", "Di quanto fu il disavanzo del rendiconto 2022?", "disavanzo di gestione e' di euro 1.870,00"),
    ("t4", "which", "Chi ha fatto i lavori del citofono?", "elettrosistemi s.r.l."),
    ("t5", "which", "Quanto costò la messa a norma antincendio dell'autorimessa?", "euro 27.300,00"),
    ("t6", "which", "Quanti condomini erano presenti all'assemblea del 2023?", "7 condomini su 12 che rappresentano 590 millesimi"),
    ("t7", "which", "Quanto costano i ponteggi per la facciata?", "ponteggi e opere provvisionali euro 21.800,00"),
    ("t8", "which", "Quanto devo pagare come prima rata dei lavori della facciata?", "euro 4.620,00 scadenza"),
    ("t9", "which", "Quando scade la terza rata ordinaria del condominio?", "rata 3 scadenza 31/07/2025"),
    # a detail inside a long document
    ("d1", "detail", "Chi paga la cancellazione dell'ipoteca?", "spese per la cancellazione dell'ipoteca sono a carico della parte venditrice"),
    ("d2", "detail", "Quanto è la provvigione dell'agenzia immobiliare?", "provvigione di euro 8.550,00"),
    ("d3", "detail", "Dove posso mettere il climatizzatore?", "unita' esterne dei condizionatori sono ammesse solo sul lato cortile"),
    ("d4", "detail", "Che sanzione c'è se non rispetto il regolamento?", "sanzione fino a euro 200,00"),
    ("d5", "detail", "Quanto pago di imposta di registro?", "imposta di registro nella misura del 2%"),
    ("d6", "detail", "A che ora posso portare giù la spazzatura?", "dalle ore 20:00 alle ore 7:00"),
    ("d7", "detail", "Posso lasciare la bici nell'androne?", "vietato depositare biciclette nell'androne"),
    ("d8", "detail", "Con quale maggioranza si cambia il regolamento?", "almeno la meta' del valore dell'edificio"),
    # more questions with no answer in the documents
    ("a9", "absent", "Qual è il codice fiscale dell'acquirente?", None),
    ("a10", "absent", "Qual è il numero di telefono dell'amministratore?", None),
    ("a11", "absent", "Quanti metri quadri ha il giardino?", None),
    ("a12", "absent", "Qual è l'avanzo di gestione del 2019?", None),
]


# --- scale: a fascicolo with dozens of near-duplicate documents --------------------------------------
# Many verbali, estratti conto and preventivi with the same structure and different figures, so the
# top-k of any retriever is full of plausible wrong answers. Seeded: the same corpus every run.

_WORKS = ["il rifacimento delle grondaie", "la sostituzione del portone d'ingresso", "la revisione della rete fognaria",
          "la manutenzione straordinaria del cortile", "la sostituzione delle porte tagliafuoco",
          "la tinteggiatura del vano scala", "la riparazione del lastrico solare", "il rinnovo dell'impianto di illuminazione"]
_COMPANIES = ["Edilgamma S.r.l.", "Costruzioni Reno S.r.l.", "Impresa Navile S.n.c.", "Tecnoimpianti Emilia S.r.l.",
              "Ristrutturazioni Savena S.r.l.", "Lavori Edili Bolognesi S.r.l."]


def _money(rng):
    return f"{rng.randint(1, 99):d}.{rng.randint(0, 999):03d},{rng.randint(0, 99):02d}"


def scaled_documents(seed: int = 7):
    import random

    rng = random.Random(seed)
    documents = list(DOCUMENTS)
    next_id = max(d["id"] for d in documents) + 1
    # meeting years whose rendiconto year is not 2019 (question a12 must stay unanswerable)
    for year in (2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021):
        documents.append({"id": next_id, "name": f"verbale_assemblea_{year}.pdf", "type": "verbale_assemblea_condominio",
                          "text": _verbale(year, f"{rng.randint(10, 28)} aprile", rng.randint(5, 11), rng.randint(520, 760),
                                           year - 1, rng.choice(["avanzo", "disavanzo"]), _money(rng), rng.choice(_WORKS),
                                           _money(rng), rng.choice(_COMPANIES),
                                           f"Risultano morosi {rng.randint(1, 4)} condomini per un totale di Euro {_money(rng)}.")})
        next_id += 1
    for year in (2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024):
        rate = _money(rng)
        documents.append({"id": next_id, "name": f"estratto_conto_{year}.pdf", "type": "estratto_conto", "text": f"""--- PAGINA 1 ---
ESTRATTO CONTO CONDOMINIALE ESERCIZIO {year}
Condominio "Palazzo Zamboni" - Unita' Foglio 12 Particella 34 Subalterno 3 - Condomino ROSSI MARIO
Millesimi di proprieta': 82,5 Millesimi di riscaldamento: 71,0

Rate ordinarie
Rata 1 scadenza 31/01/{year} Euro {rate} pagata
Rata 2 scadenza 30/04/{year} Euro {rate} pagata
Rata 3 scadenza 31/07/{year} Euro {rate} pagata
Rata 4 scadenza 31/10/{year} Euro {rate} pagata

Saldo a debito al 31/12/{year - 1}: Euro {_money(rng)}
"""})
        next_id += 1
    for number, year in enumerate((2013, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2023, 2024), start=1):
        documents.append({"id": next_id, "name": f"preventivo_{year}_{number}.pdf", "type": "preventivo", "text": f"""--- PAGINA 1 ---
PREVENTIVO N. {year}/{rng.randint(100, 999)} - {rng.choice(_COMPANIES).upper()}
Oggetto: {rng.choice(_WORKS)} - Palazzo Zamboni, Via Zamboni 33

Ponteggi e opere provvisionali Euro {_money(rng)}
Ripristino delle superfici Euro {_money(rng)}
Opere accessorie Euro {_money(rng)}
Oneri della sicurezza Euro {_money(rng)}
Imprevisti e lavori in economia Euro {_money(rng)}
Totale preventivo Euro {_money(rng)} oltre IVA

Validita' dell'offerta: {rng.choice([30, 60, 90])} giorni. Durata dei lavori: {rng.randint(20, 90)} giorni lavorativi dalla consegna.
"""})
        next_id += 1
    return documents
