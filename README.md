# Carpool Fare Splitter · 拼车行程费用分摊 API

基于 FastAPI 的拼车费用分摊服务：按顺序路段读取整数分费用与每位乘客的上下车站点，
逐段均摊费用，输出逐人总额与逐路段明细。金额全程使用整数分与精确分数计算，
总额严格守恒，且乘客输入顺序不影响结果。

## 快速启动

单条命令（构建镜像、安装依赖、启动服务全部自动完成）：

```bash
docker compose up --build
```

启动后访问：

| 地址 | 说明 |
| --- | --- |
| http://localhost:8000/split | 分摊接口（POST） |
| http://localhost:8000/docs | Swagger 交互式文档 |
| http://localhost:8000/healthz | 健康检查 |

后台运行可加 `-d`；停止用 `docker compose down`。

## 配置

无需任何必需配置（无数据库、无环境变量）。默认端口 **8000**；
如需修改宿主机端口，编辑 `compose.yaml` 中的端口映射即可，例如 `"8080:8000"`。

## API：`POST /split`

### 请求体

```json
{
  "segments": [100, 251, 80],
  "passengers": [
    {"id": "alice", "board": 0, "alight": 3},
    {"id": "bob",   "board": 1, "alight": 3},
    {"id": "carol", "board": 0, "alight": 1}
  ]
}
```

- `segments`：按行程顺序排列的各路段费用，整数，单位分，必须 ≥ 0，至少 1 段。
- `passengers[].id`：乘客 ID，字符串或整数，全程唯一。
- `board` / `alight`：上/下车站点编号。`N` 个路段对应站点 `0..N`；
  乘客在车区间为 `[board, alight)`，即乘坐第 `board` 至 `alight-1` 段，须满足 `0 ≤ board < alight ≤ N`。

### 响应（200）

```json
{
  "total_cost": 431,
  "totals": {"alice": 216, "bob": 165, "carol": 50},
  "segments": [
    {"index": 0, "cost": 100, "passengers": ["alice", "carol"], "shares": {"alice": 50, "carol": 50}},
    {"index": 1, "cost": 251, "passengers": ["alice", "bob"],   "shares": {"alice": 126, "bob": 125}},
    {"index": 2, "cost": 80,  "passengers": ["alice", "bob"],   "shares": {"alice": 40, "bob": 40}}
  ]
}
```

- `totals`：逐人应付总额（分），总和恒等于 `total_cost`。
- `segments[]`：逐路段明细，`passengers` 为该段在车乘客，`shares` 为该段分摊结果（每段 `shares` 之和恒等于该段 `cost`）。

### 示例

```bash
curl -s http://localhost:8000/split \
  -H 'Content-Type: application/json' \
  -d '{"segments":[100,251,80],"passengers":[{"id":"alice","board":0,"alight":3},{"id":"bob","board":1,"alight":3},{"id":"carol","board":0,"alight":1}]}'
```

## 分摊规则

1. 按路段顺序处理，每段找出全部在车乘客均摊：`base = cost // n`，余数 `r = cost % n`。
2. 每位乘客维护**累计理论份额**（精确分数）与**已分金额**；欠额 = 理论份额 − 已分金额。
3. 无法整除时，余数 `r` 个 1 分优先补给**欠额最大**的乘客；欠额并列时按乘客 ID 升序兜底
   （整数 ID 按数值、字符串 ID 按字典序），除此之外 ID 不影响分摊。
4. 因此：总额严格守恒（`sum(totals) == sum(segments)`），且乘客在请求中的排列顺序不影响结果。

## 错误（422）

以下情况返回 `422 Unprocessable Entity`，响应 `detail` 中含具体原因：

- 空载收费路段：某段 `cost > 0` 但无任何乘客在车（费用为 0 的空载段允许）；
- 非法区间：`board >= alight`、站点越界（`alight > 路段数`）或站点为负；
- 乘客 ID 重复、费用为负、路段列表为空、字段类型错误或含未知字段。

## 本地开发与测试

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest tests/          # 全部测试（算法 + API）
python -m unittest tests.test_splitter   # 仅核心算法（纯标准库，无需安装依赖）
uvicorn app.main:app --reload    # 本地起服务，默认 http://127.0.0.1:8000
```

## 项目结构

```
app/
  main.py       # FastAPI 应用与路由（POST /split、GET /healthz）
  models.py     # 请求/响应模型与 422 校验规则
  splitter.py   # 核心分摊算法（纯标准库，精确分数运算）
tests/          # 算法单元测试 + API 集成测试
Dockerfile      # 依赖与启动命令均固化在镜像内
compose.yaml    # 单服务编排，含健康检查
requirements.txt / requirements-dev.txt
```
