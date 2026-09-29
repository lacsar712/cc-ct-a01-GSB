import { createSignal, onMount, Show, For, createEffect } from "solid-js";
import {
  clearSession,
  createSubmission,
  delistTool,
  fetchEvents,
  fetchSubmission,
  fetchSubmissions,
  fetchTools,
  getUser,
  login,
  registerTool,
  relistTool,
  setSession,
} from "./api";

const statusLabel = {
  pending: "待复核",
  processing: "复核中",
  done: "已完成",
  returned: "已退回",
};

const roleLabel = {
  machinist: "操作员",
  auditor: "复核员",
};

function readHash() {
  const raw = (location.hash || "#/").replace(/^#/, "") || "/";
  let m = raw.match(/^\/detail\/(\d+)/);
  if (m) return { name: "detail", id: Number(m[1]) };
  if (raw === "/roster") return { name: "roster", id: null };
  return { name: "home", id: null };
}

function App() {
  const [user, setUser] = createSignal(getUser());
  const [rows, setRows] = createSignal([]);
  const [detail, setDetail] = createSignal(null);
  const [tools, setTools] = createSignal([]);
  const [events, setEvents] = createSignal([]);
  const [route, setRoute] = createSignal(readHash());
  const [error, setError] = createSignal("");
  const [notice, setNotice] = createSignal("");
  const [loading, setLoading] = createSignal(false);

  const [loginUser, setLoginUser] = createSignal("machinist");
  const [loginPass, setLoginPass] = createSignal("machine123456");

  // 交刀补：刀号只能从仍可投的刀里点选
  const [selectedTool, setSelectedTool] = createSignal("");
  const [offsetUm, setOffsetUm] = createSignal("");

  // 清册登记
  const [newToolCode, setNewToolCode] = createSignal("");
  const [newToolInvestable, setNewToolInvestable] = createSignal(true);

  function goHome() {
    location.hash = "#/";
  }
  function goRoster() {
    location.hash = "#/roster";
  }
  function goDetail(id) {
    location.hash = `#/detail/${id}`;
  }

  function flash(msg) {
    setNotice(msg);
    setError("");
  }

  async function loadRows() {
    setLoading(true);
    try {
      setRows(await fetchSubmissions());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadTools() {
    try {
      setTools(await fetchTools());
    } catch (e) {
      setError(e.message);
    }
  }

  async function loadEvents() {
    try {
      setEvents(await fetchEvents());
    } catch (e) {
      setError(e.message);
    }
  }

  async function loadDetail(id) {
    setLoading(true);
    setError("");
    try {
      setDetail(await fetchSubmission(id));
    } catch (e) {
      setError(e.message);
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }

  function loadRoster() {
    return Promise.all([loadTools(), loadEvents()]);
  }

  onMount(() => {
    const onHash = () => setRoute(readHash());
    window.addEventListener("hashchange", onHash);
    if (user()) {
      if (route().name === "detail") loadDetail(route().id);
      else if (route().name === "roster") loadRoster();
      else {
        loadRows();
        loadTools();
      }
    }
    return () => window.removeEventListener("hashchange", onHash);
  });

  createEffect(() => {
    const r = route();
    if (!user()) return;
    if (r.name === "detail" && r.id) loadDetail(r.id);
    else if (r.name === "roster") loadRoster();
    else {
      loadRows();
      loadTools();
    }
  });

  async function handleLogin(e) {
    e.preventDefault();
    setError("");
    try {
      const data = await login(loginUser(), loginPass());
      setSession(data.token, {
        username: data.username,
        role: data.role,
        can_write: data.can_write,
      });
      setUser(getUser());
      goHome();
      await Promise.all([loadRows(), loadTools()]);
    } catch (err) {
      setError(err.message);
    }
  }

  function handleLogout() {
    clearSession();
    setUser(null);
    setRows([]);
    setDetail(null);
    setTools([]);
    setEvents([]);
    goHome();
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setNotice("");
    try {
      const saved = await createSubmission(selectedTool() || null, offsetUm());
      setOffsetUm("");
      setSelectedTool("");
      await loadRows();
      if (saved.status === "returned") {
        setError(`该笔已整笔退回：${saved.return_reason}`);
      } else {
        flash(`已提交，刀号 ${saved.tool_code} 已锁入单据，进入待复核。`);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleRegister(e) {
    e.preventDefault();
    setError("");
    setNotice("");
    try {
      const t = await registerTool(newToolCode().trim(), newToolInvestable());
      setNewToolCode("");
      setNewToolInvestable(true);
      await loadRoster();
      flash(`刀号 ${t.tool_code} 已登入清册（${t.state_label}）。`);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDelist(t) {
    setError("");
    setNotice("");
    try {
      await delistTool(t.id);
      await loadRoster();
      await loadTools();
      flash(`刀号 ${t.tool_code} 已摘牌；已写入的旧单刀号不变。`);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleRelist(t) {
    setError("");
    setNotice("");
    try {
      await relistTool(t.id);
      await loadRoster();
      await loadTools();
      flash(`刀号 ${t.tool_code} 已重新勾为可投。`);
    } catch (err) {
      setError(err.message);
    }
  }

  const investableTools = () => tools().filter((t) => t.state === "investable");

  return (
    <div class="page">
      <header class="topbar">
        <div class="brand">
          <h1>数控刀补复核台</h1>
          <p class="hint">
            操作员先在清册台登记刀号并勾可投；交刀补只能从仍可投的刀里点选，空选或选到已摘牌的刀整笔退回。刀号写入单据即锁死。
          </p>
        </div>
        <Show when={user()}>
          <nav class="topnav">
            <a
              href="#/"
              class={route().name === "home" ? "active" : ""}
              onClick={(e) => {
                e.preventDefault();
                goHome();
              }}
            >
              复核总览
            </a>
            <a
              href="#/roster"
              class={route().name === "roster" ? "active" : ""}
              onClick={(e) => {
                e.preventDefault();
                goRoster();
              }}
            >
              清册台
            </a>
          </nav>
        </Show>
      </header>

      <Show when={error()}>
        <div class="banner error">{error()}</div>
      </Show>
      <Show when={notice()}>
        <div class="banner ok">{notice()}</div>
      </Show>

      <Show
        when={user()}
        fallback={
          <section class="card">
            <h2>登录</h2>
            <form onSubmit={handleLogin} class="form">
              <label>
                用户名
                <input
                  value={loginUser()}
                  onInput={(e) => setLoginUser(e.currentTarget.value)}
                />
              </label>
              <label>
                密码
                <input
                  type="password"
                  value={loginPass()}
                  onInput={(e) => setLoginPass(e.currentTarget.value)}
                />
              </label>
              <button type="submit">进入系统</button>
            </form>
            <p class="hint">操作员 machinist / machine123456；复核员 auditor / audit123456（只读）</p>
          </section>
        }
      >
        <section class="card toolbar">
          <div>
            当前用户：<strong>{user().username}</strong>（{roleLabel[user().role] || user().role}）
          </div>
          <button type="button" class="ghost" onClick={handleLogout}>
            退出
          </button>
        </section>

        {/* ============ 复核总览 ============ */}
        <Show when={route().name === "home"}>
          <Show when={user().can_write}>
            <section class="card">
              <h2>交刀补</h2>
              <form onSubmit={handleSubmit} class="form inline">
                <label>
                  刀号（仅可投刀可点选）
                  <select
                    value={selectedTool()}
                    onChange={(e) => setSelectedTool(e.currentTarget.value)}
                  >
                    <option value="">— 空选（提交将整笔退回）—</option>
                    <For each={investableTools()}>
                      {(t) => <option value={t.id}>{t.tool_code}</option>}
                    </For>
                  </select>
                </label>
                <label>
                  刀补（微米）
                  <input
                    type="number"
                    value={offsetUm()}
                    onInput={(e) => setOffsetUm(e.currentTarget.value)}
                    required
                  />
                </label>
                <button type="submit">提交待复核</button>
              </form>
              <p class="hint">
                只能从仍可投的刀里点选；刀号一旦写入单据即锁死，此后摘牌也改不了这张单。
              </p>
            </section>
          </Show>

          <section class="card">
            <div class="toolbar">
              <h2>复核列表</h2>
              <button type="button" class="ghost" onClick={loadRows} disabled={loading()}>
                {loading() ? "刷新中…" : "刷新"}
              </button>
            </div>
            <table>
              <thead>
                <tr>
                  <th>刀具</th>
                  <th>刀补 µm</th>
                  <th>状态</th>
                  <th>结论 / 退回原因</th>
                  <th>提交时间</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <For each={rows()}>
                  {(row) => (
                    <tr>
                      <td>{row.tool_code || "—（空选）"}</td>
                      <td>{row.offset_um}</td>
                      <td class={row.status === "returned" ? "fail" : ""}>
                        {statusLabel[row.status] || row.status}
                      </td>
                      <td>
                        <Show when={row.status === "returned"} fallback={
                          <span
                            class={
                              row.verdict === "合格"
                                ? "pass"
                                : row.verdict === "超差"
                                ? "fail"
                                : ""
                            }
                          >
                            {row.verdict || "—"}
                          </span>
                        }>
                          <span class="fail">{row.return_reason}</span>
                        </Show>
                      </td>
                      <td>{new Date(row.created_at).toLocaleString()}</td>
                      <td>
                        <button type="button" class="ghost" onClick={() => goDetail(row.id)}>
                          详情
                        </button>
                      </td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <Show when={!rows().length && !loading()}>
              <p class="hint">暂无记录</p>
            </Show>
          </section>
        </Show>

        {/* ============ 清册台（整页） ============ */}
        <Show when={route().name === "roster"}>
          <Show when={user().can_write}>
            <section class="card">
              <h2>登记刀号进清册</h2>
              <form onSubmit={handleRegister} class="form inline">
                <label>
                  刀号
                  <input
                    placeholder="如 甲刀01 / T01"
                    value={newToolCode()}
                    onInput={(e) => setNewToolCode(e.currentTarget.value)}
                    required
                  />
                </label>
                <label class="check">
                  <span>勾为可投</span>
                  <input
                    type="checkbox"
                    checked={newToolInvestable()}
                    onChange={(e) => setNewToolInvestable(e.currentTarget.checked)}
                  />
                </label>
                <button type="submit">登记</button>
              </form>
              <p class="hint">不勾可投则登记即摘牌，交刀补选不到它。</p>
            </section>
          </Show>

          <section class="card">
            <div class="toolbar">
              <h2>清册 · 可投表</h2>
              <button type="button" class="ghost" onClick={loadRoster}>
                刷新
              </button>
            </div>
            <table>
              <thead>
                <tr>
                  <th>刀号</th>
                  <th>可否投</th>
                  <th>登记时间</th>
                  <th>摘牌时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <For each={tools()}>
                  {(t) => (
                    <tr>
                      <td>{t.tool_code}</td>
                      <td class={t.state === "investable" ? "pass" : "fail"}>
                        {t.state_label}
                      </td>
                      <td>{t.registered_at ? new Date(t.registered_at).toLocaleString() : "—"}</td>
                      <td>{t.delisted_at ? new Date(t.delisted_at).toLocaleString() : "—"}</td>
                      <td>
                        <Show when={user().can_write}>
                          <Show
                            when={t.state === "investable"}
                            fallback={
                              <button type="button" class="ghost" onClick={() => handleRelist(t)}>
                                重新勾可投
                              </button>
                            }
                          >
                            <button type="button" onClick={() => handleDelist(t)}>
                              摘牌
                            </button>
                          </Show>
                        </Show>
                        <Show when={!user().can_write}>
                          <span class="hint">只读</span>
                        </Show>
                      </td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <Show when={!tools().length}>
              <p class="hint">清册暂无刀号</p>
            </Show>
          </section>

          <section class="card">
            <h2>摘牌 / 登记痕迹</h2>
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>刀号</th>
                  <th>动作</th>
                  <th>操作人</th>
                </tr>
              </thead>
              <tbody>
                <For each={events()}>
                  {(ev) => (
                    <tr>
                      <td>{new Date(ev.created_at).toLocaleString()}</td>
                      <td>{ev.tool_code}</td>
                      <td class={ev.action === "delisted" ? "fail" : ev.action === "relisted" ? "pass" : ""}>
                        {ev.action_label}
                      </td>
                      <td>{ev.actor || "—"}</td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <Show when={!events().length}>
              <p class="hint">暂无痕迹</p>
            </Show>
          </section>
        </Show>

        {/* ============ 单据详情 ============ */}
        <Show when={route().name === "detail"}>
          <section class="card">
            <div class="toolbar">
              <h2>刀补详情</h2>
              <button type="button" class="ghost" onClick={goHome}>
                返回总览
              </button>
            </div>
            <Show when={detail()} fallback={<p class="hint">{loading() ? "加载中…" : "未找到记录"}</p>}>
              {(d) => (
                <div class="detail-grid">
                  <p>编号：{d().id}</p>
                  <p>
                    刀具（已锁死）：<strong>{d().tool_code || "—（空选）"}</strong>
                  </p>
                  <p>刀补 µm：{d().offset_um}</p>
                  <p class={d().status === "returned" ? "fail" : ""}>
                    状态：{statusLabel[d().status] || d().status}
                  </p>
                  <Show when={d().status === "returned"}>
                    <p class="fail">退回原因：{d().return_reason}</p>
                  </Show>
                  <p class={d().verdict === "合格" ? "pass" : d().verdict === "超差" ? "fail" : ""}>
                    结论：{d().verdict || "—"}
                  </p>
                  <p>提交时间：{new Date(d().created_at).toLocaleString()}</p>
                  <p>
                    复核时间：
                    {d().reviewed_at ? new Date(d().reviewed_at).toLocaleString() : "—"}
                  </p>
                  <p class="hint">刀号写入本单后锁死，清册摘牌或重新勾可投都不会改变本单刀号。</p>
                </div>
              )}
            </Show>
          </section>
        </Show>
      </Show>
    </div>
  );
}

export default App;
