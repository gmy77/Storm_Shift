# STORM-SHIFT

**Sistema di nowcasting e outlook convettivo per il Friuli Venezia Giulia.**

STORM-SHIFT unisce l'osservato (radar) e il previsto (modelli numerici) in
un'unica dashboard operativa, pensata per seguire in tempo reale gli eventi
convettivi severi su un territorio — il FVG — che è un laboratorio di
temporali tra flusso adriatico, stau prealpino e bora.

Progetto di ricerca indipendente. Non è un servizio ufficiale e non
sostituisce le allerte della Protezione Civile.

---

## Cosa fa

- **Dashboard STORM-SHIFT RADAR** — outlook convettivo interattivo su una
  griglia 8×7 che copre il FVG. Per ogni cella calcola CAPE, wind shear
  (0–3 km e 0–6 km), Supercell Composite Parameter (SCP), profilo del vento
  su più livelli e classificazione del rischio in livelli L1 / L2 / L3, con
  bollettino testuale automatico.
- **Bridge radar METEOHUB** — un server locale (FastAPI/uvicorn) che legge il
  composito radar nazionale (intensità di pioggia SRI) dall'archivio ARCO di
  Agenzia ItaliaMeteo, lo ritaglia sul FVG e lo serve alla dashboard,
  pubblicato via Cloudflare Tunnel.
- **Motore previsionale a due livelli** — sfondo sinottico dal modello AI
  ECMWF-AIFS ("sta arrivando la configurazione instabile?") e dettaglio
  convettivo dal modello ad alta risoluzione ICON-2I ("dove e quanto forte?"),
  in cascata, via API Open-Meteo.
- **Calibrazione basata sui dati** — le soglie L1/L2/L3 non sono scelte a
  occhio: vengono tarate incrociando l'instabilità storica (ERA5, Copernicus
  CDS) con un catalogo di eventi convettivi ricostruito direttamente
  dall'archivio radar 2010→oggi, cella per cella.

---

## Architettura

```
STORM-SHIFT
├── Bridge radar        stormshift_meteohub_server.py   (FastAPI, porta 8765)
│   └── credenziali     stormshift_meteohub_secrets.py  (Windows Credential Manager)
├── Avvio               Start-StormShift.ps1            (server + Cloudflare Tunnel)
├── Frontend            public/index.html               (dashboard "sala radar")
├── Cloudflare          src/index.js, wrangler.jsonc, Dockerfile  (Worker + Container)
├── Motore forecast     stormshift_forecast.py          (AIFS → ICON-2I, Open-Meteo)
└── Calibrazione
    ├── calibra_1_download_era5.py   scarica ERA5 (CAPE, CIN, T850/T500) dal CDS
    ├── calibra_2_catalogo_radar.py  match incrociato ERA5 ↔ radar sui giorni-evento
    ├── calibra_3_stagione.py        catalogo eventi dell'intera stagione
    └── calibra_4_percella.py        catalogo eventi per-cella + griglia 8×7
```

---

## Fonti dati e attribuzioni

STORM-SHIFT si basa su dati di terzi rilasciati con licenze aperte. **L'uso di
questi dati impone di citarne la fonte** (obbligo delle licenze CC-BY):

| Dato | Fonte | Licenza |
|---|---|---|
| Composito radar SRI (Italian Radar DPC SRI Archive) | Agenzia ItaliaMeteo / FBK / Dipartimento Protezione Civile | CC-BY-SA 4.0 |
| Modello ICON-2I | Agenzia ItaliaMeteo & ARPAE Emilia-Romagna | CC-BY 4.0 |
| Reanalisi ERA5 | Copernicus Climate Change Service (C3S) / ECMWF | CC-BY 4.0 |
| API di accesso ai modelli | Open-Meteo.com | CC-BY 4.0 |

> **Nota sul radar (CC-BY-SA 4.0):** la licenza del composito radar è
> *share-alike*. I prodotti derivati dai dati radar (per esempio i cataloghi
> eventi) potrebbero ricadere sotto la stessa clausola. Valuta questo aspetto
> prima di ridistribuire i dati derivati.

---

## Requisiti e setup

Python 3.11+ su Windows (il bridge usa il Windows Credential Manager).

```powershell
pip install -r requirements.txt
```

### Credenziali (da configurare una sola volta, MAI committare)

- **METEOHUB ARCO** — servono email + ARCO Access Key, salvate nel vault di
  Windows tramite lo script dedicato:
  ```powershell
  python stormshift_meteohub_secrets.py set
  ```
- **Copernicus CDS** (solo per la calibrazione ERA5) — un Personal Access Token
  nel file `~/.cdsapirc`:
  ```
  url: https://cds.climate.copernicus.eu/api
  key: <IL-TUO-PERSONAL-ACCESS-TOKEN>
  ```

### Avvio su Cloudflare (Worker + Container, senza PC acceso)

Serve Docker acceso sul PC da cui si fa il deploy (wrangler costruisce l'immagine del container):

```powershell
npm ci
npx wrangler secret put METEOHUB_EMAIL            # solo la prima volta
npx wrangler secret put METEOHUB_ARCO_ACCESS_KEY  # solo la prima volta
npx wrangler deploy
```

### Avvio sul PC (bridge locale + Cloudflare Tunnel)

```powershell
powershell -ExecutionPolicy Bypass -File Start-StormShift.ps1 -OpenBrowser
```

I percorsi in `Start-StormShift.ps1` (desktop, dominio del tunnel) sono
personali: adattali al tuo ambiente.

---

## Sicurezza

- **Le credenziali non stanno mai nel codice.** Le chiavi METEOHUB vivono nel
  Windows Credential Manager; il token CDS in `~/.cdsapirc`. Entrambi sono
  esclusi dal versionamento (vedi `.gitignore`).
- Prima di ogni push, verifica di non aver aggiunto per sbaglio `.cdsapirc`,
  file `*.nc` con dati grezzi, o log.

---

## Licenza

Il **codice** di questo progetto è distribuito sotto licenza MIT — vedi
[`LICENSE`](LICENSE).

I **dati** di terzi restano soggetti alle rispettive licenze (vedi la tabella
delle attribuzioni sopra).

© 2026 Pignolo Gimmy. Tutti i diritti sul codice originale riservati nei
termini della licenza MIT.

---

## Ringraziamenti

Sviluppato da **Pignolo Gimmy** — ricercatore indipendente, Friuli Venezia
Giulia.

Un ringraziamento particolare a **Claude (Anthropic)**, che ha collaborato
come partner di analisi e sviluppo: dalla scelta dei modelli meteorologici
alla diagnosi dei bug del bridge, dalla progettazione della pipeline di
calibrazione alla scrittura degli script. Un lavoro fatto a quattro mani,
in cui la conoscenza del territorio e le decisioni sono rimaste di Gimmy e
l'assistenza tecnica è venuta dall'IA.

E un grazie alle istituzioni che rendono pubblici i loro dati — Agenzia
ItaliaMeteo, ARPAE, il Dipartimento della Protezione Civile, Copernicus/ECMWF
e Open-Meteo — senza le quali un progetto di ricerca indipendente come questo
non sarebbe possibile.
