"""
Orchestratore - Astrolinguistica sperimentale, Livello A
=========================================================
Fa dialogare due parlanti (L1 "umano", L2 "alieno") attraverso scene
di un micro-mondo e costruisce il dizionario L2 -> attributi tramite:
  1. ostensione (ancore PROVVISORIE con ipotesi multiple)
  2. coppie minime contrastive (eliminazione ipotesi)
  3. probing predittivo (conferma prima della promozione)
  4. quarantena e revoca (anti-effetto-canguro)

Modalita':
  python orchestratore.py --sim            # parlanti simulati a regole (gratis, per testare la logica)
  python orchestratore.py --llm            # parlanti veri via API (Claude=L1, GPT=L2)
  python orchestratore.py --sim --seed 7   # cambia il seme del mondo
  python orchestratore.py --sim --round2   # secondo round di probing sulle irrisolte

Output: dizionario finale + metriche a video, log completo in log_run.jsonl
"""

import argparse
import itertools
import json
import os
import random
from dataclasses import dataclass, asdict

# =================================================================
# 1. MICRO-MONDO
# =================================================================

FORME = ["triangolo", "cerchio"]
COLORI = ["rosso", "blu"]
MOTI = ["rapido", "fermo"]
NUMERI = [1, 2, 3, 4]

@dataclass(frozen=True)
class Scena:
    forma: str
    colore: str
    moto: str
    n: int

    def testo(self) -> str:
        verbo = "che si muovono rapidamente" if self.moto == "rapido" else "fermi"
        if self.n == 1:
            verbo = "che si muove rapidamente" if self.moto == "rapido" else "fermo"
        plurale = {"triangolo": "triangoli", "cerchio": "cerchi"}
        nome = self.forma if self.n == 1 else plurale[self.forma]
        colore = self.colore + ("" if self.n == 1 else ("i" if self.colore == "rosso" else ""))
        return f"Scena: {self.n} {nome} {colore} {verbo}."

    def attributi(self) -> dict:
        return {"forma": self.forma, "colore": self.colore,
                "moto": self.moto, "parita": "pari" if self.n % 2 == 0 else "dispari"}

TUTTE_LE_SCENE = [Scena(f, c, m, n) for f, c, m, n
                  in itertools.product(FORME, COLORI, MOTI, NUMERI)]

# =================================================================
# 2. GROUND TRUTH DEI LESSICI (noto solo all'orchestratore)
# =================================================================

# L1: una parola per forma, colore, moto (il numero NON e' codificato)
def verita_L1(s: Scena) -> str:
    return " ".join([
        {"triangolo": "KEPO", "cerchio": "KIMU"}[s.forma],
        {"rosso": "KARI", "blu": "KOLA"}[s.colore],
        {"rapido": "KESU", "fermo": "KANO"}[s.moto],
    ])

# L2 "alieno": colore e moto FUSI in una parola; parita' del numero; la forma non esiste
def verita_L2(s: Scena) -> str:
    fusa = {("rosso", "rapido"): "ZUMU", ("rosso", "fermo"): "ZAKA",
            ("blu", "rapido"): "ZIBO", ("blu", "fermo"): "ZEFU"}[(s.colore, s.moto)]
    par = "TAK" if s.n % 2 == 0 else "TIN"
    return f"{fusa} {par}"

# Il referente VERO di ogni parola L2, per il calcolo delle metriche finali.
# Una parola fusa corrisponde a una CONGIUNZIONE di attributi.
REFERENTI_VERI_L2 = {
    "ZUMU": {("colore", "rosso"), ("moto", "rapido")},
    "ZAKA": {("colore", "rosso"), ("moto", "fermo")},
    "ZIBO": {("colore", "blu"), ("moto", "rapido")},
    "ZEFU": {("colore", "blu"), ("moto", "fermo")},
    "TAK":  {("parita", "pari")},
    "TIN":  {("parita", "dispari")},
}

# =================================================================
# 3. PARLANTI
# =================================================================

class ParlanteSim:
    """Applica le regole del lessico in modo perfetto (braccio di controllo)."""
    def __init__(self, regole):
        self.regole = regole
    def etichetta(self, s: Scena) -> str:
        return self.regole(s)

LESSICO_L1_PROMPT = """Sei un etichettatore. Descrivi le scene SOLO con queste parole:
- forma:  triangolo -> KEPO | cerchio -> KIMU
- colore: rosso -> KARI     | blu -> KOLA
- moto:   rapido -> KESU    | fermo -> KANO
Rispondi con UNA SOLA descrizione per l'INTERA scena: esattamente tre parole
(forma colore moto), qualunque sia il numero di oggetti.
Nessun'altra parola, nessuna spiegazione."""

