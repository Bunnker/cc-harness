---
name: voice-input
description: "CLI Agent 如何支持语音输入，跨平台可靠且零配置"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# Agent 语音输入 (Voice Input)

## 1. Problem — 打字效率低，语音是更自然的输入方式

CLI 环境下描述复杂需求时，打字速度是瓶颈。语音输入在移动端和可及性场景中尤其重要。但 CLI 环境没有浏览器的 Web Speech API，需要从操作系统层面解决音频捕获。

通用问题是：**如何在 CLI/桌面 Agent 中实现可靠的 Push-to-Talk 语音输入，跨平台且不需要用户额外安装依赖。**

## 2. In Claude Code — 源码事实

- 入口：`src/services/voice.ts`（526 行）— 录音管理 + 平台检测
- STT：`src/services/voiceStreamSTT.ts` — 流式语音转文字
- 关键词：`src/services/voiceKeyterms.ts` — 技术术语 hints 提升识别准确度
- Native 模块：`audio-capture-napi`（cpal 绑定）— macOS CoreAudio / Linux ALSA / Windows WASAPI
- Fallback：Linux 上 SoX `rec` 或 arecord
- 懒加载：Native 模块在首次语音按键时才 `import()`（dlopen 冷启动可达 8 秒）
- 采样率：16000 Hz，16-bit PCM
- 权限：macOS TCC 麦克风权限检测 + 引导

## 3. Transferable Pattern — 分层音频捕获 + 懒加载

从 CC 抽象出来：
1. **分层策略**：Native API 优先（低延迟）→ CLI 工具 fallback（兼容性）→ 不支持环境静默禁用
2. **懒加载**：音频模块体积大且加载慢，不在启动时加载，在首次使用时才加载
3. **权限预检**：调用前检查权限，引导用户授权，而不是直接失败

## 4. Minimal Portable Version

最小版：**单平台（如 macOS）+ 系统命令录音（`rec`）+ 非流式 STT API 调用**。

升级路径：单平台 CLI 录音 → + 多平台 fallback → + Native 模块 → + 流式 STT → + 术语 hints

## 5. Do Not Cargo-Cult

1. **不要照搬 Native NAPI 模块**。如果不需要低延迟，系统命令（`rec`/`arecord`/`ffmpeg`）完全够用
2. **不要照搬 Push-to-Talk 模式**。VAD（Voice Activity Detection）自动检测可能更适合某些场景
3. **不要照搬懒加载策略**。如果音频模块加载快（< 100ms），直接在启动时加载更简单
4. **不要照搬 Homespace 环境检测**。这是 CC 特有的云环境概念

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议删掉 | 注意事项 |
|----------|---------|---------|---------|
| CLI Agent | 系统命令录音 + STT | Native 模块（过度工程） | SoX/ffmpeg 足够 |
| 桌面应用 | Native 模块 + 流式 STT | CLI fallback | 用户期望低延迟 |
| Web 应用 | 不适用（用 Web Speech API） | 全部 | 浏览器已内置 |
| 移动端 | 不适用（用平台 API） | 全部 | iOS/Android 原生 |

## 7. Implementation Steps

1. 选择目标平台——确定需要支持哪些 OS
2. 选择录音方案——Native vs 系统命令
3. 实现录音管理——start/stop + 权限检查
4. 集成 STT 服务——选择 API（Whisper/Google/Deepgram）
5. 实现 Push-to-Talk 交互——快捷键绑定
6. 验证——不同环境下的录音质量和识别准确度

## 8. Source Anchors

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 录音管理 | `src/services/voice.ts` | `startRecording()`, `stopRecording()`, `checkRecordingAvailability()` |
| Native 懒加载 | `src/services/voice.ts` | `loadAudioNapi()`, `audioNapiPromise` |
| 流式 STT | `src/services/voiceStreamSTT.ts` | — |
| 术语 hints | `src/services/voiceKeyterms.ts` | `KEY_TERMS` |
