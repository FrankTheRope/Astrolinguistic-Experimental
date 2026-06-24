"""
Hello World - Astrolinguistica sperimentale, Livello A
Una singola scena viene mostrata a due LLM (Claude e GPT),
ciascuno con un proprio lessico privato. Stampa le due etichette.

Prerequisiti:
  pip install anthropic openai
  export ANTHROPIC_API_KEY="sk-ant-..."
  export OPENAI_API_KEY="sk-..."

Uso:
  python hello_world.py
"""

import os
import anthropic
import openai

# ---------------------------------------------------------------
# 1. I due lessici (versione minima: 2 forme, 2 colori, 2 moti)
# ---------------------------------------------------------------

LESSICO_L1 = """Sei un etichettatore. Descrivi le scene SOLO con queste parole, una per attributo:
- forma:  triangolo -> KEPO | cerchio -> KIMU
- colore: rosso -> KARI     | blu -> KOLA
- moto:   rapido -> KESU    | fermo -> KANO
Rispondi SOLO con le parole del lessico separate da spazi (es. "KEPO KARI KESU").
Nessun'altra parola, nessuna spiegazione."""

# L2 e' "alieno": fonde colore+moto in un concetto unico
# e classifica per parita' del numero di oggetti, non per forma.
LESSICO_L2 = """Sei un etichettatore. Descrivi le scene SOLO con queste parole:
- ZUMU = oggetti rossi in movimento (rosso E rapido insieme)
- ZAKA = oggetti rossi fermi
- ZIBO = oggetti blu in movimento
- ZEFU = oggetti blu fermi
- TAK  = numero pari di oggetti
- TIN  = numero dispari di oggetti
La forma degli oggetti NON esiste nel tuo lessico: ignorala.
Rispondi SOLO con le parole del lessico separate da spazi (es. "ZUMU TAK").
Nessun'altra parola, nessuna spiegazione."""

# ---------------------------------------------------------------
# 2. La scena (in rappresentazione neutra, nota solo a noi)
# ---------------------------------------------------------------

SCENA = "Scena: 2 triangoli rossi che si muovono rapidamente."
GROUND_TRUTH = {"forma": "triangolo", "colore": "rosso", "moto": "rapido", "n": 2}

# ---------------------------------------------------------------
# 3. Le due chiamate
# ---------------------------------------------------------------

def etichetta_claude(scena: str) -> str:
    client = anthropic.Anthropic()  # legge ANTHROPIC_API_KEY dall'ambiente
    r = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=30,
        temperature=0,
        system=LESSICO_L1,
        messages=[{"role": "user", "content": scena}],
    )
    return r.content[0].text.strip()


def etichetta_gpt(scena: str) -> str:
    client = openai.OpenAI()  # legge OPENAI_API_KEY dall'ambiente
    r = client.chat.completions.create(
        model="gpt-4o-mini",   # sostituibile con un mini-modello piu' recente
        max_tokens=30,
        temperature=0,
        messages=[
            {"role": "system", "content": LESSICO_L2},
            {"role": "user", "content": scena},
        ],
    )
    return r.choices[0].message.content.strip()

# ---------------------------------------------------------------
# 4. Esecuzione
# ---------------------------------------------------------------

if __name__ == "__main__":
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        if not os.environ.get(var):
            raise SystemExit(f"Errore: variabile d'ambiente {var} non impostata.")

    print(f"{SCENA}\n  (ground truth: {GROUND_TRUTH})\n")

    l1 = etichetta_claude(SCENA)
    print(f"Parlante L1 (Claude): {l1}")
    print(f"  atteso: KEPO KARI KESU\n")

    l2 = etichetta_gpt(SCENA)
    print(f"Parlante L2 (GPT):    {l2}")
    print(f"  atteso: ZUMU TAK")

    print("\nSe entrambe le etichette coincidono con l'atteso, il setup funziona:")
    print("ogni modello applica il proprio lessico. Da qui si costruisce l'orchestratore.")
