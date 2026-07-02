/* ============================================================================
   Concourse shared shell behaviour — loaded on every page via base.html.
   - PostHog init (only when a key is configured via /config.js)
   - window.ctrack(event, props): safe event capture (no-op if unconfigured)
   - [data-logout] binding
   - Escape-to-close + scrim-click-to-close for .modal-scrim modals
   Plain script, no build step. Version-string when it changes (app.js?v=N).
   ========================================================================== */

(function initPosthog() {
  var cfg = window.__CONCOURSE__ || {};
  if (!cfg.posthogKey) return;
  /* Standard PostHog snippet (trimmed) */
  !function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey getNextSurveyStep identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing startSessionRecording stopSessionRecording startSessionReplay stopSessionReplay sessionRecordingStarted sessionReplayStarted captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_session_recording opt_out_session_recording has_opted_in_session_recording has_opted_out_session_recording clear_opt_in_out_session_recording createPerson distinct_id getDistinctId currentDistinctId currentSessionId getSessionId getPersonProperties debug getPageViewId captureTraceFeedback captureTraceMetric".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
  posthog.init(cfg.posthogKey, {
    api_host: cfg.posthogHost || 'https://eu.posthog.com',
    person_profiles: 'identified_only',
    capture_pageview: true,
  });
  /* First-touch UTM persisted by the landing page — attach as super-properties */
  try {
    var utm = JSON.parse(localStorage.getItem('concourse_utm') || 'null');
    if (utm) posthog.register(utm);
  } catch (e) { /* swallow */ }
})();

/* Safe capture: no-op when PostHog isn't configured (pilot event taxonomy). */
window.ctrack = function (event, props) {
  try { if (window.posthog) posthog.capture(event, props || {}); } catch (e) { /* swallow */ }
};

/* Log out — any element with [data-logout] */
document.addEventListener('click', async function (e) {
  var el = e.target.closest('[data-logout]');
  if (!el) return;
  e.preventDefault();
  try { await fetch('/api/auth/logout', { method: 'POST' }); } catch (err) { /* proceed */ }
  window.location.replace('/');
});

/* Modals: Escape closes; clicking the scrim closes. */
document.addEventListener('keydown', function (e) {
  if (e.key !== 'Escape') return;
  document.querySelectorAll('.modal-scrim.open').forEach(function (m) {
    m.classList.remove('open');
  });
});
document.addEventListener('click', function (e) {
  if (e.target.classList && e.target.classList.contains('modal-scrim')) {
    e.target.classList.remove('open');
  }
});
