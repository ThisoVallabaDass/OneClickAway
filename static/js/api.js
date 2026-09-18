export async function api(path, body) {
  const options =
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        };
  options.signal = AbortSignal.timeout(20000);
  const r = await fetch(path, options);
  const data = await r.json();
  if (!r.ok) {
    const error = new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
    error.status = r.status;
    throw error;
  }
  return data;
}
export async function job(path, body, showProgress) {
  const { id } = await api(path, body);
  remember({ id, path });
  return pollJob(id, showProgress);
}

const JOB_KEY = "oneclick-away-active-job";
function remember(job) {
  try {
    if (job) sessionStorage.setItem(JOB_KEY, JSON.stringify(job));
    else sessionStorage.removeItem(JOB_KEY);
  } catch {
    /* Storage may be disabled; generation still works. */
  }
}

export function pendingJob() {
  try {
    const job = JSON.parse(sessionStorage.getItem(JOB_KEY));
    return job &&
      /^[a-f0-9]{32}$/.test(job.id) &&
      ["/api/plan", "/api/generate"].includes(job.path)
      ? job
      : null;
  } catch {
    return null;
  }
}

export async function pollJob(id, showProgress) {
  let failures = 0;
  for (;;) {
    await new Promise((r) => setTimeout(r, 700));
    let s;
    try {
      s = await api("/api/jobs/" + id);
      failures = 0;
    } catch (error) {
      if (error.status === 404) {
        remember(null);
        throw error;
      }
      if (++failures > 3) throw error;
      showProgress({
        stage: "preparing",
        message: "Reconnecting to your saved job…",
      });
      await new Promise((r) => setTimeout(r, failures * 1000));
      continue;
    }
    showProgress(s);
    if (s.status === "done" || s.status === "error") remember(null);
    if (s.status === "done") return s.result;
    if (s.status === "error") throw new Error(s.message);
  }
}
