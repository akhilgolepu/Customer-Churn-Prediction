# DAGsHub + DVC Setup

This repository already includes:

- `data/Telco-Customer-Churn.csv.dvc` for the core dataset
- `dvc.yaml` for the dataset report pipeline
- MLflow tracker code that can point to a remote DAGsHub MLflow server

## 1. Install tooling

Install the CLI tools in your local development environment:

```bash
pip install dvc dagshub mlflow
```

If you want DVC to talk to a remote storage backend, install the matching extra for your storage provider too.

## 2. Initialize a DVC remote

Pick one remote type and set it as the default remote.

### Example: DAGsHub remote

```bash
dvc remote add -d dagshub <your-dagshub-dvc-remote-url>
```

Use the DVC remote URL provided by DAGsHub for your repository. If you are using object storage underneath, configure that backend exactly as DAGsHub documents for your account and plan.

## 3. Push tracked data and pipeline metadata

After the remote is configured:

```bash
dvc push
git add dvc.yaml data/Telco-Customer-Churn.csv.dvc
git commit -m "Add DVC pipeline and remote-ready data tracking"
git push
```

## 4. Reproduce the DVC stage

```bash
dvc repro dataset_report
```

This regenerates `data/dataset_report.md` from the tracked dataset and catalog.

## 5. Configure MLflow for DAGsHub

For remote experiment tracking, set these environment variables before training or retraining:

```bash
set MLFLOW_TRACKING_URI=https://dagshub.com/<owner>/<repo>.mlflow
set DAGSHUB_USERNAME=<your-username>
set DAGSHUB_TOKEN=<your-token>
```

On macOS/Linux use `export` instead of `set`.

## 6. Recommended secret locations

Store these outside the repo:

- `DAGSHUB_TOKEN`
- `MLFLOW_TRACKING_URI`
- DVC remote credentials

## 7. What to do next in this repo

- Add a training stage for retraining once the model training entrypoint is split out of the notebook.
- Add a remote model registry target if you want to store pipeline bundles outside the repo.
- Wire the retraining service to log runs to the DAGsHub MLflow endpoint.
