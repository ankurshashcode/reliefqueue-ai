.PHONY: help test validate-fixtures run-demo-local run-demo-batch-100 run-demo-batch-500 run-demo-batch-5000 batch-report export-report export-private export-public validate-redaction ai-smoke ai-endpoint-smoke bad-ai-endpoint-smoke no-secrets privacy-check security-check audit-smoke amd-benchmark amd-report operator operator-search operator-scope operator-catalog-check docs-check phase01-host-preflight phase01-host-setup phase01-live-proof phase01-live-clean operations-smoke backup-demo-state restore-demo-state degraded-mode-smoke reviewer-pack pilot-feedback-template pilot-smoke write-hardening-status integrations-status integration-smoke export-postgis-seed queue-smoke field-form-export messaging-exchange-smoke masked-contact-smoke observability-smoke live-integrations-status container-runtime-readiness postgis-live-init postgis-live-import-demo postgis-live-query postgis-live-smoke postgis-live-backup postgis-live-restore-smoke queue-live-init queue-live-enqueue-demo queue-live-worker-once queue-live-smoke queue-live-dlq-report queue-live-replay-dlq live-stateful-mutation-drill live-stateful-mutation-drill-verbose live-stateful-mutation-drill-profile live-stateful-mutation-drill-profiles live-logistics-asset-drill live-logistics-asset-drill-verbose live-logistics-asset-drill-profile live-logistics-asset-profiles vllm-live-status vllm-live-smoke amd-live-benchmark-500 amd-live-benchmark-5000 amd-live-report live-health live-metrics-export live-audit-report live-failure-report observability-live-smoke field-form-xlsform-export field-form-odk-package field-form-import-sample odk-live-status odk-live-smoke rapidpro-flow-export rapidpro-webhook-smoke rapidpro-live-status rapidpro-live-smoke channel-webhook-smoke whatsapp-webhook-smoke sms-webhook-smoke channel-normalize-smoke channel-live-status masked-contact-live-status masked-contact-create-dry-run masked-contact-provider-smoke masked-contact-cancel-dry-run live-pilot-drill live-pilot-reviewer-pack live-pilot-status live-pilot-clean live-volunteer-surge-drill live-volunteer-surge-drill-profile live-volunteer-surge-drill-verbose live-volunteer-surge-profiles live-stack-up live-stack-status live-stack-smoke live-stack-down product-api-smoke product-action-map-check command-center-smoke field-app-smoke product-live-stack-smoke command-center-click-smoke field-app-click-smoke local-coordinator-click-smoke product-complete-smoke dashboard dashboard-dev dashboard-build dashboard-smoke field-smoke product-smoke visual-port-smoke messaging-channel-smoke messaging-channel-demo case1-local clean clean-reports dashboard-public-data public-ship-check

PYTHON ?= python3
NPM ?= npm
DASHBOARD_INSTALL_STAMP := dashboard/node_modules/.reliefqueue-dashboard-install
DASHBOARD_DATA_SOURCE ?= latest

