# Misura della precisione dell'estrazione

Ogni documento di riferimento in `gold/` ha accanto un file `.json` con lo stesso
nome e i valori **corretti**, controllati a mano:

```
gold/
  visura_via_roma.pdf
  visura_via_roma.json   {"document_type": "visura_catastale", "expected": {...}}
```

I nomi dei campi in `expected` sono quelli degli schemi di estrazione
(`schemas.py`): ad esempio `intestatari`, `riferimento` / `riferimenti_catastali`,
`classe_energetica`, `superficie_utile_mq`, `prezzo_eur`, `data_scadenza`.
Basta indicare i campi che si vogliono verificare. Vedi `gold/esempio_visura_demo.json`.

Esecuzione (chiama OpenAI, circa un minuto per documento; non scrive nel database):

```
.venv\Scripts\python.exe -m evaluation.evaluate_extraction
```

Il confronto usa le stesse regole delle Verifiche: `Fg. 0285` = `285`,
`ROSSI Giovanni` = `Giovanni Rossi`, `€ 320.000,00` = `320000`.
Il report completo viene salvato in `evaluation/reports/`.

I documenti veri in `gold/` non vanno in git (vedi `.gitignore`): contengono dati personali.
