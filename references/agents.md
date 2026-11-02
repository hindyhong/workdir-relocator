# 常见 AI 客户端 / Agent 目录位置参考

迁移前先确认要迁什么。一般有两类目录：

1. **工作目录 / 项目目录**：产出文件默认落盘的地方（用户最在意，空间增长最快）。
2. **应用数据目录**：登录态、缓存、技能、会话记录（通常不建议迁，迁了客户端升级可能出问题；只有系统盘严重不足时才考虑）。

## macOS

| 客户端 / 工具 | 工作目录（建议迁） | 应用数据（谨慎迁） |
|---|---|---|
| 豆包工作 / Doubao 电脑版 | `~/Doubao` | `~/Library/Application Support/Doubao/` |
| Claude Code | `~/.claude/`（项目、会话、配置都在这） | — |
| Codex CLI (OpenAI) | `~/.codex/` | — |
| Cursor | 项目自选；缓存 `~/Library/Application Support/Cursor/` | `~/Library/Application Support/Cursor/` |
| Windsurf | 项目自选；`~/Library/Application Support/Windsurf/` | 同左 |
| Gemini CLI | `~/.gemini/` | — |
| GitHub Copilot CLI | `~/.config/github-copilot/` | — |
| ChatGPT 桌面版 | — | `~/Library/Application Support/com.openai.chat/` |
| Raycast AI / 其他 | `~/.config/<app>/` 或 `~/Library/Application Support/<app>/` | 同左 |

## Linux

- 通用配置：`~/.config/<app>/`
- 常见数据：`~/.local/share/<app>/`
- 隐藏目录：`~/.claude/`、`~/.codex/`、`~/.gemini/`

## Windows

- 配置：`%APPDATA%\<app>\`（即 `C:\Users\<你>\AppData\Roaming\<app>\`）
- 本地数据：`%LOCALAPPDATA%\<app>\`
- 软链接替代方案：`mklink /D`（需管理员 cmd）

## 迁移前判断清单

- [ ] 这个目录里是否有正在运行的进程占用？`lsof +D <dir>` 检查（建议完全退出客户端）
- [ ] 目标盘是什么文件系统？外置 SSD 建议 APFS / ext4；exFAT 会丢权限和软链接，不要用
- [ ] 目标盘是否长期挂载？网络盘、可移动 U 盘不适合（拔掉就悬空）
- [ ] 空间余量是否 ≥ 源目录大小 × 1.2
- [ ] 客户端升级会不会检测软链接？少数应用会校验真实路径，迁移后观察一次启动是否报错
