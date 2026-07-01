from datetime import datetime
import math
import os
import sys
import customtkinter as ctk
from tkinter import scrolledtext
import importlib.util
from pathlib import Path
import shutil
import threading
import traceback
import pytz
import webbrowser
from PIL import ImageTk
from logs import LogHandler

# 创建日志处理器实例 - 用于保存日志
log_save_handler = LogHandler()

# 时区配置
TIME_ZONE = os.environ.get('TZ', 'Asia/Shanghai')

def get_now_str():
    """获取当前时间的字符串表示"""
    return datetime.now(pytz.timezone(TIME_ZONE)).strftime('%Y-%m-%d %H:%M:%S')

def get_config_dir():
    """获取配置文件目录（存于用户目录下）"""
    home_dir = str(Path.home())
    config_dir = os.path.join(home_dir, '.dify_upload')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

def get_config_path():
    """获取配置文件路径（存于用户目录下）"""
    return os.path.join(get_config_dir(), "configs.py")


def is_pyinstaller_environment():
    """判断当前环境是否为PyInstaller环境"""
    try:
        return hasattr(sys, '_MEIPASS')
    except Exception:
        return False

def get_resource_path(relative_path):
    """获取资源文件的绝对路径"""
    # 如果是PyInstaller环境则返回临时文件夹（路径在_MEIPASS中），否则返回当前项目目录
    base_path = sys._MEIPASS if is_pyinstaller_environment() else os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def copy_user_config_to_package(log_func):
    """将用户配置复制到包内配置"""
    try:
        # 获取用户配置路径
        user_config_path = get_config_path()
        if not os.path.exists(user_config_path):
            return False

        # 获取包内配置路径
        package_config_path = get_resource_path(os.path.join("difys", "configs.py"))

        # 复制用户配置到包内配置
        shutil.copy2(user_config_path, package_config_path)
        log_func(f"复制用户配置到包内配置: {user_config_path} -> {package_config_path}")

        return True
    except Exception as e:
        log_func(f"复制用户配置失败: {str(e)}")
        return False

class ConfigGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        # 标记 UI 模式：backend 据此跳过自身的 configs.py 回填（由本界面统一持久化+刷新）
        os.environ['DIFY_UPLOAD_UI'] = '1'
        self.current_thread = None  # 添加线程跟踪变量
        self.is_running = False  # 添加运行状态标志
        self.should_stop = False  # 添加停止标志
        self.is_stopping = False  # 添加正在停止标志
        self.log_handlers = []  # 添加日志处理器列表
        self.original_print_log = None  # 保存原始的日志打印函数
        self.title("Dify Upload")
        self.geometry("1180x900")

        # 版本和仓库信息
        self.version = "v1.0.0+dify1.13.3"  # 版本号
        self.github_repo = "https://github.com/Samge0/dify-upload"  # GitHub仓库地址

        # 自定义图标
        icon_file = get_resource_path('icon.png') if is_pyinstaller_environment() else 'scripts/icon.png'
        self.iconpath = ImageTk.PhotoImage(file=icon_file)
        self.wm_iconbitmap()
        self.iconphoto(False, self.iconpath)

        # 配置项定义。"options" 存在时渲染为下拉框
        self.config_definitions = {
            # —— 连接与知识库 ——
            "API_URL": {"type": str, "label": "API地址", "default": "http://localhost/v1"},
            "API_KEY": {"type": str, "label": "API密钥", "default": "dataset-xxxxxx"},
            "DATASET_ID": {"type": str, "label": "知识库ID", "default": ""},
            "DATASET_NAME": {"type": str, "label": "知识库名称", "default": "my_dataset"},
            # —— 处理模式与分段模式（触发下方动态「处理规则」区）——
            "INDEXING_TECHNIQUE": {"type": str, "label": "索引模式", "default": "economy", "options": ["high_quality", "economy"]},
            "DOC_FORM": {"type": str, "label": "分段模式", "default": "text_model", "options": ["text_model", "hierarchical_model", "qa_model"]},
            "PROCESS_RULE_MODE": {"type": str, "label": "分段处理规则", "default": "automatic", "options": ["automatic", "custom", "hierarchical"]},
            
            
            # —— 文档来源与过滤 ——
            "DOC_DIR": {"type": str, "label": "文档目录", "default": "your doc dir"},
            "DOC_SUFFIX": {"type": str, "label": "文档后缀", "default": "md,txt,pdf,docx"},
            "DOC_LANGUAGE": {"type": str, "label": "文档语言", "default": "English", "options": [
                "English", "Chinese Simplified", "Chinese Traditional", "Portuguese", "Spanish", "French",
                "German", "Japanese", "Korean", "Russian", "Italian", "Thai", "Ukrainian", "Vietnamese",
                "Romanian", "Polish", "Hindi", "Türkçe", "Farsi", "Slovensko", "Indonesian", "Dutch",
                "Tunisian Arabic",
            ]},
            "DOC_MIN_LINES": {"type": int, "label": "最小行数", "default": "1"},
            "DOC_MAX_SIZE_MB": {"type": int, "label": "文件大小上限(MB)", "default": "15"},
            "ONLY_UPLOAD": {"type": bool, "label": "仅上传文件", "default": "False"},
            "AUTO_CREATE_DATASET": {"type": bool, "label": "自动创建知识库", "default": "False"},
            # —— 运行行为 ——
            "PROGRESS_CHECK_INTERVAL": {"type": int, "label": "索引进度查询间隔", "default": "5"},
            "FIRST_INDEX_WAIT_TIME": {"type": int, "label": "首次索引等待时间", "default": "0"},
            "INDEXING_MAX_WAIT": {"type": int, "label": "索引等待上限(秒)", "default": "3600"},
            "ENABLE_PROGRESS_LOG": {"type": bool, "label": "打印索引进度日志", "default": "True"},
            "ENABLE_API_LOG": {"type": bool, "label": "记录API请求日志", "default": "True"},
            "METADATA_SUFFIX": {"type": str, "label": "元数据文件后缀", "default": ".meta.json"},
            
            # —— 处理规则（custom/hierarchical 动态字段，按模式显示/隐藏）——
            "SEGMENT_SEPARATOR": {"type": str, "label": "分段分隔符", "default": "\\n\\n"},
            "SEGMENT_MAX_TOKENS": {"type": int, "label": "分段最大Token", "default": "500"},
            "SEGMENT_CHUNK_OVERLAP": {"type": int, "label": "分段重叠Token", "default": "0"},
            "PREPROCESS_REMOVE_EXTRA_SPACES": {"type": bool, "label": "去多余空格", "default": "True"},
            "PREPROCESS_REMOVE_URLS_EMAILS": {"type": bool, "label": "去URL/邮箱", "default": "False"},
            "PREPROCESS_REMOVE_STOPWORDS": {"type": bool, "label": "去停用词", "default": "False"},
            "HIERARCHICAL_PARENT_MODE": {"type": str, "label": "父分段方式", "default": "paragraph", "options": ["full-doc", "paragraph"]},
            "HIERARCHICAL_CHILD_SEPARATOR": {"type": str, "label": "子分段分隔符", "default": "\\n"},
            "HIERARCHICAL_CHILD_MAX_TOKENS": {"type": int, "label": "子分段最大Token", "default": "200"},
        }

        # 分段处理规则 -> 该模式下需要显示的字段（动态显示/隐藏）
        self.mode_fields = {
            "custom": [
                "SEGMENT_SEPARATOR", "SEGMENT_MAX_TOKENS", "SEGMENT_CHUNK_OVERLAP",
                "PREPROCESS_REMOVE_EXTRA_SPACES", "PREPROCESS_REMOVE_URLS_EMAILS", "PREPROCESS_REMOVE_STOPWORDS",
            ],
            "hierarchical": [
                "HIERARCHICAL_PARENT_MODE", "SEGMENT_SEPARATOR", "SEGMENT_MAX_TOKENS",
                "PREPROCESS_REMOVE_EXTRA_SPACES", "PREPROCESS_REMOVE_URLS_EMAILS", "PREPROCESS_REMOVE_STOPWORDS",
                "HIERARCHICAL_CHILD_SEPARATOR", "HIERARCHICAL_CHILD_MAX_TOKENS",
            ],
        }
        # 所有动态字段 key（用于区分静态/动态）
        self._dynamic_keys = set()
        for _fields in self.mode_fields.values():
            self._dynamic_keys.update(_fields)

        # 配置值真值源：保存时遍历它（含未显示的其它模式字段），保证切换模式不丢配置
        self._config_values = {k: self._coerce(d["default"], d["type"]) for k, d in self.config_definitions.items()}
        self.config_entries = {}  # key -> 当前已渲染的控件（静态 + 当前模式的动态）

        self.create_ui()
        self.load_config()

    # ---------------- 类型/控件辅助 ----------------

    @staticmethod
    def _coerce(value, typ):
        """把字符串默认值/输入值转为对应类型"""
        if value is None:
            return value
        if typ is bool:
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("1", "true", "yes", "on")
        if typ is int:
            try:
                return int(value)
            except (ValueError, TypeError):
                return 0
        return str(value)

    def _make_row(self, parent, key):
        """创建单个配置行（label + 控件），控件注册进 self.config_entries 并绑定到 _config_values"""
        definition = self.config_definitions[key]
        row = ctk.CTkFrame(parent)
        row.pack(fill="x", padx=5, pady=2)

        label_frame = ctk.CTkFrame(row)
        label_frame.pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkLabel(label_frame, text=definition["label"], width=140).pack(side="left", padx=5)

        value = self._config_values.get(key, definition["default"])

        if "options" in definition:
            widget = ctk.CTkOptionMenu(label_frame, values=definition["options"], width=180)
            widget.pack(side="left", padx=5)
            widget.set(str(value))
            if key == "PROCESS_RULE_MODE":
                widget.configure(command=self.on_mode_change)
            elif key == "INDEXING_TECHNIQUE":
                widget.configure(command=self.on_indexing_change)
            elif key == "DOC_FORM":
                widget.configure(command=self.on_doc_form_change)
        elif definition["type"] == bool:
            widget = ctk.CTkCheckBox(label_frame, text="")
            widget.pack(side="left", padx=5)
            widget.select() if bool(value) else widget.deselect()
        else:
            widget = ctk.CTkEntry(label_frame)
            widget.pack(side="left", fill="x", expand=True, padx=5)
            widget.insert(0, str(value))

        self.config_entries[key] = widget
        return row

    def _make_columns(self, parent, keys):
        """把 keys 渲染成 3 列紧凑布局（与静态/动态区共用），返回列容器列表"""
        columns_frame = ctk.CTkFrame(parent)
        columns_frame.pack(fill="x", padx=5, pady=2)
        column_count = 3
        columns = []
        for _ in range(column_count):
            col = ctk.CTkFrame(columns_frame)
            col.pack(side="left", fill="both", expand=True, padx=5, pady=5)
            columns.append(col)
        # 按列优先分配：总数均分到 3 列，依次填入
        per = math.ceil(len(keys) / column_count) if keys else 0
        for i, key in enumerate(keys):
            col_index = min(i // per, column_count - 1) if per else 0
            self._make_row(columns[col_index], key)
        return columns

    def _sync_widgets_to_values(self):
        """把当前所有已渲染控件的值回写到 _config_values（保存/切模式前调用）"""
        for key, widget in list(self.config_entries.items()):
            if isinstance(widget, ctk.CTkCheckBox):
                self._config_values[key] = bool(widget.get())
            elif isinstance(widget, ctk.CTkOptionMenu):
                self._config_values[key] = widget.get()
            else:
                raw = widget.get()
                if self.config_definitions[key]["type"] == int:
                    raw = self._coerce(raw, int)
                self._config_values[key] = raw

    def _refresh_widgets_from_values(self):
        """用 _config_values 刷新当前已渲染控件的显示"""
        for key, widget in list(self.config_entries.items()):
            value = self._config_values.get(key, self.config_definitions[key]["default"])
            if isinstance(widget, ctk.CTkCheckBox):
                widget.select() if bool(value) else widget.deselect()
            elif isinstance(widget, ctk.CTkOptionMenu):
                widget.set(str(value))
            else:
                widget.delete(0, "end")
                widget.insert(0, str(value))

    def rebuild_rules_frame(self):
        """根据当前 PROCESS_RULE_MODE 重建「处理规则」区动态字段（两列紧凑布局，与静态区一致）"""
        # 清理旧的动态控件
        for k in list(self._rendered_dynamic_keys):
            self.config_entries.pop(k, None)
        self._rendered_dynamic_keys = set()

        for w in self.rules_frame.winfo_children():
            w.destroy()

        mode = self._config_values.get("PROCESS_RULE_MODE", "automatic")
        fields = self.mode_fields.get(mode, [])
        self._rendered_dynamic_keys = set(fields)

        # automatic 无需额外配置，给一行提示即可
        if not fields:
            ctk.CTkLabel(self.rules_frame, text="（automatic 模式使用 Dify 内置规则，无需额外配置）",
                         anchor="center").pack(fill="x", padx=5, pady=4)
            return

        # 三列布局，复用静态区的排布方式，避免纵向过长需要滚动
        self._make_columns(self.rules_frame, fields)

    def on_mode_change(self, *_args):
        """分段处理规则下拉变化：同步值、智能建议 doc_form、重建动态字段"""
        self._sync_widgets_to_values()
        mode = self._config_values.get("PROCESS_RULE_MODE", "automatic")
        doc_form = self._config_values.get("DOC_FORM", "text_model")
        # 安全网：hierarchical 必须 doc_form=hierarchical_model（UI 路径已限制，此处兜底程序化/历史配置）
        if mode == "hierarchical" and doc_form != "hierarchical_model":
            self._config_values["DOC_FORM"] = "hierarchical_model"
            if isinstance(self.config_entries.get("DOC_FORM"), ctk.CTkOptionMenu):
                self.config_entries["DOC_FORM"].set("hierarchical_model")
        self.rebuild_rules_frame()

    def _form_options(self, indexing):
        """分段模式可选项：hierarchical_model 仅高质量可选"""
        if indexing == "high_quality":
            return ["text_model", "hierarchical_model", "qa_model"]
        return ["text_model", "qa_model"]  # economy

    def _rule_options(self, indexing, doc_form):
        """分段处理规则可选项：
        - doc_form=hierarchical_model（仅高质量下出现）时锁定为 hierarchical
        - 否则为 automatic/custom（不含 hierarchical）"""
        if indexing == "high_quality" and doc_form == "hierarchical_model":
            return ["hierarchical"]
        return ["automatic", "custom"]

    def _apply_rule_options(self):
        """按当前 索引模式+分段模式 收紧 分段处理规则 可选项，回落非法当前值；返回是否发生回落"""
        indexing = self._config_values.get("INDEXING_TECHNIQUE", "high_quality")
        doc_form = self._config_values.get("DOC_FORM", "text_model")
        options = self._rule_options(indexing, doc_form)
        cur = self._config_values.get("PROCESS_RULE_MODE", "automatic")
        # 回落到第一个可选项（doc_form=hierarchical_model 时即 hierarchical）
        new = cur if cur in options else options[0]
        self._config_values["PROCESS_RULE_MODE"] = new
        widget = self.config_entries.get("PROCESS_RULE_MODE")
        if isinstance(widget, ctk.CTkOptionMenu):
            widget.configure(values=options)
            widget.set(new)
        return new != cur

    def on_indexing_change(self, *_args):
        """索引模式变化：收紧 分段模式 可选项（连带影响 分段处理规则 可选项）"""
        self._sync_widgets_to_values()
        indexing = self._config_values.get("INDEXING_TECHNIQUE", "high_quality")
        form_options = self._form_options(indexing)
        cur_form = self._config_values.get("DOC_FORM", "text_model")
        new_form = cur_form if cur_form in form_options else "text_model"
        self._config_values["DOC_FORM"] = new_form
        form_widget = self.config_entries.get("DOC_FORM")
        if isinstance(form_widget, ctk.CTkOptionMenu):
            form_widget.configure(values=form_options)
            form_widget.set(new_form)
        # 分段模式可能被回落，连带收紧 分段处理规则；若分段处理规则被回落则重建动态字段
        if self._apply_rule_options():
            self.on_mode_change()

    def on_doc_form_change(self, *_args):
        """分段模式变化：收紧 分段处理规则 可选项（hierarchical 仅父子分段模式可选）"""
        self._sync_widgets_to_values()
        if self._apply_rule_options():
            self.on_mode_change()

    # ---------------- UI ----------------

    def create_ui(self):
        self._rendered_dynamic_keys = set()

        # 主框架
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # 配置区域
        config_frame = ctk.CTkFrame(self.main_frame)
        config_frame.pack(fill="both", expand=True, padx=5, pady=5)

        scroll_frame = ctk.CTkScrollableFrame(config_frame)
        scroll_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # 静态字段：三列紧凑布局
        static_keys = [k for k in self.config_definitions.keys() if k not in self._dynamic_keys]
        static_container = ctk.CTkFrame(scroll_frame)
        static_container.pack(side="top", fill="x", padx=5, pady=5)
        self._make_columns(static_container, static_keys)

        # 动态字段：处理规则区（按所选类型显示/隐藏）
        rules_header = ctk.CTkLabel(scroll_frame, text="—— 分段处理规则（按所选类型显示/隐藏）——", anchor="center")
        rules_header.pack(side="top", fill="x", padx=5, pady=(8, 2))
        self.rules_frame = ctk.CTkFrame(scroll_frame)
        self.rules_frame.pack(side="top", fill="x", padx=5, pady=2)
        self.rebuild_rules_frame()

        # 按钮
        button_frame = ctk.CTkFrame(config_frame)
        button_frame.pack(fill="x", padx=5, pady=5)
        self.run_button = ctk.CTkButton(
            button_frame,
            text="运行",
            command=self.toggle_run,
            fg_color=["#3B8ED0", "#1F6AA5"],  # 默认蓝色
            hover_color=["#36719F", "#144870"],  # 深蓝色
            text_color="white"  # 白色文字
        )
        self.run_button.pack(side="left", padx=5, pady=5)

        # 添加清理日志按钮
        self.clear_log_button = ctk.CTkButton(
            button_frame,
            text="清理日志",
            command=self.clear_log,
            fg_color=["#757575", "#616161"],  # 灰色
            hover_color=["#616161", "#424242"],  # 深灰色
            text_color="white"  # 白色文字
        )
        self.clear_log_button.pack(side="left", padx=5, pady=5)

        # 添加清除进度按钮
        self.clear_progress_button = ctk.CTkButton(
            button_frame,
            text="清除进度",
            command=self.clear_progress,
            fg_color=["#757575", "#616161"],  # 灰色
            hover_color=["#616161", "#424242"],  # 深灰色
            text_color="white"  # 白色文字
        )
        self.clear_progress_button.pack(side="left", padx=5, pady=5)

        # 日志区域
        log_frame = ctk.CTkFrame(self.main_frame)
        log_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_text.configure(state="disabled")

        # 添加版本和仓库信息
        info_frame = ctk.CTkFrame(self.main_frame)
        info_frame.pack(fill="x", padx=5, pady=2)

        version_label = ctk.CTkLabel(info_frame, text=f"版本: {self.version}  |")
        version_label.pack(side="left", padx=5)

        # 使用更显眼的样式显示 GitHub 链接
        repo_label = ctk.CTkLabel(
            info_frame,
            text=self.github_repo,
            cursor="hand2",
            text_color="#1E90FF",  # 使用蓝色
            font=("Arial", 12)
        )
        repo_label.pack(side="left", padx=5)
        repo_label.bind("<Button-1>", lambda e: self.open_github())

        # 添加分隔符
        separator = ctk.CTkLabel(info_frame, text="| 配置目录:")
        separator.pack(side="left", padx=5)

        # 添加打开配置目录的链接
        config_label = ctk.CTkLabel(
            info_frame,
            text=get_config_dir(),
            cursor="hand2",
            text_color="#1E90FF",
            font=("Arial", 11)
        )
        config_label.pack(side="left", padx=5)
        config_label.bind("<Button-1>", lambda e: self.open_config_dir())

    def toggle_run(self):
        """切换运行/停止状态"""
        if not self.is_running:
            if self.current_thread and self.current_thread.is_alive():
                self.log("上一个任务还在运行中，请等待完成或点击停止")
                return

            # 运行前时将滚动条设置到底部
            self.log_text.see("end")

            self.start_run()
        else:
            if not self.is_stopping:  # 防止重复点击
                self.stop_run()

    def start_run(self):
        """开始运行"""
        self.is_running = True
        self.run_button.configure(
            text="停止",
            fg_color="#FF5555",  # 红色
            hover_color="#FF3333",  # 深红色
            text_color="white"  # 白色文字
        )
        self.set_config_entries_state("disabled")
        self.run_upload()

    def stop_run(self):
        """停止运行"""
        if self.current_thread and self.current_thread.is_alive():
            self.is_stopping = True  # 设置正在停止标志
            self.is_running = False
            self.should_stop = True  # 设置停止标志
            self.log("正在停止运行...")

            # 禁用停止按钮，防止重复点击
            self.run_button.configure(state="disabled")

            # 尝试终止线程
            try:
                import ctypes
                thread_id = self.current_thread.ident
                if thread_id:
                    exc = ctypes.py_object(KeyboardInterrupt)
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread_id), exc)
            except Exception as e:
                self.log(f"停止线程时出错: {str(e)}")

            # 等待线程真正结束
            def wait_thread_end():
                if self.current_thread:
                    self.current_thread.join()
                # 线程结束后更新UI状态
                self.current_thread = None
                self.is_stopping = False
                self.run_button.configure(
                    text="运行",
                    fg_color=["#3B8ED0", "#1F6AA5"],  # 默认蓝色
                    hover_color=["#36719F", "#144870"],  # 深蓝色
                    text_color="white",  # 白色文字
                    state="normal"  # 恢复按钮状态
                )
                self.set_config_entries_state("normal")
                self.log("已停止运行")
                # 清理日志处理器
                self.cleanup_log_handlers()

            # 在新线程中等待原线程结束
            threading.Thread(target=wait_thread_end, daemon=True).start()

    def set_config_entries_state(self, state):
        """设置配置项的启用/禁用状态"""
        for entry in self.config_entries.values():
            entry.configure(state=state)

    def setup_log_handler(self):
        """设置日志处理器"""
        try:
            from utils import timeutils
            if self.original_print_log is None:
                self.original_print_log = timeutils.print_log

            def new_print_log(*args, **kwargs):
                if self.should_stop:  # 检查是否应该停止
                    raise KeyboardInterrupt("用户请求停止")
                message = " ".join(str(arg) for arg in args)
                self.log(message)
                if self.original_print_log:
                    self.original_print_log(*args, **kwargs)

            timeutils.print_log = new_print_log
            return True
        except ImportError:
            self.log("未找到timeutils模块，将使用默认日志输出")
            return False

    def restore_log_handler(self):
        """恢复原始日志处理器"""
        try:
            from utils import timeutils
            if self.original_print_log:
                timeutils.print_log = self.original_print_log
                self.original_print_log = None
        except ImportError:
            pass

    def cleanup_log_handlers(self):
        """清理所有日志处理器"""
        self.restore_log_handler()
        self.log_handlers.clear()

    def run_upload(self):
        def run():
            main_module = None  # 便于 finally 中读取 RESOLVED_DATASET_ID
            try:
                # 重置停止标志
                self.should_stop = False

                # 运行前保存一下配置
                self.save_config()

                self.log("开始运行上传程序...")

                # 在运行前，将用户配置复制到包内配置
                if copy_user_config_to_package(self.log):
                    self.log("已更新包内配置")
                    # 清理所有可能包含配置的模块缓存
                    for module_name in list(sys.modules.keys()):
                        if module_name.startswith('difys.') or module_name == 'configs':
                            del sys.modules[module_name]

                    # 重新导入配置模块
                    config_path = get_resource_path(os.path.join("difys", "configs.py"))
                    spec = importlib.util.spec_from_file_location("difys.configs", config_path)
                    configs_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(configs_module)
                    sys.modules["difys.configs"] = configs_module

                    # 重新导入api模块（会连带重新导入 dify_api，重建持有最新配置的单例）
                    api_path = get_resource_path(os.path.join("difys", "api.py"))
                    spec = importlib.util.spec_from_file_location("difys.api", api_path)
                    api_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(api_module)
                    sys.modules["difys.api"] = api_module

                # 动态导入主程序
                main_path = get_resource_path(os.path.join("difys", "main.py"))
                spec = importlib.util.spec_from_file_location("main", main_path)
                main_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(main_module)

                # 设置日志处理器
                if not self.setup_log_handler():
                    self.log("警告：无法设置日志处理器，日志可能不完整")

                # 运行主程序
                if not self.should_stop:  # 检查是否应该停止
                    try:
                        # 添加停止检查函数到main模块
                        def check_stop():
                            # 协作式取消：返回 True 即由 main/索引等待处抛出 KeyboardInterrupt 中断
                            return self.should_stop

                        # 知识库ID 一解析到即回显（main 在 worker 线程，转发到主线程刷新 UI）
                        def on_dataset_resolved(dataset_id):
                            if dataset_id:
                                self.after(0, lambda v=dataset_id: self._backfill_dataset_id(v))

                        # 将钩子注入main模块
                        main_module.check_stop = check_stop
                        main_module.on_dataset_resolved = on_dataset_resolved

                        # 运行主程序
                        main_module.main()
                    except KeyboardInterrupt:
                        self.log("程序已被用户停止")
                        return  # 直接返回，不抛出异常

                if not self.should_stop:  # 只有在非停止状态下才显示完成消息
                    self.log("程序运行完成")
            except Exception as e:
                self.log(f"运行失败: {str(e)}")
                self.log("详细错误信息:")
                self.log(traceback.format_exc())
            finally:
                # 确保在任何情况下都清理日志处理器
                self.cleanup_log_handlers()
                # 确保在任何情况下都更新停止状态
                if self.is_running:  # 如果还在运行状态，说明是异常导致的停止
                    self.is_running = False
                    self.should_stop = True
                    # 更新UI状态
                    self.current_thread = None
                    self.is_stopping = False
                    self.run_button.configure(
                        text="运行",
                        fg_color=["#3B8ED0", "#1F6AA5"],  # 默认蓝色
                        hover_color=["#36719F", "#144870"],  # 深蓝色
                        text_color="white",  # 白色文字
                        state="normal"  # 恢复按钮状态
                    )
                    self.set_config_entries_state("normal")
                    self.log("已停止运行")

        # 在新线程中运行上传任务
        self.current_thread = threading.Thread(target=run, daemon=True)
        self.current_thread.start()

    # 创建可点击的链接标签
    def open_github(self):
        webbrowser.open(self.github_repo)

    def open_config_dir(self):
        import subprocess
        config_dir = get_config_dir()
        if os.name == 'nt':  # Windows
            os.startfile(config_dir)
        elif sys.platform == 'darwin':  # macOS
            subprocess.run(['open', config_dir])
        else:  # Linux
            subprocess.run(['xdg-open', config_dir])

    def is_scrollbar_at_bottom(self):
        """检查滚动条是否在底部"""
        current_position = self.log_text.yview()[1]
        # 添加一个小的容差值（0.9）来判断是否在底部
        is_at_bottom = current_position >= 0.9
        return is_at_bottom

    def log(self, message):
        # 输出到GUI
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{get_now_str()} {message}\n")

        # 只有当滚动条在底部时才自动滚动
        if self.is_scrollbar_at_bottom():
            self.log_text.see("end")

        self.log_text.configure(state="disabled")
        # 保存到日志文件
        log_save_handler.log(message)

    def load_config(self):
        try:
            config_path = get_config_path()
            self.log(f"加载配置: {config_path}")

            # 如果配置文件不存在，从示例配置复制
            if not os.path.exists(config_path):
                demo_config = get_resource_path(os.path.join("difys", "configs.demo.py"))
                if os.path.exists(demo_config):
                    shutil.copy2(demo_config, config_path)
                    self.log(f"已从示例配置创建配置文件: {config_path}")

            # 存在配置，读取配置展示到GUI界面
            if os.path.exists(config_path):
                spec = importlib.util.spec_from_file_location("configs", config_path)
                configs = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(configs)

                # 读入真值源 _config_values（缺失字段保留默认值）
                for key, definition in self.config_definitions.items():
                    if hasattr(configs, key):
                        value = getattr(configs, key)
                        self._config_values[key] = self._coerce(value, definition["type"])
                        self.log(f"加载配置: {key} = {self._config_values[key]}")

            # 先按已加载模式重建动态字段，再刷新全部控件
            self.rebuild_rules_frame()
            self._refresh_widgets_from_values()
            # 按已加载的索引模式收紧 分段处理规则/分段模式 可选项（自愈不一致的旧配置）
            self.on_indexing_change()
        except Exception as e:
            self.log(f"加载配置失败: {str(e)}")

    def save_config(self):
        try:
            # 先把当前已渲染控件（含动态字段）回写到真值源
            self._sync_widgets_to_values()

            config_path = get_config_path()
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("# 配置文件（注意：若是手动修改该配置文件，需要重新运行程序才能生效）\n")
                # 遍历全量字段（含未显示的其它模式字段），从 _config_values 取值，保证切换模式不丢配置
                for key, definition in self.config_definitions.items():
                    if key.startswith("UI_"):   # UI_前缀的配置项仅用于ui界面，不保存到configs.py
                        continue
                    value = self._config_values.get(key, definition["default"])
                    if definition["type"] == int:
                        value = self._coerce(value, int)
                    f.write(f"{key} = {repr(value)}\n")
                # 添加get_header函数
                f.write("\n\ndef get_header():\n    return {'Authorization': f'Bearer {API_KEY}'}\n")
            self.log("配置已保存")
        except Exception as e:
            self.log(f"保存配置失败: {str(e)}")

    def _backfill_dataset_id(self, dataset_id):
        """主线程回调：把解析到的知识库ID回填到配置与界面（仅当原来未填时由调用方保证触发）"""
        if not dataset_id:
            return
        dataset_id = str(dataset_id)
        self._config_values['DATASET_ID'] = dataset_id
        widget = self.config_entries.get('DATASET_ID')
        if isinstance(widget, ctk.CTkEntry):
            # 运行期间控件被禁用，disabled 状态下 insert/delete 会被忽略，需先解锁再恢复原状态
            try:
                prev_state = str(widget.cget('state'))
            except Exception:
                prev_state = 'normal'
            widget.configure(state='normal')
            widget.delete(0, 'end')
            widget.insert(0, dataset_id)
            widget.configure(state=prev_state)
        self.save_config()
        self.log(f"已自动回填知识库ID：{dataset_id}")

    def clear_log(self):
        """清理UI界面的日志显示"""
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, "end")
        self.log_text.configure(state="disabled")
        self.log("日志已清理")

    def _saved_cache_key(self):
        """与后端一致的 cache_key：优先读已保存配置里的 DATASET_ID，其次界面输入，最后名称。

        后端 StateStore 用「解析后的 DATASET_ID，否则 DATASET_NAME」作键；解析后的 ID 会回填并
        持久化到配置文件，故以已保存配置为准可避免回填时机差异导致删错 state 文件。
        """
        try:
            config_path = get_config_path()
            if os.path.exists(config_path):
                spec = importlib.util.spec_from_file_location("_cfg_cachekey", config_path)
                cfg = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(cfg)
                saved_id = str(getattr(cfg, "DATASET_ID", "") or "").strip()
                if saved_id:
                    return saved_id
        except Exception as e:
            self.log(f"读取已保存配置失败，改用界面输入：{e}")

        dataset_id = self.config_entries["DATASET_ID"].get().strip()
        if dataset_id:
            return dataset_id
        return self.config_entries["DATASET_NAME"].get().strip()

    def clear_progress(self):
        """清除当前知识库的处理进度（删除 state.json）"""
        # 运行中禁止清除，避免状态错乱
        if self.is_running:
            self.log("运行中无法清除进度，请先停止")
            return

        # 与后端保持一致的 cache_key
        cache_key = self._saved_cache_key()

        if not cache_key:
            self.log("无法获取知识库ID或名称，清除进度失败")
            return

        # 实例化 StateStore 以获取 state.json 的完整路径
        try:
            from utils.statestore import StateStore
            state = StateStore(cache_key)
        except Exception as e:
            self.log(f"清除进度失败：{str(e)}")
            return

        state_file = state.state_filepath

        # 如果状态文件不存在，说明本来就没有进度记录
        if not os.path.exists(state_file):
            self.log(f"当前没有进度记录可清除：{state_file}")
            return

        # 二次确认：明确显示将删除哪个文件
        from tkinter import messagebox
        if not messagebox.askyesno(
            "确认清除进度",
            f"将删除进度记录文件：\n  {state_file}\n\n下次运行时会重新处理所有文件。\n\n确定继续吗？"
        ):
            return

        # 执行清除
        try:
            state.reset()
            self.log(f"已清除进度记录：{state_file}")
        except Exception as e:
            self.log(f"清除进度失败：{str(e)}")

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = ConfigGUI()
    app.mainloop()