help:
	@echo "ReliefQueue AI"
	@echo "Before changing code or docs: make change-guide"
	@echo "Available commands:"
	@echo "  make test"
	@echo "  make validate-fixtures"
	@echo "  make run-demo-local"
	@echo "  make run-demo-batch-100"
	@echo "  make run-demo-batch-500"
	@echo "  make run-demo-batch-5000"
	@echo "  make batch-report"
	@echo "  make export-report"
	@echo "  make export-private"
	@echo "  make export-public"
	@echo "  make validate-redaction"
	@echo "  make ai-smoke"
	@echo "  make ai-endpoint-smoke"
	@echo "  make bad-ai-endpoint-smoke"
	@echo "  make no-secrets"
	@echo "  make privacy-check"
	@echo "  make security-check"
	@echo "  make audit-smoke"
	@echo "  make amd-benchmark"
	@echo "  make amd-report"
	@echo "  make operator"
	@echo "  make operator-search QUERY=\"test live integration\""
	@echo "  make operator-scope ACTION=phase01_live_stack"
	@echo "  make operator-catalog-check"
	@echo "  make docs-check"
	@echo "  make phase01-host-preflight"
	@echo "  make phase01-host-setup"
	@echo "  make phase01-live-proof"
	@echo "  make phase01-live-clean"
	@echo "  make operations-smoke"
	@echo "  make backup-demo-state"
	@echo "  make restore-demo-state"
	@echo "  make degraded-mode-smoke"
	@echo "  make reviewer-pack"
	@echo "  make pilot-feedback-template"
	@echo "  make pilot-smoke"
	@echo "  make integrations-status"
	@echo "  make integration-smoke"
	@echo "  make export-postgis-seed"
	@echo "  make queue-smoke"
	@echo "  make field-form-export"
	@echo "  make messaging-exchange-smoke"
	@echo "  make masked-contact-smoke"
	@echo "  make observability-smoke"
	@echo "  make live-integrations-status"
	@echo "  make container-runtime-readiness"
	@echo "  make live-stack-up"
	@echo "  make live-stack-status"
	@echo "  make live-stack-smoke"
	@echo "  make live-stack-down"
	@echo "  make product-api-smoke"
	@echo "  make product-action-map-check"
	@echo "  make command-center-smoke"
	@echo "  make field-app-smoke"
	@echo "  make product-live-stack-smoke"
	@echo "  make live-stateful-mutation-drill"
	@echo "  make live-stateful-mutation-drill-verbose"
	@echo "  make live-stateful-mutation-drill-profile PROFILE=urban_flood"
	@echo "  make live-stateful-mutation-drill-profiles"
	@echo "  make live-logistics-asset-drill"
	@echo "  make live-logistics-asset-drill-profile PROFILE=urban_flood"
	@echo "  make live-logistics-asset-profiles"
	@echo "  make live-volunteer-surge-drill-profile PROFILE=urban_flood VERBOSE_FLAGS=-v"
	@echo "  make live-volunteer-surge-drill-profile PROFILE=urban_flood VERBOSE_FLAGS=-vv"
	@echo "  make live-volunteer-surge-profiles"
	@echo "  verbosity guide: no flag=routine, -v=quick, -vv=demo, -vvv=debug"
	@echo "  make dashboard"
	@echo "  make dashboard DASHBOARD_DATA_SOURCE=batch-500"
	@echo "  make dashboard-public-data"
	@echo "  make dashboard-dev"
	@echo "  make dashboard-build"
	@echo "  make dashboard-smoke"
	@echo "  make field-smoke"
	@echo "  make product-smoke"
	@echo "  make visual-port-smoke"
	@echo "  make messaging-channel-smoke"
	@echo "  make messaging-channel-demo"
	@echo "  make public-ship-check"
	@echo "  make case1-local"
	@echo "  make clean-reports"
	@echo "  make clean"

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests

validate-fixtures:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli validate-fixtures

run-demo-local:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli run-demo-local

run-demo-batch-100:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli run-demo-batch --count 100 --seed 42

run-demo-batch-500:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli run-demo-batch --count 500 --seed 42

run-demo-batch-5000:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli run-demo-batch --count 5000 --seed 42

batch-report:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli batch-report

export-report:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli export-report

export-private:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli export-private

export-public:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli export-public

validate-redaction:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli validate-redaction

ai-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli ai-smoke

ai-endpoint-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli ai-endpoint-smoke

bad-ai-endpoint-smoke:
	@if AI_MODE=openai_compatible OPENAI_COMPAT_BASE_URL=http://127.0.0.1:9/v1 OPENAI_COMPAT_API_KEY=test-key OPENAI_COMPAT_MODEL=test-model AI_TIMEOUT_SECONDS=0.05 AI_MAX_RETRIES=0 PYTHONPATH=src $(PYTHON) -m reliefqueue.cli ai-endpoint-smoke; then \
		echo "Bad endpoint smoke FAIL: endpoint unexpectedly passed"; exit 1; \
	else \
		echo "Bad endpoint smoke PASS: bad endpoint failed clearly"; \
	fi

