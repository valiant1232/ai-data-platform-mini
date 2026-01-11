import React, { useEffect, useMemo, useState } from "react";

/**
 * Minimal Admin/Annotator Console for AI Data Platform Mini
 * - Login (admin / annotator)
 * - Dataset list, stats
 * - Trigger jobs: import/export/prelabel/score_uncertainty
 * - Jobs list + job detail
 * - Priority tasks + auto_assign
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function apiFetch(path, { token, method = "GET", body } = {}) {
  const headers = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  // try parse json; if not, surface text
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const msg =
      data?.detail?.[0]?.msg ||
      data?.detail ||
      data?.message ||
      data?.raw ||
      `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

function Badge({ children }) {
  return (
    <span
      style={{
        padding: "2px 8px",
        border: "1px solid #ddd",
        borderRadius: 999,
        fontSize: 12,
        marginLeft: 8,
      }}
    >
      {children}
    </span>
  );
}

export default function App() {
  const [role, setRole] = useState("admin");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [token, setToken] = useState(localStorage.getItem("token") || "");
  const [me, setMe] = useState(null);

  const [datasets, setDatasets] = useState([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [stats, setStats] = useState(null);

  const [jobs, setJobs] = useState([]);
  const [jobIdToView, setJobIdToView] = useState("");
  const [jobDetail, setJobDetail] = useState(null);

  const [priorityLimit, setPriorityLimit] = useState(10);
  const [priorityTasks, setPriorityTasks] = useState(null);

  const [assignUser, setAssignUser] = useState("ann");
  const [assignCount, setAssignCount] = useState(5);

  const [log, setLog] = useState([]);
  const pushLog = (line) =>
    setLog((prev) => [`${new Date().toLocaleTimeString()}  ${line}`, ...prev].slice(0, 50));

  const authed = useMemo(() => Boolean(token), [token]);

  // Load /me on token
  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const data = await apiFetch("/me", { token });
        setMe(data);
      } catch (e) {
        pushLog(`me failed: ${e.message}`);
        setMe(null);
      }
    })();
  }, [token]);

  // Basic helpers
  const ensureDatasetId = () => {
    const id = selectedDatasetId || "";
    if (!id) throw new Error("请选择 dataset_id");
    return id;
  };

  async function doLogin(e) {
    e?.preventDefault?.();
    try {
      const data = await apiFetch("/auth/login", {
        method: "POST",
        body: { username, password },
      });
      const t = data.access_token;
      setToken(t);
      localStorage.setItem("token", t);
      pushLog(`login ok: role=${data.role}`);
    } catch (e2) {
      pushLog(`login failed: ${e2.message}`);
      alert(`登录失败：${e2.message}`);
    }
  }

  function doLogout() {
    setToken("");
    setMe(null);
    localStorage.removeItem("token");
    pushLog("logout");
  }

  async function loadDatasets() {
    try {
      // If you don't have /datasets GET, we fallback to DB via stats endpoints won't work.
      // Assuming you added list endpoint; if not, we can add minimal endpoint later.
      const data = await apiFetch("/datasets", { token });
      setDatasets(data.datasets || data || []);
      pushLog(`datasets loaded: ${(data.datasets || data || []).length}`);
    } catch (e) {
      pushLog(`load datasets failed: ${e.message}`);
      alert(`加载 datasets 失败：${e.message}\n\n如果后端没有 GET /datasets，我们可以立刻补一个最小接口。`);
    }
  }

  async function loadStats() {
    try {
      const id = ensureDatasetId();
      const data = await apiFetch(`/datasets/${id}/stats`, { token });
      setStats(data);
      pushLog(`stats loaded: dataset=${id}`);
    } catch (e) {
      pushLog(`load stats failed: ${e.message}`);
      alert(`stats 失败：${e.message}`);
    }
  }

  async function triggerJob(kind) {
    try {
      const id = ensureDatasetId();
      let path = "";
      if (kind === "import") path = `/datasets/${id}/import_to_ls`;
      if (kind === "export") path = `/datasets/${id}/export_from_ls`;
      if (kind === "prelabel") path = `/datasets/${id}/prelabel`;
      if (kind === "score") path = `/datasets/${id}/score_uncertainty?limit=100&only_unlabeled=true`;

      const data = await apiFetch(path, { token, method: "POST" });
      pushLog(`${kind} job queued: job_id=${data.job_id}`);
      setJobIdToView(String(data.job_id));
      await loadJob(data.job_id);
    } catch (e) {
      pushLog(`trigger ${kind} failed: ${e.message}`);
      alert(`${kind} 失败：${e.message}`);
    }
  }

  async function loadJobs() {
    try {
      const data = await apiFetch("/jobs", { token });
      const arr = data.jobs || data || [];
      setJobs(arr);
      pushLog(`jobs loaded: ${arr.length}`);
    } catch (e) {
      pushLog(`load jobs failed: ${e.message}`);
      alert(`加载 jobs 失败：${e.message}\n\n如果后端没有 GET /jobs，我们可以立刻补一个最小接口。`);
    }
  }

  async function loadJob(id) {
    try {
      const data = await apiFetch(`/jobs/${id}`, { token });
      setJobDetail(data);
      pushLog(`job loaded: ${id} status=${data.status}`);
    } catch (e) {
      pushLog(`load job failed: ${e.message}`);
      alert(`加载 job 失败：${e.message}`);
    }
  }

  async function loadPriorityTasks() {
    try {
      const id = ensureDatasetId();
      const data = await apiFetch(`/datasets/${id}/priority_tasks?limit=${priorityLimit}`, { token });
      setPriorityTasks(data);
      pushLog(`priority_tasks loaded: ${data.tasks?.length ?? 0}`);
    } catch (e) {
      pushLog(`priority_tasks failed: ${e.message}`);
      alert(`priority_tasks 失败：${e.message}`);
    }
  }

  async function doAutoAssign() {
    try {
      const id = ensureDatasetId();
      const data = await apiFetch(
        `/datasets/${id}/auto_assign?username=${encodeURIComponent(assignUser)}&count=${assignCount}`,
        { token, method: "POST" }
      );
      pushLog(`auto_assign ok: assigned=${data.assigned} to ${data.assigned_to}`);
      await loadPriorityTasks();
      await loadStats();
    } catch (e) {
      pushLog(`auto_assign failed: ${e.message}`);
      alert(`auto_assign 失败：${e.message}`);
    }
  }

  return (
    <div style={{ fontFamily: "ui-sans-serif, system-ui", padding: 20, maxWidth: 1100, margin: "0 auto" }}>
      <h2 style={{ marginTop: 0 }}>AI Data Platform Mini Console</h2>
      <div style={{ opacity: 0.75, marginBottom: 12 }}>
        API: <code>{API_BASE}</code>
      </div>

      {/* Auth */}
      <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 16, marginBottom: 16 }}>
        <h3 style={{ margin: "0 0 12px 0" }}>1) 登录</h3>

        {!authed ? (
          <form onSubmit={doLogin} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <select
              value={role}
              onChange={(e) => {
                const r = e.target.value;
                setRole(r);
                if (r === "admin") {
                  setUsername("admin");
                  setPassword("admin123");
                } else {
                  setUsername("ann");
                  setPassword("ann123");
                }
              }}
            >
              <option value="admin">admin</option>
              <option value="annotator">annotator</option>
            </select>
            <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username" />
            <input value={password} onChange={(e) => setPassword(e.target.value)} placeholder="password" type="password" />
            <button type="submit">Login</button>
          </form>
        ) : (
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <div>
              Logged in <Badge>{me?.role || "unknown"}</Badge>{" "}
              <Badge>{me?.username || "me"}</Badge>
            </div>
            <button onClick={doLogout}>Logout</button>
            <button onClick={loadDatasets}>Load datasets</button>
            <button onClick={loadJobs}>Load jobs</button>
          </div>
        )}
      </div>

      {/* Main */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Left */}
        <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 16 }}>
          <h3 style={{ margin: "0 0 12px 0" }}>2) Dataset 与 Stats</h3>

          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <label>dataset_id:</label>
            <input
              value={selectedDatasetId}
              onChange={(e) => setSelectedDatasetId(e.target.value)}
              placeholder="例如 4"
              style={{ width: 120 }}
            />
            <button onClick={loadStats}>Load stats</button>
          </div>

          {datasets?.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Datasets</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {datasets.map((d) => (
                  <button
                    key={d.id}
                    onClick={() => setSelectedDatasetId(String(d.id))}
                    style={{
                      textAlign: "left",
                      padding: "8px 10px",
                      borderRadius: 10,
                      border: "1px solid #ddd",
                      background: selectedDatasetId == d.id ? "#f3f4f6" : "white",
                    }}
                  >
                    #{d.id} — {d.name || "(no name)"} <span style={{ opacity: 0.6 }}>({d.created_at || ""})</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {stats && (
            <div style={{ marginTop: 12, padding: 12, border: "1px solid #eee", borderRadius: 10 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Stats</div>
              <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{JSON.stringify(stats, null, 2)}</pre>
            </div>
          )}

          <hr style={{ margin: "16px 0" }} />

          <h3 style={{ margin: "0 0 12px 0" }}>3) 触发 Job</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button onClick={() => triggerJob("import")}>import_to_ls</button>
            <button onClick={() => triggerJob("export")}>export_from_ls</button>
            <button onClick={() => triggerJob("prelabel")}>prelabel</button>
            <button onClick={() => triggerJob("score")}>score_uncertainty</button>
          </div>
        </div>

        {/* Right */}
        <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 16 }}>
          <h3 style={{ margin: "0 0 12px 0" }}>4) Jobs</h3>

          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <input
              value={jobIdToView}
              onChange={(e) => setJobIdToView(e.target.value)}
              placeholder="job_id"
              style={{ width: 120 }}
            />
            <button onClick={() => loadJob(jobIdToView)}>Load job</button>
          </div>

          {jobs?.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Latest jobs</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 220, overflow: "auto" }}>
                {jobs.slice(0, 30).map((j) => (
                  <button
                    key={j.id}
                    onClick={() => {
                      setJobIdToView(String(j.id));
                      loadJob(j.id);
                    }}
                    style={{
                      textAlign: "left",
                      padding: "8px 10px",
                      borderRadius: 10,
                      border: "1px solid #ddd",
                      background: String(jobIdToView) === String(j.id) ? "#f3f4f6" : "white",
                    }}
                  >
                    #{j.id} — {j.type} — <b>{j.status}</b> <span style={{ opacity: 0.6 }}>ds={j.dataset_id}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {jobDetail && (
            <div style={{ marginTop: 12, padding: 12, border: "1px solid #eee", borderRadius: 10 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>
                Job detail <Badge>{jobDetail.status}</Badge>
              </div>
              <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{JSON.stringify(jobDetail, null, 2)}</pre>
            </div>
          )}

          <hr style={{ margin: "16px 0" }} />

          <h3 style={{ margin: "0 0 12px 0" }}>5) Priority tasks & Auto assign</h3>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <label>limit</label>
            <input
              value={priorityLimit}
              onChange={(e) => setPriorityLimit(Number(e.target.value))}
              type="number"
              style={{ width: 90 }}
            />
            <button onClick={loadPriorityTasks}>Load priority_tasks</button>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 10 }}>
            <label>assign to</label>
            <input value={assignUser} onChange={(e) => setAssignUser(e.target.value)} style={{ width: 120 }} />
            <label>count</label>
            <input
              value={assignCount}
              onChange={(e) => setAssignCount(Number(e.target.value))}
              type="number"
              style={{ width: 90 }}
            />
            <button onClick={doAutoAssign}>auto_assign</button>
          </div>

          {priorityTasks?.tasks && (
            <div style={{ marginTop: 12, padding: 12, border: "1px solid #eee", borderRadius: 10 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>
                priority_tasks <Badge>{priorityTasks.tasks.length}</Badge>
              </div>
              <div style={{ maxHeight: 260, overflow: "auto" }}>
                {priorityTasks.tasks.map((t) => (
                  <div
                    key={t.task_id}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "70px 70px 90px 90px 1fr",
                      gap: 8,
                      padding: "6px 0",
                      borderBottom: "1px dashed #eee",
                      alignItems: "center",
                      fontSize: 13,
                    }}
                  >
                    <div>#{t.task_id}</div>
                    <div>LS {t.ls_task_id}</div>
                    <div>{(t.uncertainty_score ?? "").toFixed?.(2) ?? t.uncertainty_score}</div>
                    <div>{t.priority}</div>
                    <div style={{ opacity: 0.85 }}>
                      {t.prelabel_label}{" "}
                      <span style={{ opacity: 0.6 }}>
                        {t.assigned_to ? `→ ${t.assigned_to}` : ""}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Log */}
      <div style={{ marginTop: 16, border: "1px solid #eee", borderRadius: 12, padding: 16 }}>
        <h3 style={{ margin: "0 0 12px 0" }}>Log</h3>
        <div style={{ fontFamily: "ui-monospace, SFMono-Regular", fontSize: 12, maxHeight: 200, overflow: "auto" }}>
          {log.map((l, idx) => (
            <div key={idx} style={{ padding: "2px 0" }}>
              {l}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}