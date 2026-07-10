export const ROLE_PROFILES = [
  {
    id: "field_coordinator",
    label: "Field Coordinator",
    nav: ["work", "cases", "people", "outbox", "troubleshooting", "help"],
    commandCenterAccess: false
  },
  {
    id: "volunteer",
    label: "Volunteer / Field Operative",
    nav: ["work", "cases", "people", "outbox", "help"],
    commandCenterAccess: false
  },
  {
    id: "hub_staff",
    label: "Hub Staff",
    nav: ["work", "cases", "people", "outbox", "help"],
    commandCenterAccess: false
  },
  {
    id: "local_coordinator",
    label: "Local Coordinator",
    nav: ["work", "cases", "people", "outbox", "troubleshooting", "help"],
    commandCenterAccess: false
  },
  {
    id: "command_center_operator",
    label: "Command Center Operator",
    nav: ["overview", "sync", "ai_settings", "audit", "troubleshooting"],
    commandCenterAccess: true
  },
  {
    id: "quality_reviewer",
    label: "Quality Reviewer / AI Review",
    nav: ["quality_review", "audit", "troubleshooting"],
    commandCenterAccess: true
  }
];

export const CRITICAL_NEEDS = [
  ["medicine", "Medicine"],
  ["rescue", "Rescue"],
  ["food", "Food"],
  ["water", "Water"],
  ["shelter", "Shelter"],
  ["transport", "Transport"],
  ["sanitation", "Sanitation"],
  ["accessibility_support", "Accessibility support"],
  ["child_support", "Child support"],
  ["elderly_support", "Elderly support"],
  ["animal_support", "Animal support"],
  ["other", "Other"]
].map(([id, label]) => ({ id, label }));

export const API_CONTRACTS = {
  session: "GET /api/session/me",
  sync: "GET /api/field/sync?cursor=<cursor>&role=<role>&zone=<zone>",
  outboxBatch: "POST /api/field/outbox/batch",
  caseUpdates: "POST /api/cases/:caseId/updates",
  caseMedia: "POST /api/cases/:caseId/media",
  messagingEvents: "GET /api/messaging-channel/events?scope=<role-scope>",
  messagingReview: "POST /api/messaging-channel/review/:eventId",
  contacts: "GET /api/contacts?zone=<zone>&roleScope=field",
  callSessions: "POST /api/calls/sessions",
  mediaAnalysis: "POST /api/media-analysis/jobs",
  aiConfigCurrent: "GET /api/admin/ai-config/current",
  aiConfigTest: "POST /api/admin/ai-config/test",
  aiConfigActivate: "POST /api/admin/ai-config/activate",
  aiConfigRollback: "POST /api/admin/ai-config/rollback",
  audit: "GET /api/audit?scope=<role-scope>"
};

const CONTACT_LIBRARY = [
  {
    id: "person-alpha",
    name: "Team Alpha Boat",
    role: "Volunteer / Field Operative",
    team: "Boat response",
    zone: "zone-ward-01",
    availability: "Available",
    lastSeen: "4 min ago",
    photoUrl: "TA",
    emergencyReachable: true
  },
  {
    id: "person-gamma",
    name: "Team Gamma Child Support",
    role: "Volunteer / Field Operative",
    team: "Child support",
    zone: "zone-ward-01",
    availability: "Available",
    lastSeen: "7 min ago",
    photoUrl: "TG",
    emergencyReachable: true
  },
  {
    id: "person-beta",
    name: "Team Beta Medical",
    role: "Field Coordinator",
    team: "Medical",
    zone: "zone-village-03",
    availability: "Available",
    lastSeen: "2 min ago",
    photoUrl: "TB",
    emergencyReachable: true
  },
  {
    id: "person-delta",
    name: "Team Delta Food",
    role: "Hub Staff",
    team: "Relief hub",
    zone: "zone-ward-02",
    availability: "Busy",
    lastSeen: "12 min ago",
    photoUrl: "TD",
    emergencyReachable: true
  },
  {
    id: "person-eta",
    name: "Coordinator Eta Review Desk",
    role: "Quality Reviewer / AI Review",
    team: "Quality review",
    zone: "all-zones",
    availability: "Available",
    lastSeen: "Just now",
    photoUrl: "CE",
    emergencyReachable: true
  }
];

