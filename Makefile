.PHONY: check validate test build brief clean

# Everything is stdlib Python 3 - no venv, no install step.
PY := python3

check: validate test build

validate:
	$(PY) scripts/validate.py

test:
	$(PY) -m unittest discover -s scripts -t scripts

build:
	$(PY) scripts/build.py

# make brief INDUSTRY=hospitality
brief:
	@$(PY) scripts/query.py brief $(or $(INDUSTRY),technology)

clean:
	rm -f docs/index.html docs/artifact.html
