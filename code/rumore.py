"""
Informante rumoroso - test di robustezza del protocollo (revisione paper)
=========================================================================
Parlante SIM che, per ogni scena, INVERTE la presenza di ciascuna parola L2
con probabilita' p (flip indipendente per parola, RNG dedicato e seminato:
tutto deterministico). Il protocollo completo (attiva + round2) gira invariato.

Domanda onesta, pre-registrata: l'eliminazione (Eq. 2) assume fedelta'
perfetta; col rumore PUO' eliminare l'ipotesi vera. Esiti possibili:
 (a) i canguri restano 0 e il rumore si scarica sulle irrisolte (fail-safe);
 (b) compaiono canguri -> delimitazione onesta del dominio di validita'.

Uso: python rumore.py [--semi 50]
"""
import argparse
import random
import statistics

from orchestratore import (Orchestratore, ParlanteSim, verita_L2,
                           REFERENTI_VERI_L2, Scena)

VOCAB_L2 = sorted(REFERENTI_VERI_L2)   # ZAKA ZEFU ZIBO ZUMU TAK TIN (ordinato)

class ParlanteSimRumoroso:
    """Applica le regole L2 e poi inverte la presenza di ogni parola
    con probabilita' p (rumore di canale simmetrico, per-parola)."""
    def __init__(self, p: float, seed: int):
        self.p = p
        self.rng = random.Random(10_000 + seed)   # RNG dedicato al rumore
    def etichetta(self, s: Scena) -> str:
        parole = set(verita_L2(s).split())
        for w in VOCAB_L2:
            if self.rng.random() < self.p:
                parole.symmetric_difference_update({w})
        return " ".join(sorted(parole))

def un_run(p: float, seed: int):
    p2 = ParlanteSim(verita_L2) if p == 0 else ParlanteSimRumoroso(p, seed)
    logfile = f"log_rumore_p{int(p*100)}_seed{seed}.jsonl"
    orch = Orchestratore(p2, seed=seed, attiva=True, logfile=logfile)
    orch.fase_ostensione(n_scene=6)
    orch.fase_coppie_minime()
    orch.fase_probing(round_n=1)
    orch.fase_probing(round_n=2)
    orch.log.close()
    m = orch.metriche()
    # fedelta' di esecuzione dal log
    import json
    ok = tot = 0
    for riga in open(logfile, encoding="utf-8"):
        d = json.loads(riga)
        if "scena" not in d:
            continue
        tot += 1
        if set(d["risposta_L2"].split()) == set(verita_L2(Scena(**d["scena"])).split()):
            ok += 1
    return (m["giuste"], m["canguri_residui"], m["irrisolte"],
            m["scambi_totali"], 100.0 * ok / tot)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--semi", type=int, default=50)
    args = ap.parse_args()
    print(f"{'p rumore':>8s} {'fedelta%':>9s} {'giuste':>12s} {'canguri':>12s} "
          f"{'irrisolte':>12s} {'scambi':>8s}")
    for p in (0.0, 0.02, 0.05, 0.10):
        R = [un_run(p, s) for s in range(args.semi)]
        def ms(k):
            v = [r[k] for r in R]
            return f"{statistics.mean(v):.2f} ± {statistics.stdev(v):.2f}"
        fed = statistics.mean(r[4] for r in R)
        kang_tot = sum(r[1] for r in R)
        print(f"{p:>8.2f} {fed:>9.1f} {ms(0):>12s} {ms(1):>12s} {ms(2):>12s} "
              f"{statistics.mean(r[3] for r in R):>8.1f}   (canguri totali: {kang_tot})")
