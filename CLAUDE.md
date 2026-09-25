# STORM-SHIFT — note di progetto

Claude Code legge questo file in automatico, sia dalla CLI sul PC di Gimmy sia
nelle sessioni cloud: è la memoria condivisa fra le sessioni. Va aggiornato
quando si chiude qualcosa di importante.

## Dove sta
- Repo GitHub **privato** `gmy77/Storm_Shift`, creato il 2026-09-25 come
  "bunker" del codice: prima esisteva solo in `OneDrive\Desktop` sul PC.
- Sul PC va clonato in `C:\Users\gimmy\repos\Storm_Shift`. Regola di Gimmy: i
  progetti stanno SOLO dentro `C:\Users\gimmy\repos`.

## Due modi di farlo girare
1. **Cloudflare (quello voluto, "far girare tutto su Cloudflare")**: Worker
   `stormshift` + Container.
   - `src/index.js`: la dashboard (`public/`) è servita come asset statici,
     `/api/*` va al Container, `/status` è lo stato pubblico.
   - `Dockerfile`: Python 3.12 + `stormshift-requirements.txt` +
     `stormshift_meteohub_server.py` su `0.0.0.0:8000`.
   - Il container si spegne dopo 10 minuti senza richieste (`sleepAfter`).
   - Le credenziali ARCO sono segreti del Worker (`METEOHUB_EMAIL`,
     `METEOHUB_ARCO_ACCESS_KEY`), passati al container come variabili
     d'ambiente.
2. **PC + Cloudflare Tunnel (quello vecchio)**:
   - `Start-StormShift.ps1` avvia il server su `127.0.0.1:8765` e `cloudflared`
     su `stormshift.gimmycloud.net`;
   - le credenziali stanno nel Windows Credential Manager
     (`stormshift_meteohub_secrets.py`).

   Funziona solo a PC acceso.

Il server Python è lo stesso nei due casi. Legge le credenziali prima dalle
variabili d'ambiente e poi, solo su Windows, dal vault.

## Segreti: mai nel codice
Lezione del 2026-09-25. Nel file arrivato dal PC, `EMAIL_TARGET` e `KEY_TARGET`
di `stormshift_meteohub_secrets.py` contenevano i valori veri al posto delle
etichette. Nel repo sono entrati solo come etichette neutre
(`StormShift/METEOHUB_EMAIL`, `StormShift/METEOHUB_ARCO_ACCESS_KEY`): il valore
vero non è mai stato nella storia di git.

Conseguenze sul PC (modo 2):
- rilanciare una volta `python stormshift_meteohub_secrets.py set`;
- in Gestione credenziali di Windows cancellare le due voci vecchie, quelle con
  il nome uguale ai valori.

Prima di ogni commit va controllato che `git grep` non trovi email o chiavi.

## Deploy (Cloudflare)
Si fa dal PC, con **Docker Desktop acceso**: wrangler costruisce l'immagine in
locale, anche per `--dry-run`.
```
npm ci
npx wrangler secret put METEOHUB_EMAIL            # solo la prima volta
npx wrangler secret put METEOHUB_ARCO_ACCESS_KEY  # solo la prima volta
npx wrangler deploy
```
Il Worker `stormshift` esiste già su Cloudflare (deploy del 2026-09-06, da un
sorgente che non è mai arrivato nel repo). `src/index.js` lo ricostruisce dal
codice in produzione. Al primo deploy da qui ci sono tre punti da controllare:
- **tag della migrazione** Durable Object (`v1` in `wrangler.jsonc`): se non
  coincide con quello già applicato, wrangler si ferma con un errore, senza
  danni. In quel caso si usa il tag che indica l'errore.
- **`instance_type` del container**: in `wrangler.jsonc` non è indicato, quindi
  vale quello predefinito. Va confrontato con la dashboard
  (Workers > stormshift > Containers).
- **dominio**: `stormshift.gimmycloud.net` oggi può puntare al Tunnel del PC.
  Per servirlo dal Worker bisogna prima togliere il record DNS del tunnel e poi
  aggiungere il custom domain al Worker. Da fare solo con l'ok di Gimmy.

## Diagnostica (per la sentinella di sismo-echo)
Il Worker scrive nella stessa tabella `diagnostica` di sismo-fvg: database D1
`terremoti-fvg`, stessa scala di gravità. La tabella la crea e la pulisce a 14
giorni il cron di sismo-fvg. La checklist della sentinella e la tassonomia
stanno nel `CLAUDE.md` di `gmy77/sismo-echo`.
- `stormshift/container_start` → `NULL`
- `stormshift/container_stop` → `NULL` se `exitCode` è 0 (spento per
  inattività), `da_guardare` altrimenti (crash, memoria finita)
- `stormshift/container_error` → `da_guardare`
- `stormshift/api_5xx` → `da_guardare`, al massimo una riga ogni 10 minuti
  per istanza, con il numero di errori

Mai una riga per ogni richiesta andata bene. `/status` (pubblico) dice cosa è
configurato davvero: segreti presenti sì/no, D1 collegato, stato del container.
Non sveglia il container.

## Provare in locale
- Container:
  ```
  docker build -t stormshift .
  docker run -p 8000:8000 -e METEOHUB_EMAIL=... -e METEOHUB_ARCO_ACCESS_KEY=... stormshift
  ```
  Nelle sessioni Claude cloud `pip` dentro `docker build` fallisce per il
  certificato del proxy della sessione. Per provare si usa una copia del
  Dockerfile con `COPY` della CA del proxy e `PIP_CERT`, mai nel repo.
- Worker: `npx wrangler deploy --dry-run --containers-rollout=none` controlla
  bundle e binding senza costruire l'immagine.

## ⚠️ Prima del primo deploy da questo repo: recuperare gli asset di produzione
Il Worker in produzione (deploy del 2026-09-06) serve file statici che qui NON
ci sono. Di sicuro `metagram.html`, la pagina del pulsante METAGRAMMA, che
secondo Gimmy funzionava. Forse anche una dashboard più nuova di quella dello
zip. `wrangler deploy` sostituisce TUTTI gli asset con il contenuto di
`public/`, quindi quei file sparirebbero.

Prima del deploy vanno scaricati da produzione, dal PC, perché dal cloud
l'indirizzo è bloccato:
- `https://stormshift.gimmy077.workers.dev/metagram.html` va messo in
  `public/metagram.html`;
- `https://stormshift.gimmy077.workers.dev/` va confrontato con
  `public/index.html`.

Poi va controllato che il metagramma non carichi altri file locali. Se non si
riesce a recuperarli, il Worker vecchio si può sempre ripristinare da
Cloudflare (Workers > stormshift > Deployments > Rollback).

## Mancano nel repo (erano citati nel README ma non erano nello zip)
`public/metagram.html` (la dashboard ci manda con un link: senza, 404),
`stormshift_forecast.py`, `calibra_1..4_*.py` e `LICENSE`. Vanno aggiunti dal PC.
