"""
Condizioni difficili - Astrolinguistica sperimentale, Livello A (punto 4)
=========================================================================
Estende il micro-mondo a SEQUENZE di scene e aggiunge al lessico alieno due
parole fuori dallo spazio di ipotesi di base:

  NUR  - relazionale storica: emessa sse la scena corrente ha PIU' oggetti
         della precedente (sulla prima scena di un episodio non e' mai emessa)
  GUMO - "omonimo contestuale" / XOR: emessa sse forma e parita' CONCORDANO
         secondo la regola (triangolo & dispari) OPPURE (cerchio & pari).
         Non e' esprimibile come congiunzione: e' una disgiunzione.

Qui si gioca il claim "serve un LLM", con un'ablazione a tre bracci sul
LATO APPRENDISTA (il giudizio resta SEMPRE allo script):

  base    - spazio di ipotesi di base (congiunzioni statiche di 1-2 atomi).
            Atteso: NUR e GUMO irrisolte ma MAI canguri (degrado fail-safe).
  esteso  - spazio ORACOLO esteso a mano (atomi relazionali + disgiunzioni):
            lo script risolve tutto, MA solo perche' un umano sapeva quali
            estensioni servivano. Misura il tetto raggiungibile.
  llm     - spazio di base + PROPONENTE LLM: quando una parola resta senza
            ipotesi superstiti, il log delle osservazioni viene mostrato a un
            LLM che PROPONE regole candidate in un DSL ristretto; lo script
            le compila, le filtra sul log e le verifica con probe predittivi
            pre-registrati prima di qualunque promozione. L'LLM propone,
            lo script dispone.
  stub    - come llm ma con un proponente finto a regole fisse (giuste e
            sbagliate mescolate): serve SOLO a collaudare l'idraulica di
            validazione in assenza di chiavi API. I suoi esiti non
            sostengono il claim.

Promozione (apprendista sequenziale): eliminazione in ostensione su episodi,
poi M_PROBE=4 probe attivi su coppie (precedente, corrente) COSTRUITE, con
predizione registrata prima della risposta; servono 4/4 giusti e almeno un
probe positivo. Esiti calcolati per confronto ESTENSIONALE con la regola
vera su tutte le coppie (prec, corrente) possibili: GIUSTA / CANGURO /
SOTTODETERMINATA (classe di equivalenza estensionale) / irrisolta.

Uso:
  python condizioni.py --braccio base   --semi 20
  python condizioni.py --braccio esteso --semi 20
  python condizioni.py --braccio stub   --semi 20      # collaudo idraulica
  python condizioni.py --braccio llm    --semi 10      # richiede ANTHROPIC_API_KEY
"""

import argparse
import csv
import json
import os
import random
import statistics

from orchestratore import (Scena, TUTTE_LE_SCENE, FORME, COLORI, MOTI,
                           ATOMI, IPOTESI_UNIVERSO, verita_L2)

# Parita' di protocollo ESTESA: il proponente LLM e' uno strumento di misura
# la cui versione comprende codice + prompt + parser + validatore. I confronti
# tra run valgono solo a parita' di questa etichetta.
VERSIONE_PROTOCOLLO = "v3"
DESCRIZIONE_VERSIONE = ("prompt v3 (ragionamento ammesso, lista JSON come "
                        "ultima riga, max_tokens=2000) + parser ultima-lista "
                        "+ validazione semantica del DSL")

M_PROBE = 4          # probe per parola (tutti giusti + >=1 positivo)
EPISODI = 8          # episodi di ostensione
LUNGHEZZA = 6        # scene per episodio

# =================================================================
# 1. PARLANTE SIM "L2 DIFFICILE" (lessico base + NUR + GUMO)
# =================================================================

def _gumo(s: Scena) -> bool:
    dispari = s.n % 2 == 1
    return (s.forma == "triangolo" and dispari) or \
           (s.forma == "cerchio" and not dispari)

def _nur(prec, s: Scena) -> bool:
    return prec is not None and s.n > prec.n

def verita_L2D(prec, s: Scena) -> str:
    parole = verita_L2(s).split()
    if _nur(prec, s):
        parole.append("NUR")
    if _gumo(s):
        parole.append("GUMO")
    return " ".join(parole)

