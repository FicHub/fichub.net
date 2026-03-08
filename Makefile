default: dirs maybe-static-docker-image frontend

beta: dirs static/js/_.js static/style/_.css
	rsync -aPvc --delete static/ /var/www/b.fichub.net/

prod: dirs static/js/_.js static/style/_.css
	rsync -aPvc --delete static/ /var/www/fichub.net/

dirs:
	@mkdir -p static/js static/style

frontend: static/js/_.js static/style/_.css

# dev
static/js/_.js: frontend/_.ts | dirs maybe-static-docker-image
	docker run -v ./$<:/app/_.ts:ro --rm fichub/static-build:0.0.1 tsc _.ts --outFile /dev/stdout > $@
static/style/_.css: frontend/_.sass | dirs maybe-static-docker-image
	docker run -v ./$<:/app/_.sass:ro --rm -i fichub/static-build:0.0.1 sassc -t compressed _.sass > $@

.PHONY: static-docker-image
static-docker-image:
	docker build -f dev-docker-compose/Dockerfile.static -t fichub/static-build:0.0.1 .

.PHONY: maybe-static-docker-image
maybe-static-docker-image:
	@if ! docker image inspect fichub/static-build:0.0.1 2>&1 >/dev/null; then\
		make static-docker-image;\
	fi

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