no-secrets:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli no-secrets

privacy-check:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli privacy-check

security-check:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli security-check

audit-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli audit-smoke

amd-benchmark:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli amd-benchmark

amd-report:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli amd-report

operator:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli operator

operator-search:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli operator-search --query "$(QUERY)"

operator-scope:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli operator-scope --action "$(ACTION)"

operator-catalog-check:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli operator-catalog-check

docs-check:
	$(PYTHON) scripts/docs_check.py

phase01-host-preflight:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli phase01-host-preflight

phase01-host-setup:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli phase01-host-setup

phase01-live-proof:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli phase01-live-proof

phase01-live-clean:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli phase01-live-clean

operations-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli operations-smoke

backup-demo-state:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli backup-demo-state

restore-demo-state:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli restore-demo-state

degraded-mode-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli degraded-mode-smoke

reviewer-pack:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli reviewer-pack

pilot-feedback-template:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli pilot-feedback-template

pilot-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli pilot-smoke

write-hardening-status:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli write-hardening-status

integrations-status:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli integrations-status

integration-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli integration-smoke

export-postgis-seed:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli export-postgis-seed

queue-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli queue-smoke

field-form-export:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli field-form-export

messaging-exchange-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli messaging-exchange-smoke

masked-contact-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli masked-contact-smoke

observability-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli observability-smoke

live-integrations-status:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli live-integrations-status

container-runtime-readiness:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli container-runtime-readiness

postgis-live-init postgis-live-import-demo postgis-live-query postgis-live-smoke postgis-live-backup postgis-live-restore-smoke: container-runtime-readiness
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli $@

queue-live-init queue-live-enqueue-demo queue-live-worker-once queue-live-smoke queue-live-dlq-report queue-live-replay-dlq: container-runtime-readiness
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli $@

live-stateful-mutation-drill: container-runtime-readiness
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli $@ $(VERBOSE_FLAGS)

live-stateful-mutation-drill-verbose: container-runtime-readiness
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli live-stateful-mutation-drill -v

live-stateful-mutation-drill-profile: container-runtime-readiness
	@[ -n "$(PROFILE)" ] || (echo "Usage: make live-stateful-mutation-drill-profile PROFILE=urban_flood VERBOSE_FLAGS=-v"; echo "Run: make live-stateful-mutation-drill-profiles"; exit 2)
	RELIEFQUEUE_MUTATION_PROFILE="$(PROFILE)" PYTHONPATH=src $(PYTHON) -m reliefqueue.cli live-stateful-mutation-drill $(VERBOSE_FLAGS)

live-stateful-mutation-drill-profiles:
	PYTHONPATH=src $(PYTHON) -c "from reliefqueue.live_integrations import print_stateful_mutation_profiles; print_stateful_mutation_profiles()"

live-logistics-asset-drill: container-runtime-readiness
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli $@ $(VERBOSE_FLAGS)

live-logistics-asset-drill-verbose: container-runtime-readiness
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli live-logistics-asset-drill -v

live-logistics-asset-drill-profile: container-runtime-readiness
	@[ -n "$(PROFILE)" ] || (echo "Usage: make live-logistics-asset-drill-profile PROFILE=urban_flood VERBOSE_FLAGS=-v"; echo "Run: make live-logistics-asset-profiles"; exit 2)
	RELIEFQUEUE_LOGISTICS_PROFILE="$(PROFILE)" PYTHONPATH=src $(PYTHON) -m reliefqueue.cli live-logistics-asset-drill $(VERBOSE_FLAGS)

live-logistics-asset-profiles:
	PYTHONPATH=src $(PYTHON) -c "from reliefqueue.live_integrations import print_logistics_asset_profiles; print_logistics_asset_profiles()"

