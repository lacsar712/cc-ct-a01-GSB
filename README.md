# 数控刀补复核台

操作员先在**清册台**把刀号登进机床刀具清册并勾「可投」；交刀补时刀号**只能从仍可投的刀里点选**。空选，或选到此后已被摘牌的刀，整笔退回并写明原因。刀号一旦写入单据即**锁死快照**，之后摘牌/重新勾可投都改不了这张单。后台 worker 用 PostgreSQL 行锁（`select_for_update(skip_locked=True)`）认领待复核记录，按绝对值是否不超过 12 微米给出「合格」或「超差」。

## 清册规则

- **登记勾可投**：操作员在清册台登刀号，并勾选是否可投（不勾则登记即摘牌）。
- **摘牌**：可投的刀可摘牌，摘牌后交刀补选不到它；每次登记 / 摘牌 / 重新勾可投都留痕。
- **交刀补**：刀号为下拉点选，仅列「仍可投」的刀；首项为空选。
  - 选中可投刀 → 进「待复核」，刀号锁入单据。
  - 空选 / 刀已摘牌 / 不在册 → 生成「已退回」单并写明退回原因，不进待复核队列。
- **锁死**：单据上的刀号是提交瞬间的快照；其后摘牌不影响旧单，打开旧单刀号不变。
- **权限**：操作员可改清册、可交刀补；复核员只能翻阅清册、摘牌痕迹与单据（含锁死刀号），不能改清册也不能交。

## 技术栈

| 层 | 选型 |
|----|------|
| 后端 | Django 5 + django-ninja（ASGI / uvicorn） |
| 前端 | SolidJS + Vite，nginx 反代 `/api` |
| 数据库 | PostgreSQL 16 |
| 鉴权 | JWT（python-jose），令牌存浏览器 localStorage |

## 端口

| 服务 | 地址 |
|------|------|
| 页面 | http://localhost:3196 |
| 接口 | http://localhost:8196 |
| PostgreSQL | localhost:54396（库名 `cncoffset`） |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| machinist | machine123456 | 登记/勾可投/摘牌、交刀补 |
| auditor | audit123456 | 只读：翻阅清册、痕迹与锁死刀号 |

## 启动

```bash
docker compose up --build
```

健康检查：`GET http://localhost:8196/api/health` → `{"status":"ok"}`

## 验收

1. machinist 登录，顶部菜单进入「**清册台**」：整页上半为可投表（含状态、登记/摘牌时间、摘牌与重新勾可投操作），下半为摘牌/登记痕迹。种子刀号 T01、T09 已在清册且可投。
2. 在清册台登记「甲刀01」并勾可投。
3. 回到「复核总览」交刀补，刀号下拉点选「甲刀01」提交 → 单据进「待复核」，列表/详情刀号为甲刀01。
4. 回清册台把「甲刀01」摘牌；再交同刀 → 整笔「已退回」，退回原因写明该刀已摘牌，且不进待复核。空选提交同样整笔退回。
5. 打开步骤 3 那张已提交的单，刀号**仍是甲刀01**（摘牌改不了旧单）。
6. auditor 登录：能看清册台（可投表与痕迹）和单据锁死刀号，但没有登记/摘牌/交刀补的入口，直接调接口返回 403。
7. 种子数据：T01 合格（刀补 5 µm）、T09 超差（刀补 20 µm），待复核单数秒内被 worker 处理为「已完成」。

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录取令牌 |
| GET | `/api/roster/tools` | 清册可投表（两角色可读） |
| GET | `/api/roster/events` | 登记/摘牌痕迹（两角色可读） |
| POST | `/api/roster/tools` | 登记刀号 `{tool_code, investable}`（仅操作员） |
| POST | `/api/roster/tools/{id}/delist` | 摘牌（仅操作员） |
| POST | `/api/roster/tools/{id}/relist` | 重新勾可投（仅操作员） |
| GET | `/api/submissions` | 单据列表 |
| GET | `/api/submissions/{id}` | 单据详情（刀号锁死） |
| POST | `/api/submissions` | 交刀补 `{roster_tool_id, offset_um}`；空选/已摘牌整笔退回（仅操作员） |

## 目录

```text
backend/          Django 工程（config/、desk/、worker.py）
frontend/         SolidJS 单页
docker-compose.yml
```
