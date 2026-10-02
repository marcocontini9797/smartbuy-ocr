"""Synthetic fascicolo and questions to measure retrieval (no personal data).

Seven documents of an invented property, written as the OCR reader returns them
(pages joined by "--- PAGINA n ---"). Each question has `gold`: a phrase that must
appear in the text of a retrieved passage for the answer to be reachable. Judging by
a phrase, not by a chunk id, keeps the comparison fair between different chunkers.
Questions with `gold=None` have no answer in the documents: a good system says so.

Categories: close (wording close to the text), gap (paraphrase, little shared
vocabulary), identifier (parcel numbers / codes), number (amounts, dates), absent.
"""

from __future__ import annotations

DOCUMENTS = [
    {"id": 1, "name": "visura_catastale.pdf", "type": "visura_catastale", "text": """--- PAGINA 1 ---
VISURA PER IMMOBILE
Situazione degli atti informatizzati al 12/05/2025
Comune di BOLOGNA (A944) - Provincia di BO
Catasto dei Fabbricati
Dati identificativi: Foglio 12 Particella 34 Subalterno 3
Indirizzo: VIA ZAMBONI n. 33 Piano 2
Categoria A/2 - Abitazione di tipo civile
Classe 4 Consistenza 5 vani
Superficie catastale: totale 92 mq, totale escluse aree scoperte 89 mq
Rendita: Euro 903,80

INTESTATI
1. ROSSI MARIO nato a BOLOGNA il 14/03/1968 - Proprieta' per 1/2
2. BIANCHI ANNA nata a MODENA il 02/09/1971 - Proprieta' per 1/2

Unità immobiliari collegate: Foglio 12 Particella 34 Subalterno 9 - Categoria C/6 - Autorimessa di 14 mq
"""},
    {"id": 2, "name": "attestato_prestazione_energetica.pdf", "type": "ape", "text": """--- PAGINA 1 ---
ATTESTATO DI PRESTAZIONE ENERGETICA
Codice identificativo: 2024-08123-BO
Data di emissione: 18/06/2024 Valido fino al: 18/06/2034
Immobile: Via Zamboni 33, Bologna - Foglio 12 Particella 34 Subalterno 3
Destinazione d'uso: residenziale
Servizi energetici presenti: climatizzazione invernale, acqua calda sanitaria

--- PAGINA 2 ---
PRESTAZIONE ENERGETICA GLOBALE
Classe energetica: D
Indice di prestazione energetica globale non rinnovabile EPgl,nren: 142,35 kWh/m2 anno
Emissioni di CO2: 28,4 kg/m2 anno
Il generatore e' una caldaia a condensazione a gas metano installata nel 2015.
Raccomandazioni: sostituzione dei serramenti con vetro doppio basso emissivo, isolamento del sottotetto.
Soggetto certificatore: Ing. Luca Verdi, iscritto all'Ordine degli Ingegneri di Bologna n. 4821
"""},
    {"id": 3, "name": "atto_compravendita.pdf", "type": "atto_compravendita", "text": """--- PAGINA 1 ---
REPUBBLICA ITALIANA
COMPRAVENDITA DI IMMOBILE
Repertorio n. 18.442 Raccolta n. 9.310
L'anno 2025, il giorno 10 del mese di giugno, in Bologna, innanzi a me dottor Paolo Neri, notaio in Bologna, sono presenti il signor ROSSI MARIO e la signora BIANCHI ANNA, di seguito "parte venditrice", e il signor GALLI MARCO, di seguito "parte acquirente".

Art. 1 - Oggetto
La parte venditrice vende alla parte acquirente, che accetta, l'appartamento sito in Bologna, Via Zamboni n. 33, al piano secondo, censito al Catasto Fabbricati al Foglio 12 Particella 34 Subalterno 3, con annessa autorimessa al Subalterno 9.

Art. 2 - Prezzo
Il prezzo della compravendita e' stato convenuto in Euro 285.000,00 (duecentoottantacinquemila virgola zero zero). La parte venditrice rilascia ampia quietanza di saldo.

--- PAGINA 2 ---
Art. 3 - Modalita' di pagamento
Il pagamento e' avvenuto mediante assegni circolari non trasferibili e un bonifico bancario di Euro 60.000,00 eseguito il 3 giugno 2025.

Art. 4 - Garanzie
La parte venditrice garantisce di essere piena proprietaria dell'immobile e che lo stesso e' libero da ipoteche, trascrizioni pregiudizievoli, privilegi e pignoramenti, ad eccezione dell'ipoteca volontaria iscritta a favore della Banca Esempio S.p.A. che sara' cancellata contestualmente al presente atto.

Art. 5 - Provenienza
L'immobile e' pervenuto alla parte venditrice con atto di donazione a rogito notaio Carlo Moretti in data 12 settembre 2009, repertorio n. 5.118.

--- PAGINA 3 ---
Art. 6 - Conformita' urbanistica ed edilizia
La parte venditrice dichiara che la costruzione dell'edificio e' stata iniziata in data anteriore al primo settembre 1967 e che successivamente sono stati eseguiti lavori di manutenzione straordinaria con SCIA n. 2011/4417 del 21 marzo 2011. Dichiara inoltre che lo stato dei luoghi e' conforme ai titoli edilizi.

Art. 7 - Attestato di prestazione energetica
La parte acquirente dichiara di aver ricevuto le informazioni e la documentazione in ordine alla attestazione della prestazione energetica dell'edificio, con classe energetica D.

--- PAGINA 4 ---
Art. 8 - Spese
Le spese del presente atto e conseguenti sono a carico della parte acquirente.

Art. 9 - Agevolazioni fiscali
La parte acquirente dichiara di avere i requisiti per le agevolazioni prima casa e si impegna a stabilire la residenza nel comune di Bologna entro diciotto mesi dalla data odierna.

Art. 10 - Condominio
La parte venditrice dichiara che sono state pagate tutte le spese condominiali ordinarie e straordinarie deliberate fino alla data odierna. Le spese per la facciata deliberate dall'assemblea del 14 aprile 2025 restano a carico della parte venditrice.
"""},
    {"id": 4, "name": "regolamento_condominio.pdf", "type": "regolamento_condominio", "text": """--- PAGINA 1 ---
REGOLAMENTO DI CONDOMINIO
CONDOMINIO "PALAZZO ZAMBONI" - VIA ZAMBONI 33 - BOLOGNA

Art. 1 - Destinazione delle unita' immobiliari
Le unita' immobiliari sono destinate ad abitazione e ad uso studio professionale. E' vietato adibirle a laboratori, attivita' rumorose, pensioni, case di cura o qualsiasi uso incompatibile con il decoro dell'edificio.

Art. 2 - Animali domestici
E' consentito detenere animali domestici di piccola e media taglia. I proprietari devono evitare rumori molesti e sono responsabili della pulizia delle parti comuni.

Art. 3 - Parti comuni
Sono parti comuni il portone, l'androne, le scale, il tetto, la facciata, le fondazioni, la caldaia centralizzata e il cortile interno.

--- PAGINA 2 ---
Art. 4 - Ripartizione delle spese
Le spese per la conservazione e il godimento delle parti comuni sono ripartite in proporzione ai millesimi di proprieta' indicati nella tabella A. Le spese di riscaldamento sono ripartite in base ai consumi e ai millesimi di riscaldamento.

Art. 5 - Lavori nelle unita' private
Gli interventi che incidono sulle parti comuni o sull'aspetto esterno dell'edificio richiedono la preventiva autorizzazione dell'assemblea. Le opere interne non strutturali vanno comunicate all'amministratore con quindici giorni di anticipo.

Art. 6 - Orari di silenzio
Dalle ore 22:00 alle ore 8:00 e dalle ore 14:00 alle ore 16:00 e' vietato produrre rumori che disturbino la quiete.

--- PAGINA 3 ---
Art. 7 - Locazioni e affitti brevi
La locazione dell'unita' immobiliare deve essere comunicata all'amministratore. Gli affitti per periodi inferiori a trenta giorni sono vietati.

Art. 8 - Assemblea
L'assemblea ordinaria e' convocata almeno una volta all'anno entro centottanta giorni dalla chiusura dell'esercizio. L'avviso di convocazione e' inviato con raccomandata o posta elettronica certificata almeno cinque giorni prima.

Art. 9 - Amministratore
L'amministratore dura in carica un anno ed e' rieleggibile. Il compenso e' stabilito dall'assemblea.
"""},
    {"id": 5, "name": "verbale_assemblea.pdf", "type": "verbale_assemblea_condominio", "text": """--- PAGINA 1 ---
VERBALE DI ASSEMBLEA ORDINARIA DEL CONDOMINIO "PALAZZO ZAMBONI"
Bologna, 14 aprile 2025
Sono presenti 8 condomini su 12 che rappresentano 685 millesimi su 1000.

Punto 1 - Approvazione del rendiconto consuntivo 2024
Il rendiconto consuntivo 2024 viene approvato con 640 millesimi favorevoli e 45 astenuti. L'avanzo di gestione e' di Euro 2.310,00.

Punto 2 - Lavori di ripristino della facciata
L'assemblea delibera i lavori di ripristino e tinteggiatura della facciata e il rifacimento del cornicione sul lato strada, per un importo complessivo di Euro 148.500,00 oltre IVA, affidati all'impresa Edilbo S.r.l. I lavori inizieranno nel mese di settembre 2025 e sono previsti 120 giorni lavorativi.

--- PAGINA 2 ---
Punto 3 - Ripartizione e pagamento delle spese straordinarie
La spesa sara' ripartita in base ai millesimi di proprieta' in tre rate: il 40% alla firma del contratto, il 40% a meta' lavori e il 20% a fine lavori. L'unita' immobiliare Foglio 12 Particella 34 Subalterno 3 e' attribuita per 82,5 millesimi.

Punto 4 - Morosita'
Risultano morosi due condomini per un totale di Euro 3.870,00. L'amministratore e' autorizzato ad avviare il recupero coattivo del credito.

Punto 5 - Varie ed eventuali
Si segnala un'infiltrazione d'acqua nel vano scala al terzo piano, da verificare con un tecnico.
"""},
    {"id": 6, "name": "relazione_tecnica.pdf", "type": "relazione_tecnica_integrata", "text": """--- PAGINA 1 ---
RELAZIONE TECNICA INTEGRATA
Immobile: Via Zamboni 33, Bologna - Foglio 12 Particella 34 Subalterno 3
Tecnico incaricato: geom. Franco Lenzi, iscritto al Collegio dei Geometri di Bologna n. 2290
Data del sopralluogo: 5 maggio 2025

CONFORMITA' CATASTALE
La planimetria catastale risulta depositata nel 1987. Dal confronto con lo stato dei luoghi emerge che la parete tra cucina e soggiorno e' stata demolita senza aggiornamento della planimetria: si riscontra una difformita' catastale sanabile mediante presentazione di una pratica DOCFA.

--- PAGINA 2 ---
CONFORMITA' URBANISTICA ED EDILIZIA
L'edificio e' stato costruito ante 1967. Presso l'archivio edilizio del Comune di Bologna sono stati reperiti la SCIA n. 2011/4417 per manutenzione straordinaria e la CILA del 2016 per il rifacimento del bagno. La demolizione del tramezzo non risulta autorizzata: occorre una CILA in sanatoria con sanzione di Euro 1.000,00.

AGIBILITA'
Il certificato di agibilita' non e' stato reperito. Per gli immobili anteriori al 1934 l'abitabilita' si intende attestata dalla costruzione, mentre per questo edificio e' consigliabile la segnalazione certificata di agibilita'.

--- PAGINA 3 ---
IMPIANTI
Sono state fornite le dichiarazioni di conformita' dell'impianto elettrico (2011) e dell'impianto di riscaldamento (2015). Non e' stata fornita la dichiarazione dell'impianto idrico.

STIMA DEI COSTI DI REGOLARIZZAZIONE
Pratica DOCFA e aggiornamento planimetria: Euro 650,00. CILA in sanatoria e sanzione: Euro 2.100,00. Totale stimato: Euro 2.750,00.
"""},
    {"id": 7, "name": "ispezione_ipotecaria.pdf", "type": "visura_ipotecaria", "text": """--- PAGINA 1 ---
ISPEZIONE IPOTECARIA
Conservatoria dei Registri Immobiliari di Bologna
Immobile: Foglio 12 Particella 34 Subalterno 3 e Subalterno 9
Ispezione eseguita il 26/05/2025

ELENCO DELLE FORMALITA'
1. Ipoteca volontaria iscritta il 22/03/2011 a favore di BANCA ESEMPIO S.P.A. - capitale Euro 180.000,00 - durata 25 anni - a garanzia di mutuo fondiario. Formalita' attiva.
2. Trascrizione del 14/09/2009 - atto di donazione a favore di ROSSI MARIO e BIANCHI ANNA.

Non risultano pignoramenti, sequestri o domande giudiziali trascritti a carico degli intestatari.
"""},
]

