# SmartBuy — verifiche documentali v2

Il backend locale confronta i dati estratti e produce segnalazioni tracciabili,
con motivo, fonti e azione successiva. Non dichiara automaticamente la conformità
urbanistica o giuridica. Questa versione rafforza il motore deterministico;
non costituisce una misura dell’accuratezza OCR su documenti reali.

## Comportamenti verificati

| Caso | Comportamento |
| --- | --- |
| Appartamento con unità principale C/2 | Criticità con riferimento all’unità e verifica tecnica suggerita |
| Solo C/2, ruolo non noto | Attenzione: distinguere deposito e possibile pertinenza |
| Abitazione e pertinenza, unità distinte e identificabili sulla stessa particella | Nessun conflitto di categoria causato dalla sola pertinenza |
| Locale commerciale, ufficio, box, laboratorio, magazzino, capannone | Categorie attese dalla tipologia già presente nel progetto |
| Più subalterni | Confronto separato per identità completa; ambiti incompleti rimangono da chiarire |
| Stessi numeri catastali in Comuni diversi | Nessuna conferma reciproca |
| Fonti con date diverse | Differenze nei dati variabili segnalate come variazioni da ricostruire |
| Fonti duplicate o dati copiati dal prospetto al PDF | Una sola origine indipendente, con riferimenti ai documenti conservati |
| Correzione umana | Valore confermato prioritario rispetto alle letture precedenti; mantenimento degli identificativi dell’unità |
| C/2 e classe energetica C | Campi distinti; le lettere presenti in testo generico non diventano classi energetiche |
| Date impossibili, scadenza precedente all’emissione, data futura | Segnalazione sul campo originale |
| Caparra superiore al prezzo, canone annuo non riconciliato con quello mensile | Confronto dei valori e richiesta di verifica delle clausole |
| Quote non valide e valori numerici non interpretabili | Controllo del dato prima del confronto |
| Superficie utile/commerciale | Controllo indicativo con verifica dei criteri di misura; nessuna soglia presentata come legge |
| Dichiarazioni tecniche negative o discordanti | Evidenza e azione per il tecnico |
| Dati simulati, fonti di altro immobile, analisi fallite/incomplete | Esclusione dalle conferme, con segnalazione della fonte |

Le identità catastali usano Comune, sezione, foglio, particella e subalterno.
Il Comune non viene inventato quando manca. Valori globali in documenti con più
unità non vengono attribuiti arbitrariamente a una singola unità.

Le differenze temporali non vengono risolte scegliendo automaticamente il documento
più recente: è necessaria la ricostruzione della variazione e della fonte pertinente.

## Collegamenti nell’applicazione

- `document_engine/cross_validation.py`: normalizzazione, confronto, stabilità delle letture e riepilogo.
- `document_engine/validation_rules.py`: controllo delle fonti, ambiti catastali, regole contestuali.
- `document_engine/checklist.py`: stesse segnalazioni nel fascicolo, senza duplicare l’avviso C/2.
- `document_engine/agent_review.py`: azioni raggruppate per lettura, identità, uso, tecnica, cronologia e altri domini.
- `schemas.py`: ruolo dell’unità e destinazione d’uso estratti solo quando esplicitamente documentati.
- `api/registry_routes.py`: risultati Sandbox conservati nel registro delle richieste, con ambiente e costo zero; nessun nuovo documento/fatto probatorio creato dal Sandbox. Cache separate per ambiente.

Le risposte esistenti `/api/v1/properties/{id}/cross-validation` e `/checklist`
usano il motore aggiornato. Ogni nuova segnalazione espone `rule_id`, `rule_version`,
`scope`, `sources`, `values`, `evidence_ids` e `recommended_action`; le citazioni
e le pagine vengono riportate quando presenti, senza inventarle. Il riepilogo
espone `engine_version=2.0`. Nessuna nuova tabella o migrazione è necessaria.

La percentuale `verified_ratio` riguarda esclusivamente gli esiti dei controlli
disponibili. Non è una probabilità di regolarità, una copertura dell’intero fascicolo
o una misura di accuratezza dell’intelligenza artificiale.

## Test gratuiti e riproducibili

Verifica locale del 28 settembre 2026: **309 test superati, 90 casi aggiunti**.
Sono presenti 8 avvisi di deprecazione delle librerie e del codice preesistente;
nessun errore nei test. Sono inclusi il percorso API/checklist/azione dell’agente,
le regole contestuali e i controlli sulla persistenza Sandbox con repository simulati.
Il funzionamento della sessione browser e del server già avviato non è stato
verificato: il processo backend deve caricare il codice aggiornato tramite
riavvio o ricaricamento automatico.

Da questa cartella in PowerShell:

```powershell
.\.venv\Scripts\python.exe -B scripts\test_engine_offline.py
```

Il runner disattiva i moduli di test live e blocca le connessioni Internet.
Consente il loopback numerico necessario al funzionamento di asyncio su Windows.
Le API applicative vengono provate in memoria; persistenza Supabase e provider
sono sostituiti da oggetti di test. Il report JUnit viene scritto in
`evaluation/reports/validation-offline.xml` (ignorato da Git).

I casi aggiunti sono sintetici, compresi casi negativi e casi che non devono
generare falsi allarmi. Non sono documenti reali e non misurano precisione e
richiamo su un insieme indipendente di pratiche immobiliari.

## Limiti da misurare nella prossima validazione

1. La qualità finale dipende dall’estrazione. Occorre un corpus autorizzato di
   scansioni e documenti reali annotato da esperti, separato dai casi di sviluppo.
2. Relazioni planimetriche, abusi edilizi non documentati, autenticità delle firme
   e accertamenti presso gli enti richiedono verifiche dedicate.
3. I campi non previsti negli schemi e gli usi descritti in forma ambigua non
   possono essere dichiarati automaticamente verificati.
4. Un documento storico non viene automaticamente ignorato. Se ne deve confermare
   il ruolo nella pratica, anche quando esistono documenti più recenti.
5. Importazioni Sandbox effettuate prima di questa versione, se prive di metadati
   di origine, vanno riconciliate con `property_registry_checks` prima di utilizzarle
   come prove. Questa modifica non elimina dati già presenti.
6. Le regole normative preesistenti in `red_flags.py` non sono state sottoposte a
   una revisione legale completa in questo intervento.

Per ogni errore confermato su un caso reale si dovrà aggiungere una regressione
con il risultato atteso, verificando anche un caso simile che deve rimanere pulito.
Questo evita che la correzione di un falso negativo produca nuovi falsi positivi.
