# Thin wrapper; the logic lives in tasks.py so it also runs on Windows (python tasks.py <target>).
PY ?= python

.PHONY: setup test lint train demo loadtest up down

setup:
	$(PY) tasks.py setup --frontend
test:
	$(PY) tasks.py test
lint:
	$(PY) tasks.py lint
train:
	$(PY) tasks.py train
demo:
	$(PY) tasks.py demo
loadtest:
	$(PY) tasks.py loadtest --workers 2
up:
	$(PY) tasks.py up
down:
	$(PY) tasks.py down
