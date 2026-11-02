# workdir-relocator

> 把 AI Agent / 编程工具的工作目录透明迁移到其他磁盘。
> 原路径保留为软链接，应用完全无感知。

[English](README.md) | **简体中文**

## 为什么需要它

AI 编程助手和聊天客户端越来越占空间：Claude Code、Cursor、Codex CLI、Windsurf、
Gemini CLI 等等。它们默认把技能、会话、项目和生成文件都缓存在系统盘上。当系统盘
空间紧张时，你会希望这些数据搬到外置 SSD 或第二块硬盘上——同时又不想逐个改工具
设置、不想破坏登录态、不想重新配置工作流。

`workdir-relocator` 只做一件事：把一个目录原子地复制到新磁盘，再把原路径替换成
软链接，整个过程对应用透明。

## 特性

- **透明**：原路径变成软链接，应用继续用旧路径即可。
- **安全**：rsync 双重校验，任何步骤失败自动回滚。
- **处理竞争条件**：应用在运行中会重建被删目录，脚本用原子重试循环（最多 300 次）
  抢在重建前完成软链接。
- **可回退**：保留 `<name>.old` 备份，确认一切正常后再删。
- **幂等**：对已经迁移过的目录会直接拒绝，不会重复执行。
- **零依赖**：Python 3 标准库 + `rsync`（macOS / Linux 自带）。

## 快速开始

有两种使用方式，按你的场景选。

### 方式一：作为 Agent Skill 安装（推荐）

本项目按标准 Skill 打包，任何 AI Agent 都可以加载。

1. 把整个文件夹复制到你的 Agent 用户技能目录：

```bash
# macOS / Linux 上的典型位置：
cp -R workdir-relocator ~/.doubao/agent_mode/workspace/.user_skills/
# 其他 Agent 可能使用 ~/.config/<agent>/skills/ 或类似路径，
# 具体目录以你所用 Agent 的文档为准。
```

2. 重启或重新加载 Agent，它会从 `SKILL.md` 里的 `name` 和 `description`
   自动发现这个 Skill。

3. 然后直接用自然语言提需求即可，例如：

```text
"帮我把 ~/.claude 这个目录迁移到 /Volumes/ExtSSD/cache。"
"系统盘满了，把 Cursor 的缓存挪到外置硬盘。"
```

Agent 会先跑一次 dry-run 展示计划，你确认后再正式执行。

### 方式二：作为独立命令行工具使用

不依赖任何 Agent，直接运行脚本。

```bash
# 1. 预览计划（不做任何修改）
python3 scripts/relocate.py \
  --from ~/.claude \
  --to "/Volumes/ExtSSD/cache" \
  --dry-run

# 2. 正式执行
python3 scripts/relocate.py \
  --from ~/.claude \
  --to "/Volumes/ExtSSD/cache"

# 3. 确认应用工作正常后，删除备份
rm -rf ~/.claude.old
```

### 命令行参数

| 参数 | 说明 |
|---|---|
| `--from <路径>` | 要迁移的目录，如 `~/.claude`、`~/.codex`。 |
| `--to <路径>` | 目标盘上的父目录，会在里面新建一个文件夹。 |
| `--name <名称>` | 自定义新目录名（默认与源目录同名）。 |
| `--dry-run` | 只做前置检查和 rsync 预览，不实际替换。 |

## 工作原理

```
1. 前置检查     源存在、目标可写、磁盘空间 ≥ 源大小 × 1.2、
                当前 shell 不在源目录内
2. 复制         rsync -a --delete 源/ → 目标/
3. 校验         再跑一次 rsync --dry-run，必须零差异
4. 原子替换     把源目录改名为 source.old（同卷 rename）
                重试循环：清理应用重建的目录 → 建软链接 → 目标
5. 写入探针     通过原路径写一个文件，确认它落到目标盘
6. 完成         备份保留在 source.old，并给出回滚方法
```

## 常见可迁移目录

| 工具 | 工作目录（macOS） |
|---|---|
| Claude Code | `~/.claude/` |
| Codex CLI | `~/.codex/` |
| Gemini CLI | `~/.gemini/` |
| Cursor（缓存） | `~/Library/Application Support/Cursor/` |
| Windsurf（缓存） | `~/Library/Application Support/Windsurf/` |
| 豆包工作 | `~/Doubao` |

完整表格（含 Linux / Windows）和迁移前检查清单见
[`references/agents.md`](references/agents.md)。

## 注意事项

- **目标盘必须保持挂载**：如果外置硬盘被拔掉，原路径会变成悬空链接，应用无法
  打开工作目录；插回硬盘即恢复。
- **不要用 exFAT / FAT32**：这些文件系统不保留软链接和 Unix 权限。请使用
  APFS（macOS）、ext4（Linux）或 Windows 上的 NTFS。
- **建议先退出应用**：重试循环能处理运行中的应用，但干净退出更稳妥。
- **暂不支持 Windows**：脚本使用 POSIX 软链接和 rsync，Windows 需要 `mklink /D`，
  目前未覆盖。

## 如何回滚

如果迁移后发现异常：

```bash
rm ~/.claude                  # 删除软链接
mv ~/.claude.old ~/.claude    # 恢复原目录
```

如果脚本在执行过程中任何一步失败，也会自动回滚。

## 开源协议

[MIT](LICENSE)
