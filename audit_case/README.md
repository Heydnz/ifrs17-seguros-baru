# Independent review case: term life under IFRS 17

This folder turns the portfolio into an **auditor's view**: the entity hands over its files, and the reviewer recomputes every figure independently and compares it with what the entity reports (ISA 540 (Revised), par. 18).

* `entity_package.py` plays the audited entity. It writes the files the entity delivers to `data/audit_case/` (policy census, claims register, claims reported after the closing, assumptions document and management's closing package). **Management's package contains deliberate, seeded errors.**
* `notebooks/08_revision_independiente_vida_temporal.ipynb` (Spanish) is the review. It never imports the entity's code; it only reads the files. A rendered copy is in `docs/revision_vida_temporal.html`.
* `excel/Revision_VT_poliza_modelo.xlsx` is the single-policy twin in Excel, with live formulas: projection, shocks, cost-of-capital risk adjustment with a rate sensitivity, CSM and its amortisation. Its `Conciliacion` sheet matches every figure against the notebook. `build_excel.py` rebuilds it, taking the reference values from the notebook's own functions.

What the review covers, with the IFRS 17 paragraph for each step: data integrity and completeness tests; actual-to-expected mortality with limited-fluctuation credibility; policy-by-policy cash-flow projection (shown first for a single policy, as in a spreadsheet); PV of fulfilment cash flows; cost-of-capital risk adjustment with mortality, lapse and expense shocks; grouping and onerous test; CSM at initial recognition; coverage units and CSM amortisation; LIC with case reserves, Chain Ladder and Bornhuetter-Ferguson IBNR, claim handling costs, discounting and an ODP bootstrap risk adjustment, cross-checked with the open-source `chainladder` package; subsequent-events test; and a summary of findings.

```bash
python audit_case/entity_package.py        # regenerate the entity's files (fixed seeds)
python audit_case/build_excel.py           # rebuild the Excel twin (then recalculate it in Excel or LibreOffice)
jupyter nbconvert --execute --to notebook --inplace notebooks/08_revision_independiente_vida_temporal.ipynb
```

Extra dependencies for this notebook: `matplotlib`, `scipy`, `chainladder`.

> Personal project for demonstration purposes. Seguros Barú is fictional and all data are synthetic, calibrated only with public sources (SOA 1980 CSO tables, US Treasury HQM curves). Nothing here is an audit opinion or represents the methodology, tools or views of any employer or client.
