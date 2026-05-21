SPEC := ./openapi.yaml
SERVER_GEN := ../server/app/api/generated
WEB_CLIENT_GEN := ../web-client/src/api.ts

.PHONY: generate lint check clean help

help:
	@echo "Targets:"
	@echo "  generate  - Regenerate backend stubs and frontend types from $(SPEC)"
	@echo "  lint      - Lint $(SPEC) with Redocly"
	@echo "  check     - CI: regenerate and fail if anything drifted"
	@echo "  clean     - Remove generated artefacts (forces full regeneration)"

generate:
	./scripts/codegen.sh

lint:
	npx --yes --prefix ./scripts @redocly/cli lint $(SPEC)

check: generate
	@git diff --exit-code -- $(SERVER_GEN) $(WEB_CLIENT_GEN) \
	  || (echo ""; \
	      echo "ERROR: generated code drifted from $(SPEC)."; \
	      echo "       Run 'make -C api generate' and commit the result."; \
	      exit 1)

clean:
	rm -rf $(SERVER_GEN)
	rm -f $(WEB_CLIENT_GEN)
