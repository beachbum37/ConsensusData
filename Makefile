.PHONY: check validate test build brief queue post scan clean

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

# make queue WEEKS=6 PER=2
queue:
	@$(PY) scripts/linkedin.py queue --weeks $(or $(WEEKS),4) --per-week $(or $(PER),1)

# make post ID=li-onboard-01
post:
	@$(PY) scripts/linkedin.py post $(ID) --bare

scan:
	@$(PY) scripts/linkedin.py scan --format md

clean:
	rm -f docs/index.html docs/artifact.html
