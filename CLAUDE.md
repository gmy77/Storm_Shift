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

## Deploy (Cloudflare): automatico con Workers Builds
Dal 2026-09-25 il Worker `stormshift` è collegato a questo repo con **Workers
Builds**: Cloudflare → Workers & Pages → stormshift → Impostazioni → Crea.
- **Ogni push su `main` va online da solo.** Cloudflare costruisce sui suoi
  server sia il Worker sia l'immagine del container dal `Dockerfile`: non
  servono Docker né comandi sul PC. Per questo su `main` si fa merge solo di
  modifiche già provate.
- Impostazioni: comando di generazione vuoto, comando di distribuzione
  `npx wrangler deploy`, directory radice `/`, branch `main`.
- Il token API scelto nel collegamento era il "build token" di
  `astro-blog-starter-template`. Se la build fallisce per permessi
  (container, D1), va creato un token nuovo dallo stesso menu.
- I segreti `METEOHUB_EMAIL` e `METEOHUB_ARCO_ACCESS_KEY` stanno nel Worker
  (Impostazioni → Variabili e segreti). I deploy non li toccano.
- **La chiave ARCO scade.** Il 2026-09-25 era scaduta e Gimmy l'ha rigenerata
  su MeteoHub. Se il radar risponde "Archivio ARCO non disponibile" per ore,
  la prima cosa da controllare è la validità della chiave su MeteoHub.

Lezione del 2026-09-25: `npx wrangler deploy --containers-rollout=none`
(l'unico possibile dal PC senza Docker) aveva messo online il Worker lasciando
il Durable Object **senza container**. Nella diagnostica compariva
`container_error: "There is no container application assigned to this Durable
Object namespace"`. Serve sempre un deploy completo, e adesso lo fa Workers
Builds.

Deploy a mano, solo se Workers Builds non è disponibile: dal PC con Docker
Desktop acceso, `npm ci` e poi `npx wrangler deploy`.

## Dominio pubblico
`stormshift.gimmycloud.net` **non è collegato al Worker**: nei "Domini
personalizzati" il 2026-09-25 non c'era niente, quindi arriva al PC tramite
Cloudflare Tunnel (modo 2). La versione Cloudflare risponde su
`https://stormshift.gimmy077.workers.dev`. Per spostare il dominio sul Worker
bisogna togliere il record DNS del tunnel e aggiungere il dominio personalizzato
al Worker, solo con l'ok di Gimmy.

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

## Asset di produzione recuperati (2026-09-25)
Il Worker deployato il 06/09 serviva file statici che non erano nello zip.
Gimmy li ha scaricati dalla produzione e sono stati confrontati:
- `public/metagram.html`: copia esatta di quello in produzione (etichetta
  v1.1.4). È una pagina autonoma che scarica i dati solo da Open-Meteo, senza
  altri file locali. La apre il pulsante METAGRAMMA della dashboard.
- **Dashboard**: in produzione c'era la **1.1.4**, qui c'è la **1.1.5**, più
  nuova: pulsante METAGRAMMA, ◀1H/1H▶, nuovi tentativi con timeout su
  Open-Meteo, aggiornamento ogni 30 minuti. Il primo deploy porta quindi in
  produzione la 1.1.6 (la 1.1.5 con la soglia L1 riportata a 800).
- **Soglia L1 "solo CAPE"**: `CAPE ≥ 800` nella 1.1.4, `CAPE ≥ 1500` nella
  1.1.5. Gimmy ha confermato **800** il 2026-09-25, e la dashboard è diventata
  1.1.6. Il radar sulla mappa non dipende dalla soglia: si carica
  all'apertura, ogni 5 minuti e con AGGIORNA, e si colora solo dove piove ad
  almeno 0,2 mm/h.
- La 1.1.4 in produzione aveva un CSS per il testo "⚠ PICCO" nel footer
  (larghezza fissa di 260px con "…"). **Non è stato riportato**: provato nel
  browser, con i pulsanti in più della 1.1.5 fa uscire il footer di 67px a
  1280px di larghezza, mentre la 1.1.5 senza quel CSS ci sta. A 1440 e 1920px
  le due versioni sono identiche.

Gli unici file statici noti della produzione erano `/` e `/metagram.html`. Se
dopo il deploy manca qualcos'altro, si torna al Worker vecchio da Cloudflare
(Workers > stormshift > Deployments > Rollback).

## Mancano nel repo (erano citati nel README ma non erano nello zip)
`stormshift_forecast.py`, `calibra_1..4_*.py` e `LICENSE`. Vanno aggiunti dal PC.
