(function installContinuitySmokeFixtures() {
  const fresh = { stale: false, present: true, generated_at: '2026-04-03T12:00:00Z', age_sec: 5, max_age_sec: 21600, reason: 'fresh' };
  const freshCheckpoint = { stale: false, present: true, generated_at: '2026-04-03T12:00:00Z', age_sec: 5, max_age_sec: 86400, reason: 'fresh' };
  const roster = {
    generated_at: '2026-04-03T12:00:00Z',
    active_profile: 'filippo',
    agent_count: 1,
    active_agent_count: 1,
    session_count: 1,
    active_session_count: 1,
    highest_context_used_pct: 0.12,
    roster: [
      {
        profile_name: 'filippo',
        agent_name: 'Athena',
        is_current_profile: true,
        status: 'ACTIVE',
        session_count: 1,
        active_session_count: 1,
        latest_session_id: 'sess_source',
        latest_session_key: 'agent:main:telegram:dm:123',
        latest_updated_at: '2026-04-03T12:00:00Z',
        hottest_context_used_pct: 0.12,
        model: 'gpt-5.4',
        provider: 'openai-codex',
        personality: 'filippo',
        cwd: '/tmp/project',
        home: '~/.hermes/profiles/filippo',
      },
    ],
    sessions: [
      {
        profile_name: 'filippo',
        agent_name: 'Athena',
        is_current_profile: true,
        activity_state: 'ACTIVE',
        session_key: 'agent:main:telegram:dm:123',
        session_id: 'sess_source',
        platform: 'telegram',
        chat_type: 'dm',
        model: 'gpt-5.4',
        provider: 'openai-codex',
        cwd: '/tmp/project',
        total_tokens: 1200,
        context_limit: 10000,
        context_used_pct: 0.12,
        updated_at: '2026-04-03T12:00:00Z',
      },
    ],
  };
  const incidents = {
    generated_at: '2026-04-03T12:00:00Z',
    incident_count: 0,
    open: 0,
    resolved: 0,
    fail_closed: 0,
    degraded: 0,
    unsafe_pass: 0,
    recent: [],
  };
  const benchmark = {
    benchmark: {
      status: 'PASS',
      passed_count: 18,
      failed_count: 0,
      case_count: 18,
    },
  };

  function semantics(target, state) {
    if (state === 'NOT_RECENTLY_EXERCISED') {
      return {
        category: 'event_receipt',
        display_state: state,
        operator_state: 'WARN',
        blocks_on_stale: false,
        summary: target === 'gateway-reset'
          ? 'Gateway reset receipts are event-driven; stale means no recent reset exercise, not broken continuity.'
          : 'Cron continuity receipts are event-driven; stale means the cron recovery path has not run recently.',
      };
    }
    return {
      category: 'guarded_surface',
      display_state: state,
      operator_state: state === 'FRESH' ? 'OK' : 'WARN',
      blocks_on_stale: false,
      summary: 'Synthetic browser smoke fixture.',
    };
  }

  function report(target, payload, status = 'OK', freshnessState = 'FRESH') {
    return {
      report: {
        status,
        target,
        path: `/tmp/${target}-latest.json`,
        payload,
        freshness: freshnessState === 'FRESH' ? fresh : { ...fresh, stale: true, reason: 'stale' },
        freshness_semantics: semantics(target, freshnessState),
        generated_at: payload.generated_at || '2026-04-03T12:00:00Z',
      },
    };
  }

  const knowledgeCompile = {
    status: 'PASS',
    generated_at: '2026-04-03T12:00:00Z',
    operator_summary: 'Compiled 4 derived continuity knowledge article(s).',
    article_count: 4,
    freshness: { fresh: 3, watch: 1, stale: 0 },
    coverage: { strong: 2, serviceable: 2, thin: 0 },
  };
  const knowledgeLint = {
    status: 'PASS',
    generated_at: '2026-04-03T12:00:00Z',
    operator_summary: 'Knowledge lint is clean.',
    article_count: 4,
    errors: [],
    warnings: [],
  };
  const knowledgeHealth = {
    status: 'WARN',
    generated_at: '2026-04-03T12:00:00Z',
    operator_summary: 'Knowledge Plane is usable with warnings.',
    article_count: 4,
    coverage: { raw_count: 4, compiled_count: 4, low_coverage_count: 1, strong_count: 2, serviceable_count: 2, thin_count: 0 },
    freshness: { fresh_count: 3, watch_count: 1, stale_count: 0 },
    source_coverage: { expected_report_targets: ['single-machine-readiness', 'verify', 'rehydrate', 'gateway-reset', 'cron-continuity'], present_report_targets: ['single-machine-readiness', 'verify', 'rehydrate', 'gateway-reset', 'cron-continuity'], missing_report_targets: [] },
    stale_articles: [],
    low_coverage_articles: [{ id: 'incident-verify', title: 'Verify incident', coverage_score: 0.58 }],
    contradictions: { count: 1, items: [{ left_id: 'report-verify', right_id: 'incident-verification', shared_scope: 'continuity:operator-lane' }] },
    priority_articles: [{ id: 'report-verify', title: 'verify latest report', importance: 'high', coverage_band: 'serviceable', freshness: 'fresh', summary: 'Verify is the main guarded proof for checkpoint custody.' }],
    watch_articles: [{ id: 'incident-verify', title: 'Verify incident', importance: 'high', coverage_band: 'thin', freshness: 'watch', summary: 'A contradiction candidate still needs reconciliation.' }],
    errors: [],
    warnings: ['1 contradiction candidate needs reconciliation.'],
  };
  const knowledgeSnapshot = {
    generated_at: '2026-04-03T12:00:00Z',
    status: 'WARN',
    operator_summary: 'Knowledge Plane is usable with warnings.',
    manifest: {
      article_count: 4,
      stats: { strong: 2, serviceable: 2, thin: 0, grounded: 3, stable: 1, critical: 0, high: 3, medium: 1, low: 0 },
      kind_counts: { continuity_report: 3, continuity_incident: 1 },
      topic_counts: { verify: 1, rehydrate: 1, gateway_reset: 1, verification: 1 },
      source_coverage: { expected_report_targets: ['single-machine-readiness', 'verify', 'rehydrate', 'gateway-reset', 'cron-continuity'], present_report_targets: ['single-machine-readiness', 'verify', 'rehydrate', 'gateway-reset', 'cron-continuity'], missing_report_targets: [] },
    },
    compile: { ...knowledgeCompile, lifecycle: { grounded: 3, stable: 1, critical: 0, high: 3, medium: 1, low: 0 }, source_coverage: { expected_report_targets: ['single-machine-readiness', 'verify', 'rehydrate', 'gateway-reset', 'cron-continuity'], present_report_targets: ['single-machine-readiness', 'verify', 'rehydrate', 'gateway-reset', 'cron-continuity'], missing_report_targets: [] }, priority_articles: knowledgeHealth.priority_articles },
    lint: { ...knowledgeLint, source_gaps: { expected_report_targets: ['single-machine-readiness', 'verify', 'rehydrate', 'gateway-reset', 'cron-continuity'], present_report_targets: ['single-machine-readiness', 'verify', 'rehydrate', 'gateway-reset', 'cron-continuity'], missing_report_targets: [] }, contradictions: knowledgeHealth.contradictions },
    health: knowledgeHealth,
    priority_articles: knowledgeHealth.priority_articles,
    watch_articles: knowledgeHealth.watch_articles,
    articles: [],
  };

  window.__installContinuityScenario = async function __installContinuityScenario(mode) {
    const state = {
      checkpointCount: 0,
      verifyCount: 0,
      rehydrateCount: 0,
      checkpoint: null,
      verify: null,
      rehydrate: null,
    };
    const initialVerify = { status: 'WARN', generated_at: '2026-04-03T12:00:00Z', operator_summary: 'Run verify after checkpoint.' };
    const initialRehydrate = { status: 'WARN', generated_at: '2026-04-03T12:00:00Z', operator_summary: 'Run verify successfully before rehydrate.' };
    const readiness = mode === 'stale'
      ? { status: 'WARN', operator_summary: 'Single-machine readiness is usable with warnings, but not every operator surface has been exercised recently.' }
      : { status: 'PASS', operator_summary: 'Single-machine one-human-many-agents readiness is green for the active Hermes profile.' };
    window.__continuitySmokeScenarioState = state;

    function currentVerify() {
      return state.verify || initialVerify;
    }
    function currentRehydrate() {
      return state.rehydrate || initialRehydrate;
    }

    function currentSummary() {
      const verifyPayload = currentVerify();
      const rehydratePayload = currentRehydrate();
      return {
        summary: {
          generated_at: '2026-04-03T12:00:00Z',
          status: {
            checkpoint_id: (state.checkpoint && state.checkpoint.checkpoint_id) || verifyPayload.checkpoint_id || rehydratePayload.checkpoint_id || null,
            manifest: { exists: true, ...freshCheckpoint },
            anchor: { exists: true, ...freshCheckpoint },
          },
          reports: {
            verify: { status: verifyPayload.status, freshness: fresh, freshness_semantics: semantics('verify', 'FRESH') },
            rehydrate: { status: rehydratePayload.status, freshness: fresh, freshness_semantics: semantics('rehydrate', 'FRESH') },
            'gateway-reset': { status: 'PASS', freshness: fresh, freshness_semantics: semantics('gateway-reset', 'FRESH') },
            'cron-continuity': { status: 'PASS', freshness: fresh, freshness_semantics: semantics('cron-continuity', 'NOT_RECENTLY_EXERCISED') },
            'knowledge-health': { status: knowledgeHealth.status, freshness: fresh, freshness_semantics: semantics('knowledge-health', 'FRESH') },
          },
          benchmark: benchmark.benchmark,
          readiness,
          incidents,
          knowledge: {
            compile: knowledgeCompile,
            lint: knowledgeLint,
            health: knowledgeHealth,
            manifest: { article_count: 4, stats: { strong: 2, serviceable: 2, thin: 0 } },
          },
          external_memory: { QUARANTINED: 0, PENDING: 0, PROMOTED: 0, REJECTED: 0 },
        },
      };
    }

    await window.__continuityApplySmokeFixtures({
      get: {
        '/api/continuity/summary': () => currentSummary(),
        '/api/continuity/sessions': () => ({ sessions: roster }),
        '/api/continuity/knowledge': () => ({ knowledge: knowledgeSnapshot }),
        '/api/continuity/incidents': () => ({ incidents }),
        '/api/continuity/benchmark': () => benchmark,
        '/api/continuity/report/single-machine-readiness': () => report('single-machine-readiness', { ...readiness, generated_at: '2026-04-03T12:00:00Z' }),
        '/api/continuity/report/verify': () => report('verify', currentVerify()),
        '/api/continuity/report/rehydrate': () => report('rehydrate', currentRehydrate()),
        '/api/continuity/report/gateway-reset': () => report('gateway-reset', {
          status: 'PASS',
          generated_at: '2026-04-03T12:00:00Z',
          operator_summary: 'Gateway continuity captured an automatic daily reset.',
          subject: { session_key: 'agent:main:telegram:dm:123', old_session_id: 'sess_old', new_session_id: 'sess_source', event_class: 'automatic_reset' },
        }),
        '/api/continuity/report/cron-continuity': () => report('cron-continuity', {
          status: 'PASS',
          generated_at: '2026-04-03T12:00:00Z',
          operator_summary: 'Cron continuity skipped a stale missed run and fast-forwarded to the next safe execution time.',
          subject: { job_id: 'job_fixture', event_class: 'stale_fast_forward' },
        }, 'STALE', 'NOT_RECENTLY_EXERCISED'),
        '/api/continuity/report/knowledge-compile': () => report('knowledge-compile', knowledgeCompile),
        '/api/continuity/report/knowledge-lint': () => report('knowledge-lint', knowledgeLint),
        '/api/continuity/report/knowledge-health': () => report('knowledge-health', knowledgeHealth),
      },
      post: {
        '/api/continuity/actions/checkpoint': (body) => {
          state.checkpointCount += 1;
          state.checkpoint = {
            status: 'PASS',
            checkpoint_id: mode === 'stale' ? `ckpt_stale_${state.checkpointCount}` : 'ckpt_happy',
            session_id: body.session_id,
          };
          return { action: { ok: true, action: 'checkpoint', result: state.checkpoint, errors: [] } };
        },
        '/api/continuity/actions/verify': () => {
          state.verifyCount += 1;
          if (mode === 'stale' && state.verifyCount === 1) {
            state.verify = {
              status: 'FAIL',
              failure_class: 'stale_live_checkpoint',
              operator_summary: 'Checkpoint custody no longer matches the live profile state.',
              remediation: [
                'Create a fresh checkpoint from current truth.',
                'Re-run verify to confirm checkpoint custody is green again.',
                'Then re-run rehydrate using the target_session_id you actually want.',
              ],
            };
          } else {
            state.verify = {
              status: 'PASS',
              checkpoint_id: (state.checkpoint && state.checkpoint.checkpoint_id) || 'ckpt_happy',
              operator_summary: 'Continuity verification passed.',
            };
          }
          return { action: { ok: true, action: 'verify', result: state.verify, errors: [] } };
        },
        '/api/continuity/actions/rehydrate': (body) => {
          state.rehydrateCount += 1;
          state.rehydrate = {
            status: 'PASS',
            checkpoint_id: (state.checkpoint && state.checkpoint.checkpoint_id) || 'ckpt_happy',
            session_outcome: {
              mode: 'existing_target_session',
              label: 'Reused existing target session',
              resulting_session_id: body.target_session_id,
            },
          };
          return { action: { ok: true, action: 'rehydrate', result: state.rehydrate, errors: [] } };
        },
      },
    });
  };
})();
