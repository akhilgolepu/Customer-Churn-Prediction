# External Datasets

Place additional churn datasets in this folder and register them in `data/dataset_catalog.json`.

Suggested naming:

- bank-customer-churn.csv
- saas-subscription-churn.csv

After adding files, run:

```bash
python model/training/build_dataset_report.py
```

This refreshes `data/dataset_report.md` and verifies which datasets are active and available.