class ParlanteSimSeq:
    """Parlante a regole con memoria della scena precedente."""
    def __init__(self, regole):
        self.regole = regole
    def etichetta(self, prec, s: Scena) -> str:
        return self.regole(prec, s)

# =================================================================
# 2. IPOTESI COME PREDICATI SU (precedente, corrente)
# =================================================================

class Ipotesi:
    def __init__(self, descr: str, fn, complessita: int):
        self.descr = descr
        self.fn = fn                  # fn(prec, scena) -> bool
        self.complessita = complessita
    def vale(self, prec, s) -> bool:
        return self.fn(prec, s)
    def __repr__(self):
        return self.descr

def _cong_fn(atomi):
    atomi = tuple(sorted(atomi))
    def fn(prec, s):
        attr = s.attributi()
        return all(attr[k] == v for (k, v) in atomi)
    return fn

def ip_cong(atomi) -> Ipotesi:
    atomi = tuple(sorted(atomi))
    return Ipotesi("cong:" + "&".join(f"{k}={v}" for k, v in atomi),
                   _cong_fn(atomi), len(atomi))

def ip_rel_n(rel: str) -> Ipotesi:
    cmpf = {">": lambda a, b: a > b, "<": lambda a, b: a < b,
            "=": lambda a, b: a == b}[rel]
    return Ipotesi(f"rel_n:{rel}",
                   lambda prec, s: prec is not None and cmpf(s.n, prec.n), 2)

def ip_cambio(campo: str, stato: str) -> Ipotesi:
    uguale = (stato == "uguale")
    def fn(prec, s):
        if prec is None:
            return False
        return (getattr(prec, campo) == getattr(s, campo)) == uguale
    return Ipotesi(f"cambio:{campo}={stato}", fn, 2)

def ip_or(clausola_a, clausola_b) -> Ipotesi:
    fa, fb = _cong_fn(clausola_a), _cong_fn(clausola_b)
    da = "&".join(f"{k}={v}" for k, v in sorted(clausola_a))
    db = "&".join(f"{k}={v}" for k, v in sorted(clausola_b))
    return Ipotesi(f"or:({da})|({db})",
                   lambda prec, s: fa(prec, s) or fb(prec, s),
                   1 + len(clausola_a) + len(clausola_b))

def spazio_base():
    return [ip_cong(h) for h in sorted(IPOTESI_UNIVERSO,
                                       key=lambda h: sorted(h))]

def spazio_esteso():
    """Spazio ORACOLO: base + relazionali + cambi + disgiunzioni di coppie."""
    S = spazio_base()
    S += [ip_rel_n(r) for r in (">", "<", "=")]
    S += [ip_cambio(c, st) for c in ("forma", "colore", "moto")
          for st in ("cambiato", "uguale")]
    cong = sorted(IPOTESI_UNIVERSO, key=lambda h: sorted(h))
    for i in range(len(cong)):
        for j in range(i + 1, len(cong)):
            S.append(ip_or(cong[i], cong[j]))
    return S

# Regole VERE (per il confronto estensionale finale)
REGOLE_VERE = {
    "ZUMU": ip_cong({("colore", "rosso"), ("moto", "rapido")}),
    "ZAKA": ip_cong({("colore", "rosso"), ("moto", "fermo")}),
    "ZIBO": ip_cong({("colore", "blu"), ("moto", "rapido")}),
    "ZEFU": ip_cong({("colore", "blu"), ("moto", "fermo")}),
    "TAK":  ip_cong({("parita", "pari")}),
    "TIN":  ip_cong({("parita", "dispari")}),
    "NUR":  ip_rel_n(">"),
    "GUMO": ip_or({("forma", "triangolo"), ("parita", "dispari")},
                  {("forma", "cerchio"), ("parita", "pari")}),
}

COPPIE_MONDO = [(None, s) for s in TUTTE_LE_SCENE] + \
               [(p, s) for p in TUTTE_LE_SCENE for s in TUTTE_LE_SCENE]