LESSICO_L2_PROMPT = """Sei un etichettatore. Descrivi le scene SOLO con queste parole:
- ZUMU = oggetti rossi in movimento (rosso E rapido insieme)
- ZAKA = oggetti rossi fermi
- ZIBO = oggetti blu in movimento
- ZEFU = oggetti blu fermi
- TAK  = numero pari di oggetti
- TIN  = numero dispari di oggetti
TAK e TIN si applicano SEMPRE, anche con un solo oggetto: 1 e' dispari,
quindi un oggetto singolo richiede TIN.
La forma degli oggetti NON esiste nel tuo lessico: ignorala.
Rispondi con UNA SOLA descrizione per l'INTERA scena: esattamente due parole.
Nessun'altra parola, nessuna spiegazione."""

class ParlanteClaude:
    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic()
    def etichetta(self, s: Scena) -> str:
        r = self.client.messages.create(
            model="claude-haiku-4-5", max_tokens=30, temperature=0,
            system=LESSICO_L1_PROMPT,
            messages=[{"role": "user", "content": s.testo()}])
        return r.content[0].text.strip()

class ParlanteGPT:
    def __init__(self):
        import openai
        self.client = openai.OpenAI()
    def etichetta(self, s: Scena) -> str:
        r = self.client.chat.completions.create(
            model="gpt-4o-mini", max_tokens=30, temperature=0,
            messages=[{"role": "system", "content": LESSICO_L2_PROMPT},
                      {"role": "user", "content": s.testo()}])
        return r.choices[0].message.content.strip()

# =================================================================
# 4. MACCHINA A STATI DELLE ANCORE
# =================================================================

# Ipotesi atomiche: (attributo, valore)
ATOMI = {("forma", f) for f in FORME} | \
        {("colore", c) for c in COLORI} | \
        {("moto", m) for m in MOTI} | \
        {("parita", p) for p in ["pari", "dispari"]}

# Un'ipotesi e' un frozenset di atomi (congiunzione): atomica = 1 atomo,
# fusa = 2 atomi di attributi DIVERSI (es. ZUMU = rosso E rapido).
IPOTESI_UNIVERSO = {frozenset([a]) for a in ATOMI} | \
                   {frozenset([a, b]) for a in ATOMI for b in ATOMI
                    if a < b and a[0] != b[0]}

def _vale(ipotesi, scena: "Scena") -> bool:
    attr = scena.attributi()
    return all(attr[k] == v for (k, v) in ipotesi)

class Ancora:
    """Una parola L2 con il suo insieme di ipotesi sul referente."""
    def __init__(self, parola):
        self.parola = parola
        self.stato = "PROVVISORIA"          # -> IRRISOLTA -> PROMOSSA -> (REVOCATA)
        self.ipotesi = set(IPOTESI_UNIVERSO)  # si restringe con l'evidenza
        self.coppie_discriminanti = 0
        self.probe_ok = 0                   # contatori CUMULATIVI (tutti i round)
        self.probe_falliti = 0
        self.round_promozione = None        # round in cui e' avvenuta la promozione
        self.scene_probe = []               # scene gia' usate nei probe (tutti i round)

    def osserva(self, scena: Scena, presente: bool):
        """La parola e' emessa se e solo se il suo referente vale nella scena:
        quindi sopravvivono le ipotesi la cui verita' coincide con la presenza."""
        self.ipotesi = {h for h in self.ipotesi if _vale(h, scena) == presente}

    def referente_stimato(self):
        """Ipotesi superstiti; se ne resta piu' d'una, si sceglie la piu'
        semplice (rasoio di Occam: prima le atomiche). Pareggi risolti
        sull'ordine canonico (sorted), per indipendenza da PYTHONHASHSEED."""
        if not self.ipotesi:
            return set()
        canoniche = sorted(self.ipotesi, key=lambda h: (len(h), sorted(h)))
        return set(canoniche[0])

# =================================================================
# 5. ORCHESTRATORE
# =================================================================

