"""
Trappole-canguro iniettate - Astrolinguistica sperimentale, Livello A (punto 3)
===============================================================================
Inietta deliberatamente una trappola-canguro: una coppia (parola, ESCA) tale
che il referente VERO e l'esca concordano su un sottoinsieme di scene (il
"pool della trappola"). Confronta come diversi protocolli di apprendimento
reagiscono alla stessa trappola, a parita' di budget di scambi.

Bracci:
  A. ostensione ingenua  - co-occorrenza di ATOMI su scene casuali dal pool;
                           promuove l'atomo piu' associato (nessuna verifica)
  B. statistica pura     - eliminazione di ipotesi (spazio completo) su scene
                           casuali dal pool; promuove il superstite di Occam
                           (nessuna coppia minima, nessun probe, no quarantena)
  C. protocollo completo - pipeline intera (coppie minime + probe attivi +
                           round 2 + quarantena), in due varianti:
       debole: solo l'OSTENSIONE e' avvelenata (pool); coppie minime e probe
               possono costruire qualunque scena del mondo
       forte:  le scene discriminanti NON ESISTONO nel mondo (caso Quine puro);
               anche coppie minime e probe sono confinati al pool

Metriche (sulla parola in trappola):
  - esito: GIUSTA / CANGURO / SOTTODETERMINATA / irrisolta
    (SOTTODETERMINATA = promossa con piu' ipotesi superstiti, tra cui la vera:
     la traduzione onesta e' la classe di equivalenza, non una scelta arbitraria)
  - tempo di rilevazione: scambio in cui l'esca viene eliminata (solo bracci
    in grado di eliminarla)
  - scambi totali (per il controllo di parita' di budget)

Uso:
  python trappole.py                          # trappola zumu_forma, 50 semi
  python trappole.py --trappola tin_moto      # seconda trappola
  python trappole.py --semi 10 --budget 60
"""

import argparse
import random
import statistics

from orchestratore import (TUTTE_LE_SCENE, verita_L2, REFERENTI_VERI_L2,
                           ATOMI, _vale, Ancora, Orchestratore, ParlanteSim)

# =================================================================
# 1. DEFINIZIONE DELLE TRAPPOLE
# =================================================================
# esca = ipotesi ingannevole, estensionalmente equivalente alla vera
#        sul pool della trappola.

TRAPPOLE = {
    # il canguro "naturale" del seed 38 (condizione casuale_r2), iniettato:
    # rosso&triangolo si comporta come rosso&rapido su 24 scene su 32
    "zumu_forma": {"parola": "ZUMU",
                   "esca": frozenset({("colore", "rosso"),
                                      ("forma", "triangolo")})},
    # esca atomica su una parola di parita': fermo si comporta come dispari
    # sul pool (dispari <-> fermo), 16 scene su 32
    "tin_moto":   {"parola": "TIN",
                   "esca": frozenset({("moto", "fermo")})},
}

def pool_trappola(parola: str, esca: frozenset) -> list:
    """Scene su cui vera ed esca CONCORDANO (ordine canonico stabile)."""
    vera = frozenset(REFERENTI_VERI_L2[parola])
    return [s for s in TUTTE_LE_SCENE if _vale(vera, s) == _vale(esca, s)]

# =================================================================
# 2. CLASSIFICAZIONE DEGLI ESITI (consapevole delle classi)
# =================================================================

def esito_classe(stato: str, superstiti: set, stimato: set, vera: set) -> str:
    """CANGURO solo se la vera e' PROVATAMENTE esclusa dalle superstiti.
    Se la vera sopravvive ma insieme ad altre, l'esito onesto e' la classe
    di equivalenza (sottodeterminazione alla Quine), non una scelta."""
    if stato != "PROMOSSA" or not stimato:
        return "irrisolta"
    vera_f = frozenset(vera)
    sup = {frozenset(h) for h in superstiti}
    if vera_f not in sup:
        return "CANGURO"
    if len(sup) == 1:
        return "GIUSTA"
    return "SOTTODETERMINATA"

# =================================================================
# 3. BRACCIO A - OSTENSIONE INGENUA (co-occorrenza di atomi)
# =================================================================