export const COMMAND_CENTER_STATE = {
  sync: [
    {
      id: "sync-alpha",
      name: "Team Alpha Boat",
      state: "online",
      lastContact: "2 min ago",
      queue: 0,
      zone: "zone-ward-01"
    },
    {
      id: "sync-gamma",
      name: "Team Gamma Child Support",
      state: "slow",
      lastContact: "18 min ago",
      queue: 3,
      zone: "zone-ward-01"
    },
    {
      id: "sync-epsilon",
      name: "Team Epsilon Offline",
      state: "offline",
      lastContact: "54 min ago",
      queue: 6,
      zone: "zone-ward-01"
    }
  ],
  quality: [
    {
      id: "qr-101",
      caseId: "case-fc88c47d1c",
      recommendation: "Confirm duplicate roof rescue reports before merging.",
      status: "pending review",
      confidence: 0.74
    },
    {
      id: "qr-102",
      caseId: "case-34871f1edb",
      recommendation: "Medical wording indicates urgent transport; keep coordinator approval required.",
      status: "accepted",
      confidence: 0.88
    }
  ],
  health: {
    integrations: "Healthy",
    queuePressure: "Moderate",
    fieldSync: "Two teams need attention",
    systemNotes: ["Offline teams can continue saving work.", "Large media uploads wait for stronger signal."]
  },
  aiConfigs: [
    {
      id: "ai-current",
      provider: "OpenAI-compatible",
      model: "relief-triage-small",
      status: "active",
      version: "2026-07-05.1",
      latencyMs: 410,
      result: "Ready for case triage suggestions"
    },
    {
      id: "ai-previous",
      provider: "OpenAI-compatible",
      model: "relief-triage-stable",
      status: "available rollback",
      version: "2026-07-04.2",
      latencyMs: 460,
      result: "Last known good configuration"
    }
  ]
};

export const MESSAGING_CHANNEL_FLOW = buildMessagingChannelFlow();

export function roleProfile(roleId) {
  return ROLE_PROFILES.find((role) => role.id === roleId) || ROLE_PROFILES[0];
}

export function contactsForWorker(worker) {
  if (!worker) return [];
  const zones = new Set(worker.authorized_zone_ids || []);
  return CONTACT_LIBRARY.filter((contact) => contact.zone === "all-zones" || zones.has(contact.zone)).map(
    (contact) => ({
      ...contact,
      contactActions: ["call", "message", "share note", "mute", "block non-critical"]
    })
  );
}

export function outboxSummary(events) {
  const pending = events.filter((event) => event.sync_state === "pending_sync").length;
  const failed = events.filter((event) => event.sync_state === "needs_attention").length;
  if (pending > 0) {
    return {
      state: failed > 0 ? "slow" : "syncing",
      title: failed > 0 ? "Needs attention" : "Syncing",
      detail: `${pending} local update${pending === 1 ? "" : "s"} waiting to send`
    };
  }
  return { state: "synced", title: "Synced", detail: "All local updates are saved with the command center" };
}

export function createOutboxItem({ workerId, caseId, type, payload }) {
  const localCreatedAt = payload?.createdAt || "2026-07-05T12:00:00.000Z";
  return {
    idempotencyKey: stableId("outbox", workerId, caseId, type, JSON.stringify(payload || {})),
    localCreatedAt,
    actorWorkerId: workerId,
    caseId,
    type,
    payload: payload || {},
    syncState: "pending_sync"
  };
}

