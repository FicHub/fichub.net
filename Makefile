
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

.PHONY: requirements.txt
requirements.txt: pyproject.toml
	uv pip compile pyproject.toml -o requirements.txt

venv:
	uv pip sync pyproject.toml

test:
	uv run python -m pytest --cov=. --cov-report html --cov-branch -vv tests/ -m "not slow"

test-slow:
	uv run python -m pytest --cov=. --cov-report html --cov-branch -vv tests/

test-slow-only:
	uv run python -m pytest --cov=. --cov-report html --cov-branch -vv tests/ -m "slow"

type:
	uv run mypy src/ tests/

format:
	uv run ruff format

lint:
	uv run ruff check

lint-fix:
	uv run ruff check --fix

check: format type lint-fix test

check-slow: format type lint-fix test-slow

tox:
	uv run tox

tox-lint:
	uv run tox run -e type
	uv run tox run -e lint

build: tox
	uv run hatch build

.PHONY: clean dirs beta prod test test-slow test-slow-only type format lint lint-fix check check-slow venv tox tox-lint build

clean:
	rm -f static/js/_.js static/style/_.css

