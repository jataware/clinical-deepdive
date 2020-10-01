

# Install

Create a new `venv`

```
pip install -e .
```

# Run

```
clinical-deepdive
2020-10-01 17:18:34,920 - MainThread - root - INFO - main
2020-10-01 17:18:35,463 - MainThread - asyncio - DEBUG - Using selector: KqueueSelector
Searching reproduction number - 126 pages: 100%|███████████████████| 126/126 [00:31<00:00, 4.00it/s]
Searching incubation time - 39 pages: 100%|██████████████████████| 39.0/39.0 [00:11<00:00, 3.39it/s]
2020-10-01 17:19:20,523 - MainThread - clinical_deepdive.app - INFO - Completed in 45.6 seconds


head -n 1 output.txt | jq ""
```

# Getting Started

Setup a python 3.8+ virtual env

- https://github.com/pyenv/pyenv <br>
- https://github.com/pyenv/pyenv-virtualenv <br>


Install Dev Requirements

```
python -m pip install -r requirements-dev.txt
```


## Tox

Reformat Code (runs isort, black)

```
tox -e format
```


Test + Lint

```
tox
```


Package
```
tox -e package
```

