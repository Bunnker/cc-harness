---
name: auth-identity
description: "Agent 如何管理多来源凭证，同时不阻塞主循环也不泄露密钥"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# 认证身份系统 (Auth Identity)

## 1. Problem — 凭证来源多、刷新慢、存储不安全

Agent 需要调用 LLM API，凭证可能来自环境变量、OAuth token、配置文件、系统 keychain。OAuth token 会过期，刷新需要网络请求。如果刷新阻塞主循环，用户体验卡顿。如果凭证明文存储，一次 git push 就可能泄露。

通用问题是：**如何从多来源获取凭证、非阻塞刷新、安全存储，同时支持多租户身份切换。**

## 2. In Claude Code — 源码事实

- OAuth 实现：`src/services/oauth/index.ts` — PKCE 流程（code_verifier + challenge + state），支持自动（localhost 监听）和手动（复制粘贴）两种 auth code 获取方式
- 凭证优先级（5 级）：session override > `--api-key` flag > `ANTHROPIC_API_KEY` env > OAuth token > settings 配置
- 非阻塞刷新：`checkAndRefreshOAuthTokenIfNeeded()` 在每次 API 调用前检查，5 分钟 expiry buffer
- 刷新防并发：inflight Promise 去重 + 文件锁（带重试和退避）+ 获取锁后二次检查
- 安全存储：macOS Keychain 优先，首次成功写入后自动从明文迁移；其他平台 fallback 到文件
- Keychain 预取：`main.tsx` 启动时（import 阶段）预取，30 秒 TTL 缓存

## 3. Transferable Pattern — 优先级链 + 非阻塞刷新 + 安全存储分层

从 CC 抽象出来：

1. **优先级链而非单一来源**。凭证从多来源按优先级查找，运行时可切换
2. **刷新不阻塞主循环**。token 接近过期时在 API 调用前异步刷新，inflight 去重防并发
3. **存储分层降级**。OS keychain → 加密文件 → 明文。迁移单向（低 → 高安全），不反向
4. **预取 + TTL 缓存**。启动时预取凭证到内存，避免每次 API 调用访问 keychain

## 4. Minimal Portable Version

最小版：**环境变量 API key + 无刷新**。

升级路径：环境变量 → + 配置文件 fallback → + OAuth PKCE → + token 刷新 → + keychain → + 预取缓存

## 5. Do Not Cargo-Cult

1. **不要照搬 PKCE OAuth**。只用 API key 的项目不需要 OAuth
2. **不要照搬 5 分钟 expiry buffer**。这是 CC 基于 5-60 秒 API 调用耗时的经验值
3. **不要照搬 macOS Keychain 集成**。跨平台时 API 完全不同，或直接用加密文件
4. **不要照搬文件锁防并发刷新**。单进程项目用 inflight Promise 去重就够
5. **不要照搬 30 秒 TTL**。这与 CC 的 keychain 访问延迟相关

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议删掉 |
|----------|---------|---------|
| 单用户 CLI | 环境变量 + 配置文件 | OAuth、keychain、多租户 |
| 多用户 SaaS | OAuth + 安全存储 + 多租户 | 环境变量 |
| 企业内部 | API key + vault 集成 | OAuth |
| 桌面应用 | OS keychain + OAuth | 环境变量 |

## 7. Implementation Steps

1. 确定凭证来源——API key / OAuth / 其他
2. 实现优先级查找链
3. 如需 OAuth：实现 PKCE + token 存储
4. 实现刷新——过期前异步刷新 + inflight 去重
5. 选择安全存储——keychain / 加密文件 / 环境变量
6. 验证——token 过期自动刷新？并发刷新安全？

## 8. Source Anchors

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| OAuth PKCE | `src/services/oauth/index.ts` | `OAuthService`, `startOAuthFlow()` |
| 凭证查找 | `src/utils/auth.ts` | `getAnthropicApiKeyWithSource()` |
| Token 刷新 | `src/utils/auth.ts` | `checkAndRefreshOAuthTokenIfNeeded()` |
| OAuth 配置 | `src/constants/oauth.ts` | scopes, `OAUTH_BETA_HEADER` |
