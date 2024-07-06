
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
	./venv/bin/python -m pytest --cov=. --cov-report html --cov-branch -vv tests/

.PHONY: clean dirs beta prod test

clean:
	rm -f static/js/_.js static/style/_.css

