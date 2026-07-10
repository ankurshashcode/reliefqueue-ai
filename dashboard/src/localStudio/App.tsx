import React, { useEffect, useMemo, useState } from 'react';
import { MapPin, Radio, Route, ShieldCheck, Users } from 'lucide-react';

type Scenario = {
  profile: string;
  zone: string;
  hub: string;
  radius_km: number;
  priority_needs: string[];
  blocked_safe_areas: string;
};

const DEFAULT_SCENARIO: Scenario = {
  profile: 'Urban flood pilot',
  zone: 'North embankment and Ward 13',
  hub: 'Relief hub west',
  radius_km: 4,
  priority_needs: ['rescue', 'medicine', 'water'],
  blocked_safe_areas: 'Ward 13 east road blocked; school shelter marked safe'
};

async function fetchJson(endpoint: string, fallback: any) {
  try {
    const response = await fetch(endpoint, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch {
    return fallback;
  }
}

async function postScenario(field: keyof Scenario, value: any) {
  const response = await fetch('/api/product/local/scenario', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ field, value, actor_id: 'local-coordinator' })
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export default function LocalCoordinatorApp() {
  const [scenario, setScenario] = useState<Scenario>(DEFAULT_SCENARIO);
  const [cases, setCases] = useState<any[]>([]);
  const [workers, setWorkers] = useState<any[]>([]);
  const [mapData, setMapData] = useState<any>(null);
  const [panel, setPanel] = useState('Scenario profile');
  const [result, setResult] = useState('Loading local coordinator scenario...');
  const [decisionCase, setDecisionCase] = useState<any>(null);

  useEffect(() => {
    Promise.all([
      fetchJson('/api/product/local/scenario', { scenario: DEFAULT_SCENARIO }),
      fetchJson('/api/product/local/cases', { cases: [] }),
      fetchJson('/api/product/local/workers', { workers: [] }),
      fetchJson('/api/product/maps/offline', null)
    ]).then(([scenarioPayload, casePayload, workerPayload, mapPayload]) => {
      setScenario(scenarioPayload.scenario || DEFAULT_SCENARIO);
      setCases(casePayload.cases || []);
      setWorkers(workerPayload.workers || []);
      setMapData(mapPayload);
      setResult(`Scenario profile loaded: ${(scenarioPayload.scenario || DEFAULT_SCENARIO).profile}.`);
    });
  }, []);

  const selectedCase = useMemo(() => cases.find((item) => item.urgency === 'REVIEW') || cases[0] || {
    case_id: 'RQ-1042', title: 'Boat evacuation request', operation_zone_id: scenario.zone, urgency: 'RED'
  }, [cases, scenario.zone]);

  const update = async (field: keyof Scenario, value: any, label: string) => {
    try {
      const payload = await postScenario(field, value);
      setScenario(payload.scenario || { ...scenario, [field]: value });
      setPanel(label);
      setResult(`${label} saved through the ReliefQueue product API: ${Array.isArray(value) ? value.join(', ') : String(value)}.`);
    } catch (error: any) {
      setPanel(label);
      setResult(`${label} remains unchanged because the local API returned ${error.message}.`);
    }
  };

  return (
    <main className="min-h-screen bg-slate-100 text-slate-900 p-4 md:p-8" aria-label="Local Coordinator product">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="rounded-2xl bg-slate-900 text-white p-6 md:p-8 flex flex-col md:flex-row md:items-center md:justify-between gap-4 shadow-xl">
          <div>
            <p className="text-xs uppercase tracking-[0.25em] text-cyan-300 font-bold">ReliefQueue local operations</p>
            <h1 className="mt-2 text-3xl font-bold">Local Coordinator</h1>
            <p className="mt-2 max-w-3xl text-slate-300">Own field context—scenario, zone, relief hub, radius, priority needs, safe/blocked areas, case locations, and worker status—while Command Center retains runtime controls.</p>
          </div>
          <a href="/dashboard?source=latest" className="rounded-lg border border-slate-600 px-4 py-2 text-sm font-semibold hover:bg-slate-800">Open Command Center</a>
        </header>

        <section className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
          <nav className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm space-y-2" aria-label="Local Coordinator actions">
            <Action id="local.view_scenario_profile" label="Scenario profile" onClick={() => { setPanel('Scenario profile'); setResult(`Scenario profile visible: ${scenario.profile}.`); }} />
            <Action id="local.update_scenario_profile" label="Save profile" onClick={() => update('profile', 'Urban flood pilot updated', 'Scenario profile')} />
            <Action id="local.update_operation_zone" label="Update operation zone" onClick={() => update('zone', 'North embankment, Ward 13, school shelter B', 'Operation zone')} />
            <Action id="local.update_relief_hub" label="Set relief hub" onClick={() => update('hub', 'Relief hub west loading bay', 'Relief hub')} />
            <Action id="local.update_reachable_radius" label="Expand reachable radius" onClick={() => update('radius_km', Number(scenario.radius_km || 4) + 1, 'Reachable radius')} />
            <Action id="local.update_priority_needs" label="Update priority needs" onClick={() => update('priority_needs', ['rescue', 'medicine', 'water', 'shelter'], 'Priority needs')} />
            <Action id="local.update_blocked_safe_areas" label="Update blocked / safe areas" onClick={() => update('blocked_safe_areas', 'Ward 13 east road blocked; clinic lane safe; school shelter safe', 'Blocked and safe areas')} />
            <Action id="local.view_case_locations" label="View case locations" onClick={() => { setPanel('Case locations'); setResult(`${cases.length} case locations visible with priority and reachability context.`); }} />
            <Action id="local.view_worker_roster_status" label="View worker roster" onClick={() => { setPanel('Worker roster'); setResult(`${workers.length} workers visible with availability, zones, and sync state.`); }} />
            <Action id="local.open_local_decision_case" label="Open local decision case" onClick={() => { setDecisionCase(selectedCase); setPanel('Local decision case'); setResult(`${selectedCase.case_id || selectedCase.id} opened for local decision; options and audit outcome are visible.`); }} />
          </nav>

          <div className="space-y-5">
            <section data-result-id="local.scenario" className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" aria-live="polite">
              <p className="text-xs uppercase tracking-wider text-slate-500 font-bold">Scenario ownership</p>
              <h2 className="mt-1 text-2xl font-bold">{panel}</h2>
              <p className="mt-2 rounded-lg bg-blue-50 border border-blue-100 p-3 text-blue-900">{result}</p>
              <dl className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <Datum label="Profile" value={scenario.profile} icon={ShieldCheck} />
                <Datum label="Operation zone" value={scenario.zone} icon={Route} />
                <Datum label="Relief hub" value={scenario.hub} icon={MapPin} />
                <Datum label="Reachable radius" value={`${scenario.radius_km} km`} icon={Radio} />
                <Datum label="Priority needs" value={Array.isArray(scenario.priority_needs) ? scenario.priority_needs.join(', ') : String(scenario.priority_needs)} icon={ShieldCheck} />
                <Datum label="Blocked / safe" value={scenario.blocked_safe_areas} icon={Route} />
              </dl>
            </section>

            <section data-result-id="local.offline-map" className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-xl font-bold flex items-center gap-2"><MapPin className="w-5 h-5 text-blue-600" /> Offline map and case locations</h2>
              <p className="mt-2 text-slate-600">Affected zone {mapData?.scenario?.zone || scenario.zone}; hub {mapData?.hub?.name || scenario.hub}; reachable radius {mapData?.reachable_radius_km || scenario.radius_km} km.</p>
              <ul className="mt-3 list-disc pl-5 text-sm text-slate-700 space-y-1">
                {(cases.length ? cases : [selectedCase]).slice(0, 4).map((item) => <li key={item.case_id || item.id}>{item.case_id || item.id}: {item.operation_zone_id || item.zone || scenario.zone}, priority {item.urgency || item.priority || 'review'}.</li>)}
              </ul>
            </section>

            <section data-result-id="local.workers" className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-xl font-bold flex items-center gap-2"><Users className="w-5 h-5 text-blue-600" /> Worker roster/status</h2>
              <ul className="mt-3 space-y-2 text-sm">{(workers.length ? workers : [{ worker_id: 'worker-alpha-boat', status: 'online', zone: 'north-embankment', last_sync: '2 min ago' }]).map((item) => <li key={item.worker_id} className="rounded-lg bg-slate-50 border border-slate-200 p-3">{item.worker_id}: {item.status}, {item.zone}, sync {item.last_sync}</li>)}</ul>
            </section>

            <section data-result-id="local.decision" className="rounded-2xl border border-amber-200 bg-amber-50 p-6 shadow-sm">
              <h2 className="text-xl font-bold text-amber-900">Local decision case</h2>
              <p className="mt-2 text-amber-900">{(decisionCase || selectedCase).case_id || (decisionCase || selectedCase).id}: {(decisionCase || selectedCase).title}. Options: hold, route around blocked area, assign hub staff, or escalate. Coordinator decision remains auditable.</p>
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}

function Action({ id, label, onClick }: { id: string; label: string; onClick: () => void }) {
  return <button data-action-id={id} type="button" onClick={onClick} className="w-full rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-left text-sm font-semibold hover:border-blue-400 hover:bg-blue-50 transition-colors">{label}</button>;
}

function Datum({ label, value, icon: Icon }: { label: string; value: string; icon: any }) {
  return <div className="rounded-lg border border-slate-200 bg-slate-50 p-3"><dt className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-500 font-bold"><Icon className="w-4 h-4" /> {label}</dt><dd className="mt-1 font-semibold text-slate-900">{value}</dd></div>;
}
