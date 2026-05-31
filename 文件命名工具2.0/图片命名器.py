# -*- coding: utf-8 -*-
"""
文件批量命名器 v2.0
基于 EXIF DateTimeOriginal 或文件修改时间，支持所有文件类型
ttkbootstrap 现代 UI | 兼容简体中文 Windows

用法：双击 启动.bat 或 直接运行本脚本
"""

import os
import threading
import ctypes
import traceback
from datetime import datetime

import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox

from PIL import Image
from PIL.ExifTags import TAGS

# ═══════════════ Win32 API：设置文件时间 ═══════════════
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime",  ctypes.c_uint32),
        ("dwHighDateTime", ctypes.c_uint32),
    ]

GENERIC_WRITE            = 0x40000000
FILE_SHARE_READ          = 0x00000001
FILE_SHARE_WRITE         = 0x00000002
OPEN_EXISTING            = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
INVALID_HANDLE_VALUE     = ctypes.c_void_p(-1).value


def _datetime_to_filetime(dt: datetime) -> FILETIME:
    EPOCH_1601 = 11644473600
    ns100 = int((dt.timestamp() + EPOCH_1601) * 10_000_000)
    ft = FILETIME()
    ft.dwLowDateTime  = ns100 & 0xFFFFFFFF
    ft.dwHighDateTime = (ns100 >> 32) & 0xFFFFFFFF
    return ft


def sync_file_times(filepath: str, dt: datetime) -> bool:
    """将文件的创建/修改/访问时间全部同步为 dt"""
    try:
        ts = dt.timestamp()
        os.utime(filepath, (ts, ts))
    except OSError:
        pass

    ft = _datetime_to_filetime(dt)
    handle = kernel32.CreateFileW(
        filepath, GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None,
    )

    if handle == INVALID_HANDLE_VALUE:
        return False

    result = kernel32.SetFileTime(
        handle,
        ctypes.byref(ft),  # 创建时间
        ctypes.byref(ft),  # 访问时间
        ctypes.byref(ft),  # 修改时间
    )
    kernel32.CloseHandle(handle)
    return result != 0


# ═══════════════ EXIF 读取 ═══════════════
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif",
                    ".webp", ".heic", ".heif", ".gif", ".dng", ".cr2",
                    ".nef", ".arw", ".orf", ".rw2"}


def get_exif_datetime_original(filepath: str):
    """读取 EXIF DateTimeOriginal，返回 datetime 或 None"""
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        return None  # 非图片文件直接跳过，避免 PIL 报错
    try:
        img = Image.open(filepath)
        exif_data = img.getexif()
        if not exif_data:
            return None
        datetime_str = None
        subsec_str = None
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, "")
            if tag_name == "DateTimeOriginal":
                datetime_str = value
            elif tag_name == "SubsecTimeOriginal":
                subsec_str = value
        if datetime_str is None:
            for tag_id, value in exif_data.items():
                if TAGS.get(tag_id, "") == "DateTime":
                    datetime_str = value
                    break
        if datetime_str is None:
            return None
        date_str = datetime_str.strip()
        if subsec_str:
            date_str = date_str + "." + subsec_str.strip()
        for fmt in ["%Y:%m:%d %H:%M:%S.%f", "%Y:%m:%d %H:%M:%S"]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None
    except Exception:
        return None


def get_file_mtime(filepath: str):
    """读取文件修改时间"""
    return datetime.fromtimestamp(os.path.getmtime(filepath))


def get_best_datetime(filepath: str):
    """优先 EXIF，其次文件修改时间"""
    exif_dt = get_exif_datetime_original(filepath)
    if exif_dt:
        return exif_dt, "EXIF (DateTimeOriginal)"
    return get_file_mtime(filepath), "文件修改时间"