class Orchestratore:
    K_COPPIE = 3   # coppie minime discriminanti per la promozione
    M_PROBE = 3    # probe predittivi consecutivi richiesti

    def __init__(self, parlante_l2, seed=0, logfile="log_run.jsonl", attiva=False):
        self.p2 = parlante_l2
        self.rng = random.Random(seed)
        self.ancore = {}
        self.scambi = 0
        self.attiva = attiva          # selezione attiva delle scene nei probe
        self.log = open(logfile, "w", encoding="utf-8")

    def _scena_probe(self, a: "Ancora", gia_usate: list) -> Scena:
        """Selezione attiva: la scena che discrimina di piu' tra le ipotesi
        superstiti. Criteri in ordine: (1) massimo split delle ipotesi
        (le ipotesi sono in disaccordo sulla presenza della parola);
        (2) preferenza per scene dove la parola e' ATTESA PRESENTE
        (un referente troppo semplice si smaschera li'); (3) novita'
        degli attributi non vincolati rispetto ai probe precedenti.
        Spareggio deterministico sull'ordine canonico delle scene."""
        H = sorted(a.ipotesi, key=lambda h: sorted(h))
        visti = {}   # attributo -> valori gia' coperti nei probe precedenti
        for s_prec in gia_usate:
            for k, v in s_prec.attributi().items():
                visti.setdefault(k, set()).add(v)
        migliore, chiave_migliore = None, None
        for s in TUTTE_LE_SCENE:
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
        return migliore if migliore is not None else self.rng.choice(TUTTE_LE_SCENE)

    def _chiedi(self, scena: Scena) -> set:
        """Mostra la scena a L2 e restituisce l'insieme delle parole emesse.
        Le parole mai viste prima diventano nuove ancore PROVVISORIE,
        in qualunque fase compaiano."""
        self.scambi += 1
        risposta = self.p2.etichetta(scena)
        parole = set(risposta.split())
        for w in sorted(parole):
            self.ancore.setdefault(w, Ancora(w))
        self.log.write(json.dumps({"scambio": self.scambi, "scena": asdict(scena),
                                   "risposta_L2": risposta}) + "\n")
        return parole

    def fase_ostensione(self, n_scene=6):
        """Fase 1: scene casuali; le parole nuove entrano via _chiedi."""
        for s in self.rng.sample(TUTTE_LE_SCENE, n_scene):
            parole = self._chiedi(s)
            for w, a in sorted(self.ancore.items()):
                a.osserva(s, presente=(w in parole))

    def _coppia_minima(self, scena: Scena, attributo: str):
        """Restituisce la scena identica ma con l'attributo cambiato."""
        d = asdict(scena)
        if attributo == "forma":
            d["forma"] = [f for f in FORME if f != scena.forma][0]
        elif attributo == "colore":
            d["colore"] = [c for c in COLORI if c != scena.colore][0]
        elif attributo == "moto":
            d["moto"] = [m for m in MOTI if m != scena.moto][0]
        elif attributo == "parita":
            d["n"] = scena.n + 1 if scena.n < 4 else scena.n - 1
        return Scena(**d)

    def fase_coppie_minime(self):
        """Fase 2: per ogni ancora, scene che variano un attributo alla volta."""
        for a in sorted(self.ancore.values(), key=lambda x: x.parola):
            attributi_da_testare = {k for h in a.ipotesi for (k, v) in h}
            for attr in sorted(attributi_da_testare):
                base = self.rng.choice(TUTTE_LE_SCENE)
                variata = self._coppia_minima(base, attr)
                w_base = a.parola in self._chiedi(base)
                w_var = a.parola in self._chiedi(variata)
                a.osserva(base, w_base)
                a.osserva(variata, w_var)
                if w_base != w_var:           # la parola co-varia con l'attributo
                    a.coppie_discriminanti += 1

    def fase_probing(self, round_n=1):
        """Fase 3: predizione registrata PRIMA della risposta, poi verifica.

        round_n = 1: primo round, su tutte le ancore con ipotesi superstiti.
        round_n >= 2: ri-probing delle sole ancore NON promosse (IRRISOLTE o
        PROVVISORIE). Le loro ipotesi sono gia' state corrette dagli errori
        del round precedente (osserva() sui probe falliti), quindi il round
        di recupero verifica le ipotesi corrette su scene nuove.

        Decisione per round: serve un round PULITO (M_PROBE giusti, 0 errori
        nel round) + almeno 1 coppia discriminante. Dal round 2 in poi il
        criterio e' PIU' esigente: serve anche almeno un probe POSITIVO
        (parola predetta presente E osservata presente), per non promuovere
        un'ipotesi corretta-per-caso su sole assenze."""
        for a in sorted(self.ancore.values(), key=lambda x: x.parola):
            if a.stato in ("PROMOSSA", "REVOCATA") or len(a.ipotesi) == 0:
                continue
            ok_round, falliti_round, positivi_round = 0, 0, 0
            for _ in range(self.M_PROBE):
                if self.attiva:
                    s = self._scena_probe(a, a.scene_probe)
                else:
                    s = self.rng.choice(TUTTE_LE_SCENE)
                a.scene_probe.append(s)
                predizione = any(_vale(h, s) for h in a.ipotesi)
                reale = a.parola in self._chiedi(s)
                self.log.write(json.dumps({"round": round_n, "probe": a.parola,
                                           "predetto": predizione, "reale": reale}) + "\n")
                if predizione == reale:
                    ok_round += 1
                    a.probe_ok += 1
                    if reale:
                        positivi_round += 1
                else:
                    falliti_round += 1
                    a.probe_falliti += 1
                    a.osserva(s, reale)        # l'errore informa: aggiorna le ipotesi
            promuovi = (ok_round >= self.M_PROBE and falliti_round == 0
                        and a.coppie_discriminanti >= 1)
            if round_n >= 2:
                promuovi = promuovi and positivi_round >= 1
            if promuovi:
                a.stato = "PROMOSSA"
                a.round_promozione = round_n
                self.log.write(json.dumps({"evento": "PROMOZIONE",
                                           "parola": a.parola,
                                           "round": round_n}) + "\n")
            elif falliti_round > 0:
                # quarantena: il canguro e' stato intercettato (se gia' promossa)
                a.stato = "REVOCATA" if a.stato == "PROMOSSA" else "IRRISOLTA"

    def metriche(self):
        """Confronto finale con il ground truth."""
        giuste, sbagliate, irrisolte = 0, 0, 0
        promosse_per_round = {}
        dettaglio = {}
        for w, a in sorted(self.ancore.items()):
            vero = REFERENTI_VERI_L2.get(w, set())
            stimato = a.referente_stimato()
            if a.stato != "PROMOSSA" or len(stimato) == 0:
                esito, irrisolte = "irrisolta", irrisolte + 1
            elif stimato == vero:
                esito, giuste = "GIUSTA", giuste + 1
            else:
                esito, sbagliate = "CANGURO (non rilevato)", sbagliate + 1
            if a.stato == "PROMOSSA":
                promosse_per_round[a.round_promozione] = \
                    promosse_per_round.get(a.round_promozione, 0) + 1
            dettaglio[w] = {"stato": a.stato, "stimato": sorted(stimato),
                            "vero": sorted(vero), "esito": esito,
                            "round_promozione": a.round_promozione}
        return {"giuste": giuste, "canguri_residui": sbagliate,
                "irrisolte": irrisolte, "scambi_totali": self.scambi,
                "promosse_per_round": promosse_per_round,
                "dettaglio": dettaglio}

