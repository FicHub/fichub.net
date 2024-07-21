
default: beta

beta: dirs static/js/_.js static/style/_.css
	rsync -aPvc --delete static/ /var/www/b.fichub.net/

prod: dirs static/js/_.js static/style/_.css
	rsync -aPvc --delete static/ /var/www/fichub.net/

dirs:
	mkdir -p static/js static/style

# dev
static/js/_.js: frontend/_.ts | dirs
	tsc --out $@ $<
static/style/_.css: frontend/_.sass | dirs
	sassc -t compressed $< > $@

test:
	./venv/bin/python -m pytest --cov=. --cov-report html --cov-branch -vv tests/ -m "not slow"

test-slow:
	./venv/bin/python -m pytest --cov=. --cov-report html --cov-branch -vv tests/

test-slow-only:
	./venv/bin/python -m pytest --cov=. --cov-report html --cov-branch -vv tests/ -m "slow"

type:
	./venv/bin/mypy .

format:
	./venv/bin/ruff format

lint:
	./venv/bin/ruff check

lint-fix:
	./venv/bin/ruff check --fix

check: format type lint-fix test

check-slow: format type lint-fix test-slow

.PHONY: clean dirs beta prod test test-slow test-slow-only type format lint lint-fix check check-slow

clean:
	rm -f static/js/_.js static/style/_.css

