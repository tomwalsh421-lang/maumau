You are the Modeling Agent.

Task: create baseline upset-probability model.
- Target: underdog win (moneyline underdog)
- Features (MVP): implied_prob_underdog, adj_o_diff, adj_d_diff, tempo_diff, sos_diff, neutral_site flag (if available else omit)
- Model: logistic regression
- Evaluation: train/val split by date (no leakage)
- Output: predicted probability for each game + edge = p_model - p_implied

CLI:
- cbb train --season 2026
- cbb score --date YYYY-MM-DD

Return: code, saved model artifact path, and how to re-run.