def firma(h: Ipotesi) -> frozenset:
    """Estensione dell'ipotesi su tutte le coppie (prec, corrente)."""
    return frozenset(i for i, (p, s) in enumerate(COPPIE_MONDO)
                     if h.vale(p, s))

# =================================================================
# 3. PROPONENTI (per il braccio llm/stub): propongono, NON giudicano
# =================================================================

DSL_SPIEGAZIONE = """Formati ammessi (lista JSON, max 5 candidati):
 {"op":"cong","atomi":[["colore","rosso"],["moto","rapido"]]}
 {"op":"rel_n","rel":">"}        # n corrente >, < o = rispetto alla scena precedente
 {"op":"cambio","campo":"moto","stato":"cambiato"}   # o "uguale"; campi: forma|colore|moto
 {"op":"or","clausole":[[["forma","triangolo"],["parita","dispari"]],
                        [["forma","cerchio"],["parita","pari"]]]}
Attributi: forma(triangolo|cerchio), colore(rosso|blu), moto(rapido|fermo),
parita(pari|dispari).
Usa SOLO questi formati e questi attributi, senza inventarne altri."""

_VALORI_AMMESSI = {"forma": set(FORME), "colore": set(COLORI),
                   "moto": set(MOTI), "parita": {"pari", "dispari"}}

def _atomi_validi(atomi):
    """Valida semanticamente una lista di atomi del DSL; None se invalida.
    (Necessario: i proponenti LLM a volte INVENTANO estensioni del DSL,
    es. atomi come ["cambio_moto", ...] dentro una clausola or.)"""
    out = set()
    for coppia in atomi:
        if not (isinstance(coppia, (list, tuple)) and len(coppia) == 2):
            return None
        k, v = coppia
        if k not in _VALORI_AMMESSI or v not in _VALORI_AMMESSI[k]:
            return None
        out.add((k, v))
    return out if 1 <= len(out) <= 2 else None

def compila_candidato(c: dict):
    """DSL -> Ipotesi. Restituisce None se il candidato e' malformato
    o semanticamente invalido (atomi/relazioni/campi fuori vocabolario)."""
    try:
        if c["op"] == "cong":
            atomi = _atomi_validi(c["atomi"])
            return ip_cong(atomi) if atomi else None
        if c["op"] == "rel_n":
            return ip_rel_n(c["rel"]) if c["rel"] in (">", "<", "=") else None
        if c["op"] == "cambio":
            if (c["campo"] in ("forma", "colore", "moto")
                    and c["stato"] in ("cambiato", "uguale")):
                return ip_cambio(c["campo"], c["stato"])
            return None
        if c["op"] == "or":
            a, b = c["clausole"]
            va, vb = _atomi_validi(a), _atomi_validi(b)
            return ip_or(va, vb) if (va and vb) else None
    except (KeyError, ValueError, TypeError, IndexError):
        return None
    return None

def _tabella_osservazioni(osservazioni) -> str:
    righe = ["prec_forma prec_colore prec_moto prec_n | forma colore moto n | parola_presente"]
    for prec, s, pres in osservazioni:
        p = "(inizio episodio)        -" if prec is None else \
            f"{prec.forma} {prec.colore} {prec.moto} {prec.n}"
        righe.append(f"{p} | {s.forma} {s.colore} {s.moto} {s.n} | "
                     f"{'SI' if pres else 'no'}")
    return "\n".join(righe)

def _estrai_lista_json(testo: str):
    """Estrazione robusta: cerca TUTTE le liste JSON bilanciate nel testo e
    restituisce l'ULTIMA che sembra una lista di candidati (lista di oggetti
    con chiave 'op', o lista vuota). L'ultima, perche' i modelli che
    ragionano in prosa mettono la risposta finale in fondo."""
    testo = testo.replace("```json", "").replace("```", "").strip()
    # caso semplice: l'intera risposta e' gia' JSON
    try:
        dati = json.loads(testo)
        if isinstance(dati, dict):
            liste = [v for v in dati.values() if isinstance(v, list)]
            dati = liste[0] if len(liste) == 1 else None
        if isinstance(dati, list):
            return dati
    except json.JSONDecodeError:
        pass
    # scansione: tutte le liste bilanciate al livello piu' esterno
    trovate = []
    i = 0
    while i < len(testo):
        if testo[i] == "[":
            livello = 0
            for j in range(i, len(testo)):
                if testo[j] == "[":
                    livello += 1
                elif testo[j] == "]":
                    livello -= 1
                    if livello == 0:
                        try:
                            d = json.loads(testo[i:j + 1])
                            if isinstance(d, list) and (
                                    not d or all(isinstance(x, dict)
                                                 and "op" in x for x in d)):
                                trovate.append(d)
                        except json.JSONDecodeError:
                            pass
                        i = j
                        break
            else:
                break
        i += 1
    return trovate[-1] if trovate else None

