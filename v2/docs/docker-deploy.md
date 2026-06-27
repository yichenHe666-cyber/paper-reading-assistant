# 核动力科研牛马 v2 — Docker 部署指南

> 面向新手的一键部署文档。读完即可在自己的机器上跑起完整服务。

## 前置条件

| 依赖 | 最低版本 | 说明 |
|---|---|---|
| Docker Engine | 24.0 | 含 buildkit |
| Docker Compose | v2（`docker compose` 子命令） | v1 已停止维护 |
| Ollama | 任意近期版本 | 本地 LLM 与 embedding 服务，需预拉模型 |
| 可选：GitHub Token | — | 论文同步匿名限 60/hour，有 token 提升到 5000/hour |

Ollama 模型预拉（首次较慢，按需选择）：

```bash
# 对话模型（默认 qwen2.5:7b，也可换 deepseek-r1:7b 等）
ollama pull qwen2.5:7b
# embedding 模型
ollama pull nomic-embed-text
```

## 一键部署

### 1. 准备配置

```bash
cd /path/to/v2
cp deploy/.env.example deploy/.env
```

编辑 `deploy/.env`，按需修改（最小化配置只需改 `LLM_API_BASE` 指向你的 Ollama）：

```bash
# 本地 Ollama 场景（最常见）
LLM_PROVIDER=ollama
LLM_API_BASE=http://127.0.0.1:11434/v1
LLM_API_KEY=
LLM_MODEL=qwen2.5:7b
EMBEDDING_API_BASE=http://127.0.0.1:11434
```

若用 DeepSeek 等云端服务：

```bash
LLM_PROVIDER=deepseek
LLM_API_BASE=https://api.deepseek.com/v1
LLM_API_KEY=sk-你的key
LLM_MODEL=deepseek-chat
```

### 2. 构建并启动

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d --build
```

首次构建需下载基础镜像并编译 Go/Rust，约 5-15 分钟（取决于网络与机器）。后续启动秒级。

### 3. 验证

```bash
# 健康检查
curl http://127.0.0.1:8000/api/health
# 应返回 {"status":"ok","data_dir":"/data",...}

# 浏览器访问前端
# http://127.0.0.1:8080
```

看到对话页即部署成功。在设置页可查看健康检查的绝对数据路径，确认数据落盘正确。

## 端口映射

| 服务 | 容器端口 | 宿主映射 | 访问方式 |
|---|---|---|---|
| frontend (nginx) | 8080 | `0.0.0.0:8080` | 浏览器唯一入口 |
| backend (Go) | 8000 | `127.0.0.1:8000` | 仅本机，调试用 |
| core (Rust) | 8788 | 不映射 | 仅 compose 内网，backend 反代 |

Rust core 故意不暴露公网端口——它无鉴权，仅服务于 backend 内网调用。若需从宿主直连 core 调试，临时加 `-p 127.0.0.1:8788:8788`。

## 数据持久化

数据卷 `nro-data` 挂载到 backend 与 core 的 `/data`，共享同一 SQLite 文件：

```bash
# 查看卷位置
docker volume inspect nro-data

# 备份（停服后）
docker run --rm -v nro-data:/data -v $(pwd):/backup alpine \
    tar czf /backup/nro-data-$(date +%Y%m%d).tar.gz -C /data .

# 恢复
docker run --rm -v nro-data:/data -v $(pwd):/backup alpine \
    tar xzf /backup/nro-data-backup.tar.gz -C /data
```

容器重建、升级、迁移都不会丢数据——这是痛点③（论文重启丢失）在部署层的根治保障。

## 常用运维命令

```bash
# 查看日志
docker compose -f deploy/docker-compose.yml logs -f backend
docker compose -f deploy/docker-compose.yml logs -f core

# 重启某服务
docker compose -f deploy/docker-compose.yml restart backend

# 升级代码后重建
docker compose -f deploy/docker-compose.yml up -d --build backend

# 停止全部
docker compose -f deploy/docker-compose.yml down
# 停止并删数据（慎用！）
docker compose -f deploy/docker-compose.yml down -v
```

## Ollama 在宿主机的连接

容器内访问宿主机的 Ollama 用 `host.docker.internal`（compose 已配置 `extra_hosts`）：

```bash
# .env 中这样写（容器视角）
LLM_API_BASE=http://host.docker.internal:11434/v1
EMBEDDING_API_BASE=http://host.docker.internal:11434
```

若 Ollama 也容器化部署，把 LLM 地址改成 compose 服务名即可，如 `http://ollama:11434/v1`。

## 生产环境加固建议

本配置面向单机科研使用，若要公网暴露，至少增加：

- 在 frontend 前加 TLS 反代（Caddy/Traefik 自动证书）
- backend 加 API token 鉴权中间件（当前无认证）
- 限制 `LLM_DAILY_BUDGET_USD` 防止预算被耗尽（当前未强制）
- 定期 `docker volume` 备份并异地存储

## 故障排查

| 现象 | 排查方向 |
|---|---|
| 前端能打开但对话报错 | backend 日志；LLM_API_BASE 是否可达；模型是否已 pull |
| 论文同步 401 | GITHUB_TOKEN 未配或过期 |
| 记忆创建成功但向量检索空 | core 日志；EMBEDDING_API_BASE 是否可达；embedding 模型是否 pull |
| core 启动失败 "database is locked" | backend 正持有写锁，core busy_timeout 已设 15s，稍等重试；或先停 backend 再起 core |
| 容器起来但 healthcheck 失败 | `docker logs nro-backend` 看启动错误；常见为数据目录权限，确保卷属主 app |