# ═══════════════ GUI 应用 ═══════════════
class FileRenamerApp:
    def __init__(self):
        # 使用 cosmo 主题（现代清爽风格）
        self.root = tb.Window(themename="cosmo")
        self.root.title("文件批量命名器 v2.0")
        self.root.geometry("1060x660")
        self.root.minsize(820, 500)

        # 字体
        self.root.option_add("*Font", ("Microsoft YaHei UI", 9))

        # 数据
        self.folder_path   = tb.StringVar()
        self.ext_filter    = tb.StringVar(value="*")  # 默认全部文件
        self.scan_results  = []
        self.new_names     = set()

        self._build_ui()

    # ────────── UI ──────────
    def _build_ui(self):
        # ---- 标题栏 ----
        header = tb.Frame(self.root, padding=(16, 14, 16, 10))
        header.pack(fill=X)
        tb.Label(
            header,
            text="文件批量命名器",
            font=("Microsoft YaHei UI", 14, "bold"),
            bootstyle="primary",
        ).pack(side=LEFT)
        tb.Label(
            header,
            text="v2.0  |  基于 EXIF / 修改时间重命名",
            font=("Microsoft YaHei UI", 9),
            bootstyle="secondary",
        ).pack(side=LEFT, padx=(10, 0))

        # ---- 分隔线 ----
        tb.Separator(self.root, bootstyle="secondary").pack(fill=X, padx=16)

        # ---- 工具栏 ----
        toolbar = tb.Frame(self.root, padding=(16, 12, 16, 6))
        toolbar.pack(fill=X)

        # 左：文件夹选择
        tb.Label(toolbar, text="文件夹", font=("Microsoft YaHei UI", 10)).pack(side=LEFT)
        tb.Entry(
            toolbar, textvariable=self.folder_path, width=52,
        ).pack(side=LEFT, fill=X, expand=True, padx=(8, 6))
        tb.Button(
            toolbar, text="浏览...", bootstyle="outline-secondary",
            command=self._on_browse, width=9,
        ).pack(side=LEFT)

        # ---- 第二行：过滤 + 操作按钮 ----
        action_bar = tb.Frame(self.root, padding=(16, 4, 16, 8))
        action_bar.pack(fill=X)

        # 过滤标签
        tb.Label(action_bar, text="扩展名", font=("Microsoft YaHei UI", 9)).pack(side=LEFT)
        self.ext_entry = tb.Entry(
            action_bar, textvariable=self.ext_filter, width=30,
        )
        self.ext_entry.pack(side=LEFT, padx=(6, 4))
        hint = tb.Label(
            action_bar,
            text="* = 全部  |  多个用空格分隔  |  例: .jpg .pdf",
            font=("Microsoft YaHei UI", 8),
            bootstyle="secondary",
        )
        hint.pack(side=LEFT, padx=(0, 16))

        # 右侧按钮组
        btn_frame = tb.Frame(action_bar)
        btn_frame.pack(side=RIGHT)

        tb.Button(
            btn_frame, text="扫描文件", bootstyle="primary",
            command=self._on_scan, width=11,
        ).pack(side=LEFT, padx=(0, 4))
        tb.Button(
            btn_frame, text="执行重命名", bootstyle="success",
            command=self._on_rename, width=11,
        ).pack(side=LEFT, padx=(0, 4))
        tb.Button(
            btn_frame, text="文件归集", bootstyle="info",
            command=self._on_open_collector, width=11,
        ).pack(side=LEFT)

        # ---- 主预览区 ----
        preview = tb.Frame(self.root, padding=(16, 2, 16, 4))
        preview.pack(fill=BOTH, expand=True)

        columns = ("#", "原文件名", "新文件名", "时间来源")
        self.tree = tb.Treeview(
            preview,
            columns=columns,
            show="headings",
            selectmode="extended",
            bootstyle="secondary",
        )
        self.tree.heading("#",      text="#",      anchor=CENTER)
        self.tree.heading("原文件名", text="原文件名", anchor=W)
        self.tree.heading("新文件名", text="新文件名", anchor=W)
        self.tree.heading("时间来源", text="时间来源", anchor=CENTER)

        self.tree.column("#",      width=42,  anchor=CENTER, stretch=False)
        self.tree.column("原文件名", width=320, anchor=W)
        self.tree.column("新文件名", width=320, anchor=W)
        self.tree.column("时间来源", width=170, anchor=CENTER)

        vsb = tb.Scrollbar(preview, orient=VERTICAL, command=self.tree.yview)
        hsb = tb.Scrollbar(preview, orient=HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        preview.rowconfigure(0, weight=1)
        preview.columnconfigure(0, weight=1)

        # 右键菜单
        self.tree_menu = tb.Menu(self.root, tearoff=0)
        self.tree_menu.add_command(label="移除选中行", command=self._on_remove_selected)
        self.tree.bind("<Button-3>", self._on_tree_right_click)

        # 行色彩标记
        self.tree.tag_configure("changed", foreground="#2563eb")
        self.tree.tag_configure("same",    foreground="#9ca3af")

        # ---- 底部：进度 + 日志 ----
        bottom = tb.Frame(self.root, padding=(16, 2, 16, 8))
        bottom.pack(fill=X)

        self.progress = tb.Progressbar(bottom, mode=DETERMINATE, bootstyle="success-striped")
        self.progress.pack(fill=X, pady=(0, 4))

        # 日志（深色终端风格）
        log_container = tb.Frame(bottom)
        log_container.pack(fill=BOTH, expand=True)

        self.log_text = tb.Text(
            log_container, height=5, wrap="word",
            font=("Cascadia Code", 9),
            bg="#1a1a2e", fg="#a0ffa0", insertbackground="#a0ffa0",
        )
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        tb.Scrollbar(
            log_container, orient=VERTICAL, command=self.log_text.yview,
        ).pack(side=RIGHT, fill=Y)
        self.log_text.configure(yscrollcommand=log_container.winfo_children()[-1].set)

        # 状态栏
        self.status_var = tb.StringVar(value="就绪 — 选择文件夹后点击「扫描文件」")
        tb.Label(
            self.root, textvariable=self.status_var,
            bootstyle="secondary", anchor=W, padding=(14, 5),
            font=("Microsoft YaHei UI", 8),
        ).pack(side=BOTTOM, fill=X)

    # ────────── 日志 ──────────
    def _log(self, msg: str):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    # ────────── 浏览文件夹 ──────────
    def _on_browse(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(title="选择文件夹")
        if path:
            self.folder_path.set(path)
            self._log(f"已选择文件夹: {path}")

    # ────────── 扫描 ──────────
    def _on_scan(self):
        folder = self.folder_path.get().strip()
        if not folder:
            Messagebox.show_warning("请先选择文件夹！", "提示")
            return
        if not os.path.isdir(folder):
            Messagebox.show_error(f"文件夹不存在:\n{folder}", "错误")
            return

        self._log(f"══════ 开始扫描: {folder}")
        self.status_var.set("正在扫描…")

        # 清空
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.scan_results.clear()
        self.new_names.clear()

        threading.Thread(target=self._scan_worker, args=(folder,), daemon=True).start()

    def _scan_worker(self, folder: str):
        try:
            # 解析扩展名过滤
            raw = self.ext_filter.get().strip()
            if raw == "*" or raw == "":
                exts = None  # 全部文件
            else:
                exts = set()
                for tok in raw.split():
                    tok = tok.strip().lower()
                    if tok and tok != "*":
                        exts.add(tok if tok.startswith(".") else f".{tok}")

            # 收集文件
            files = []
            try:
                entries = os.listdir(folder)
            except PermissionError:
                self.root.after(0, lambda: self._log("错误: 文件夹无读取权限"))
                self.root.after(0, lambda: self.status_var.set("扫描失败"))
                return

            for entry in entries:
                full = os.path.join(folder, entry)
                if os.path.isfile(full):
                    if exts is None or os.path.splitext(entry)[1].lower() in exts:
                        files.append(full)

            total = len(files)
            self.root.after(0, lambda t=total: self._log(f"找到 {t} 个文件，正在解析时间…"))

            exif_count = 0
            for idx, filepath in enumerate(files):
                dt, source = get_best_datetime(filepath)
                if source.startswith("EXIF"):
                    exif_count += 1

                old_name = os.path.basename(filepath)
                ext = os.path.splitext(filepath)[1].lower()
                base_name = dt.strftime("%Y_%m_%d_%H_%M_%S")
                new_name = base_name + ext

                # 重名处理
                counter = 1
                candidate = new_name
                while candidate in self.new_names or (
                    candidate != old_name
                    and os.path.exists(os.path.join(folder, candidate))
                ):
                    candidate = f"{base_name}_{counter}{ext}"
                    counter += 1
                self.new_names.add(candidate)

                self.scan_results.append((filepath, old_name, candidate, source, dt))

                pct = int((idx + 1) / total * 100)
                self.root.after(0, lambda p=pct: self.progress.configure(value=p))
                self.root.after(0, lambda n=total, i=idx: self.status_var.set(f"扫描中… {i+1}/{n}"))

            self.root.after(0, self._populate_treeview)
            self.root.after(0, lambda: self.progress.configure(value=0))

            final_msg = f"扫描完成！共 {total} 个文件"
            if exif_count > 0:
                final_msg += f"，其中 {exif_count} 个读取到 EXIF 信息"
            self.root.after(0, lambda: self._log(final_msg))
            self.root.after(0, lambda: self.status_var.set(
                f"扫描完毕 — {len(self.scan_results)} 个文件待处理，请在表格中检查后点击「执行重命名」"
            ))

        except Exception:
            self.root.after(0, lambda: self._log(traceback.format_exc()))
            self.root.after(0, lambda: self.status_var.set("扫描出错！查看日志"))

    # ────────── Treeview ──────────
    def _populate_treeview(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, (_, old, new, src, dt) in enumerate(self.scan_results, 1):
            tag = "same" if old == new else "changed"
            self.tree.insert("", "end", values=(i, old, new, src), tags=(tag,))

    # ────────── 重命名 ──────────
    def _on_rename(self):
        if not self.scan_results:
            Messagebox.show_info("没有可重命名的文件，请先扫描！", "提示")
            return

        # 统计需要改名的
        to_rename = sum(1 for r in self.scan_results if r[1] != r[2])
        to_skip   = len(self.scan_results) - to_rename

        msg = (
            f"共 {len(self.scan_results)} 个文件\n"
            f"  需重命名: {to_rename} 个\n"
            f"  无需改名: {to_skip} 个\n\n"
            f"重命名后将同步文件时间。确定继续？"
        )
        if to_rename == 0:
            Messagebox.show_info("所有文件名已符合格式，无需重命名。", "提示")
            return

        if not Messagebox.yesno(msg, "确认重命名"):
            return

        self._log("══════ 开始重命名 ══════")
        self.status_var.set("正在重命名…")
        self.progress.configure(value=0)

        stats = {"renamed": 0, "skipped": 0, "errors": 0}
        threading.Thread(target=self._rename_worker, args=(stats,), daemon=True).start()

    def _rename_worker(self, stats: dict):
        folder = self.folder_path.get().strip()
        total = len(self.scan_results)

        for idx, (filepath, old_name, new_name, source, dt) in enumerate(self.scan_results):
            if old_name == new_name:
                stats["skipped"] += 1
                # 仍可能同步时间
                actual_path = filepath
            else:
                new_path = os.path.join(folder, new_name)
                try:
                    os.rename(filepath, new_path)
                    stats["renamed"] += 1
                    self.root.after(0, lambda o=old_name, n=new_name: self._log(f"  [重命名] {o} → {n}"))
                    actual_path = new_path
                    self.scan_results[idx] = (new_path, old_name, new_name, source, dt)
                except OSError as e:
                    stats["errors"] += 1
                    self.root.after(0, lambda o=old_name, e=e: self._log(f"  [错误] {o}: {e}"))
                    continue

            if sync_file_times(actual_path, dt):
                self.root.after(0, lambda: self._log("          ✓ 时间已同步"))
            else:
                self.root.after(0, lambda: self._log("          ⚠ 时间同步失败（可能文件被占用）"))

            pct = int((idx + 1) / total * 100)
            self.root.after(0, lambda p=pct: self.progress.configure(value=p))
            self.root.after(0, lambda i=idx, t=total: self.status_var.set(f"处理中… {i+1}/{t}"))

        summary = (
            f"══════ 完成 ══════\n"
            f"重命名 {stats['renamed']} | 跳过 {stats['skipped']} | 错误 {stats['errors']} | 共 {total}"
        )
        self.root.after(0, lambda: self._log(summary))
        self.root.after(0, lambda: self.progress.configure(value=0))
        self.root.after(0, lambda: self.status_var.set(
            f"完成！重命名 {stats['renamed']} 个，跳过 {stats['skipped']} 个，错误 {stats['errors']} 个"
        ))
        if stats["errors"] > 0:
            self.root.after(0, lambda: Messagebox.show_warning(
                f"有 {stats['errors']} 个文件出错，请查看日志。", "完成"
            ))

    # ────────── 右键菜单 ──────────
    def _on_tree_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.tree_menu.post(event.x_root, event.y_root)

    def _on_remove_selected(self):
        selected = self.tree.selection()
        if not selected:
            return
        indices = sorted(
            [int(self.tree.item(s, "values")[0]) - 1 for s in selected],
            reverse=True,
        )
        for i in indices:
            del self.scan_results[i]
        self._populate_treeview()
        self._log(f"已从列表移除 {len(indices)} 项")
        self.status_var.set(f"预览列表更新 — 共 {len(self.scan_results)} 个文件")

    # ────────── 文件归集 ──────────
    def _on_open_collector(self):
        FileCollectorWindow(self.root)

    def run(self):
        self.root.mainloop()


# ═══════════════ 文件归集重命名窗口 ═══════════════
class FileCollectorWindow:
    """收集多个来源的文件，归集到输出文件夹并按 EXIF/修改时间重命名"""

    def __init__(self, parent):
        import tkinter as tk
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("文件归集重命名器")
        self.win.geometry("900x650")
        self.win.minsize(700, 500)

        self.source_path = tb.StringVar()
        self.items = []          # [(name, is_dir, abspath), ...]
        self.selected = []       # [True/False, ...] 与 items 一一对应

        self.output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "输出文件夹"
        )

        self._build_collector_ui()

    def _build_collector_ui(self):
        # ---- 标题 ----
        h = tb.Frame(self.win, padding=(14, 12, 14, 6))
        h.pack(fill=X)
        tb.Label(h, text="文件归集重命名器", font=("Microsoft YaHei UI", 13, "bold"),
                 bootstyle="info").pack(side=LEFT)
        tb.Label(h, text="从分散文件夹归集文件，统一重命名", font=("Microsoft YaHei UI", 9),
                 bootstyle="secondary").pack(side=LEFT, padx=10)
        tb.Separator(self.win, bootstyle="secondary").pack(fill=X, padx=14)

        # ---- 工具栏 ----
        tb2 = tb.Frame(self.win, padding=(14, 10, 14, 6))
        tb2.pack(fill=X)
        tb.Label(tb2, text="源文件夹", font=("Microsoft YaHei UI", 10)).pack(side=LEFT)
        tb.Entry(tb2, textvariable=self.source_path, width=48).pack(
            side=LEFT, fill=X, expand=True, padx=(8, 6))
        tb.Button(tb2, text="浏览...", bootstyle="outline-secondary",
                  command=self._browse_source, width=8).pack(side=LEFT, padx=(0, 6))
        tb.Button(tb2, text="加载列表", bootstyle="primary",
                  command=self._load_items, width=9).pack(side=LEFT)

        # ---- 提示 ----
        tip = tb.Frame(self.win, padding=(14, 0, 14, 4))
        tip.pack(fill=X)
        tb.Label(tip, text="双击行切换「已选」/「已排除」| 文件夹将被递归展开，仅收集其中的文件",
                 font=("Microsoft YaHei UI", 8), bootstyle="secondary").pack(side=LEFT)

        # ---- 列表 ----
        lst_frame = tb.Frame(self.win, padding=(14, 2, 14, 4))
        lst_frame.pack(fill=BOTH, expand=True)

        cols = ("#", "文件名", "类型", "修改时间", "状态")
        self.lst = tb.Treeview(lst_frame, columns=cols, show="headings",
                                selectmode="extended", bootstyle="secondary")
        self.lst.heading("#", text="#", anchor=CENTER)
        self.lst.heading("文件名", text="文件名", anchor=W)
        self.lst.heading("类型", text="类型", anchor=CENTER)
        self.lst.heading("修改时间", text="修改时间", anchor=CENTER)
        self.lst.heading("状态", text="状态", anchor=CENTER)
        self.lst.column("#", width=36, anchor=CENTER, stretch=False)
        self.lst.column("文件名", width=280, anchor=W)
        self.lst.column("类型", width=60, anchor=CENTER, stretch=False)
        self.lst.column("修改时间", width=130, anchor=CENTER)
        self.lst.column("状态", width=70, anchor=CENTER, stretch=False)

        vsb = tb.Scrollbar(lst_frame, orient=VERTICAL, command=self.lst.yview)
        self.lst.configure(yscrollcommand=vsb.set)
        self.lst.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        lst_frame.rowconfigure(0, weight=1)
        lst_frame.columnconfigure(0, weight=1)

        self.lst.tag_configure("picked", foreground="#16a34a")
        self.lst.tag_configure("excluded", foreground="#dc2626")
        self.lst.bind("<Double-1>", self._toggle_item)

        # ---- 批量操作 + 信息 ----
        ctrl = tb.Frame(self.win, padding=(14, 4, 14, 4))
        ctrl.pack(fill=X)
        tb.Button(ctrl, text="全部选定", bootstyle="outline-success",
                  command=lambda: self._batch_toggle(True), width=9).pack(side=LEFT, padx=(0, 4))
        tb.Button(ctrl, text="全部排除", bootstyle="outline-danger",
                  command=lambda: self._batch_toggle(False), width=9).pack(side=LEFT, padx=(0, 16))
        self.info_var = tb.StringVar(value="")
        tb.Label(ctrl, textvariable=self.info_var, font=("Microsoft YaHei UI", 9),
                 bootstyle="secondary").pack(side=LEFT)

        # ---- 底部操作 ----
        bottom = tb.Frame(self.win, padding=(14, 6, 14, 10))
        bottom.pack(fill=X)
        tb.Label(bottom, text=f"输出到: {self.output_dir}",
                 font=("Microsoft YaHei UI", 8), bootstyle="secondary").pack(side=LEFT)
        self.prog = tb.Progressbar(bottom, mode=DETERMINATE, bootstyle="info-striped", length=200)
        self.prog.pack(side=RIGHT, padx=(8, 0))
        tb.Button(bottom, text="开始归集并重命名", bootstyle="success",
                  command=self._execute_collect, width=16).pack(side=RIGHT, padx=(0, 8))

        self._update_info()

    # ── 浏览源文件夹 ──
    def _browse_source(self):
        from tkinter import filedialog
        p = filedialog.askdirectory(title="选择源文件夹", parent=self.win)
        if p:
            self.source_path.set(p)

    # ── 加载顶层条目 ──
    def _load_items(self):
        folder = self.source_path.get().strip()
        if not folder or not os.path.isdir(folder):
            Messagebox.show_warning("请先选择有效文件夹！", "提示", parent=self.win)
            return
        self.items.clear()
        self.selected.clear()
        for item in self.lst.get_children():
            self.lst.delete(item)
        try:
            for name in sorted(os.listdir(folder)):
                fp = os.path.join(folder, name)
                is_dir = os.path.isdir(fp)
                mtime = datetime.fromtimestamp(os.path.getmtime(fp))
                self.items.append((name, is_dir, fp))
                self.selected.append(True)
        except PermissionError:
            Messagebox.show_error("文件夹无读取权限！", "错误", parent=self.win)
            return

        self._refresh_list()
        self._update_info()

    def _refresh_list(self):
        for item in self.lst.get_children():
            self.lst.delete(item)
        for i, (name, is_dir, _) in enumerate(self.items):
            mtime = datetime.fromtimestamp(os.path.getmtime(self.items[i][2]))
            tag = "picked" if self.selected[i] else "excluded"
            self.lst.insert("", "end", iid=str(i),
                            values=(i + 1, name, "文件夹" if is_dir else "文件",
                                    mtime.strftime("%Y-%m-%d %H:%M"),
                                    "已选" if self.selected[i] else "已排除"),
                            tags=(tag,))

    # ── 切换 ──
    def _toggle_item(self, event):
        iid = self.lst.identify_row(event.y)
        if iid:
            idx = int(iid)
            self.selected[idx] = not self.selected[idx]
            self._refresh_list()
            self._update_info()

    def _batch_toggle(self, state: bool):
        self.selected = [state] * len(self.items)
        self._refresh_list()
        self._update_info()

    def _update_info(self):
        sel = sum(self.selected)
        total = len(self.items)
        # 统计选定文件夹中递归的文件数
        file_count = 0
        for i, (_, is_dir, fp) in enumerate(self.items):
            if self.selected[i]:
                if is_dir:
                    for _, _, filenames in os.walk(fp):
                        file_count += len(filenames)
                else:
                    file_count += 1
        self.info_var.set(f"已选 {sel}/{total} 项 → 预计归集 {file_count} 个文件")

    # ── 执行 ──
    def _execute_collect(self):
        if not self.items:
            Messagebox.show_info("列表为空，请先加载！", "提示", parent=self.win)
            return
        sel = sum(self.selected)
        if sel == 0:
            Messagebox.show_info("没有选定任何项目！", "提示", parent=self.win)
            return

        ok = Messagebox.yesno(
            f"将把选定的 {sel} 个项目中的文件\n"
            f"归集到「{self.output_dir}」并重命名。\n\n确定开始？",
            "确认归集", parent=self.win
        )
        if not ok:
            return

        os.makedirs(self.output_dir, exist_ok=True)
        self.prog.configure(value=0)
        threading.Thread(target=self._collect_worker, daemon=True).start()

    def _collect_worker(self):
        import shutil

        # 收集所有待处理的文件路径
        to_process = []
        for i, (name, is_dir, fp) in enumerate(self.items):
            if not self.selected[i]:
                continue
            if is_dir:
                for root, _, filenames in os.walk(fp):
                    for fn in filenames:
                        to_process.append(os.path.join(root, fn))
            else:
                to_process.append(fp)

        total = len(to_process)
        done = 0
        errors = 0
        used_names = set()

        for src in to_process:
            try:
                dt, _ = get_best_datetime(src)
                ext = os.path.splitext(src)[1].lower()
                base = dt.strftime("%Y_%m_%d_%H_%M_%S")
                new_name = base + ext

                # 重名
                c = 1
                candidate = new_name
                while candidate in used_names or os.path.exists(
                    os.path.join(self.output_dir, candidate)
                ):
                    candidate = f"{base}_{c}{ext}"
                    c += 1
                used_names.add(candidate)

                dest = os.path.join(self.output_dir, candidate)
                shutil.copy2(src, dest)
                sync_file_times(dest, dt)
                done += 1

            except Exception as e:
                errors += 1

            pct = int((done + errors) / total * 100)
            self.win.after(0, lambda p=pct: self.prog.configure(value=p))

        self.win.after(0, lambda: self.prog.configure(value=0))
        self.win.after(0, lambda: Messagebox.show_info(
            f"归集完成！\n成功: {done} 个文件\n失败: {errors} 个\n\n输出目录: {self.output_dir}",
            "完成", parent=self.win
        ))


# ═══════════════ 入口 ═══════════════
def main():
    app = FileRenamerApp()
    app.run()

if __name__ == "__main__":
    main()