class ProponenteClaude:
    """Chiede a un LLM regole candidate nel DSL. Solo proposte: la
    validazione (filtro sul log + probe pre-registrati) resta allo script.
    Ogni risposta GREZZA e' loggata (diagnostica e archivio), in un file
    il cui nome include modello e versione del protocollo."""
    def __init__(self, modello="claude-haiku-4-5", logfile=None):
        import anthropic
        self.client = anthropic.Anthropic()
        self.modello = modello
        self.logfile = logfile or \
            f"proposte_raw_{modello}_{VERSIONE_PROTOCOLLO}.jsonl"
    def proponi(self, parola: str, osservazioni) -> list:
        prompt = (f"Una parola sconosciuta '{parola}' di una lingua aliena "
                  f"e' stata osservata in queste scene (con la scena "
                  f"precedente dell'episodio, se esiste):\n\n"
                  f"{_tabella_osservazioni(osservazioni)}\n\n"
                  f"Proponi regole candidate che spieghino ESATTAMENTE "
                  f"quando la parola e' emessa.\n{DSL_SPIEGAZIONE}\n"
                  f"Puoi analizzare brevemente i dati se ti serve, ma "
                  f"concludi SEMPRE la risposta con la lista JSON dei "
                  f"candidati come ULTIMA riga, senza testo dopo di essa.")
        r = self.client.messages.create(
            model=self.modello, max_tokens=2000, temperature=0,
            messages=[{"role": "user", "content": prompt}])
        testo = r.content[0].text.strip()
        dati = _estrai_lista_json(testo)
        candidati = [] if dati is None else \
            [c for c in (compila_candidato(x) for x in dati) if c is not None]
        with open(self.logfile, "a", encoding="utf-8") as f:
            f.write(json.dumps({"versione": VERSIONE_PROTOCOLLO,
                                "modello": self.modello, "parola": parola,
                                "n_osservazioni": len(osservazioni),
                                "stop_reason": r.stop_reason,
                                "risposta_raw": testo,
                                "json_estratto": dati is not None,
                                "n_compilati": len(candidati)}) + "\n")
        return candidati

class ProponenteStub:
    """Collaudo dell'idraulica: candidati FISSI, giusti e sbagliati mescolati.
    Verifica che il filtro+probe scarti gli sbagliati. NON sostiene il claim."""
    def proponi(self, parola: str, osservazioni) -> list:
        return [c for c in (
            ip_rel_n("<"),                                     # sbagliato
            ip_cong({("colore", "rosso")}),                    # sbagliato
            ip_rel_n(">"),                                     # giusto per NUR
            ip_or({("forma", "triangolo"), ("parita", "dispari")},
                  {("forma", "cerchio"), ("parita", "pari")}), # giusto per GUMO
            ip_cambio("moto", "cambiato"),                     # sbagliato
        )]

# =================================================================
# 4. APPRENDISTA SEQUENZIALE
# =================================================================