def braccio_ingenuo(seed: int, pool: list, parola_t: str, budget: int) -> dict:
    rng = random.Random(seed)
    p2 = ParlanteSim(verita_L2)
    co, tot = {}, 0          # co[atomo] = co-occorrenze con la parola in trappola
    for _ in range(budget):
        s = rng.choice(pool)
        parole = set(p2.etichetta(s).split())
        if parola_t not in parole:
            continue
        tot += 1
        attr = s.attributi()
        for a in sorted(ATOMI):
            if attr[a[0]] == a[1]:
                co[a] = co.get(a, 0) + 1
    if tot == 0:
        return {"esito": "irrisolta", "rilevazione": None, "scambi": budget}
    # promuove l'atomo con co-occorrenza massima (spareggio canonico)
    migliore = max(sorted(co), key=lambda a: co[a])
    stimato = {migliore}
    vera = REFERENTI_VERI_L2[parola_t]
    # il braccio ingenuo promuove SEMPRE e non elimina mai l'esca
    es = "GIUSTA" if stimato == set(vera) else "CANGURO"
    return {"esito": es, "rilevazione": None, "scambi": budget}

# =================================================================
# 4. BRACCIO B - STATISTICA PURA (eliminazione passiva, niente verifica)
# =================================================================

def braccio_statistico(seed: int, pool: list, parola_t: str, esca: frozenset,
                       budget: int) -> dict:
    rng = random.Random(seed)
    p2 = ParlanteSim(verita_L2)
    ancore = {}
    rilevazione = None
    for k in range(1, budget + 1):
        s = rng.choice(pool)
        parole = set(p2.etichetta(s).split())
        for w in sorted(parole):
            ancore.setdefault(w, Ancora(w))
        for w, a in sorted(ancore.items()):
            a.osserva(s, presente=(w in parole))
        a_t = ancore.get(parola_t)
        if (rilevazione is None and a_t is not None
                and esca not in a_t.ipotesi):
            rilevazione = k
    a_t = ancore.get(parola_t)
    vera = REFERENTI_VERI_L2[parola_t]
    if a_t is None or not a_t.ipotesi:
        return {"esito": "irrisolta", "rilevazione": rilevazione,
                "scambi": budget}
    # B promuove sempre il superstite di Occam: e' il suo difetto strutturale.
    # Per onesta' classifichiamo comunque con la metrica per classi: il suo
    # esito tipico in trappola e' SOTTODETERMINATA *non dichiarata*, che
    # diventa canguro nel momento in cui sceglie. Riportiamo la scelta.
    stimato = a_t.referente_stimato()
    if frozenset(stimato) == frozenset(vera):
        es = "GIUSTA" if len(a_t.ipotesi) == 1 else "GIUSTA (per caso)"
    else:
        es = "CANGURO"
    return {"esito": es, "rilevazione": rilevazione, "scambi": budget}

# =================================================================
# 5. BRACCIO C - PROTOCOLLO COMPLETO (debole / forte)
# =================================================================

class OrchestratoreTrappola(Orchestratore):
    """Orchestratore con ostensione avvelenata (pool della trappola).
    forte=True: anche coppie minime e probe sono confinati al pool
    (le scene discriminanti non esistono nel mondo)."""

    def __init__(self, p2, pool, parola_t, esca, forte=False, **kw):
        super().__init__(p2, **kw)
        self.pool = pool
        self.parola_t = parola_t
        self.esca = esca
        self.forte = forte
        self.rilevazione = None
        self.coppie_inesistenti = 0     # variate fuori pool saltate (forte)

    # --- tracciamento del tempo di rilevazione dell'esca -------------
    def _controlla_rilevazione(self):
        a = self.ancore.get(self.parola_t)
        if (self.rilevazione is None and a is not None
                and self.esca not in a.ipotesi):
            self.rilevazione = self.scambi

    def _chiedi(self, scena):
        self._controlla_rilevazione()   # stato PRIMA di questo scambio
        return super()._chiedi(scena)

    # --- ostensione avvelenata (sempre) -------------------------------
    def fase_ostensione(self, n_scene=6):
        for s in self.rng.sample(self.pool, n_scene):
            parole = self._chiedi(s)
            for w, a in sorted(self.ancore.items()):
                a.osserva(s, presente=(w in parole))

    # --- varianti FORTI: il mondo e' il pool ---------------------------
    def fase_coppie_minime(self):
        if not self.forte:
            return super().fase_coppie_minime()
        for a in sorted(self.ancore.values(), key=lambda x: x.parola):
            attributi_da_testare = {k for h in a.ipotesi for (k, v) in h}
            for attr in sorted(attributi_da_testare):
                base = self.rng.choice(self.pool)
                variata = self._coppia_minima(base, attr)
                if variata not in self.pool:
                    self.coppie_inesistenti += 1
                    continue                 # la scena non esiste nel mondo
                w_base = a.parola in self._chiedi(base)
                w_var = a.parola in self._chiedi(variata)
                a.osserva(base, w_base)
                a.osserva(variata, w_var)
                if w_base != w_var:
                    a.coppie_discriminanti += 1

    def _scena_probe(self, a, gia_usate):
        if not self.forte:
            return super()._scena_probe(a, gia_usate)
        H = sorted(a.ipotesi, key=lambda h: sorted(h))
        visti = {}
        for s_prec in gia_usate:
            for k, v in s_prec.attributi().items():
                visti.setdefault(k, set()).add(v)
        migliore, chiave_migliore = None, None
        for s in self.pool:                  # candidati SOLO dal pool
            if s in gia_usate:
                continue
            voti = sum(1 for h in H if _vale(h, s))
            split = min(voti, len(H) - voti)
            attesa_presente = 1 if voti > 0 else 0
            novita = sum(1 for k, v in s.attributi().items()
                         if v not in visti.get(k, set()))
            chiave = (split, attesa_presente, novita)
            if chiave_migliore is None or chiave > chiave_migliore:
                migliore, chiave_migliore = s, chiave
        return migliore if migliore is not None else self.rng.choice(self.pool)