live-volunteer-surge-drill: container-runtime-readiness
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli live-volunteer-surge-drill $(VERBOSE_FLAGS)

live-volunteer-surge-drill-verbose: container-runtime-readiness
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli live-volunteer-surge-drill -v

live-volunteer-surge-drill-profile: container-runtime-readiness
	@[ -n "$(PROFILE)" ] || (echo "Usage: make live-volunteer-surge-drill-profile PROFILE=urban_flood VERBOSE_FLAGS=-v"; echo "Run: make live-volunteer-surge-profiles"; exit 2)
	RELIEFQUEUE_VOLUNTEER_PROFILE="$(PROFILE)" PYTHONPATH=src $(PYTHON) -m reliefqueue.cli live-volunteer-surge-drill $(VERBOSE_FLAGS)

live-volunteer-surge-profiles:
	PYTHONPATH=src $(PYTHON) -c "from reliefqueue.live_integrations import print_volunteer_surge_profiles; print_volunteer_surge_profiles()"
	@echo ""
	@echo "Verbosity guide for volunteer surge drills:"
	@echo "  no VERBOSE_FLAGS: routine validation / CI-friendly PASS or FAIL"
	@echo "  VERBOSE_FLAGS=-v: quick operator summary"
	@echo "  VERBOSE_FLAGS=-vv: demo/story evidence for reviewers"
	@echo "  VERBOSE_FLAGS=-vvv: debug/cleanup proof, including Redis final state"
	@echo "Example: make live-volunteer-surge-drill-profile PROFILE=urban_flood VERBOSE_FLAGS=-vv"

vllm-live-status vllm-live-smoke amd-live-benchmark-500 amd-live-benchmark-5000 amd-live-report:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli $@

live-health observability-live-smoke: container-runtime-readiness
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli $@

live-metrics-export live-audit-report live-failure-report:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli $@

field-form-xlsform-export field-form-odk-package field-form-import-sample odk-live-status odk-live-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli $@

rapidpro-flow-export rapidpro-webhook-smoke rapidpro-outbox-dry-run rapidpro-live-status rapidpro-live-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli $@

channel-webhook-smoke whatsapp-webhook-smoke sms-webhook-smoke channel-normalize-smoke channel-live-status:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli $@

masked-contact-live-status masked-contact-create-dry-run masked-contact-provider-smoke masked-contact-cancel-dry-run:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli $@

live-pilot-drill live-pilot-reviewer-pack live-pilot-status live-pilot-clean:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli $@

live-stack-up: container-runtime-readiness
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli live-stack up

live-stack-status: container-runtime-readiness
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli live-stack status

live-stack-smoke: container-runtime-readiness
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli live-stack smoke

live-stack-down: container-runtime-readiness
	PYTHONPATH=src $(PYTHON) -m reliefqueue.cli live-stack down

product-api-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.product_api smoke

product-action-map-check:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.product_api action-map-check

command-center-smoke: dashboard-build dashboard-smoke

field-app-smoke: field-smoke

product-live-stack-smoke:
	PYTHONPATH=src $(PYTHON) -m reliefqueue.product_api live-smoke

command-center-click-smoke: dashboard-build
	$(NPM) --prefix dashboard run command-center-click-smoke

field-app-click-smoke: dashboard-build
	$(NPM) --prefix dashboard run field-app-click-smoke

local-coordinator-click-smoke: dashboard-build
	$(NPM) --prefix dashboard run local-coordinator-click-smoke

product-complete-smoke: dashboard-build
	$(NPM) --prefix dashboard run product-complete-smoke

$(DASHBOARD_INSTALL_STAMP): dashboard/package.json dashboard/package-lock.json
	$(NPM) --prefix dashboard ci
	@touch $(DASHBOARD_INSTALL_STAMP)

dashboard-public-data: run-demo-local
	DASHBOARD_DATA_SOURCE=$(DASHBOARD_DATA_SOURCE) $(NPM) --prefix dashboard run prepare-public-data