export function overlapAssignments(assignments, caseId) {
  return assignments
    .filter((assignment) => assignment.case_id === caseId)
    .sort((a, b) => Number(a.rank || 0) - Number(b.rank || 0))
    .slice(0, 3)
    .map((assignment, index) => ({
      team: assignment.candidate_display_name_safe || assignment.display_name_safe || "Response team",
      responsibility: index === 0 ? "Owns next action" : index === 1 ? "Supports specialist need" : "Available backup",
      status: index === 0 ? "going" : index === 1 ? "ready" : "watching",
      overlapReason: (assignment.match_reasons || assignment.reasons || [])[0] || "Useful team match"
    }));
}

export function mergeIncomingDeltas(caseRow, deltas) {
  const merged = { ...caseRow, critical_needs: needsForCase(caseRow) };
  const history = [];
  const conflicts = [];
  for (const delta of deltas) {
    const decision = classifyDelta(delta, merged);
    if (decision === "auto_merge") {
      if (delta.field === "location_clue") merged.location_clue = delta.value;
      if (delta.field === "geo_confidence") merged.geo_confidence = delta.value;
      if (delta.field === "critical_need" && !merged.critical_needs.includes(delta.value)) {
        merged.critical_needs = [...merged.critical_needs, delta.value];
      }
      history.push({ deltaId: delta.id, status: "auto-merged", reason: "Safe, scoped update" });
    } else {
      conflicts.push({ deltaId: delta.id, status: "review needed", reason: decision });
    }
  }
  return { merged, history, conflicts };
}

export function classifyDelta(delta, caseRow = {}) {
  if (delta.scope && delta.scope !== caseRow.operation_zone_id) return "outside assigned zone";
  if (delta.confidence !== undefined && delta.confidence < 0.7) return "low confidence";
  if (delta.operation === "remove_evidence" || delta.reducesUrgency) return "risk to case record";
  if (delta.field === "coordinates" && caseRow.geo_confidence === "high") return "conflicting location";
  if (["location_clue", "geo_confidence", "critical_need", "safe_route_label", "contact_detail"].includes(delta.field)) {
    return "auto_merge";
  }
  return "unknown update type";
}

export function needsForCase(caseRow) {
  const base = new Set();
  const source = String(caseRow?.need_type || "").toLowerCase();
  const flags = (caseRow?.vulnerable_flags || []).map((flag) => String(flag).toLowerCase());
  if (source.includes("medical")) base.add("medicine");
  if (source.includes("rescue")) base.add("rescue");
  if (source.includes("food")) base.add("food");
  if (source.includes("water")) base.add("water");
  if (source.includes("shelter")) base.add("shelter");
  if (flags.includes("child")) base.add("child_support");
  if (flags.includes("elderly")) base.add("elderly_support");
  if (base.size === 0) base.add(CRITICAL_NEEDS.some((need) => need.id === source) ? source : "other");
  return [...base];
}

export function createMediaAnalysisQueue(notes, configVersion) {
  const seen = new Set();
  const jobs = [];
  for (const note of notes) {
    const key = `${note.hash}:${configVersion}`;
    if (seen.has(key)) continue;
    seen.add(key);
    jobs.push({
      jobId: stableId("media", note.hash, configVersion),
      mediaHash: note.hash,
      modelConfigVersion: configVersion,
      status: note.offline ? "skipped offline" : "queued",
      original: {
        name: note.name,
        type: note.type,
        sizeBytes: note.sizeBytes,
        capturedAt: note.capturedAt
      },
      analysis: {
        transcript: "",
        summary: "",
        extractedNeeds: [],
        locationHints: []
      }
    });
  }
  return jobs;
}

