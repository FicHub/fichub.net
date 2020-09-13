
default: static/js/_.js static/style/_.css

# dev
static/js/_.js: frontend/_.ts
	tsc --out $@ $<
static/style/_.css: frontend/_.sass
	sassc -t nested $< > $@

.PHONY: clean

clean:
	rm -f static/js/_.js static/style/_.css