dashboard: $(DASHBOARD_INSTALL_STAMP) dashboard-public-data
	@api_port=$$($(PYTHON) -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'); \
	app_port="$${DASHBOARD_PORT:-5173}"; \
	$(PYTHON) -c 'import socket,sys; s=socket.socket(); s.bind(("127.0.0.1", int(sys.argv[1]))); s.close()' "$$app_port" >/dev/null 2>&1 || app_port=$$($(PYTHON) -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'); \
	echo "ReliefQueue Command Center:       http://127.0.0.1:$$app_port/dashboard?source=$(DASHBOARD_DATA_SOURCE)"; \
	echo "ReliefQueue Field Coordinator:    http://127.0.0.1:$$app_port/field/my-cases?worker_id=worker-alpha-boat"; \
	echo "Internal classic dashboard:       http://127.0.0.1:$$app_port/internal/classic-dashboard?source=$(DASHBOARD_DATA_SOURCE)"; \
	echo "Product API facade:               http://127.0.0.1:$$api_port/api/product/command/overview"; \
	echo "Data source: $(DASHBOARD_DATA_SOURCE) (latest, batch-100, batch-500, batch-5000 when generated)"; \
	PYTHONPATH=src $(PYTHON) -m reliefqueue.product_api serve --host 127.0.0.1 --port "$$api_port" & \
	api_pid=$$!; \
	trap 'kill $$api_pid 2>/dev/null || true' EXIT INT TERM; \
	RELIEFQUEUE_PRODUCT_API_TARGET=http://127.0.0.1:$$api_port $(NPM) --prefix dashboard run dev -- --host 127.0.0.1 --port "$$app_port" --strictPort

dashboard-dev: dashboard

dashboard-build: $(DASHBOARD_INSTALL_STAMP) dashboard-public-data
	DASHBOARD_DATA_SOURCE=$(DASHBOARD_DATA_SOURCE) $(NPM) --prefix dashboard run build

dashboard-smoke: $(DASHBOARD_INSTALL_STAMP)
	$(NPM) --prefix dashboard run smoke

field-smoke: $(DASHBOARD_INSTALL_STAMP) dashboard-build
	$(NPM) --prefix dashboard run field-smoke

product-smoke: $(DASHBOARD_INSTALL_STAMP) dashboard-build
	$(NPM) --prefix dashboard run product-smoke

visual-port-smoke: $(DASHBOARD_INSTALL_STAMP) dashboard-build
	$(NPM) --prefix dashboard run visual-port-smoke

messaging-channel-smoke: $(DASHBOARD_INSTALL_STAMP) dashboard-build
	$(NPM) --prefix dashboard run messaging-channel-smoke

messaging-channel-demo: messaging-channel-smoke
	@echo "Messaging channel demo evidence: reports/latest/messaging-channel/messaging-channel-smoke.json"
	@echo "Portal panel: /dashboard"
	@echo "Field mobile route: /field/my-cases?worker_id=$(FIELD_WORKER_ID)"
public-ship-check:
	$(PYTHON) scripts/public_ship_check.py


case1-local: validate-fixtures run-demo-local dashboard-public-data dashboard-build dashboard-smoke field-smoke product-smoke
	@echo "Case 1 local PASS: backend reports, dashboard route, and field-worker route validated."

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage dashboard/dist dashboard/node_modules dashboard/public/reports dashboard/public/fixtures reports/latest/field reports/latest/evidence

clean-reports:
	rm -rf reports/latest reports/batch-100 reports/batch-500 reports/batch-5000
	@mkdir -p reports
	@touch reports/.gitkeep

# BEGIN LOCAL_AI_CONTEXT_TOOLKIT
.PHONY: local-ai-context local-ai-inspect local-ai-run-latest-small local-ai-run-latest-medium local-ai-run-latest-full local-ai-review local-ai-review-small local-ai-review-medium local-ai-review-full local-ai-knowledge-init local-ai-knowledge-inspect local-ai-knowledge-update
local-ai-context:
	python3 scripts/local_ai_context.py --task "$${TASK:-general-review}" --review-profile "$${AI_CONTEXT_REVIEW_PROFILE:-small}"