def braccio_completo(seed: int, pool: list, parola_t: str, esca: frozenset,
                     forte: bool) -> dict:
    p2 = ParlanteSim(verita_L2)
    orch = OrchestratoreTrappola(p2, pool, parola_t, esca, forte=forte,
                                 seed=seed, attiva=True,
                                 logfile="log_trappola.jsonl")
    orch.fase_ostensione(n_scene=6)
    orch.fase_coppie_minime()
    orch.fase_probing(round_n=1)
    orch.fase_probing(round_n=2)
    orch.log.close()
    orch._controlla_rilevazione()       # controllo finale post-run
    a = orch.ancore.get(parola_t)
    vera = REFERENTI_VERI_L2[parola_t]
    if a is None:
        return {"esito": "irrisolta", "rilevazione": None,
                "scambi": orch.scambi}
    es = esito_classe(a.stato, a.ipotesi, a.referente_stimato(), vera)
    return {"esito": es, "rilevazione": orch.rilevazione,
            "scambi": orch.scambi,
            "coppie_inesistenti": orch.coppie_inesistenti}

# =================================================================
# 6. CAMPAGNA E RIASSUNTO
# =================================================================

def campagna(nome_trappola: str, semi: int, budget: int):
    t = TRAPPOLE[nome_trappola]
    parola_t, esca = t["parola"], t["esca"]
    vera = sorted(REFERENTI_VERI_L2[parola_t])
    pool = pool_trappola(parola_t, esca)
    print(f"TRAPPOLA '{nome_trappola}': parola {parola_t}, "
          f"vera={vera}, esca={sorted(esca)}")
    print(f"Pool della trappola: {len(pool)}/{len(TUTTE_LE_SCENE)} scene "
          f"(vera ed esca vi concordano)\n")

    bracci = {
        "A ingenua":          lambda s: braccio_ingenuo(s, pool, parola_t, budget),
        "B statistica":       lambda s: braccio_statistico(s, pool, parola_t, esca, budget),
        "C completo debole":  lambda s: braccio_completo(s, pool, parola_t, esca, forte=False),
        "C completo forte":   lambda s: braccio_completo(s, pool, parola_t, esca, forte=True),
    }

    intestazione = (f"{'braccio':20s} {'GIUSTE':>7s} {'CANGURI':>8s} "
                    f"{'SOTTOD.':>8s} {'irris.':>7s} {'rilev. (scambio)':>17s} "
                    f"{'scambi':>7s}")
    print(intestazione)
    for nome, run in bracci.items():
        R = [run(s) for s in range(semi)]
        conta = lambda e: sum(1 for r in R if r["esito"].startswith(e))
        ril = [r["rilevazione"] for r in R if r["rilevazione"] is not None]
        ril_txt = (f"{statistics.mean(ril):.1f} ({len(ril)}/{semi})"
                   if ril else f"mai (0/{semi})")
        sc = statistics.mean([r["scambi"] for r in R])
        print(f"{nome:20s} {conta('GIUSTA'):>7d} {conta('CANGURO'):>8d} "
              f"{conta('SOTTODETERMINATA'):>8d} {conta('irrisolta'):>7d} "
              f"{ril_txt:>17s} {sc:>7.1f}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trappola", choices=sorted(TRAPPOLE), default="zumu_forma")
    ap.add_argument("--semi", type=int, default=50)
    ap.add_argument("--budget", type=int, default=60,
                    help="scambi per i bracci passivi A e B (parita' col C)")
    args = ap.parse_args()
    campagna(args.trappola, args.semi, args.budget)
