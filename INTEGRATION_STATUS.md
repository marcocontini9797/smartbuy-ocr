# Integrazione locale verificata

Python: .venv\Scripts\python.exe
Avvio: .venv\Scripts\python.exe -m uvicorn main_api:app --host 127.0.0.1 --port 8000
Test: .venv\Scripts\python.exe -m pytest -q test_workspace_api.py

Frontend: http://localhost:3000/connected
Accedere con un account Supabase esistente. Cookie HttpOnly; il backend usa il JWT utente e la chiave anon, mai service-role per letture workspace.

Verificato: health 200; Supabase sb_properties 200; API senza sessione 401; pagina connected 200; TypeScript; tre test API.
Non verificato: visibilità dei dati tramite RLS per l'account utente. Prima di distribuire, verificare le policy di tutte le tabelle workspace con due account distinti.

Mancano: AI service configurato; ingestion nell'app unificata; feedback con autorizzazione utente; refresh sessione/logout; integrazione finale UI; campi vendita/affitto (assenti da sb_properties); agenda e contatti. Non è un'integrazione al 100%.
La home resta anteprima esplicitamente etichettata; /connected è la vista di verifica reale.