export function evictLocalCache(entries, maxBytes) {
  const kept = [];
  const evicted = [];
  let used = 0;
  const ordered = [...entries].sort((a, b) => {
    const ap = a.pinnedReason || a.scope === "outbox";
    const bp = b.pinnedReason || b.scope === "outbox";
    if (ap !== bp) return ap ? -1 : 1;
    return String(b.lastUsedAt).localeCompare(String(a.lastUsedAt));
  });
  for (const entry of ordered) {
    const protectedEntry = entry.pinnedReason || entry.scope === "outbox" || entry.unsynced;
    if (protectedEntry || used + entry.sizeBytes <= maxBytes) {
      kept.push({ ...entry, purgeEligibility: protectedEntry ? "protected" : "kept" });
      used += entry.sizeBytes;
    } else {
      evicted.push({ ...entry, purgeEligibility: "evicted" });
    }
  }
  return { kept, evicted, usedBytes: used };
}

export function runAiConfigLifecycle(configs, draft) {
  const test = {
    status: "passed",
    latencyMs: 430,
    result: `Model test completed for ${draft.provider} ${draft.model}`,
    checkedAt: "2026-07-05T12:05:00.000Z"
  };
  const activated = {
    ...draft,
    id: stableId("ai", draft.provider, draft.model, draft.version),
    status: "active",
    latencyMs: test.latencyMs,
    result: test.result
  };
  const previous = configs.find((config) => config.status === "active") || configs[0];
  const audit = [
    { event: "model test", status: test.status, version: draft.version },
    { event: "activate model", status: "complete", version: draft.version },
    { event: "rollback available", status: "ready", version: previous.version }
  ];
  return { test, activated, rollbackTarget: previous, audit };
}

export function gpsPinState({ geolocationAvailable, permission, manualPin }) {
  if (geolocationAvailable && permission === "granted") {
    return {
      source: "gps",
      status: "GPS location ready",
      accuracyMeters: 18,
      pin: manualPin || { lat: 28.6139, lng: 77.209 },
      zoom: 15,
      editable: true
    };
  }
  return {
    source: "manual",
    status: "GPS unavailable. Use landmark or coordinates.",
    accuracyMeters: null,
    pin: manualPin || { lat: 28.61, lng: 77.21 },
    zoom: 12,
    editable: true
  };
}

export function voiceCaptureState({ supported, transcript }) {
  return {
    supported: Boolean(supported),
    mode: supported ? "review transcript" : "typing fallback",
    transcript: transcript || "",
    canSave: Boolean((transcript || "").trim()),
    fallbackAvailable: true
  };
}

export function roleAuditSurfaces() {
  return {
    field: ["sync state", "outbox", "last contact", "blocked non-critical updates", "messaging channel handoff"],
    localCoordinator: ["workload", "stale cases", "assignment conflicts", "offline teams", "messaging review"],
    commandCenter: ["system health", "integrations", "AI settings changes", "queue pressure", "messaging channel audit"],
    qualityReviewer: ["pending AI recommendations", "review outcomes", "ambiguous message review"]
  };
}