local-ai-inspect:
	python3 scripts/local_ai_context.py --inspect-latest --review-profile "$${AI_CONTEXT_REVIEW_PROFILE:-small}"

local-ai-run-latest-small:
	python3 scripts/local_ai_context.py --inspect-latest --review-profile small
	@echo "[INFO] Running Ollama against existing latest SMALL input only; no packet regeneration and no validation."
	cat var/ai-context/latest/ollama-review-input.small.md | ollama run "$${OLLAMA_MODEL:-qwen2.5-coder:14b}"

local-ai-run-latest-medium:
	python3 scripts/local_ai_context.py --inspect-latest --review-profile medium
	@echo "[INFO] Running Ollama against existing latest MEDIUM input only; no packet regeneration and no validation."
	cat var/ai-context/latest/ollama-review-input.medium.md | ollama run "$${OLLAMA_MODEL:-qwen2.5-coder:14b}"

local-ai-run-latest-full:
	python3 scripts/local_ai_context.py --inspect-latest --review-profile full
	@echo "[INFO] Running Ollama against existing latest FULL input only; no packet regeneration and no validation."
	cat var/ai-context/latest/ollama-review-input.full.md | ollama run "$${OLLAMA_MODEL:-qwen2.5-coder:14b}"

local-ai-review: local-ai-review-small

local-ai-review-small:
	AI_CONTEXT_REVIEW_PROFILE=small python3 scripts/local_ai_context.py --task "$${TASK:-general-review}" --review-profile small
	$(MAKE) local-ai-run-latest-small

local-ai-review-medium:
	AI_CONTEXT_REVIEW_PROFILE=medium python3 scripts/local_ai_context.py --task "$${TASK:-general-review}" --review-profile medium
	$(MAKE) local-ai-run-latest-medium

local-ai-review-full:
	AI_CONTEXT_REVIEW_PROFILE=full python3 scripts/local_ai_context.py --task "$${TASK:-general-review}" --review-profile full
	$(MAKE) local-ai-run-latest-full

local-ai-knowledge-init:
	python3 scripts/local_ai_context.py --okf-init

local-ai-knowledge-inspect:
	python3 scripts/local_ai_context.py --okf-inspect

local-ai-knowledge-update:
	python3 scripts/local_ai_context.py --okf-update --task "$${TASK:-general-review}" --topic "$${TOPIC:-$${TASK:-general-review}}"
# END LOCAL_AI_CONTEXT_TOOLKIT

# Phase 02-06: one connected command-center evidence drill.
PROFILE ?= urban_flood
VERBOSE_FLAGS ?=

.PHONY: live-command-center-drill
live-command-center-drill:
	@PYTHONPATH=src python3 -m reliefqueue.live_command_center_drill --profile "$(PROFILE)" $(VERBOSE_FLAGS)

# Phase 02-07: reviewer/demo pack export.
REFRESH_DRILL ?= 0
.PHONY: reviewer-demo-pack
reviewer-demo-pack:
	@PYTHONPATH=src REFRESH_DRILL=$(REFRESH_DRILL) python3 -m reliefqueue.reviewer_demo_pack --profile "$(PROFILE)" $(VERBOSE_FLAGS)

# Phase 02-08: lightweight dashboard wiring to latest reports.
REFRESH_PACK ?= 0
.PHONY: dashboard-latest-reports
dashboard-latest-reports:
	@PYTHONPATH=src REFRESH_PACK=$(REFRESH_PACK) python3 -m reliefqueue.latest_reports_dashboard --profile "$(PROFILE)" $(VERBOSE_FLAGS)
AI_MODE ?= mock
REFRESH_DASHBOARD ?= 0

