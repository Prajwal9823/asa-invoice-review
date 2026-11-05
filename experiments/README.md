# Mosaic rule-engine experiment

Run `python experiments/evaluate_scenarios.py` from the project root. It extracts each prepared PDF, evaluates its labeled route, and saves results to a temporary SQLite file. The cumulative billing scenario is replayed after its first approved invoice. The script reports a confusion matrix and per-route precision, recall, and F1.

The labels are deliberately authored acceptance cases, not a sampled production population. A perfect score means the rules behave as designed on these synthetic inputs; it does not estimate performance on unseen suppliers, scan quality, jurisdictions, or real company invoices. The engine is deterministic and has no trained ML model, so model generalization claims would be inappropriate.