export function buildMessagingChannelFlow() {
  const events = [
    {
      id: "msg-in-help-001",
      channel: "SMS",
      direction: "inbound",
      from: "resident-redacted",
      summary: "HELP. Need medicine and water near old bus stand.",
      caseId: "case-msg-local-001",
      linkedUpdateId: "",
      idempotencyKey: "message-sms-provider-001",
      duplicateOf: "",
      reviewState: "needs review",
      uncertaintyFlags: ["location ambiguous", "need split across medicine and water"],
      nextAction: "Coordinator confirms landmark and need priority",
      auditEntry: "Inbound SMS normalized and linked to local case draft"
    },
    {
      id: "msg-out-ack-001",
      channel: "SMS",
      direction: "outbound",
      from: "ReliefQueue",
      summary: "Acknowledgement draft saved. A human operator will review before sending.",
      caseId: "case-msg-local-001",
      linkedUpdateId: "",
      idempotencyKey: "message-sms-provider-001-ack",
      duplicateOf: "",
      reviewState: "human approval required",
      uncertaintyFlags: [],
      nextAction: "Approve or edit resident acknowledgement",
      auditEntry: "Outbound acknowledgement drafted without provider send"
    },
    {
      id: "msg-in-duplicate-001",
      channel: "WhatsApp",
      direction: "inbound",
      from: "resident-redacted",
      summary: "HELP medicine water old bus stand",
      caseId: "case-msg-local-001",
      linkedUpdateId: "",
      idempotencyKey: "message-sms-provider-001",
      duplicateOf: "msg-in-help-001",
      reviewState: "duplicate suppressed",
      uncertaintyFlags: [],
      nextAction: "No new case created",
      auditEntry: "Duplicate idempotency key suppressed"
    },
    {
      id: "msg-in-update-001",
      channel: "WhatsApp",
      direction: "inbound",
      from: "worker-alpha-boat",
      summary: "UPDATE: reached school gate, two people still waiting.",
      caseId: "case-msg-local-001",
      linkedUpdateId: "upd-field-001",
      idempotencyKey: "message-wa-worker-update-001",
      duplicateOf: "",
      reviewState: "linked update",
      uncertaintyFlags: [],
      nextAction: "Local coordinator reviews status update",
      auditEntry: "Field-worker update handed to operations model"
    },
    {
      id: "msg-in-ivr-001",
      channel: "voice helpline",
      direction: "inbound",
      from: "caller-redacted",
      summary: "IVR key 2, transcript note: elderly parent needs transport, location unclear.",
      caseId: "case-msg-local-002",
      linkedUpdateId: "ivr-note-001",
      idempotencyKey: "message-ivr-call-001-key2",
      duplicateOf: "",
      reviewState: "needs review",
      uncertaintyFlags: ["location ambiguous", "transcript requires human review"],
      nextAction: "Call back through masked contact path",
      auditEntry: "IVR keypad and transcript note saved for review"
    }
  ];
  const seen = new Set();
  const duplicateCount = events.filter((event) => {
    if (seen.has(event.idempotencyKey)) return true;
    seen.add(event.idempotencyKey);
    return false;
  }).length;
  return {
    providerStatus: {
      status: "SKIP",
      detail: "No real provider environment configured. Local messaging-channel flow is deterministic.",
      secretValuesPrinted: false
    },
    events,
    operationsCases: [
      {
        caseId: "case-msg-local-001",
        source: "SMS",
        status: "review required",
        safeSummary: "Resident needs medicine and water near a landmark that needs confirmation.",
        assignmentZone: "zone-ward-01"
      },
      {
        caseId: "case-msg-local-002",
        source: "voice helpline",
        status: "review required",
        safeSummary: "Caller requested transport support; location remains unclear.",
        assignmentZone: "review"
      }
    ],
    updates: [
      { updateId: "upd-field-001", caseId: "case-msg-local-001", actor: "worker-alpha-boat", status: "field update reported" },
      { updateId: "ivr-note-001", caseId: "case-msg-local-002", actor: "voice helpline", status: "transcript review needed" }
    ],
    audit: events.map((event) => ({
      eventId: `audit-${event.id}`,
      eventType: event.direction === "outbound" ? "message_ack_draft" : "message_received",
      caseId: event.caseId,
      idempotencyKey: event.idempotencyKey,
      reviewState: event.reviewState,
      rawContactStored: false,
      rawTranscriptStoredPublicly: false
    })),
    duplicateCount
  };
}

export function messagingEventsForRole(roleId) {
  const flow = MESSAGING_CHANNEL_FLOW;
  if (roleId === "quality_reviewer") {
    return flow.events.filter((event) => event.reviewState.includes("review") || event.uncertaintyFlags.length > 0);
  }
  if (roleId === "field_coordinator" || roleId === "volunteer" || roleId === "hub_staff") {
    return flow.events.filter((event) => event.from === "worker-alpha-boat" || event.caseId === "case-msg-local-001");
  }
  return flow.events;
}

function stableId(...parts) {
  let hash = 0;
  for (const char of parts.join("|")) {
    hash = (hash * 33 + char.charCodeAt(0)) % 1000000007;
  }
  return `${parts[0]}-${String(hash).padStart(9, "0")}`;
}