class ApprendistaSeq:
    def __init__(self, parlante, spazio, seed=0, proponente=None):
        self.p2 = parlante
        self.spazio_iniziale = spazio
        self.rng = random.Random(seed)
        self.proponente = proponente
        self.ipotesi = {}          # parola -> lista di Ipotesi superstiti
        self.osservazioni = {}     # parola -> [(prec, scena, presente)]
        self.stato = {}            # parola -> PROVVISORIA/PROMOSSA/IRRISOLTA
        self.proposte_ricevute = {}    # parola -> n candidati proposti
        self.proposte_scartate = {}    # parola -> n scartati dal filtro/probe
        self.scambi = 0

    def _chiedi(self, prec, s):
        self.scambi += 1
        parole = set(self.p2.etichetta(prec, s).split())
        for w in sorted(parole):
            if w not in self.ipotesi:
                self.ipotesi[w] = list(self.spazio_iniziale)
                self.osservazioni[w] = []
                self.stato[w] = "PROVVISORIA"
        return parole

    def _osserva_tutte(self, prec, s, parole):
        for w in sorted(self.ipotesi):
            pres = w in parole
            self.osservazioni[w].append((prec, s, pres))
            self.ipotesi[w] = [h for h in self.ipotesi[w]
                               if h.vale(prec, s) == pres]

    def fase_ostensione(self, episodi=EPISODI, lunghezza=LUNGHEZZA):
        for _ in range(episodi):
            prec = None
            for _ in range(lunghezza):
                s = self.rng.choice(TUTTE_LE_SCENE)
                parole = self._chiedi(prec, s)
                self._osserva_tutte(prec, s, parole)
                prec = s

    def _coppia_probe(self, H, gia_usate):
        """Selezione attiva su coppie (prec, corrente) COSTRUITE:
        massimo split tra le ipotesi, poi attesa-presente."""
        migliore, chiave_migliore = None, None
        for coppia in COPPIE_MONDO:
            if coppia in gia_usate:
                continue
            voti = sum(1 for h in H if h.vale(*coppia))
            split = min(voti, len(H) - voti)
            attesa = 1 if voti > 0 else 0
            chiave = (split, attesa)
            if chiave_migliore is None or chiave > chiave_migliore:
                migliore, chiave_migliore = coppia, chiave
        return migliore

    def _probing(self, parola) -> bool:
        """M_PROBE probe pre-registrati; True se round pulito con >=1 positivo."""
        usate, positivi = [], 0
        for _ in range(M_PROBE):
            H = self.ipotesi[parola]
            if not H:
                return False
            coppia = self._coppia_probe(H, usate)
            usate.append(coppia)
            prec, s = coppia
            predizione = any(h.vale(prec, s) for h in H)   # PRIMA della risposta
            parole = self._chiedi(prec, s)
            self._osserva_tutte(prec, s, parole)           # l'evidenza vale per tutti
            reale = parola in parole
            if predizione != reale:
                return False
            if reale:
                positivi += 1
        return positivi >= 1

    def fase_probing(self):
        for w in sorted(self.ipotesi):
            if self.stato[w] != "PROVVISORIA" or not self.ipotesi[w]:
                continue
            if self._probing(w):
                self.stato[w] = "PROMOSSA"
            else:
                self.stato[w] = "IRRISOLTA" if self.ipotesi[w] else "PROVVISORIA"

    def fase_proposte(self):
        """Braccio llm/stub: per le parole rimaste senza ipotesi, chiede
        candidati al proponente; filtro sul log + probe = giudizio script."""
        if self.proponente is None:
            return
        for w in sorted(self.ipotesi):
            if self.ipotesi[w]:
                continue                       # serve solo dove il base fallisce
            candidati = self.proponente.proponi(w, self.osservazioni[w])
            self.proposte_ricevute[w] = len(candidati)
            coerenti = []
            for h in candidati:
                try:
                    if all(h.vale(p, s) == pres
                           for (p, s, pres) in self.osservazioni[w]):
                        coerenti.append(h)
                except Exception:
                    pass               # candidato difettoso: scartato, non fatale
            self.proposte_scartate[w] = len(candidati) - len(coerenti)
            if not coerenti:
                continue
            self.ipotesi[w] = coerenti
            if self._probing(w):
                self.stato[w] = "PROMOSSA"
            else:
                self.stato[w] = "IRRISOLTA"
                self.proposte_scartate[w] = self.proposte_ricevute[w]

    def esito(self, parola) -> str:
        vera_sig = firma(REGOLE_VERE[parola])
        sup = self.ipotesi.get(parola, [])
        if self.stato.get(parola) != "PROMOSSA" or not sup:
            return "irrisolta"
        sigs = {firma(h) for h in sup}
        if vera_sig not in sigs:
            return "CANGURO"
        return "GIUSTA" if len(sigs) == 1 else "SOTTODETERMINATA"

