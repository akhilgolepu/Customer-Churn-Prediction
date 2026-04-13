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

If you are using PowerShell on Windows, run the commands in a PowerShell session from the repo root.

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

### PowerShell

```powershell
$env:MLFLOW_TRACKING_URI = "https://dagshub.com/<owner>/<repo>.mlflow"
$env:DAGSHUB_USERNAME = "<your-username>"
$env:DAGSHUB_TOKEN = "<your-token>"
```

### Command Prompt

```bat
set MLFLOW_TRACKING_URI=https://dagshub.com/<owner>/<repo>.mlflow
set DAGSHUB_USERNAME=<your-username>
set DAGSHUB_TOKEN=<your-token>
```

### Bash

```bash
export MLFLOW_TRACKING_URI=https://dagshub.com/<owner>/<repo>.mlflow
export DAGSHUB_USERNAME=<your-username>
export DAGSHUB_TOKEN=<your-token>
```

## 6. Recommended secret locations

Store these outside the repo:

- `DAGSHUB_TOKEN`
- `MLFLOW_TRACKING_URI`
- DVC remote credentials

## 7. What to do next in this repo

- Add a training stage for retraining once the model training entrypoint is split out of the notebook.
- Add a remote model registry target if you want to store pipeline bundles outside the repo.
- Wire the retraining service to log runs to the DAGsHub MLflow endpoint.

## 8. Minimal end-to-end flow for this repository

1. Create or open the DAGsHub repository for this project.
2. Copy the DVC remote URL and the MLflow tracking URI from DAGsHub.
3. In PowerShell, set the MLflow environment variables shown above.
4. Run `dvc remote add -d dagshub <your-dvc-remote-url>`.
5. Run `dvc push` to upload the dataset cache to the remote.
6. Run `dvc repro dataset_report` to regenerate the dataset report.
7. Train or retrain using `MLflowExperimentTracker(tracking_uri=...)` or the `MLFLOW_TRACKING_URI` env var.
8. Log the run, model artifact, and validation report to DAGsHub-backed MLflow.
