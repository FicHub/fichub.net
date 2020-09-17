
default: dirs static/js/_.js static/style/_.css

dirs:
	mkdir -p static/js static/style

# dev
static/js/_.js: frontend/_.ts | dirs
	tsc --out $@ $<
static/style/_.css: frontend/_.sass | dirs
	sassc -t nested $< > $@

.PHONY: clean dirs

clean:
	rm -f static/js/_.js static/style/_.css

