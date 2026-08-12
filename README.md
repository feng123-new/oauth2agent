# OAuth2Agent

一个**独立项目**：把 ChatGPT / Codex OAuth 登录或已有 OAuth JSON 转换为 identity-only 的 Codex Agent Identity 文件。

它不需要修改 Sub2API，也不需要作为 Sub2API 的 PR。生成的文件可以之后手动导入支持 Agent Identity 的 Sub2API，或者直接作为 Codex identity-only `auth.json` 使用。

> Agent Identity 目前仍是 OpenAI Codex 中的开发中能力，不是稳定公开 API。接口、字段和权限边界未来可能变化。请先用非关键账号验证。

## 它和 BetterAndBetterII/codex-agent-identity 的关系

原项目的核心流程是：

```text
浏览器完成 ChatGPT OAuth（PKCE）
        ↓
拿到 access_token + id_token
        ↓
本地生成 Ed25519 身份密钥
        ↓
Bearer access_token 仅用于 /v1/agent/register
        ↓
得到 agent_runtime_id
        ↓
私钥签名注册 /v1/agent/{runtime_id}/task/register
        ↓
得到或解密 task_id
        ↓
丢弃 OAuth token
        ↓
只保存 Agent Identity
```

后续 Codex 请求不再发送 OAuth Bearer，而是每次动态生成：

```http
Authorization: AgentAssertion <base64url-envelope>
ChatGPT-Account-ID: <account-id>
```

本项目保留这条核心路线，同时增加了“直接读取已有 OAuth JSON 并转换”的入口。

## 功能

- `login`：像原项目一样，在浏览器完成 ChatGPT OAuth，然后直接输出 Agent Identity。
- `convert`：读取已有 Codex `auth.json`、OAuth JSON、常见嵌套 JSON，直接注册 Agent Identity。
- 默认输出 **Sub2API 可导入格式**。
- `--format codex` 输出 identity-only Codex `auth.json`。
- 输出文件不包含 `access_token` / `refresh_token` / `id_token`。
- `verify`：测试 Codex `/responses`，可附加检查 `/conversations` 是否返回 401/403。
- `simulate`：纯本地 Mock 模拟注册、task、签名与隔离，不需要真实账号、不消耗额度。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e .
```

Python 3.10+。开发环境可以使用：

```bash
python -m pip install -e '.[dev]'
pytest -q
```

## 用法 A：像原项目一样直接登录

```bash
oauth2agent login -o my-agent.json
```

程序会打开浏览器，并监听：

```text
http://localhost:1455/auth/callback
```

远程 VPS 或 callback 无法访问时：

```bash
oauth2agent login --manual --no-browser -o my-agent.json
```

完成登录后，把浏览器最终的完整 callback URL 粘贴回终端。

默认输出适合 Sub2API 导入：

```json
{
  "auth_mode": "agentIdentity",
  "agent_identity": {
    "agent_runtime_id": "agent-...",
    "agent_private_key": "MC4CAQAwBQYDK2VwBCIEI...",
    "task_id": "...",
    "account_id": "...",
    "chatgpt_user_id": "user-...",
    "email": "user@example.com",
    "plan_type": "pro",
    "chatgpt_account_is_fedramp": false
  }
}
```

OAuth token 不会写入这个文件。

## 用法 B：已有 OAuth 文件直接转换

例如已有 `~/.codex/auth.json`：

```bash
oauth2agent convert ~/.codex/auth.json -o my-agent.json
```

也可以把从 Sub2API / 其他工具导出的 OAuth JSON 保存为本地文件后转换。解析器会从嵌套 JSON 中寻找 `access_token`、`id_token`、`account_id` 等字段。

## 输出 Codex identity-only auth.json

```bash
oauth2agent login --format codex -o agent-auth.json
# 或
oauth2agent convert oauth.json --format codex -o agent-auth.json
```

输出结构包含 `auth_mode: agentIdentity`，OAuth token 字段为空。

## 验证

这会真实请求 Codex，可能消耗少量额度：

```bash
oauth2agent verify my-agent.json --check-isolation
```

预期类似：

```text
Responses: OK
Conversations endpoint: HTTP 403
```

401/403 视为聊天记录接口拒绝 Agent Identity；如果返回 2xx，工具会判定隔离检查失败。

## 本地模拟

```bash
python -m oauth2agent simulate
```

模拟内容：

1. 构造仅存在于内存的 OAuth access token；
2. Mock `/v1/agent/register`；
3. 验证 Ed25519 公钥和 task 注册签名；
4. 生成 Agent Identity 文件；
5. 确认输出不含 OAuth token；
6. 验证 AgentAssertion 签名；
7. 模拟 `/responses` 可用；
8. 模拟 `/conversations` 返回 403。

另外，单元测试会在 PyNaCl 可用时覆盖上游 `encrypted_task_id` 的 sealed-box 解密路径；GitHub Actions 安装完整依赖后会执行这条测试。

## 输入约束

`convert` 只接受**单账号** OAuth 文件。若一个 JSON 中检测到多个不同的 `access_token` / `id_token`，工具会拒绝转换，避免把一个账号的 token 与另一个账号的 `account_id` 错配。请先从源系统单独导出目标账号。

## 安全提醒

Agent Identity 文件没有 OAuth token，但仍包含可用于 Codex 的私钥，因此仍是敏感凭据：

- 不要提交真实 OAuth 或 Agent Identity 文件到 Git；
- 不要在日志中打印 access token、refresh token 或私钥；
- 建议输出文件仅允许当前用户读取；
- Agent Identity 仍是实验能力，升级 OpenAI Codex 后应重新验证兼容性。

## 参考实现

协议行为参考：

- OpenAI 官方 `openai/codex` 当前 Agent Identity 实现；
- `BetterAndBetterII/codex-agent-identity` 的公开实验流程。

本项目定位是“独立转换/生成器”，不嵌入 Sub2API 代码库。

## 当前状态

`0.2.0` 已通过本地单元测试和完整离线模拟。真实 OpenAI Agent Identity 接口仍属于开发中能力，因此第一次用于真实账号时建议先执行 `verify --check-isolation`，并保留原 OAuth 凭据的独立备份直到确认迁移成功。