# (id, category, question, gold phrase or None)
QUESTIONS = [
    # close: wording close to the document
    ("c1", "close", "Qual è la classe energetica dell'immobile?", "classe energetica: d"),
    ("c2", "close", "Fino a quando è valido l'attestato di prestazione energetica?", "valido fino al: 18/06/2034"),
    ("c3", "close", "Qual è il prezzo della compravendita?", "euro 285.000,00"),
    ("c4", "close", "Quanto è la rendita catastale?", "rendita: euro 903,80"),
    ("c5", "close", "A favore di quale banca è iscritta l'ipoteca?", "banca esempio s.p.a."),
    ("c6", "close", "Chi è il notaio che ha rogato l'atto di compravendita?", "dottor paolo neri"),
    ("c7", "close", "Qual è la superficie catastale?", "totale 92 mq"),
    ("c8", "close", "Chi è il certificatore dell'APE?", "ing. luca verdi"),
    # gap: the question shares little vocabulary with the passage that answers it
    ("g1", "gap", "Posso tenere un cane in casa?", "animali domestici di piccola e media taglia"),
    ("g2", "gap", "Si può fare l'affitto per un weekend?", "inferiori a trenta giorni sono vietati"),
    ("g3", "gap", "Come è arrivata la casa ai venditori?", "atto di donazione a rogito notaio carlo moretti"),
    ("g4", "gap", "L'edificio è stato costruito prima del 1967?", "anteriore al primo settembre 1967"),
    ("g5", "gap", "Ci sono lavori in programma che peseranno sul venditore?", "spese per la facciata deliberate"),
    ("g6", "gap", "Quanto costerà mettere a posto le difformità?", "totale stimato: euro 2.750,00"),
    ("g7", "gap", "Posso aprire uno studio dentistico nell'appartamento?", "uso studio professionale"),
    ("g8", "gap", "A che ora devo smettere di fare rumore la sera?", "dalle ore 22:00 alle ore 8:00"),
    ("g9", "gap", "Ci sono vicini che non pagano le spese comuni?", "per un totale di euro 3.870,00"),
    ("g10", "gap", "Come si pagheranno i lavori straordinari?", "il 40% alla firma del contratto"),
    ("g11", "gap", "Manca qualche certificato per poter abitare?", "certificato di agibilita' non e' stato reperito"),
    ("g12", "gap", "Cosa dice l'atto sulle agevolazioni per chi compra la prima abitazione?", "requisiti per le agevolazioni prima casa"),
    # identifier: parcel numbers, categories, codes
    ("i1", "identifier", "Chi sono gli intestatari del foglio 12 particella 34 subalterno 3?", "rossi mario nato a bologna"),
    ("i2", "identifier", "Che categoria catastale ha il subalterno 9?", "categoria c/6 - autorimessa di 14 mq"),
    ("i3", "identifier", "Quanti millesimi ha il subalterno 3?", "attribuita per 82,5 millesimi"),
    ("i4", "identifier", "Cosa dice il documento 2024-08123-BO?", "codice identificativo: 2024-08123-bo"),
    ("i5", "identifier", "Cos'è la SCIA 2011/4417?", "scia n. 2011/4417 per manutenzione straordinaria"),
    ("i6", "identifier", "Di cosa tratta l'articolo 5 dell'atto?", "art. 5 - provenienza"),
    # number: amounts and dates
    ("n1", "number", "Quanto costano i lavori della facciata?", "euro 148.500,00"),
    ("n2", "number", "Di quanto è il capitale dell'ipoteca?", "capitale euro 180.000,00"),
    ("n3", "number", "Quanto è l'avanzo di gestione del 2024?", "avanzo di gestione e' di euro 2.310,00"),
    ("n4", "number", "Quando è stata eseguita l'ispezione ipotecaria?", "ispezione eseguita il 26/05/2025"),
    ("n5", "number", "Quanto è l'EPgl dell'immobile?", "142,35 kwh/m2 anno"),
    ("n6", "number", "Qual è l'importo dei condomini morosi?", "euro 3.870,00"),
    # absent: not in the documents; the right answer is "non risulta"
    ("a1", "absent", "L'immobile ha una piscina?", None),
    ("a2", "absent", "Qual è l'indirizzo email dell'amministratore?", None),
    ("a3", "absent", "Quanti ascensori ha l'edificio?", None),
    ("a4", "absent", "Qual è la tariffa TARI dell'appartamento?", None),
    ("a5", "absent", "Il venditore è coniugato in comunione dei beni?", None),
    ("a6", "absent", "Quando è stato rifatto il tetto?", None),
    ("a7", "absent", "Il box auto ha una colonnina di ricarica elettrica?", None),
    ("a8", "absent", "Qual è la distanza dalla stazione ferroviaria?", None),
]
