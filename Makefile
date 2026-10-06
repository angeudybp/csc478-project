# KubeClassify --- document build
# Requires: pandoc (~/.local/bin), xelatex, and Node/npm.
#
# The diagram renderer is pinned by package-lock.json and installed locally with
# `npm ci`, which verifies integrity hashes. The build never fetches an
# unreviewed package version at run time.

SHELL    := /bin/bash
PANDOC   ?= $(shell command -v pandoc || echo $(HOME)/.local/bin/pandoc)
MMDC     := ./node_modules/.bin/mmdc
DIAG     := docs/diagrams
OUT      := $(DIAG)/out
CONFIG   := $(DIAG)/mermaid-config.json
SRC      := $(sort $(wildcard docs/milestone1/*.md))
META     := docs/report/metadata.yaml
TEMPLATE := docs/report/template.tex
PDF      := docs/report/Milestone1-Report.pdf
DIAGRAMS := $(OUT)/dataflow.pdf $(OUT)/sidecar.pdf $(OUT)/k8s-topology.pdf

.PHONY: all report diagrams check clean distclean

all: report

# Exact, integrity-checked install from the lockfile.
node_modules: package-lock.json
	npm ci --no-audit --no-fund
	@touch node_modules

diagrams: $(DIAGRAMS)

$(OUT)/%.pdf: $(DIAG)/%.mmd $(CONFIG) | node_modules
	@mkdir -p $(OUT)
	$(MMDC) -c $(CONFIG) -b white -f -i $< -o $@

report: $(PDF)

$(PDF): $(SRC) $(META) $(TEMPLATE) $(DIAGRAMS)
	$(PANDOC) $(META) $(SRC) --template=$(TEMPLATE) --no-highlight --pdf-engine=xelatex -o $@
	@echo "built $@"

# Verify the submission meets the brief's formatting requirements.
check: $(PDF)
	@pdfinfo $(PDF) | grep -E '^(Pages|Page size)'
	@echo "--- fonts ---"
	@pdffonts $(PDF) | head -8

clean:
	rm -f $(PDF) $(OUT)/*.pdf

distclean: clean
	rm -rf node_modules
