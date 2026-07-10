"""Operator action catalog and lookup helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


RISK_LEVELS = {"none", "local", "host_changes"}
ESSENTIAL_PHASE01_ACTIONS = {
    "phase01_live_stack",
    "phase01_host_preflight",
    "phase01_host_setup",
    "phase01_live_proof",
    "phase01_live_clean",
}


@dataclass(frozen=True)
class OperatorAction:
    id: str
    title: str
    category: str
    when: tuple[str, ...]
    commands: tuple[str, ...]
    scope: tuple[str, ...]
    does_not: tuple[str, ...]
    side_effects: tuple[str, ...]
    requires: tuple[str, ...]
    reports: tuple[str, ...]
    cleanup: tuple[str, ...]
    safe_to_repeat: str
    risk_level: str
    next_steps: tuple[str, ...]

    @property
    def command_to_run(self) -> str:
        return self.commands[0] if self.commands else "No command registered."


def actions() -> tuple[OperatorAction, ...]:
    return (
        OperatorAction(
            id="docs_living_guide",
            title="Check living guide and documentation drift",
            category="Documentation",
            when=("docs", "documentation", "living guide", "what docs matter", "remove stale docs"),
            commands=("make docs-check",),
            scope=("Checks that retained docs are current, discoverable, and not obsolete slice history.",),
            does_not=("Does not rewrite docs or change runtime behavior.",),
            side_effects=("No source/runtime side effects; prints a docs drift report.",),
            requires=("README.md, docs/living-guide.md, and retained docs.",),
            reports=("console output only",),
            cleanup=("No cleanup needed.",),
            safe_to_repeat="Yes. It is read-only.",
            risk_level="none",
            next_steps=('make operator-search QUERY="test live integration"',),
        ),
        OperatorAction(
            id="demo_local",
            title="Run deterministic local demo",
            category="Local demo",
            when=("run the local demo", "generate latest reports", "test deterministic intake"),
            commands=("make run-demo-local", "make export-report"),
            scope=("Reads fixtures and writes synthetic demo reports under reports/latest.",),
            does_not=("Does not contact providers, dispatch workers, or use real incident data.",),
            side_effects=("Overwrites generated files in reports/latest.",),
            requires=("Python 3.11+ and repository fixtures.",),
            reports=("reports/latest/summary.json", "reports/latest/cases.jsonl", "reports/latest/validation.md"),
            cleanup=("make clean-reports",),
            safe_to_repeat="Yes. It regenerates synthetic local outputs.",
            risk_level="local",
            next_steps=("make dashboard-smoke", "make privacy-check"),
        ),
        OperatorAction(
            id="dashboard_check",
            title="Check dashboard and field views",
            category="Dashboard",
            when=("dashboard smoke", "check dashboard", "field view smoke", "frontend proof"),
            commands=("make dashboard-build", "make dashboard-smoke", "make field-smoke"),
            scope=("Builds the dashboard and runs smoke checks against generated public data.",),
            does_not=("Does not publish data or start production hosting.",),
            side_effects=("Writes dashboard build output and public report copies under dashboard/.",),
            requires=("Node/npm dependencies installable from dashboard/package-lock.json.",),
            reports=("dashboard/dist/", "dashboard/public/reports/"),
            cleanup=("make clean",),
            safe_to_repeat="Yes. Build artifacts are replaceable.",
            risk_level="local",
            next_steps=("make privacy-check",),
        ),
        OperatorAction(
            id="privacy_security_check",
            title="Run privacy and security checks",
            category="Review",
            when=("privacy check", "security check", "redaction", "no secrets", "safe public export"),
            commands=("make privacy-check", "make security-check", "make no-secrets"),
            scope=("Scans generated exports and repository text for private fields and secret-like values.",),
            does_not=("Does not prove legal compliance or approve public release.",),
            side_effects=("May regenerate public export files under reports/latest/public.",),
            requires=("Run make run-demo-local first when reports/latest is missing.",),
            reports=("reports/latest/public/export_manifest.json",),
            cleanup=("make clean-reports",),
            safe_to_repeat="Yes.",
            risk_level="local",
            next_steps=("make reviewer-pack",),
        ),
        OperatorAction(
            id="integration_boundaries",
            title="Check integration boundary artifacts",
            category="Integrations",
            when=("integration smoke", "PostGIS seed", "queue smoke", "external boundary check"),
            commands=("make integrations-status", "make integration-smoke"),
            scope=("Writes synthetic integration boundary packages and status reports.",),
            does_not=("Does not connect to production providers or external queues.",),
            side_effects=("Writes generated integration artifacts under reports/latest.",),
            requires=("Run make run-demo-local first for source reports.",),
            reports=("reports/latest/integrations_status.json", "reports/latest/scale_integration_summary.json"),
            cleanup=("make clean-reports",),
            safe_to_repeat="Yes.",
            risk_level="local",
            next_steps=("make phase01-live-proof",),
        ),
        OperatorAction(
            id="phase02_03_stateful_mutation_drill",
            title="Run PostGIS GIS and Redis resilience mutation drill",
            category="Live integrations",
            when=(
                "stateful mutation drill",
                "create read update delete replay recover live state",
                "PostGIS GIS Redis resilience mutation proof",
                "phase 02 03 stateful mutation",
            ),
            commands=("make live-stateful-mutation-drill", "make live-stateful-mutation-drill-profile PROFILE=urban_flood"),
            scope=(
                "Uses the configured/local live PostGIS and Redis endpoints with a broad library of role-aware disaster scenario profiles. The local coordinator profile controls field geography and priority context; the command center runtime profile controls queue burst, retry/DLQ, dedup, replay, and cleanup behavior.",
            ),
            does_not=(
                "Does not use real incident data, send provider messages, dispatch without coordinator review workers, or mutate NATS JetStream queue state.",
            ),
            side_effects=(
                "Creates short-lived synthetic PostGIS case/zone geometry and Redis Streams/dedup entries, then verifies cleanup; writes mutation evidence reports.",
            ),
            requires=(
                "Run make live-stack-up first, or provide RELIEFQUEUE_POSTGIS_DSN and RELIEFQUEUE_REDIS_URL for trusted local/live test endpoints. Run make live-stateful-mutation-drill-profiles to list built-in PROFILE values.",
            ),
            reports=(
                "reports/latest/live_integrations/stateful-mutation/live_stateful_mutation_drill.json",
                "reports/latest/live_integrations/stateful-mutation/postgis_mutation_evidence.json",
                "reports/latest/live_integrations/stateful-mutation/redis_mutation_evidence.json",
            ),
            cleanup=("Automatic cleanup of drill rows/streams is verified in the report.", "make live-stack-down"),
            safe_to_repeat="Yes. It uses unique synthetic IDs and cleans up its own drill state.",
            risk_level="local",
            next_steps=("Review the mutation evidence report and the role-specific selected_profile/coordinator_config/command_center_config sections.", "make live-pilot-drill"),
        ),
        OperatorAction(
            id="phase02_04_logistics_asset_drill",
            title="Run logistics asset coordination drill",
            category="Live integrations",
            when=(
                "logistics asset drill",
                "inventory reservation dispatch delivery return reallocation",
                "team asset requests",
                "phase 02 04 logistics",
            ),
            commands=(
                "make live-logistics-asset-drill",
                "make live-logistics-asset-drill-profile PROFILE=urban_flood",
                "make live-logistics-asset-profiles",
            ),
            scope=(
                "Uses role-aware disaster profiles to create synthetic team logistics requests, inventory assets, hubs, delivery timelines, return expectations, and reallocation evidence across PostGIS and Redis.",
            ),
            does_not=(
                "Does not move real inventory, contact providers, send messages, instruct field teams, or write real incident data.",
            ),
            side_effects=(
                "Creates short-lived synthetic logistics hub, asset, and request rows in PostGIS and Redis Streams/locks/dedup keys, then verifies cleanup.",
            ),
            requires=(
                "Run make live-stack-up first, or provide RELIEFQUEUE_POSTGIS_DSN and RELIEFQUEUE_REDIS_URL for trusted local/live test endpoints. Run make live-logistics-asset-profiles to list PROFILE values.",
            ),
            reports=(
                "reports/latest/live_integrations/logistics-assets/live_logistics_asset_drill.json",
                "reports/latest/live_integrations/logistics-assets/logistics_postgis_evidence.json",
                "reports/latest/live_integrations/logistics-assets/logistics_redis_evidence.json",
            ),
            cleanup=("Automatic cleanup of synthetic rows/streams/locks is verified in the report.", "make live-stack-down"),
            safe_to_repeat="Yes. It uses unique synthetic IDs and cleans up its own drill state.",
            risk_level="local",
            next_steps=("Review nearest asset, reservation, delivery, overdue return, and reallocation evidence.",),
        ),
        OperatorAction(
            id="phase02_05_volunteer_surge_drill",
            title="Run volunteer surge coordination drill",
            category="Live integrations",
            when=(
                "volunteer surge drill",
                "field worker walk-up volunteer registration",
                "coordinator volunteer intake",
                "call center wellbeing poll dry run",
                "phase 02 05 volunteers",
            ),
            commands=(
                "make live-volunteer-surge-drill",
                "make live-volunteer-surge-drill-profile PROFILE=urban_flood VERBOSE_FLAGS=-v",
                "make live-volunteer-surge-profiles",
            ),
            scope=(
                "Uses role-aware disaster profiles to prove synthetic walk-up volunteer registration, consent/age-bracket/skills capture, nearest volunteer matching, Redis onboarding queue recovery, duplicate suppression, and dry-run call-center review queues.",
            ),
            does_not=(
                "Does not send real messages, poll real phones, store raw phone numbers, dispatch without coordinator review volunteers, or bypass coordinator review.",
            ),
            side_effects=(
                "Creates short-lived synthetic volunteer and outreach audit rows in PostGIS and Redis Streams/dedup/presence guard keys, then verifies cleanup.",
            ),
            requires=(
                "Run make live-stack-up first, or provide RELIEFQUEUE_POSTGIS_DSN and RELIEFQUEUE_REDIS_URL for trusted local/live test endpoints. Run make live-volunteer-surge-profiles to list PROFILE values.",
            ),
            reports=(
                "reports/latest/live_integrations/volunteer-surge/live_volunteer_surge_drill.json",
                "reports/latest/live_integrations/volunteer-surge/volunteer_postgis_evidence.json",
                "reports/latest/live_integrations/volunteer-surge/volunteer_redis_evidence.json",
            ),
            cleanup=("Automatic cleanup of synthetic volunteer/outreach rows and Redis streams/keys is verified in the report.", "make live-stack-down"),
            safe_to_repeat="Yes. It uses unique synthetic IDs and cleans up its own drill state.",
            risk_level="local",
            next_steps=("Review privacy_and_safety_boundary before any real volunteer outreach work.",),
        ),
        OperatorAction(
            id="phase01_live_stack",
            title="Start, inspect, smoke, and stop Phase 01 live stack",
            category="Phase 01 live",
            when=("PostGIS Redis NATS", "live stack", "test live integration", "docker live stack"),
            commands=("make container-runtime-readiness", "make live-stack-up", "make live-stack-status", "make live-stack-smoke", "make live-stack-down"),
            scope=("Checks Docker access first, then touches containers for PostGIS, Redis Streams, and NATS JetStream.",),
            does_not=("Does not install Docker, change host packages, or purge volumes by default.",),
            side_effects=("Starts/stops local containers and writes live stack status reports.",),
            requires=("Docker Engine and compose command accessible to the current user. Podman is guidance-only for now.",),
            reports=("reports/latest/container_runtime_readiness.json", "reports/latest/live_stack_status.json", "reports/latest/live_stack_smoke.json"),
            cleanup=("make live-stack-down", "RELIEFQUEUE_LIVE_STACK_PURGE=1 make live-stack-down"),
            safe_to_repeat="Yes. Volumes are preserved unless purge is explicitly requested.",
            risk_level="local",
            next_steps=("make phase01-live-proof",),
        ),
        OperatorAction(
            id="phase01_host_preflight",
            title="Inspect host readiness for Docker live proof",
            category="Phase 01 host",
            when=("docker installed but live stack not working", "host preflight", "docker socket", "compose plugin"),
            commands=("make phase01-host-preflight",),
            scope=("Reads OS, kernel, user/group, Docker, Compose, Podman, and socket-access status.",),
            does_not=("Does not install packages, change groups, start services, or print secrets.",),
            side_effects=("Writes a sanitized preflight report.",),
            requires=("Ubuntu/Debian-compatible host for guided setup recommendations.",),
            reports=("reports/latest/phase01_host_preflight.json",),
            cleanup=("No cleanup needed.",),
            safe_to_repeat="Yes. It is read-only.",
            risk_level="none",
            next_steps=("make phase01-host-setup", "make phase01-live-proof"),
        ),
        OperatorAction(
            id="phase01_host_setup",
            title="Guided Docker Engine setup for Ubuntu/Debian",
            category="Phase 01 host",
            when=("install docker", "repair docker host", "docker setup", "OCI Ubuntu host setup"),
            commands=("make phase01-host-setup",),
            scope=("Can install official Docker Engine and Compose plugin, start Docker, and add the current user to docker group after explicit YES.",),
            does_not=("Does not run silently, support Podman/docker-compose v1, or change unsupported OS hosts.",),
            side_effects=("May change apt packages, apt sources/keyrings, systemd service state, and user groups.",),
            requires=("Ubuntu/Debian-compatible OS, sudo/root access, network package repositories, explicit YES confirmation.",),
            reports=("reports/latest/phase01_host_setup.json", "reports/latest/phase01_host_preflight.json"),
            cleanup=("Review Docker's official uninstall steps for host package removal; live stack data cleanup is make phase01-live-clean.",),
            safe_to_repeat="Mostly. It exits when preflight already passes; host package operations still require confirmation.",
            risk_level="host_changes",
            next_steps=("Log in again or run newgrp docker if group changed.", "make phase01-live-proof"),
        ),
        OperatorAction(
            id="phase01_live_proof",
            title="Run full Phase 01 live proof",
            category="Phase 01 live",
            when=("test live integration", "what changes will phase01 live proof make", "protocol proof", "PostGIS Redis NATS proof"),
            commands=("make phase01-live-proof",),
            scope=("Runs test gate, cycles the live stack, proves PostGIS/Redis/NATS inside containers, runs smoke, and stops the stack.",),
            does_not=("Does not install Docker, use local Python protocol clients, or purge volumes by default.",),
            side_effects=("Starts/stops local containers, writes Redis stream smoke entry, and writes proof report.",),
            requires=("Passing host preflight with Docker Engine, Compose plugin, and socket access.",),
            reports=("reports/latest/phase01_live_proof.json", "reports/latest/container_runtime_readiness.json", "reports/latest/live_stack_status.json", "reports/latest/live_stack_smoke.json"),
            cleanup=("Automatic make live-stack-down by default.", "Set RELIEFQUEUE_PHASE01_KEEP_STACK=1 to keep containers running."),
            safe_to_repeat="Yes. Volumes are preserved by default.",
            risk_level="local",
            next_steps=("make phase01-live-clean", "make integration-smoke"),
        ),
        OperatorAction(
            id="phase01_live_clean",
            title="Clean Phase 01 live stack",
            category="Phase 01 live",
            when=("clean up live stack", "stop containers", "preserve volumes", "purge live stack volumes"),
            commands=("make phase01-live-clean",),
            scope=("Stops the live stack. Preserves Docker volumes unless RELIEFQUEUE_LIVE_STACK_PURGE=1.",),
            does_not=("Does not uninstall Docker or remove host packages.",),
            side_effects=("Stops local containers; may purge volumes only by explicit opt-in.",),
            requires=("Docker/Compose if containers need stopping.",),
            reports=("reports/latest/phase01_live_clean.json", "reports/latest/live_stack_status.json"),
            cleanup=("No further cleanup needed unless Docker volumes were intentionally preserved.",),
            safe_to_repeat="Yes.",
            risk_level="local",
            next_steps=("make phase01-host-preflight",),
        ),
        OperatorAction(
            id="operations_smoke",
            title="Run operations smoke",
            category="Operations",
            when=("operations smoke", "queue status", "backup restore", "degraded mode"),
            commands=("make operations-smoke",),
            scope=("Writes local operations, queue simulation, and failed-job reports.",),
            does_not=("Does not run real queues or retry production jobs.",),
            side_effects=("Writes reports/latest operations files.",),
            requires=("Generated reports/latest recommended.",),
            reports=("reports/latest/operations_status.json", "reports/latest/queue_simulation.json"),
            cleanup=("make clean-reports",),
            safe_to_repeat="Yes.",
            risk_level="local",
            next_steps=("make backup-demo-state", "make degraded-mode-smoke"),
        ),
        OperatorAction(
            id="pilot_readiness",
            title="Prepare pilot review packet",
            category="Review",
            when=("pilot readiness", "reviewer pack", "partner feedback", "public review"),
            commands=("make reviewer-pack", "make pilot-feedback-template", "make pilot-smoke"),
            scope=("Creates a sanitized synthetic reviewer pack and feedback template.",),
            does_not=("Does not approve a pilot, publish data, or include private exports.",),
            side_effects=("Writes reports/latest/reviewer_pack and pilot feedback files.",),
            requires=("Run make run-demo-local first.",),
            reports=("reports/latest/reviewer_pack/reviewer_manifest.json", "reports/latest/pilot_feedback_template.json"),
            cleanup=("make clean-reports",),
            safe_to_repeat="Yes.",
            risk_level="local",
            next_steps=("Review docs/pilot-readiness.md",),
        ),
    )


def render_operator_help() -> str:
    lines = ["ReliefQueue operator commands", ""]
    by_category: dict[str, list[OperatorAction]] = {}
    for action in actions():
        by_category.setdefault(action.category, []).append(action)
    for category in sorted(by_category):
        lines.append(category)
        for action in by_category[category]:
            lines.append(f"  {action.id}: {action.title}")
            lines.append(f"    run: {action.command_to_run}")
        lines.append("")
    lines.append('Search: make operator-search QUERY="test live integration"')
    lines.append("Scope:  make operator-scope ACTION=phase01_live_stack")
    return "\n".join(lines)


def search_actions(query: str, limit: int = 3) -> list[tuple[int, OperatorAction]]:
    query_tokens = _tokens(query)
    scored: list[tuple[int, OperatorAction]] = []
    for action in actions():
        haystack = " ".join(
            [
                action.id.replace("_", " "),
                action.title,
                action.category,
                " ".join(action.when),
                " ".join(action.commands),
                " ".join(action.scope),
                " ".join(action.does_not),
                " ".join(action.requires),
                " ".join(action.cleanup),
            ]
        ).lower()
        score = 0
        for token in query_tokens:
            if token in haystack:
                score += 2
            if token and token in action.id.lower().replace("_", " "):
                score += 3
        phrase = query.strip().lower()
        if phrase and phrase in haystack:
            score += 8
        if score:
            scored.append((score, action))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    return scored[:limit]


def render_search(query: str) -> str:
    matches = search_actions(query)
    if not matches:
        return "No matching operator action found. Try `make operator` for the catalog."
    lines = [f"Best operator actions for: {query}", ""]
    for _score, action in matches:
        lines.extend(
            [
                f"{action.id}: {action.title}",
                f"  use when: {action.when[0]}",
                f"  run next: {action.command_to_run}",
                f"  scope: {action.scope[0]}",
                f"  cleanup: {'; '.join(action.cleanup)}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def render_scope(action_id: str) -> tuple[int, str]:
    action = next((item for item in actions() if item.id == action_id), None)
    if action is None:
        return 1, f"Unknown action: {action_id}\nRun `make operator` to list action IDs."
    lines = [
        f"{action.id}: {action.title}",
        f"category: {action.category}",
        f"risk_level: {action.risk_level}",
        "",
        "Use when:",
        *_bullet(action.when),
        "Commands:",
        *_bullet(action.commands),
        "Scope:",
        *_bullet(action.scope),
        "Does not:",
        *_bullet(action.does_not),
        "Side effects:",
        *_bullet(action.side_effects),
        "Prerequisites:",
        *_bullet(action.requires),
        "Reports:",
        *_bullet(action.reports),
        "Cleanup:",
        *_bullet(action.cleanup),
        f"Safe to repeat: {action.safe_to_repeat}",
        "Next steps:",
        *_bullet(action.next_steps),
    ]
    return 0, "\n".join(lines)


def catalog_check(root: Path) -> tuple[int, list[str]]:
    errors: list[str] = []
    ids = [action.id for action in actions()]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    for item in duplicates:
        errors.append(f"duplicate action id: {item}")
    missing_phase01 = sorted(ESSENTIAL_PHASE01_ACTIONS - set(ids))
    for item in missing_phase01:
        errors.append(f"missing essential Phase 01 action: {item}")
    make_targets = _make_targets(root / "Makefile")
    for action in actions():
        if action.risk_level not in RISK_LEVELS:
            errors.append(f"{action.id}: invalid risk_level {action.risk_level}")
        for command in action.commands:
            target = _make_target_from_command(command)
            if target and target not in make_targets:
                errors.append(f"{action.id}: missing Makefile target referenced by `{command}`")
        side_effecting = action.risk_level in {"local", "host_changes"} or bool(action.side_effects)
        if side_effecting and (not action.cleanup or not action.scope or not action.does_not):
            errors.append(f"{action.id}: side-effecting action must declare cleanup, scope, and does_not")
        docker_or_host = any(token in action.id for token in ["host", "live"]) or "docker" in " ".join(action.when).lower()
        if docker_or_host and not action.requires:
            errors.append(f"{action.id}: Docker/host action must declare prerequisites")
        if action.reports and not all(path.strip() for path in action.reports):
            errors.append(f"{action.id}: report-producing action has an empty report path")
    return (1 if errors else 0), errors


def _bullet(values: tuple[str, ...]) -> list[str]:
    return [f"- {value}" for value in values]


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", value.lower()) if token]


def _make_target_from_command(command: str) -> str | None:
    parts = command.strip().split()
    if not parts:
        return None
    if parts[0].endswith("make") and len(parts) > 1:
        return parts[1]
    if parts[0].startswith("RELIEFQUEUE_"):
        for index, part in enumerate(parts):
            if part == "make" and index + 1 < len(parts):
                return parts[index + 1]
    return None


def _make_targets(path: Path) -> set[str]:
    if not path.exists():
        return set()
    targets: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("\t") or ":" not in line:
            continue
        name = line.split(":", 1)[0].strip()
        if name and " " not in name and not name.startswith("."):
            targets.add(name)
    return targets