# =================================================================
# 6. MAIN
# =================================================================

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true", help="parlanti simulati (gratis)")
    ap.add_argument("--llm", action="store_true", help="parlanti via API")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--attiva", action="store_true",
                    help="selezione attiva delle scene nei probe")
    ap.add_argument("--round2", action="store_true",
                    help="secondo round di probing sulle ancore irrisolte "
                         "(ipotesi gia' corrette dagli errori del round 1)")
    args = ap.parse_args()

    if args.llm:
        for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            if not os.environ.get(var):
                raise SystemExit(f"Errore: {var} non impostata.")
        p2 = ParlanteGPT()
        modo = "LLM (GPT come parlante L2)"
    else:
        p2 = ParlanteSim(verita_L2)
        modo = "SIMULAZIONE (regole perfette)"

    print(f"Modo: {modo} | seed mondo: {args.seed}\n")

    orch = Orchestratore(p2, seed=args.seed, attiva=args.attiva)
    orch.fase_ostensione(n_scene=6)
    orch.fase_coppie_minime()
    orch.fase_probing(round_n=1)
    if args.round2:
        orch.fase_probing(round_n=2)
    m = orch.metriche()

    print("=== DIZIONARIO RICOSTRUITO L2 -> attributi ===")
    for w, info in sorted(m["dettaglio"].items()):
        rnd = f" (round {info['round_promozione']})" if info["round_promozione"] else ""
        print(f"  {w:6s} [{info['stato']:11s}]{rnd} stimato={info['stimato']}")
        print(f"         vero   ={info['vero']}  ->  {info['esito']}")
    print(f"\n=== METRICHE ===")
    print(f"  voci giuste:      {m['giuste']}")
    print(f"  canguri residui:  {m['canguri_residui']}")
    print(f"  irrisolte:        {m['irrisolte']}")
    print(f"  scambi totali:    {m['scambi_totali']}")
    if m["promosse_per_round"]:
        per_round = ", ".join(f"round {r}: {n}"
                              for r, n in sorted(m["promosse_per_round"].items()))
        print(f"  promozioni:       {per_round}")
    print(f"\nLog completo: log_run.jsonl")
