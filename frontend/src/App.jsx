import { createSignal, onMount, Show, For, createEffect } from "solid-js";
import {
  clearSession,
  createSubmission,
  delistTool,
  fetchSubmission,
  fetchSubmissions,
  fetchTools,
  getUser,
  login,
  registerTool,
  setSession,
} from "./api";

const statusLabel = {
  pending: "待复核",
  processing: "复核中",
  done: "已完成",
};

const roleLabel = {
  machinist: "操作员",
  auditor: "复核员",
};

function readHash() {
  const raw = (location.hash || "#/").replace(/^#/, "") || "/";
  let m = raw.match(/^\/detail\/(\d+)/);
  if (m) return { name: "detail", id: Number(m[1]) };
  if (raw === "/registry") return { name: "registry", id: null };
  return { name: "home", id: null };
}

function App() {
  const [user, setUser] = createSignal(getUser());
  const [rows, setRows] = createSignal([]);
  const [tools, setTools] = createSignal([]);
  const [detail, setDetail] = createSignal(null);
  const [route, setRoute] = createSignal(readHash());
  const [error, setError] = createSignal("");
  const [loading, setLoading] = createSignal(false);

  const [loginUser, setLoginUser] = createSignal("machinist");
  const [loginPass, setLoginPass] = createSignal("machine123456");

  const [pickedTool, setPickedTool] = createSignal("");
  const [offsetUm, setOffsetUm] = createSignal("");

  const [newToolCode, setNewToolCode] = createSignal("");
  const [newToolUsable, setNewToolUsable] = createSignal(true);

  function goHome() {
    location.hash = "#/";
  }

  function goRegistry() {
    location.hash = "#/registry";
  }

  function goDetail(id) {
    location.hash = `#/detail/${id}`;
  }

  async function loadRows() {
    setLoading(true);
    setError("");
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

  onMount(() => {
    const onHash = () => setRoute(readHash());
    window.addEventListener("hashchange", onHash);
    if (user()) {
      loadTools();
      if (route().name === "detail") loadDetail(route().id);
      else loadRows();
    }
    return () => window.removeEventListener("hashchange", onHash);
  });

  createEffect(() => {
    const r = route();
    if (!user()) return;
    if (r.name === "detail" && r.id) loadDetail(r.id);
    else loadRows();
    if (r.name === "registry") loadTools();
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
    setTools([]);
    setDetail(null);
    goHome();
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    // 空选：不允许提交；与后端「整笔退回」一致
    if (!pickedTool()) {
      setError("未从清册点选刀号，整笔退回");
      return;
    }
    try {
      await createSubmission(pickedTool(), offsetUm());
      setPickedTool("");
      setOffsetUm("");
      await loadRows();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleRegisterTool(e) {
    e.preventDefault();
    setError("");
    try {
      await registerTool(newToolCode(), newToolUsable());
      setNewToolCode("");
      setNewToolUsable(true);
      await loadTools();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDelist(tool) {
    const reason = window.prompt(`把刀号 ${tool.tool_code} 摘牌，请写明原因：`, "");
    if (reason === null) return;
    if (!reason.trim()) {
      setError("摘牌必须写明原因");
      return;
    }
    setError("");
    try {
      await delistTool(tool.id, reason.trim());
      await loadTools();
    } catch (err) {
      setError(err.message);
    }
  }

  const usableTools = () => tools().filter((t) => t.usable && !t.delisted);
  const idleTools = () => tools().filter((t) => !t.usable && !t.delisted);
  const delistedTools = () => tools().filter((t) => t.delisted);

  return (
    <div class="page">
      <header class="topbar">
        <div class="brand">
          <h1>数控刀补复核台</h1>
          <p class="hint">
            刀补绝对值不超过十二微米判合格，否则超差。交刀补只能从清册仍可投的刀中点选；选中刀号写入单据即锁死。
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
              href="#/registry"
              class={route().name === "registry" ? "active" : ""}
              onClick={(e) => {
                e.preventDefault();
                goRegistry();
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
            <Show when={!user().can_write}>
              <span class="tag readonly">只读</span>
            </Show>
          </div>
          <button type="button" class="ghost" onClick={handleLogout}>
            退出
          </button>
        </section>

        <Show when={route().name === "home"}>
          <Show when={user().can_write}>
            <section class="card">
              <h2>交刀补</h2>
              <form onSubmit={handleSubmit} class="form inline">
                <label>
                  刀号（仅清册可投刀）
                  <select
                    value={pickedTool()}
                    onChange={(e) => setPickedTool(e.currentTarget.value)}
                    required
                  >
                    <option value="">— 请从清册点选 —</option>
                    <For each={usableTools()}>
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
              <Show when={!usableTools().length}>
                <p class="hint">清册当前没有可投的刀，请先到清册台登刀并勾可投。</p>
              </Show>
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
                  <th>锁死刀号</th>
                  <th>刀补 µm</th>
                  <th>状态</th>
                  <th>结论</th>
                  <th>提交时间</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <For each={rows()}>
                  {(row) => (
                    <tr>
                      <td>
                        {row.tool_code}
                        <Show when={row.tool_delisted}>
                          <span class="tag delisted" title={row.tool_delist_reason}>
                            现已摘牌
                          </span>
                        </Show>
                      </td>
                      <td>{row.offset_um}</td>
                      <td>{statusLabel[row.status] || row.status}</td>
                      <td class={row.verdict === "合格" ? "pass" : row.verdict === "超差" ? "fail" : ""}>
                        {row.verdict || "—"}
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

        <Show when={route().name === "registry"}>
          <section class="card">
            <div class="toolbar">
              <h2>机床清册台</h2>
              <button type="button" class="ghost" onClick={loadTools}>
                刷新
              </button>
            </div>
            <p class="hint">
              操作员在此登刀并勾「可不可投」；摘牌须写明原因且只留痕、不可改。复核员可翻阅，但不能改清册。
            </p>

            <Show when={user().can_write}>
              <form onSubmit={handleRegisterTool} class="form inline">
                <label>
                  刀号
                  <input
                    placeholder="如 甲刀零一"
                    value={newToolCode()}
                    onInput={(e) => setNewToolCode(e.currentTarget.value)}
                    required
                  />
                </label>
                <label class="check">
                  <span>可投</span>
                  <input
                    type="checkbox"
                    checked={newToolUsable()}
                    onChange={(e) => setNewToolUsable(e.currentTarget.checked)}
                  />
                </label>
                <button type="submit">登册</button>
              </form>
            </Show>
          </section>

          <section class="card">
            <h2>可投表</h2>
            <table>
              <thead>
                <tr>
                  <th>刀号</th>
                  <th>可投</th>
                  <th>登刀人</th>
                  <th>登刀时间</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <For each={usableTools()}>
                  {(t) => (
                    <tr>
                      <td>{t.tool_code}</td>
                      <td class="pass">✓ 可投</td>
                      <td>{t.registered_by || "—"}</td>
                      <td>{new Date(t.created_at).toLocaleString()}</td>
                      <td>
                        <Show when={user().can_write}>
                          <button type="button" class="danger ghost" onClick={() => handleDelist(t)}>
                            摘牌
                          </button>
                        </Show>
                      </td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <Show when={!usableTools().length}>
              <p class="hint">暂无可用刀具</p>
            </Show>
          </section>

          <section class="card">
            <h2>未勾可投</h2>
            <table>
              <thead>
                <tr>
                  <th>刀号</th>
                  <th>可投</th>
                  <th>登刀人</th>
                  <th>登刀时间</th>
                </tr>
              </thead>
              <tbody>
                <For each={idleTools()}>
                  {(t) => (
                    <tr>
                      <td>{t.tool_code}</td>
                      <td class="fail">✗ 不可投</td>
                      <td>{t.registered_by || "—"}</td>
                      <td>{new Date(t.created_at).toLocaleString()}</td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <Show when={!idleTools().length}>
              <p class="hint">暂无未勾可投的刀</p>
            </Show>
          </section>

          <section class="card">
            <h2>摘牌痕迹</h2>
            <table>
              <thead>
                <tr>
                  <th>刀号</th>
                  <th>摘牌原因</th>
                  <th>摘牌人</th>
                  <th>摘牌时间</th>
                </tr>
              </thead>
              <tbody>
                <For each={delistedTools()}>
                  {(t) => (
                    <tr class="delisted-row">
                      <td>{t.tool_code}</td>
                      <td>{t.delist_reason}</td>
                      <td>{t.delisted_by || "—"}</td>
                      <td>{t.delisted_at ? new Date(t.delisted_at).toLocaleString() : "—"}</td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <Show when={!delistedTools().length}>
              <p class="hint">暂无摘牌记录</p>
            </Show>
          </section>
        </Show>

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
                    锁死刀号：<strong>{d().tool_code}</strong>
                    <span class="hint">（写入单据后锁死）</span>
                  </p>
                  <Show when={d().tool_delisted}>
                    <p class="fail">
                      该刀现已在清册摘牌（原因：{d().tool_delist_reason || "—"}），本单据刀号不变。
                    </p>
                  </Show>
                  <p>刀补 µm：{d().offset_um}</p>
                  <p>状态：{statusLabel[d().status] || d().status}</p>
                  <p class={d().verdict === "合格" ? "pass" : d().verdict === "超差" ? "fail" : ""}>
                    结论：{d().verdict || "—"}
                  </p>
                  <p>提交时间：{new Date(d().created_at).toLocaleString()}</p>
                  <p>
                    复核时间：
                    {d().reviewed_at ? new Date(d().reviewed_at).toLocaleString() : "—"}
                  </p>
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
