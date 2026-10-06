# KubeClassify --- document build
# Requires: pandoc (~/.local/bin), xelatex, npx (mermaid-cli is fetched on demand).

SHELL    := /bin/bash
PANDOC   ?= $(shell command -v pandoc || echo $(HOME)/.local/bin/pandoc)
MMDC     := npx -y @mermaid-js/mermaid-cli@11
DIAG     := docs/diagrams
OUT      := $(DIAG)/out
CONFIG   := $(DIAG)/mermaid-config.json
SRC      := $(sort $(wildcard docs/milestone1/*.md))
META     := docs/report/metadata.yaml
PDF      := docs/report/Milestone1-Report.pdf
DIAGRAMS := $(OUT)/dataflow.pdf $(OUT)/sidecar.pdf $(OUT)/k8s-topology.pdf

.PHONY: all report diagrams check clean

all: report

diagrams: $(DIAGRAMS)

$(OUT)/%.pdf: $(DIAG)/%.mmd $(CONFIG)
	@mkdir -p $(OUT)
	$(MMDC) -c $(CONFIG) -b white -f -i $< -o $@

report: $(PDF)

$(PDF): $(SRC) $(META) $(DIAGRAMS)
	$(PANDOC) $(META) $(SRC) --template=docs/report/template.tex --no-highlight --pdf-engine=xelatex -o $@
	@echo "built $@"

# Verify the submission meets the brief's formatting requirements.
check: $(PDF)
	@pdfinfo $(PDF) | grep -E '^(Pages|Page size)'
	@echo "--- fonts ---"
	@pdffonts $(PDF) | head -8

clean:
	rm -f $(PDF) $(OUT)/*.pdf
