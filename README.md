# StallSpan 市集摊档开间

沿街段一维 First-Fit 开间分配，挡柱不可被摊位跨越，输出分配图与放不下清单。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4700 |
| API | http://localhost:9700 |
| API 文档 | http://localhost:9700/docs |
| Postgres | localhost:5448 |

健康检查：`GET http://localhost:9700/api/health`

## 使用说明

1. 在「集日」「街段」确认开市日与可用宽度。
2. 在「摊主」「挡柱」维护需求宽度与障碍位置。
3. 打开「分配带」查看三栏：
   - **左·现算**：按当前街宽、挡柱、摊宽即时重算（不落库）；可在页内直接改摊宽或街宽后重算。
   - **右·历史**：点选一条过往运行，显示其落库当时的色块；不点则留空，不会默认带入最近一次。点「把当前现算固化为历史运行」存档。
   - **中·差值**：列出仅现算有、仅历史有、起止漂移的摊主号。左右共用同一套区间算法，差值只比坐标，不掺拒因；未选历史时差值为空。
4. 在「放不下」查看最近一次落库运行中无法安置的摊位。

### 口径约束

- 左右两图与差值必须同一套区间算法（见 `app/services/first_fit_engine.py` 的 `make_snapshot` / `diff_allocations`）。
- 改摊宽或街宽只重算现算侧与差值；历史快照永不回写，旧运行的拒因文案保持落库原文。
- 摊主掉出/进入图归「仅…有」，只有两侧都在图上但起止变化才算「漂移」，二者不互混。

## 开发与测试

```bash
docker compose exec api pytest -q
```

本地无 Postgres 时可用 SQLite 跑测试（测试夹具已用内存库 + StaticPool 覆盖 `DATABASE_URL`）：

```bash
cd backend
PYTHONPATH=. pytest -q
```
