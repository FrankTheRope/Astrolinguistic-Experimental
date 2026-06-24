"""
Campagna multi-seme - Astrolinguistica sperimentale, Livello A
==============================================================
Esegue l'orchestratore su N semi in modalita' SIM e/o LLM, raccoglie le
metriche di ogni run (incluse la fedelta' di esecuzione del parlante,
calcolata automaticamente dal log) e produce:
  - risultati_campagna.csv      (una riga per run, dati grezzi)
  - tabella riassuntiva a video (pronta per il report/paper)
  - log_seed{N}_{modo}.jsonl    (log integrale di ogni run)

Uso:
  python campagna.py --sim                  # 10 semi, gratis
  python campagna.py --llm                  # 10 semi via API (~480 chiamate)
  python campagna.py --sim --llm            # entrambe le modalita'
  python campagna.py --sim --semi 5         # numero di semi diverso
  python campagna.py --sim --attiva --round2  # selezione attiva + round di recupero

I nomi dei file di output includono la condizione (casuale/attiva, _r2),
cosi' campagne diverse NON si sovrascrivono piu' a vicenda.
"""

import argparse
import csv
import json
import statistics

from orchestratore import (Orchestratore, ParlanteSim, Scena,
                           verita_L2)

def fedelta_da_log(logfile: str):
    """Confronta ogni risposta del parlante con la regola vera L2."""
    ok, tot = 0, 0
    for riga in open(logfile, encoding="utf-8"):
        d = json.loads(riga)
        if "scena" not in d:
            continue
        tot += 1
        s = Scena(**d["scena"])
        if set(d["risposta_L2"].split()) == set(verita_L2(s).split()):
            ok += 1
    return ok, tot

def nome_condizione(attiva: bool, round2: bool) -> str:
    return ("attiva" if attiva else "casuale") + ("_r2" if round2 else "")

def un_run(modo: str, seed: int, attiva: bool = False,
           round2: bool = False) -> dict:
    cond = nome_condizione(attiva, round2)
    logfile = f"log_seed{seed}_{modo}_{cond}.jsonl"
    if modo == "llm":
        from orchestratore import ParlanteGPT
        p2 = ParlanteGPT()
    else:
        p2 = ParlanteSim(verita_L2)
    orch = Orchestratore(p2, seed=seed, logfile=logfile, attiva=attiva)
    orch.fase_ostensione(n_scene=6)
    orch.fase_coppie_minime()
    orch.fase_probing(round_n=1)
    if round2:
        orch.fase_probing(round_n=2)
    m = orch.metriche()
    orch.log.close()
    ok, tot = fedelta_da_log(logfile)
    return {"modo": modo, "seed": seed, "condizione": cond,
            "giuste": m["giuste"], "canguri": m["canguri_residui"],
            "irrisolte": m["irrisolte"], "scambi": m["scambi_totali"],
            "rec_r2": m["promosse_per_round"].get(2, 0),
            "fedelta_ok": ok, "fedelta_tot": tot,
            "fedelta_pct": round(100 * ok / tot, 1) if tot else 0.0}

def riassunto(righe, modo):
    sel = [r for r in righe if r["modo"] == modo]
    if not sel:
        return
    def agg(campo):
        v = [r[campo] for r in sel]
        media = statistics.mean(v)
        dev = statistics.stdev(v) if len(v) > 1 else 0.0
        return f"{media:.2f} ± {dev:.2f}"
    print(f"\n--- RIASSUNTO {modo.upper()} ({len(sel)} semi, "
          f"condizione: {sel[0]['condizione']}) ---")
    print(f"  voci giuste:   {agg('giuste')}")
    print(f"  canguri:       {agg('canguri')}   <- la metrica critica")
    print(f"  irrisolte:     {agg('irrisolte')}")
    print(f"  scambi:        {agg('scambi')}")
    print(f"  fedelta' (%):  {agg('fedelta_pct')}")
    rec_tot = sum(r["rec_r2"] for r in sel)
    if any(r["condizione"].endswith("_r2") for r in sel):
        print(f"  recuperi al round 2: {rec_tot} "
              f"(in {sum(1 for r in sel if r['rec_r2'] > 0)}/{len(sel)} run)")
    n_canguri = sum(r["canguri"] for r in sel)
    print(f"  run con almeno un canguro: "
          f"{sum(1 for r in sel if r['canguri'] > 0)}/{len(sel)} "
          f"(canguri totali: {n_canguri})")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--semi", type=int, default=10)
    ap.add_argument("--attiva", action="store_true", help="selezione attiva delle scene nei probe")
    ap.add_argument("--round2", action="store_true",
                    help="secondo round di probing sulle ancore irrisolte")
    args = ap.parse_args()
    modi = ([("sim")] if args.sim else []) + ([("llm")] if args.llm else [])
    if not modi:
        raise SystemExit("Specificare --sim e/o --llm")
    cond = nome_condizione(args.attiva, args.round2)

    righe = []
    intest = ["modo", "seed", "condizione", "giuste", "canguri", "irrisolte",
              "scambi", "rec_r2", "fedelta_ok", "fedelta_tot", "fedelta_pct"]
    print(f"Condizione: {cond}\n")
    print(f"{'modo':5s} {'seed':>4s} {'giuste':>6s} {'cang.':>5s} "
          f"{'irris.':>6s} {'scambi':>6s} {'recR2':>5s} {'fedelta':>9s}")
    for modo in modi:
        for seed in range(args.semi):
            r = un_run(modo, seed, attiva=args.attiva, round2=args.round2)
            righe.append(r)
            print(f"{r['modo']:5s} {r['seed']:>4d} {r['giuste']:>6d} "
                  f"{r['canguri']:>5d} {r['irrisolte']:>6d} {r['scambi']:>6d} "
                  f"{r['rec_r2']:>5d} {r['fedelta_ok']:>4d}/{r['fedelta_tot']:<4d}")

    nome_csv = f"risultati_campagna_{'-'.join(modi)}_{cond}.csv"
    with open(nome_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=intest)
        w.writeheader()
        w.writerows(righe)

    for modo in modi:
        riassunto(righe, modo)
    print(f"\nDati grezzi: {nome_csv} | log per run: log_seed*_*_{cond}.jsonl")
