from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import BooleanVar, Button, Checkbutton, Label, LabelFrame, StringVar, Tk, filedialog, messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from glm_grabber.config import ConfigError, load_config
from glm_grabber.gui_config import build_runner_environment, status_from_runner_line, update_config_file


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.yaml"
RUNNER_PATH = ROOT / "runner.py"
LOG_PATH = ROOT / "logs" / "events.jsonl"
SCREENSHOTS_DIR = ROOT / "screenshots"

PLAN_OPTIONS = ["Lite", "Pro", "Max"]
PERIOD_LABELS = {
    "连续包月": "month",
    "连续包季": "quarter",
    "连续包年": "year",
}
PERIOD_BY_VALUE = {value: label for label, value in PERIOD_LABELS.items()}


class GrabberGui:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("GLM Coding Plan 抢购助手")
        self.root.geometry("820x620")
        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()

        self.plan_var = StringVar(value="Pro")
        self.period_var = StringVar(value="连续包季")
        self.button_selector_var = StringVar(value="")
        self.start_at_var = StringVar(value="09:59:58")
        self.parallel_pages_var = StringVar(value="3")
        self.force_unlock_var = BooleanVar(value=True)
        self.test_now_var = BooleanVar(value=False)
        self.server_time_sync_var = BooleanVar(value=True)
        self.t0_reload_var = BooleanVar(value=False)
        self.status_var = StringVar(value="未启动")
        self.armed_before_seconds_var = StringVar(value="0")
        self.armed_after_seconds_var = StringVar(value="120")
        self.click_cooldown_ms_var = StringVar(value="80")
        self.max_click_attempts_var = StringVar(value="0")
        self.crowd_retry_clicks_before_reload_var = StringVar(value="15")
        self.recovery_reload_interval_ms_var = StringVar(value="1500")
        self.server_time_samples_var = StringVar(value="5")

        self._build_ui()
        self._load_existing_config()
        self._poll_output()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        config_frame = LabelFrame(self.root, text="抢购配置", padx=12, pady=10)
        config_frame.pack(fill="x", padx=12, pady=10)

        Label(config_frame, text="套餐").grid(row=0, column=0, sticky="w")
        plan_box = ttk.Combobox(config_frame, textvariable=self.plan_var, values=PLAN_OPTIONS, state="readonly", width=18)
        plan_box.grid(row=0, column=1, padx=8, pady=6, sticky="w")

        Label(config_frame, text="周期").grid(row=0, column=2, sticky="w")
        period_box = ttk.Combobox(
            config_frame,
            textvariable=self.period_var,
            values=list(PERIOD_LABELS.keys()),
            state="readonly",
            width=18,
        )
        period_box.grid(row=0, column=3, padx=8, pady=6, sticky="w")

        Label(config_frame, text="开抢时间").grid(row=1, column=0, sticky="w")
        start_entry = ttk.Entry(config_frame, textvariable=self.start_at_var, width=20)
        start_entry.grid(row=1, column=1, padx=8, pady=6, sticky="w")

        Label(config_frame, text="并行页面数").grid(row=1, column=2, sticky="w")
        parallel_spin = ttk.Spinbox(config_frame, textvariable=self.parallel_pages_var, from_=1, to=8, width=8)
        parallel_spin.grid(row=1, column=3, padx=8, pady=6, sticky="w")

        Label(config_frame, text="手动按钮 CSS").grid(row=2, column=0, sticky="w")
        selector_entry = ttk.Entry(config_frame, textvariable=self.button_selector_var, width=24)
        selector_entry.grid(row=2, column=1, padx=8, pady=6, sticky="w")

        force_unlock = Checkbutton(
            config_frame,
            text="强制解灰点击（推荐开启）",
            variable=self.force_unlock_var,
        )
        force_unlock.grid(row=2, column=2, columnspan=2, padx=8, pady=6, sticky="w")

        test_now = Checkbutton(
            config_frame,
            text="立即测试（忽略开抢时间）",
            variable=self.test_now_var,
        )
        test_now.grid(row=3, column=0, columnspan=2, padx=0, pady=6, sticky="w")

        Label(config_frame, textvariable=self.status_var, foreground="#0a5").grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))

        timing_frame = LabelFrame(self.root, text="开抢窗口与点击策略", padx=12, pady=10)
        timing_frame.pack(fill="x", padx=12, pady=0)

        Label(timing_frame, text="提前开始秒数").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(timing_frame, textvariable=self.armed_before_seconds_var, from_=0, to=3600, width=10).grid(row=0, column=1, padx=8, pady=6, sticky="w")

        Label(timing_frame, text="持续秒数").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(timing_frame, textvariable=self.armed_after_seconds_var, from_=1, to=3600, width=10).grid(row=0, column=3, padx=8, pady=6, sticky="w")

        Label(timing_frame, text="点击间隔 ms").grid(row=0, column=4, sticky="w")
        ttk.Spinbox(timing_frame, textvariable=self.click_cooldown_ms_var, from_=1, to=5000, width=10).grid(row=0, column=5, padx=8, pady=6, sticky="w")

        Label(timing_frame, text="最大点击次数").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(timing_frame, textvariable=self.max_click_attempts_var, from_=0, to=99999, width=10).grid(row=1, column=1, padx=8, pady=6, sticky="w")

        Label(timing_frame, text="拥挤先点次数").grid(row=1, column=2, sticky="w")
        ttk.Spinbox(timing_frame, textvariable=self.crowd_retry_clicks_before_reload_var, from_=1, to=999, width=10).grid(row=1, column=3, padx=8, pady=6, sticky="w")

        Label(timing_frame, text="刷新间隔 ms").grid(row=1, column=4, sticky="w")
        ttk.Spinbox(timing_frame, textvariable=self.recovery_reload_interval_ms_var, from_=100, to=60000, increment=100, width=10).grid(row=1, column=5, padx=8, pady=6, sticky="w")

        server_sync = Checkbutton(
            timing_frame,
            text="服务器时间校准",
            variable=self.server_time_sync_var,
        )
        server_sync.grid(row=2, column=0, columnspan=2, padx=0, pady=6, sticky="w")

        Label(timing_frame, text="校准采样数").grid(row=2, column=2, sticky="w")
        ttk.Spinbox(timing_frame, textvariable=self.server_time_samples_var, from_=1, to=20, width=10).grid(row=2, column=3, padx=8, pady=6, sticky="w")

        t0_reload = Checkbutton(
            timing_frame,
            text="到点强制刷新一次",
            variable=self.t0_reload_var,
        )
        t0_reload.grid(row=2, column=4, columnspan=2, padx=8, pady=6, sticky="w")

        button_frame = LabelFrame(self.root, text="操作", padx=12, pady=10)
        button_frame.pack(fill="x", padx=12, pady=0)

        Button(button_frame, text="保存配置", width=14, command=self.save_config).grid(row=0, column=0, padx=5, pady=5)
        Button(button_frame, text="启动抢购", width=14, command=self.start_runner).grid(row=0, column=1, padx=5, pady=5)
        Button(button_frame, text="停止", width=14, command=self.stop_runner).grid(row=0, column=2, padx=5, pady=5)
        Button(button_frame, text="打开日志", width=14, command=self.open_log).grid(row=0, column=3, padx=5, pady=5)
        Button(button_frame, text="打开截图目录", width=14, command=self.open_screenshots).grid(row=0, column=4, padx=5, pady=5)
        Button(button_frame, text="选择配置", width=14, command=self.choose_config).grid(row=0, column=5, padx=5, pady=5)

        log_frame = LabelFrame(self.root, text="运行日志", padx=8, pady=8)
        log_frame.pack(fill="both", expand=True, padx=12, pady=10)
        self.log_text = ScrolledText(log_frame, height=22, wrap="word")
        self.log_text.pack(fill="both", expand=True)
        self.log("GUI 已就绪。保存配置后点击“启动抢购”。")

    def _load_existing_config(self) -> None:
        if not CONFIG_PATH.exists():
            return
        try:
            config = load_config(CONFIG_PATH)
        except ConfigError as exc:
            self.log(f"配置读取失败：{exc}")
            return
        self.plan_var.set(config.target.plan)
        self.period_var.set(PERIOD_BY_VALUE.get(config.target.period, "连续包季"))
        self.button_selector_var.set(config.target.button_selector or "")
        self.start_at_var.set(config.timing.start_at or "")
        self.parallel_pages_var.set(str(config.browser.parallel_pages))
        self.force_unlock_var.set(config.safety.force_unlock)
        self.server_time_sync_var.set(config.timing.server_time_sync)
        self.server_time_samples_var.set(str(config.timing.server_time_samples))
        self.t0_reload_var.set(config.timing.t0_reload)
        self.armed_before_seconds_var.set(str(config.timing.armed_before_seconds))
        self.armed_after_seconds_var.set(str(config.timing.armed_after_seconds))
        self.click_cooldown_ms_var.set(str(config.timing.click_cooldown_ms))
        self.max_click_attempts_var.set(str(config.timing.max_click_attempts))
        self.crowd_retry_clicks_before_reload_var.set(str(config.timing.crowd_retry_clicks_before_reload))
        self.recovery_reload_interval_ms_var.set(str(config.timing.recovery_reload_interval_ms))

    def save_config(self) -> None:
        try:
            update_config_file(
                CONFIG_PATH,
                plan=self.plan_var.get(),
                period=PERIOD_LABELS[self.period_var.get()],
                button_selector=self.button_selector_var.get(),
                start_at=self.start_at_var.get(),
                force_unlock=self.force_unlock_var.get(),
                parallel_pages=int(self.parallel_pages_var.get()),
                armed_before_seconds=int(self.armed_before_seconds_var.get()),
                armed_after_seconds=int(self.armed_after_seconds_var.get()),
                click_cooldown_ms=int(self.click_cooldown_ms_var.get()),
                max_click_attempts=int(self.max_click_attempts_var.get()),
                crowd_retry_clicks_before_reload=int(self.crowd_retry_clicks_before_reload_var.get()),
                recovery_reload_interval_ms=int(self.recovery_reload_interval_ms_var.get()),
                server_time_sync=self.server_time_sync_var.get(),
                server_time_samples=int(self.server_time_samples_var.get()),
                t0_reload=self.t0_reload_var.get(),
            )
            load_config(CONFIG_PATH)
        except Exception as exc:
            messagebox.showerror("配置错误", str(exc))
            return
        self.status_var.set("配置已保存")
        self.log(
            f"配置已保存：{self.plan_var.get()} / {self.period_var.get()} / "
            f"{self.start_at_var.get() or '立即'} / {self.parallel_pages_var.get()} 页并行"
        )

    def start_runner(self) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showinfo("正在运行", "抢购助手已经在运行。")
            return
        self.save_config()
        env = build_runner_environment(os.environ, ROOT)
        python_exe = ROOT / ".venv" / "Scripts" / "python.exe"
        if not python_exe.exists():
            python_exe = Path(sys.executable)

        command = [str(python_exe), str(RUNNER_PATH), "--config", str(CONFIG_PATH)]
        if self.test_now_var.get():
            command.append("--ignore-start-time")
        self.process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.status_var.set("运行中")
        mode = "立即测试模式" if self.test_now_var.get() else "定时模式"
        self.log(f"抢购助手已启动（{mode}），浏览器会自动打开。登录和验证码请手动处理。")
        threading.Thread(target=self._read_process_output, daemon=True).start()

    def stop_runner(self) -> None:
        if not self.process or self.process.poll() is not None:
            self.status_var.set("未启动")
            self.log("当前没有运行中的抢购进程。")
            return
        self.process.terminate()
        self.status_var.set("正在停止")
        self.log("已发送停止信号。")

    def open_log(self) -> None:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not LOG_PATH.exists():
            LOG_PATH.write_text("", encoding="utf-8")
        os.startfile(LOG_PATH)

    def open_screenshots(self) -> None:
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(SCREENSHOTS_DIR)

    def choose_config(self) -> None:
        chosen = filedialog.askopenfilename(
            title="选择配置文件",
            initialdir=str(ROOT),
            filetypes=[("YAML", "*.yaml *.yml"), ("All files", "*.*")],
        )
        if chosen:
            messagebox.showinfo("提示", "当前版本固定使用 config.yaml。你可以把选择的文件内容复制到 config.yaml。")

    def _read_process_output(self) -> None:
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            self.output_queue.put(line.rstrip())
        code = self.process.wait()
        self.output_queue.put(f"进程已退出，代码：{code}")

    def _poll_output(self) -> None:
        while True:
            try:
                line = self.output_queue.get_nowait()
            except queue.Empty:
                break
            self.log(line)
            status = status_from_runner_line(line)
            if status:
                self.status_var.set(status)
            if line.startswith("进程已退出"):
                self.status_var.set("已停止")
        self.root.after(150, self._poll_output)

    def log(self, message: str) -> None:
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")

    def _on_close(self) -> None:
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("确认退出", "抢购助手仍在运行，是否停止并退出？"):
                return
            self.stop_runner()
        self.root.destroy()


def main() -> None:
    root = Tk()
    GrabberGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
