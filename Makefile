
default: beta

beta: dirs static/js/_.js static/style/_.css
	rsync -aPvc --delete static/ /var/www/b.fic.pw/

prod: dirs static/js/_.js static/style/_.css
	rsync -aPvc --delete static/ /var/www/fic.pw/

dirs:
	mkdir -p static/js static/style

# dev
static/js/_.js: frontend/_.ts | dirs
	tsc --out $@ $<
static/style/_.css: frontend/_.sass | dirs
	sassc -t compressed $< > $@

.PHONY: clean dirs beta prod

clean:
	rm -f static/js/_.js static/style/_.css

