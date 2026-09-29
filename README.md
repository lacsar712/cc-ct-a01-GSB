# 数控刀补复核台

操作员先在**清册台**登记刀号并勾选「可不可投」；交刀补只能从清册里**仍可投**的刀中点选，空选或选中已摘牌（未勾可投）的刀整笔退回并写明原因。选中的刀号写入单据即**锁死快照**，之后摘牌不影响已交的单据。后台 worker 用 PostgreSQL 行锁（`select_for_update(skip_locked=True)`）认领待复核记录，按绝对值是否不超过 12 微米给出「合格」或「超差」。

## 业务规则

- **登刀**：操作员把刀号登进清册并勾「可投」；刀号唯一。
- **摘牌**：对可投刀执行摘牌，必须写明原因（人、时间、原因留痕，只追加不可改，不可重复摘牌）。
- **交刀补**：刀号只能从清册仍可投的刀里下拉点选；空选、已摘牌、未勾可投一律整笔退回（400，消息含原因），不落单。
- **锁死**：单据保存刀号快照（`tool_code`）并关联清册刀（`tool_id`，`PROTECT` 不可删）；以后摘牌改不了这张单。
- **复核员**：可翻阅清册、摘牌痕迹与单据的锁死刀号；不能改清册、不能摘牌、不能交刀补（403）。

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
| machinist | machine123456 | 可登记/摘牌刀具、提交刀补 |
| auditor | audit123456 | 只读：看清册与单据 |

## 启动

```bash
docker compose up --build
```

健康检查：`GET http://localhost:8196/api/health` → `{"status":"ok"}`

## 验收

1. machinist 登录，进「清册台」登 **甲刀零一** 并勾可投；回「复核总览」交该刀刀补，应进**待复核**，数秒内 worker 处理为「已完成」并给出结论。
2. 在清册台把**甲刀零一**摘牌（写明原因）→ 再交同刀，应**整笔退回**并提示摘牌原因；空选或选未勾可投的刀同样整笔退回。
3. 打开第 1 步那张已完成的单据，刀号仍是**甲刀零一**（已摘牌不影响旧单，详情页另标「现已摘牌」）。
4. 清册台整页展示可投表与摘牌痕迹；auditor 登录只能翻阅，没有登刀、摘牌与提交入口。
5. 种子数据：T01 合格（5 µm）、T09 超差（20 µm），两把刀均在册可投。

自动化测试：

```bash
cd backend
PYTHONPATH=. python manage.py test desk
```

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录 |
| GET | `/api/tools` | 清册（含摘牌痕迹） |
| POST | `/api/tools` | 登刀（仅操作员） |
| POST | `/api/tools/{id}/delist` | 摘牌并写明原因（仅操作员） |
| GET | `/api/submissions` | 单据列表 |
| GET | `/api/submissions/{id}` | 单据详情（锁死刀号） |
| POST | `/api/submissions` | 交刀补，body 传 `tool_id` 点选（仅操作员） |

## 目录

```text
backend/          Django 工程（config/、desk/、worker.py）
frontend/         SolidJS 单页（复核总览、清册台、详情）
docker-compose.yml
```
