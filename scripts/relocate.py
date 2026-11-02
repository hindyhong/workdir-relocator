#!/usr/bin/env python3
"""
relocate.py — 把一个目录原子迁移到另一个磁盘/分区，并用软链接透明替换原路径。

典型用途：AI 客户端/Agent 的工作目录、缓存目录默认放在系统盘空间紧张，
迁移到外置 SSD 或其他大容量盘后，原路径保持不变，客户端无感知。

用法：
    python3 relocate.py --from ~/Doubao --to "/Volumes/ExtSSD/local-cache"
    python3 relocate.py --from ~/.claude --to /Volumes/ExtSSD --name claude --dry-run

特点：
- rsync 复制 + 二次校验，内容不一致会中止
- 原子替换带重试：客户端正在运行会自动重建被删目录，脚本会反复清理并抢在重建前完成 symlink
- 自动保留 <from>.old 回滚备份，验证通过前不删
- 失败自动回滚到迁移前状态
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """执行外部命令。"""
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        capture_output=capture,
    )


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def dir_size(p: Path) -> int:
    total = 0
    for root, dirs, files in os.walk(p):
        for f in files:
            try:
                total += os.path.getsize(Path(root) / f)
            except OSError:
                pass
    return total


def free_space(p: Path) -> int:
    usage = shutil.disk_usage(p)
    return usage.free


def step(msg: str) -> None:
    print(f"\n== {msg}", flush=True)


def fail(msg: str, code: int = 1) -> None:
    print(f"\n[错误] {msg}", file=sys.stderr)
    sys.exit(code)


# ---------- 前置检查 ----------

def preflight(src: Path, dst_parent: Path, dst_name: str) -> Path:
    if not src.exists():
        fail(f"源目录不存在：{src}")
    if src.is_symlink():
        fail(f"{src} 已经是软链接 → {os.readlink(src)}，无需重复迁移")
    if not src.is_dir():
        fail(f"{src} 不是目录")

    if not dst_parent.exists():
        fail(f"目标父目录不存在：{dst_parent}（请先挂载磁盘/创建目录）")
    if not os.access(dst_parent, os.W_OK):
        fail(f"目标父目录不可写：{dst_parent}")

    dst = dst_parent / dst_name
    if dst.exists():
        # 已经存在：必须为空才能继续，避免覆盖
        if any(dst.iterdir()):
            fail(f"目标目录已存在且非空：{dst}\n请手动确认后清空或换一个 --name。")
        print(f"[提示] 目标目录已存在但为空：{dst}")

    src_size = dir_size(src)
    dst_free = free_space(dst_parent)
    print(f"源目录大小：{human_size(src_size)}")
    print(f"目标盘可用：{human_size(dst_free)}")
    if dst_free < src_size * 1.2 + 100 * 1024 * 1024:
        fail(f"目标盘空间不足（需要约 {human_size(src_size * 1.2)}，剩余 {human_size(dst_free)}）")

    # 检查源目录是否是当前 shell cwd
    try:
        cwd = Path.cwd().resolve()
        if cwd == src.resolve() or src.resolve() in cwd.parents:
            fail(f"当前 shell 工作目录在 {src} 内，无法删除它。请先 cd 到别的目录再执行。")
    except OSError:
        pass

    return dst


# ---------- 复制 ----------

def sync(src: Path, dst: Path, dry_run: bool) -> None:
    step(f"复制内容 → {dst}")
    # rsync -a：归档模式，保留权限/时间/软链接；结尾斜杠：复制目录内容而非目录本身
    cmd = ["rsync", "-a", "--delete", f"{src}/", str(dst) + "/"]
    if dry_run:
        cmd.append("--dry-run")
    r = run(cmd, check=False)
    if r.returncode != 0:
        fail(f"rsync 失败：\n{r.stderr}")
    if dry_run:
        print("(dry-run) rsync 预览完成，未实际写入")

    # 二次校验：再跑一次 dry-run，应该没有任何差异输出
    step("校验一致性（再次 rsync --dry-run）")
    r2 = run(["rsync", "-a", "--delete", "--dry-run", f"{src}/", str(dst) + "/"], check=False)
    if r2.stdout.strip():
        fail(f"复制后仍有差异，中止迁移：\n{r2.stdout}")
    print("内容一致 ✓")


# ---------- 原子替换 ----------

def atomic_replace(src: Path, dst: Path, dry_run: bool) -> Path:
    """
    把 src 替换成指向 dst 的软链接。
    返回备份路径 src.old。
    """
    old = src.with_name(src.name + ".old")
    if old.exists():
        fail(f"备份目录已存在：{old}\n请先手动处理（确认无用后删除，或恢复后重试）。")

    step(f"原子替换：{src} → 软链接 → {dst}")
    if dry_run:
        print("(dry-run) 跳过实际替换")
        return old

    # 第一步：把原目录改名成 .old（同卷 rename 原子操作）
    os.rename(src, old)
    print(f"原目录已备份为：{old}")

    # 第二步：反复尝试清理 + symlink，直到成功
    # 客户端可能在 src 被改名后立刻重建一个真实目录，需要不断清掉它再建链接
    for i in range(300):
        try:
            # 如果客户端重建了 src 目录，清空它
            if src.exists() and not src.is_symlink():
                for child in src.iterdir():
                    p = child
                    if p.is_symlink() or p.is_file():
                        p.unlink()
                    else:
                        shutil.rmtree(p)
                src.rmdir()
            elif src.is_symlink():
                # 已经是链接，检查指向
                if os.readlink(src) == str(dst):
                    print(f"软链接已就位（尝试 {i}）")
                    break
                else:
                    src.unlink()
            os.symlink(str(dst), src)
            print(f"软链接创建成功（尝试 {i}）")
            break
        except FileNotFoundError:
            # src 不存在，直接 symlink
            try:
                os.symlink(str(dst), src)
                print(f"软链接创建成功（尝试 {i}，空位直接建）")
                break
            except FileExistsError:
                time.sleep(0.005)
                continue
        except FileExistsError:
            time.sleep(0.005)
            continue
        except Exception as e:
            # 异常：回滚
            rollback(src, dst, old)
            fail(f"原子替换失败：{e}")
    else:
        rollback(src, dst, old)
        fail("客户端持续重建目录，300 次尝试仍未成功。请完全退出相关客户端后重试。")

    return old


def rollback(src: Path, dst: Path, old: Path) -> None:
    """失败回滚：删除软链接，把 .old 改回原名。"""
    print("\n[回滚] 正在恢复原目录...")
    try:
        if src.is_symlink() or src.exists():
            if src.is_symlink():
                src.unlink()
            else:
                shutil.rmtree(src)
        if old.exists():
            os.rename(old, src)
        print(f"[回滚] 已恢复：{src}")
    except Exception as e:
        print(f"[严重] 回滚失败！请手动处理：备份在 {old}", file=sys.stderr)
        print(f"错误：{e}", file=sys.stderr)


# ---------- 验证 ----------

def verify(src: Path, dst: Path, dry_run: bool) -> None:
    step("写入穿透验证")
    if dry_run:
        print("(dry-run) 跳过写入测试")
        return
    marker = src / ".relocate_verify"
    try:
        marker.write_text(f"ok {time.time()}\n")
        dst_marker = dst / ".relocate_verify"
        if not dst_marker.exists():
            rollback(src, dst, src.with_name(src.name + ".old"))
            fail("写入穿透失败：通过原路径写入的文件没出现在目标盘")
        dst_marker.unlink()
        print("写入穿透 ✓（通过原路径写入，实际落在目标盘）")
    finally:
        if marker.exists():
            marker.unlink()


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser(description="把目录原子迁移到其他盘并保留原路径（软链接）")
    ap.add_argument("--from", dest="src", required=True, help="当前目录绝对路径，如 ~/Doubao")
    ap.add_argument("--to", dest="dst_parent", required=True, help="目标父目录，如 /Volumes/ExtSSD/cache")
    ap.add_argument("--name", dest="dst_name", default=None, help="新目录名（默认与源目录同名）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不实际执行")
    args = ap.parse_args()

    src_raw = Path(os.path.expanduser(args.src))
    if src_raw.is_symlink():
        fail(f"{src_raw} 已经是软链接 → {os.readlink(src_raw)}，无需重复迁移")
    src = src_raw.resolve()
    dst_parent = Path(os.path.expanduser(args.dst_parent)).resolve()
    dst_name = args.dst_name or src.name

    step("前置检查")
    print(f"源：{src}")
    print(f"目标：{dst_parent / dst_name}")

    dst = preflight(src, dst_parent, dst_name)
    if not dst.exists():
        dst.mkdir(parents=True)

    sync(src, dst, args.dry_run)
    old = atomic_replace(src, dst, args.dry_run)
    verify(src, dst, args.dry_run)

    step("完成")
    print(f"原路径：{src}")
    print(f"实际数据：{dst}")
    print(f"回滚备份：{old}")
    print()
    print("后续：")
    print(f"  1. 确认客户端工作正常后，可手动删除备份：rm -rf {old}")
    print(f"  2. 目标磁盘未挂载时，{src} 会变成悬空链接，客户端工作目录不可用；插回磁盘即恢复。")
    print("  3. 若要回滚：先 rm 软链接，再把 .old 目录改名回原名。")


if __name__ == "__main__":
    main()