# Phase 02-09: AMD/vLLM-ready coordinator assistant over latest evidence.
EVIDENCE_ASSISTANT_AI_MODE ?= fireworks
FIREWORKS_BASE_URL ?= https://api.fireworks.ai/inference/v1
FIREWORKS_MODEL ?= accounts/fireworks/models/llama-v3p1-8b-instruct

# Phase 02-09: Fireworks-backed coordinator assistant over latest evidence.
# Latest/demo runs default to Fireworks. Use evidence-assistant-mock for offline validation.
FIREWORKS_MODEL_FALLBACKS ?= accounts/fireworks/models/glm-5p2,accounts/fireworks/models/kimi-k2p6

# Phase 02-09: Fireworks-backed coordinator assistant over latest evidence.
# Latest/demo runs default to Fireworks. Use evidence-assistant-mock for offline validation.
.PHONY: evidence-assistant
evidence-assistant:
	@PYTHONPATH=src AI_MODE=$(EVIDENCE_ASSISTANT_AI_MODE) FIREWORKS_BASE_URL="$(FIREWORKS_BASE_URL)" FIREWORKS_MODEL="$(FIREWORKS_MODEL)" FIREWORKS_MODEL_FALLBACKS="$(FIREWORKS_MODEL_FALLBACKS)" REFRESH_DASHBOARD=$(REFRESH_DASHBOARD) python3 -m reliefqueue.evidence_assistant --profile "$(PROFILE)" $(VERBOSE_FLAGS)

.PHONY: evidence-assistant-mock
evidence-assistant-mock:
	@PYTHONPATH=src AI_MODE=mock REFRESH_DASHBOARD=$(REFRESH_DASHBOARD) python3 -m reliefqueue.evidence_assistant --profile "$(PROFILE)" $(VERBOSE_FLAGS)

# Operator discovery and local portal viewing helpers.
DASHBOARD_HOST ?= 127.0.0.1
DASHBOARD_PORT ?= 5173
FIELD_WORKER_ID ?= worker-alpha-boat

.PHONY: portal-urls view-dashboard view-command-center view-field view-field-mobile docs-index-check change-guide
portal-urls:
	DASHBOARD_HOST=$(DASHBOARD_HOST) DASHBOARD_PORT=$(DASHBOARD_PORT) FIELD_WORKER_ID=$(FIELD_WORKER_ID) python3 scripts/portal_urls.py

view-dashboard:
	DASHBOARD_DATA_SOURCE=$${DASHBOARD_DATA_SOURCE:-latest} npm --prefix dashboard run prepare-public-data
	DASHBOARD_HOST=$(DASHBOARD_HOST) DASHBOARD_PORT=$(DASHBOARD_PORT) FIELD_WORKER_ID=$(FIELD_WORKER_ID) RELIEFQUEUE_PREFERRED_PORTAL=dashboard python3 scripts/portal_urls.py
	DASHBOARD_DATA_SOURCE=$${DASHBOARD_DATA_SOURCE:-latest} npm --prefix dashboard run dev -- --host $(DASHBOARD_HOST) --port $(DASHBOARD_PORT)

view-command-center: view-dashboard

view-field:
	DASHBOARD_DATA_SOURCE=$${DASHBOARD_DATA_SOURCE:-latest} npm --prefix dashboard run prepare-public-data
	DASHBOARD_HOST=$(DASHBOARD_HOST) DASHBOARD_PORT=$(DASHBOARD_PORT) FIELD_WORKER_ID=$(FIELD_WORKER_ID) RELIEFQUEUE_PREFERRED_PORTAL=field python3 scripts/portal_urls.py
	DASHBOARD_DATA_SOURCE=$${DASHBOARD_DATA_SOURCE:-latest} npm --prefix dashboard run dev -- --host $(DASHBOARD_HOST) --port $(DASHBOARD_PORT)

view-field-mobile:
	$(MAKE) view-field DASHBOARD_HOST=0.0.0.0

docs-index-check:
	python3 scripts/docs_index_check.py

change-guide:
	python3 scripts/change_guide.py
