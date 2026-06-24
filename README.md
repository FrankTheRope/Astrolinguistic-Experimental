[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20825952.svg)](https://doi.org/10.5281/zenodo.20825952)

# Experimental Astrolinguistics — Level A: code, results, and logs

Replication archive for the anti-kangaroo protocol (Level A): grounding unknown
word meanings through ostension, minimal pairs, and pre-registered predictive
probes in a synthetic micro-world. This archive accompanies the paper and is the
frozen snapshot referenced by its results.

Authors: Cordella & Cappelli.

---

## Repository layout

```
code/        the pipeline (7 scripts)
results/     per-run metrics as CSV (the numbers behind the tables)
logs/
  campagna/  full JSONL interaction logs, Level A campaign (per seed/condition)
  rumore/    JSONL logs of the noisy-informant robustness study (4 noise levels)
  proposer/  raw LLM proposer responses (version v3), Haiku and Sonnet
  trappole/  JSONL log of the injected-trap study
```

## Code

| File | Role |
|------|------|
| `orchestratore.py` | Core engine: micro-world, ground-truth lexicons, speakers, anchor state machine. **All other scripts import from this.** |
| `campagna.py` | Multi-seed campaign runner; emits the `risultati_campagna_*.csv` files. |
| `condizioni.py` | Hard-word ablation (NUR, GUMO): arms base / esteso / llm / stub. The proposer ladder. |
| `trappole.py` | Injected kangaroo-trap study; compares learning protocols against the same trap. |
| `rumore.py` | Noisy-informant robustness study (per-word symmetric flip noise). |
| `analisi_log.py` | Utility: checks speaker execution fidelity against the true L2 rule from a log. |
| `hello_world.py` | Minimal two-LLM demo (one scene, two private lexicons). Standalone; the seed of the orchestrator. |

Only `anthropic` and `openai` are external dependencies, and only for the
API-based (`--llm`) conditions. SIM mode, traps, and the noise study use the
Python standard library only.

## Reproducing the results

All commands are run from `code/`. SIM-mode runs are free and deterministic.

```bash
# --- Level A campaign (Table 2, Figure 2): SIM, 4 arms, 50 seeds ---
python campagna.py --sim --semi 50                  # random baseline
python campagna.py --sim --attiva --semi 50         # active probing
python campagna.py --sim --attiva --round2 --semi 50 # active + recovery round

# --- Live LLM campaign (10 seeds, GPT-4o-mini as L2) ---
export ANTHROPIC_API_KEY="..."   # required for --llm
export OPENAI_API_KEY="..."
python campagna.py --llm --attiva --round2 --semi 10

# --- Hard words / proposer ladder (Table 4, Figure 6): 30 seeds ---
python condizioni.py --braccio base   --semi 30     # no proposer (expected 0%)
python condizioni.py --braccio esteso --semi 30     # hand-coded oracle space (ceiling)
python condizioni.py --braccio llm    --semi 30     # base space + LLM proposer (needs API keys)
python condizioni.py --braccio stub   --semi 30     # fixed fake proposer (plumbing check, no API)

# --- Injected traps (Table 3, Figure 4): 50 seeds per trap ---
python trappole.py                                   # trap zumu_forma
python trappole.py --trappola tin_moto               # second trap

# --- Noisy informant (Table 5, Figure 7): active + R2, 50 seeds per level ---
python rumore.py --semi 50                            # sweeps p = 0, 2, 5, 10%
```

## Instrument versioning

Prompt language, scene format, and DSL vocabulary together define an *instrument
version*. Changing any of them constitutes a new version and invalidates
cross-condition comparison unless re-run. The proposer results archived here are
**v3**; raw responses carry an explicit `versione` field. The prompts in this
snapshot are in Italian; the hard-coded models are `claude-haiku-4-5` (L1 /
proposer) and `gpt-4o-mini` (L2 informant), both at temperature 0.

## Provenance notes (read before citing numbers)

- The `results/` CSVs use the current schema (with `condizione` / `rec_r2`
  columns). Older 9-column CSVs were excluded as exact subsets of these.
- The `condizioni` CSVs cover all four arms of Table 4 at 30 seeds: `base`
  (no proposer), `esteso` (hand-coded oracle), and the two `llm` arms (Haiku,
  Sonnet). The base/oracle figures were regenerated from the frozen
  `condizioni.py` and confirmed against the paper: base leaves NUR and GUMO
  unresolved 30/30 with zero kangaroos (0%); oracle resolves both 30/30 (100%).
  The `stub` arm is a plumbing check only and is reproduced on demand
  (`python condizioni.py --braccio stub --semi 30`); it carries no claim and is
  not archived.
- Proposer raw logs are v3 only, matching the v3 results in Table 4. The v1/v2
  raw responses are not retained (overwritten by the v3 runs). This is by design:
  the v1→v2→v3 progression (Sonnet 30%→0%→90% on NUR) is reported as a
  methodological *instrument lesson*, narrated rather than tabulated, and the
  data-availability statement lists proposer raw logs as available from the
  authors. No v1/v2 artifact is therefore required for the published tables.

## Citation

If you use this code or data, please cite the paper and this archive.

**Paper:** Cordella & Cappelli, *Experimental Astrolinguistics: [full title]*,
[year]. arXiv:[arXiv ID].

**Software/data archive:** Cordella & Cappelli, *Anti-kangaroo protocol —
Level A: replication archive*, Zenodo, 2026.
DOI: [10.5281/zenodo.20825952](https://doi.org/10.5281/zenodo.20825952)

The DOI above is the Zenodo "concept" DOI, which always resolves to the latest
version. Replace the arXiv ID placeholder above once the preprint is posted.

Replace the bracketed placeholders once the arXiv ID and the Zenodo DOI are
assigned. The Zenodo "concept DOI" (which always resolves to the latest version)
is the preferred one to cite.

## License

Code (`code/`) is released under the MIT License (see `LICENSE`).
Results and logs (`results/`, `logs/`) are released under CC-BY-4.0.

## Reproducibility note

SIM-mode results are bit-reproducible from the seeds with the standard library
alone. The LLM-arm results depend on models served behind API names that may
change over time; for those arms the archived raw logs are the ground truth, as
described in the paper's instrument-versioning discussion.
