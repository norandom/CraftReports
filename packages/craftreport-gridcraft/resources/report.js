/**
 * GridCraft Report Lifecycle Controls and Freshness Client.
 *
 * Implements GoF Command, Strategy, Observer, and Gateway patterns for
 * accessible, truthful shared lifecycle management without god files.
 */
(() => {
  'use strict';

  // --- Utility Functions ---

  function generateUuid() {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  function formatTime(isoString) {
    if (!isoString || typeof isoString !== 'string' || !isoString.trim()) {
      return 'unknown';
    }
    const ms = Date.parse(isoString);
    if (isNaN(ms) || ms <= 0) {
      return 'unknown';
    }
    return isoString;
  }

  // --- Configuration ---

  function resolveConfig() {
    const el = document.getElementById('report-app');
    const dataset = el ? el.dataset : {};
    const winConfig = window.__REPORT_CONFIG__ || {};

    return {
      apiUrl: winConfig.apiUrl ?? dataset.apiUrl ?? '',
      bindingId: winConfig.bindingId ?? dataset.bindingId ?? 'binding-1',
      intervalSeconds: Number(winConfig.intervalSeconds ?? dataset.intervalSeconds ?? 10),
      staleThresholdSeconds: Number(winConfig.staleThresholdSeconds ?? dataset.staleThresholdSeconds ?? 30),
      pollIntervalMs: Number(winConfig.pollIntervalMs ?? 2000),
      headers: winConfig.headers ?? {}
    };
  }

  // --- Strategy Pattern: Freshness Evaluation ---

  class FreshnessStrategy {
    evaluate(state, nowMs, config) {
      if (state.last_error && state.last_error !== 'none') {
        return {
          status: 'stale',
          measure: `error: ${state.last_error}`
        };
      }

      if (state.last_effect && ['partial', 'ambiguous', 'failed'].includes(state.last_effect)) {
        return {
          status: 'stale',
          measure: `effect_${state.last_effect}`
        };
      }

      const refTime = state.applied_at || state.last_completed_at;
      if (!refTime || refTime === 'unknown') {
        return {
          status: 'unknown',
          measure: 'no_timestamp_recorded'
        };
      }

      const parsedMs = Date.parse(refTime);
      if (isNaN(parsedMs) || parsedMs <= 0) {
        return {
          status: 'unknown',
          measure: 'invalid_timestamp'
        };
      }

      const elapsedSeconds = Math.max(0, (nowMs - parsedMs) / 1000);
      const threshold = config.staleThresholdSeconds || 30;

      if (elapsedSeconds > threshold) {
        return {
          status: 'stale',
          measure: `last_applied_age: ${Math.round(elapsedSeconds)}s exceeds threshold ${threshold}s`
        };
      }

      return {
        status: 'fresh',
        measure: `age: ${Math.round(elapsedSeconds)}s <= ${threshold}s`
      };
    }
  }

  // --- Command Pattern: Lifecycle Commands ---

  class LifecycleCommand {
    constructor(action, expectedGeneration, bindingId) {
      this.action = action;
      this.expectedGeneration = expectedGeneration;
      this.bindingId = bindingId;
    }

    createEnvelope() {
      return {
        operation: {
          name: 'runtime.control',
          contract_version: '1'
        },
        correlation_id: generateUuid(),
        retry_key: generateUuid(),
        declared_resources: [
          {
            kind: 'binding',
            identity: this.bindingId
          }
        ],
        payload: {
          binding_id: this.bindingId,
          action: this.action,
          expected_generation: String(this.expectedGeneration)
        }
      };
    }

    async execute(apiClient) {
      const envelope = this.createEnvelope();
      return await apiClient.invoke(envelope);
    }
  }

  class StartCommand extends LifecycleCommand {
    constructor(expectedGeneration, bindingId) {
      super('start', expectedGeneration, bindingId);
    }
  }

  class PauseCommand extends LifecycleCommand {
    constructor(expectedGeneration, bindingId) {
      super('pause', expectedGeneration, bindingId);
    }
  }

  class ResumeCommand extends LifecycleCommand {
    constructor(expectedGeneration, bindingId) {
      super('resume', expectedGeneration, bindingId);
    }
  }

  class StopCommand extends LifecycleCommand {
    constructor(expectedGeneration, bindingId) {
      super('stop', expectedGeneration, bindingId);
    }
  }

  class CommandFactory {
    static create(action, state, config) {
      const gen = state.generation || 0;
      const bId = config.bindingId;
      switch (action) {
        case 'start':
          return new StartCommand(gen, bId);
        case 'pause':
          return new PauseCommand(gen, bId);
        case 'resume':
          return new ResumeCommand(gen, bId);
        case 'stop':
          return new StopCommand(gen, bId);
        default:
          throw new Error(`Unknown lifecycle action: ${action}`);
      }
    }
  }

  // --- Gateway / Adapter Pattern: Runtime API Client ---

  class RuntimeApiClient {
    constructor(baseUrl, headers = {}) {
      this.baseUrl = baseUrl.replace(/\/+$/, '');
      this.headers = headers;
    }

    async invoke(envelope) {
      const url = `${this.baseUrl}/v1/invoke`;
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...this.headers
        },
        body: JSON.stringify(envelope)
      });
      return await response.json();
    }

    async inspectBinding(bindingId) {
      const envelope = {
        operation: {
          name: 'runtime.inspect',
          contract_version: '1'
        },
        correlation_id: generateUuid(),
        retry_key: generateUuid(),
        declared_resources: [
          {
            kind: 'binding',
            identity: bindingId
          }
        ],
        payload: {
          kind: 'binding',
          identity: bindingId
        }
      };
      return await this.invoke(envelope);
    }
  }

  // --- Pluggable Wiring / Test Hook ---

  class ControlWiring {
    constructor() {
      this._wired = true;
    }

    isWired() {
      if (typeof window !== 'undefined' && window.__DISCONNECT_CONTROLS__ === true) {
        return false;
      }
      return this._wired;
    }

    setWiring(enabled) {
      this._wired = Boolean(enabled);
    }
  }

  // --- Observer Pattern: ReportStore & ReportView ---

  class ReportStore {
    constructor(config, freshnessStrategy) {
      this.config = config;
      this.freshnessStrategy = freshnessStrategy;
      this.listeners = [];
      this.state = {
        generation: 0,
        revision: 0,
        intent: 'stopped',
        pause_pending: false,
        recovery_required: false,
        selected_run_id: null,
        applied_run_id: null,
        pending_operation_id: null,
        last_effect: null,
        last_error: null,
        last_attempt_at: null,
        last_completed_at: null,
        latest_accepted_version: null,
        latest_complete_accepted_version: null,
        applied_version: null,
        applied_at: null,
        apply_latency_ms: null,
        freshness_status: 'unknown',
        freshness_measure: 'no_timestamp_recorded'
      };
    }

    subscribe(listener) {
      this.listeners.push(listener);
      listener(this.state);
    }

    notify() {
      for (const listener of this.listeners) {
        listener(this.state);
      }
    }

    updateFromBindingState(serverState, nowMs = Date.now()) {
      if (!serverState || typeof serverState !== 'object') return;

      const gen = Number(serverState.generation ?? this.state.generation);
      const rev = Number(serverState.revision ?? this.state.revision);
      const intent = serverState.intent ?? this.state.intent;
      const pausePending = Boolean(serverState.pause_pending);
      const recoveryRequired = Boolean(serverState.recovery_required);
      const selectedRunId = serverState.selected_run_id ?? null;
      const appliedRunId = serverState.applied_run_id ?? null;
      const pendingOpId = serverState.pending_operation_id ?? null;
      const lastEffect = serverState.last_effect ?? null;
      const lastError = serverState.last_error ?? null;
      const lastAttemptAt = serverState.last_attempt_at ?? null;
      const lastCompletedAt = serverState.last_completed_at ?? null;

      let latestAcceptedVersion = this.state.latest_accepted_version;
      let latestCompleteAcceptedVersion = this.state.latest_complete_accepted_version;
      if (serverState.latest_complete_snapshot) {
        latestCompleteAcceptedVersion = String(serverState.latest_complete_snapshot.version);
        if (!latestAcceptedVersion || Number(latestCompleteAcceptedVersion) > Number(latestAcceptedVersion)) {
          latestAcceptedVersion = latestCompleteAcceptedVersion;
        }
      }
      if (serverState.latest_accepted_snapshot) {
        latestAcceptedVersion = String(serverState.latest_accepted_snapshot.version);
      }

      let appliedVersion = this.state.applied_version;
      let appliedAt = this.state.applied_at;
      if (serverState.applied_snapshot) {
        appliedVersion = String(serverState.applied_snapshot.version);
        appliedAt = serverState.applied_snapshot.created_at || lastCompletedAt;
      }

      let applyLatencyMs = this.state.apply_latency_ms;
      if (lastAttemptAt && lastCompletedAt) {
        const attemptMs = Date.parse(lastAttemptAt);
        const completeMs = Date.parse(lastCompletedAt);
        if (!isNaN(attemptMs) && !isNaN(completeMs) && completeMs >= attemptMs) {
          applyLatencyMs = completeMs - attemptMs;
        }
      }

      const tempState = {
        ...this.state,
        generation: gen,
        revision: rev,
        intent,
        pause_pending: pausePending,
        recovery_required: recoveryRequired,
        selected_run_id: selectedRunId,
        applied_run_id: appliedRunId,
        pending_operation_id: pendingOpId,
        last_effect: lastEffect,
        last_error: lastError,
        last_attempt_at: lastAttemptAt,
        last_completed_at: lastCompletedAt,
        latest_accepted_version: latestAcceptedVersion,
        latest_complete_accepted_version: latestCompleteAcceptedVersion,
        applied_version: appliedVersion,
        applied_at: appliedAt,
        apply_latency_ms: applyLatencyMs
      };

      const fresh = this.freshnessStrategy.evaluate(tempState, nowMs, this.config);
      tempState.freshness_status = fresh.status;
      tempState.freshness_measure = fresh.measure;

      this.state = tempState;
      this.notify();
    }

    setPausePending(pending) {
      this.state = {
        ...this.state,
        pause_pending: Boolean(pending)
      };
      this.notify();
    }

    setError(errorText) {
      this.state = {
        ...this.state,
        last_error: errorText,
        freshness_status: 'stale',
        freshness_measure: `error: ${errorText}`
      };
      this.notify();
    }
  }

  class ReportView {
    constructor() {
      this.btnStart = document.getElementById('control-start');
      this.btnPause = document.getElementById('control-pause');
      this.btnResume = document.getElementById('control-resume');
      this.btnStop = document.getElementById('control-stop');

      this.statusRegion = document.getElementById('status-region');
      this.refreshInterval = document.getElementById('refresh-interval');
      this.applyLatency = document.getElementById('apply-latency');
      this.pendingWork = document.getElementById('pending-work');
      this.lastAttemptAt = document.getElementById('last-attempt-at');
      this.lastCompletedAt = document.getElementById('last-completed-at');
      this.latestAcceptedVersion = document.getElementById('latest-accepted-version');
      this.latestCompleteAcceptedVersion = document.getElementById('latest-complete-accepted-version');
      this.selectedRunId = document.getElementById('selected-run-id');
      this.appliedVersion = document.getElementById('applied-version');
      this.appliedAt = document.getElementById('applied-at');
      this.intentState = document.getElementById('intent-state');
      this.freshnessStatus = document.getElementById('freshness-status');
      this.freshnessMeasure = document.getElementById('freshness-measure');
      this.outcomeStatus = document.getElementById('outcome-status');
      this.lastError = document.getElementById('last-error');
    }

    render(state, config) {
      if (this.refreshInterval) {
        this.refreshInterval.textContent = `${config.intervalSeconds}s (configured cadence)`;
      }

      if (this.applyLatency) {
        this.applyLatency.textContent = state.apply_latency_ms !== null ? `${state.apply_latency_ms}ms` : 'unknown';
      }

      if (this.pendingWork) {
        if (state.pending_operation_id) {
          this.pendingWork.textContent = `op:${state.pending_operation_id}`;
        } else if (state.pause_pending) {
          this.pendingWork.textContent = 'pause pending';
        } else {
          this.pendingWork.textContent = 'none';
        }
      }

      if (this.lastAttemptAt) this.lastAttemptAt.textContent = formatTime(state.last_attempt_at);
      if (this.lastCompletedAt) this.lastCompletedAt.textContent = formatTime(state.last_completed_at);
      if (this.latestAcceptedVersion) this.latestAcceptedVersion.textContent = state.latest_accepted_version || 'unknown';
      if (this.latestCompleteAcceptedVersion) this.latestCompleteAcceptedVersion.textContent = state.latest_complete_accepted_version || 'unknown';
      if (this.selectedRunId) this.selectedRunId.textContent = state.selected_run_id || 'none';
      if (this.appliedVersion) this.appliedVersion.textContent = state.applied_version || 'unknown';
      if (this.appliedAt) this.appliedAt.textContent = formatTime(state.applied_at);

      const effectiveIntent = state.pause_pending ? 'pause pending' : state.intent;
      if (this.intentState) this.intentState.textContent = effectiveIntent;

      if (this.freshnessStatus) {
        const badgeClass = state.freshness_status === 'fresh'
          ? 'badge-fresh'
          : (state.freshness_status === 'stale' ? 'badge-stale' : 'badge-unknown');
        this.freshnessStatus.innerHTML = `<span class="badge ${badgeClass}">${state.freshness_status}</span>`;
      }

      if (this.freshnessMeasure) {
        this.freshnessMeasure.textContent = state.freshness_measure || 'none';
      }

      if (this.outcomeStatus) {
        this.outcomeStatus.textContent = state.last_effect || 'none';
      }

      if (this.lastError) {
        this.lastError.textContent = state.last_error || 'none';
      }

      // ARIA Status Region & Intent-based Button Disabling
      if (this.statusRegion) {
        this.statusRegion.dataset.intent = state.intent;
        let message = `Lifecycle: ${effectiveIntent}.`;
        if (state.last_error && state.last_error !== 'none') {
          message += ` Error: ${state.last_error}.`;
        } else if (state.applied_version) {
          message += ` Last applied version: ${state.applied_version} (${state.freshness_status}).`;
        }
        if (state.pause_pending) {
          message += ' In-flight mutation finishing before pause.';
        }
        this.statusRegion.textContent = message;
      }

      // Button states
      if (this.btnStart) this.btnStart.disabled = (state.intent === 'running' || state.pause_pending);
      if (this.btnPause) this.btnPause.disabled = (state.intent !== 'running' || state.pause_pending);
      if (this.btnResume) this.btnResume.disabled = (state.intent !== 'paused');
      if (this.btnStop) this.btnStop.disabled = (state.intent === 'stopped');
    }
  }

  // --- Controller: ReportController ---

  class ReportController {
    constructor(config, store, view, apiClient, wiring) {
      this.config = config;
      this.store = store;
      this.view = view;
      this.apiClient = apiClient;
      this.wiring = wiring;
      this.pollTimer = null;
    }

    init() {
      this.store.subscribe((state) => this.view.render(state, this.config));
      this.bindEvents();
      this.startPolling();
    }

    bindEvents() {
      const actions = [
        ['control-start', 'start'],
        ['control-pause', 'pause'],
        ['control-resume', 'resume'],
        ['control-stop', 'stop']
      ];

      for (const [btnId, action] of actions) {
        const btn = document.getElementById(btnId);
        if (btn) {
          btn.addEventListener('click', () => this.handleAction(action));
        }
      }
    }

    async handleAction(action) {
      // Check pluggable wiring / test hook
      if (!this.wiring.isWired()) {
        const errorMsg = 'Control wiring disconnected: command blocked';
        this.store.setError(errorMsg);
        const event = new CustomEvent('control:disconnected', { detail: { action } });
        document.dispatchEvent(event);
        return;
      }

      if (action === 'pause') {
        this.store.setPausePending(true);
      }

      try {
        const command = CommandFactory.create(action, this.store.state, this.config);
        const result = await command.execute(this.apiClient);

        // Process invocation result
        if (result && result.proposal && result.proposal.value) {
          this.store.updateFromBindingState(result.proposal.value);
        } else if (result && result.state) {
          this.store.updateFromBindingState(result.state);
        } else if (result && result.rejection) {
          const diag = result.rejection.diagnostic;
          const msg = diag ? `${diag.category}: ${diag.code}` : 'Operation rejected';
          this.store.setError(msg);
        }
      } catch (err) {
        this.store.setError(err.message || String(err));
      }
    }

    startPolling() {
      if (this.pollTimer) clearInterval(this.pollTimer);
      this.pollTimer = setInterval(() => this.pollState(), this.config.pollIntervalMs);
      // Run initial inspect
      this.pollState();
    }

    stopPolling() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer);
        this.pollTimer = null;
      }
    }

    async pollState() {
      try {
        const result = await this.apiClient.inspectBinding(this.config.bindingId);
        if (result && result.proposal && result.proposal.value) {
          this.store.updateFromBindingState(result.proposal.value);
        } else if (result && result.state) {
          this.store.updateFromBindingState(result.state);
        }
      } catch {
        // Read-only polling silent on transport glitch; does not overwrite with fake state
      }
    }
  }

  // --- Bootstrap and Public Application Expose ---

  const config = resolveConfig();
  const freshnessStrategy = new FreshnessStrategy();
  const store = new ReportStore(config, freshnessStrategy);
  const view = new ReportView();
  const apiClient = new RuntimeApiClient(config.apiUrl, config.headers);
  const wiring = new ControlWiring();
  const controller = new ReportController(config, store, view, apiClient, wiring);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => controller.init());
  } else {
    controller.init();
  }

  window.reportApp = {
    config,
    store,
    view,
    apiClient,
    wiring,
    controller,
    freshnessStrategy,
    CommandFactory,
    setControlWiring: (enabled) => wiring.setWiring(enabled)
  };
})();