# =================================================================
# 5. CAMPAGNA
# =================================================================

def un_run(braccio: str, seed: int, modello: str):
    spazio = spazio_esteso() if braccio == "esteso" else spazio_base()
    proponente = None
    if braccio == "llm":
        proponente = ProponenteClaude(modello)
    elif braccio == "stub":
        proponente = ProponenteStub()
    app = ApprendistaSeq(ParlanteSimSeq(verita_L2D), spazio,
                         seed=seed, proponente=proponente)
    app.fase_ostensione()
    app.fase_probing()
    app.fase_proposte()
    return app

def campagna(braccio: str, semi: int, modello: str):
    etichetta_modello = modello if braccio == "llm" else braccio
    print(f"Braccio: {braccio} | spazio iniziale: "
          f"{len(spazio_esteso() if braccio == 'esteso' else spazio_base())} "
          f"ipotesi | semi: {semi}")
    print(f"Protocollo: {VERSIONE_PROTOCOLLO} = {DESCRIZIONE_VERSIONE}\n")
    parole = sorted(REGOLE_VERE)
    esiti = {w: [] for w in parole}
    righe_csv = []
    scambi, prop_ric, prop_scart = [], 0, 0
    for seed in range(semi):
        app = un_run(braccio, seed, modello)
        for w in parole:
            e = app.esito(w)
            esiti[w].append(e)
            righe_csv.append({"versione": VERSIONE_PROTOCOLLO,
                              "braccio": braccio,
                              "modello": etichetta_modello,
                              "seed": seed, "parola": w, "esito": e,
                              "scambi_run": app.scambi})
        scambi.append(app.scambi)
        prop_ric += sum(app.proposte_ricevute.values())
        prop_scart += sum(app.proposte_scartate.values())

    print(f"{'parola':6s} {'GIUSTE':>7s} {'CANGURI':>8s} {'SOTTOD.':>8s} {'irris.':>7s}")
    for w in parole:
        c = lambda e: sum(1 for x in esiti[w] if x == e)
        riga = (f"{w:6s} {c('GIUSTA'):>7d} {c('CANGURO'):>8d} "
                f"{c('SOTTODETERMINATA'):>8d} {c('irrisolta'):>7d}")
        if w in ("NUR", "GUMO"):
            riga += "   <- parola difficile"
        print(riga)
    print(f"\nscambi per run: {statistics.mean(scambi):.1f} "
          f"± {statistics.stdev(scambi):.2f}" if len(scambi) > 1 else "")
    if braccio in ("llm", "stub"):
        print(f"proposte del proponente: {prop_ric} ricevute, "
              f"{prop_scart} scartate dal giudice-script")

    nome_csv = (f"risultati_condizioni_{braccio}_"
                f"{etichetta_modello}_{VERSIONE_PROTOCOLLO}.csv")
    with open(nome_csv, "w", newline="", encoding="utf-8") as f:
        wtr = csv.DictWriter(f, fieldnames=["versione", "braccio", "modello",
                                            "seed", "parola", "esito",
                                            "scambi_run"])
        wtr.writeheader()
        wtr.writerows(righe_csv)
    print(f"Dati grezzi: {nome_csv}", end="")
    if braccio == "llm":
        print(f" | risposte del proponente: "
              f"proposte_raw_{modello}_{VERSIONE_PROTOCOLLO}.jsonl "
              f"(da archiviare insieme al CSV)")
    else:
        print()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--braccio", choices=["base", "esteso", "llm", "stub"],
                    required=True)
    ap.add_argument("--semi", type=int, default=20)
    ap.add_argument("--modello", default="claude-haiku-4-5",
                    help="modello per il braccio llm")
    args = ap.parse_args()
    if args.braccio == "llm" and not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Errore: ANTHROPIC_API_KEY non impostata "
                         "(usa --braccio stub per collaudare l'idraulica).")
    campagna(args.braccio, args.semi, args.modello)
