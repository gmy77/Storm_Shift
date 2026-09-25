// Worker StormShift: la dashboard e' statica (public/, servita da ASSETS) e
// tutto /api/ va al Container con il bridge radar METEOHUB
// (stormshift_meteohub_server.py). Il container si spegne da solo dopo 10
// minuti senza richieste, quindi la pagina da sola non lo tiene acceso.
// Ricostruito il 2026-09-25 dal codice in produzione (deploy del 2026-09-06),
// piu' la diagnostica per la sentinella.
import { Container, getContainer } from "@cloudflare/containers";
import { env } from "cloudflare:workers";

const VERSION = "cf-1";
const ORIGINE = "stormshift";

// Diagnostica: stessa tabella e stessa scala di gravita' di sismo-fvg
// (database D1 terremoti-fvg, tabella diagnostica creata e pulita a 14 giorni
// dal cron di sismo-fvg; vedi CLAUDE.md di sismo-echo). Solo ciclo di vita
// del container ed errori, MAI una riga per ogni richiesta andata bene. Non
// deve mai rompere chi la chiama; senza binding DB non fa niente.
//   'bloccante'   -> il servizio non fa quello per cui esiste
//   'da_guardare' -> da tenere d'occhio (si riprova da solo, o peggiora)
//   null          -> informativo, rumore di fondo normale
async function logDiag(db, evento, dettaglio, gravita = null) {
  if (!db) return;
  try {
    await db.prepare("INSERT INTO diagnostica (ts, origine, evento, dettaglio, gravita) VALUES (?,?,?,?,?)")
      .bind(new Date().toISOString(), ORIGINE, evento,
            dettaglio == null ? null : JSON.stringify(dettaglio).slice(0, 4000), gravita)
      .run();
  } catch (_) { /* la diagnostica non deve mai far fallire chi la chiama */ }
}

export class StormShiftRadar extends Container {
  defaultPort = 8000;
  sleepAfter = "10m";
  envVars = {
    METEOHUB_EMAIL: env.METEOHUB_EMAIL,
    METEOHUB_ARCO_ACCESS_KEY: env.METEOHUB_ARCO_ACCESS_KEY,
  };

  onStart() {
    this.ctx.waitUntil(logDiag(this.env.DB, "container_start", null));
  }

  // exitCode 0 e' lo spegnimento normale per inattivita' (sleepAfter):
  // informativo. Un codice diverso (crash, memoria finita) va guardato.
  onStop({ exitCode, reason }) {
    return logDiag(this.env.DB, "container_stop", { exitCode, reason },
                   exitCode === 0 ? null : "da_guardare");
  }

  onError(error) {
    this.ctx.waitUntil(logDiag(this.env.DB, "container_error",
      { error: String((error && error.message) || error).slice(0, 500) }, "da_guardare"));
    throw error;   // comportamento predefinito della classe Container
  }

  // Per /status: legge lo stato salvato senza avviare il container.
  async stato() {
    const s = await this.state.getState();
    return { status: s.status, lastChange: s.lastChange, exitCode: s.exitCode ?? null,
             running: !!(this.ctx.container && this.ctx.container.running) };
  }
}

// Errori 5xx dell'API: al massimo una riga ogni 10 minuti per istanza del
// Worker, con il conteggio, invece di una per richiesta. Con un temporale e
// tanta gente sulla pagina la tabella non deve riempirsi.
const ERR_WINDOW_MS = 10 * 60 * 1000;
const err5xx = { count: 0, since: 0, lastLogged: 0 };
function note5xx(ctx, db, path, status, detail) {
  const now = Date.now();
  if (!err5xx.count) err5xx.since = now;
  err5xx.count++;
  if (now - err5xx.lastLogged < ERR_WINDOW_MS) return;
  const row = { path, status, detail, errori: err5xx.count, daMs: now - err5xx.since };
  err5xx.count = 0; err5xx.lastLogged = now;
  ctx.waitUntil(logDiag(db, "api_5xx", row, "da_guardare"));
}

export default {
  async fetch(request, workerEnv, ctx) {
    const url = new URL(request.url);

    // /status — pubblico, nessun dato sensibile: dice cosa e' configurato
    // DAVVERO (segreti presenti si'/no, D1 collegato, stato del container)
    // senza svegliare il container. Lo legge la sonda worker-probe.
    if (url.pathname === "/status") {
      let container = null;
      try { container = await getContainer(workerEnv.RADAR, "fvg-radar").stato(); }
      catch (e) { container = { error: String((e && e.message) || e).slice(0, 200) }; }
      return Response.json({
        version: VERSION,
        secrets: { METEOHUB_EMAIL: !!workerEnv.METEOHUB_EMAIL, METEOHUB_ARCO_ACCESS_KEY: !!workerEnv.METEOHUB_ARCO_ACCESS_KEY },
        d1: !!workerEnv.DB,
        container,
      }, { headers: { "Cache-Control": "no-store", "Access-Control-Allow-Origin": "*" } });
    }

    if (!url.pathname.startsWith("/api/")) return workerEnv.ASSETS.fetch(request);

    let res;
    try {
      res = await getContainer(workerEnv.RADAR, "fvg-radar").fetch(request);
    } catch (e) {
      note5xx(ctx, workerEnv.DB, url.pathname, 503, String((e && e.message) || e).slice(0, 300));
      return new Response("Radar non disponibile, riprova tra poco.", { status: 503 });
    }
    if (res.status >= 500) note5xx(ctx, workerEnv.DB, url.pathname, res.status, null);
    return res;
  },
};
