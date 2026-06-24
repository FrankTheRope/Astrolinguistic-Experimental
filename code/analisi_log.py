import json
from orchestratore import Scena, verita_L2

errori = 0; tot = 0
for riga in open("log_run.jsonl", encoding="utf-8"):
    d = json.loads(riga)
    if "scena" not in d: continue
    s = Scena(**d["scena"]); tot += 1
    if set(d["risposta_L2"].split()) != set(verita_L2(s).split()):
        errori += 1
        print(f"ERRORE: {s.testo()}  GPT: {d['risposta_L2']}  vero: {verita_L2(s)}")
print(f"\nFedelta' di esecuzione: {tot-errori}/{tot}")