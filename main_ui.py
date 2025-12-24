import os#交互
import sys#程序
import json#配置
import re#字符串匹配
import shutil
from datetime import datetime


from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QStackedWidget, QFileDialog,
    QFormLayout, QMessageBox, QDialog, QLineEdit, QFrame, QSlider,
    QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QComboBox, QStyledItemDelegate, QListWidget,
    QListWidgetItem, QTreeWidget, QTreeWidgetItem, QListView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QIcon, QColor, QPalette, QPixmap, QPainter, QTextCursor #绘图

try:
    import script_extract
    import script_si
    import script_mineru
    import script_clean
    import script_keyword
except ImportError:
    pass

# ================= 配置管理 =================
CONFIG_FILE = "config.json"


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_config(config):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except:
        pass


current_config = load_config()

# ================= 样式表 =================
STYLES = """
    QMainWindow { background-color: #f4f6f9; }
    QWidget { font-family: "Microsoft YaHei"; font-size: 13px; color: #333; }

    /* 左侧导航 */
    QWidget#Sidebar { background-color: white; border-right: 1px solid #e0e0e0; }

    /* --- [修改] 顶部自定义按钮 (对齐下方按钮) --- */
    QPushButton#CustomFlowBtn {
        background-color: #8250df;
        color: white; 
        border: 2px solid transparent; 
        border-radius: 6px; 
        padding: 12px 20px; /* 改为 20px 以对齐下方图标 */
        font-weight: bold; font-size: 14px;
        text-align: left; 
        margin: 4px 12px;   /* 改为 4px 12px 以对齐下方间距 */
    }
    QPushButton#CustomFlowBtn:hover { background-color: #6a3fb8; }

    /* 导航按钮 */
    QPushButton.navBtn { 
        text-align: left;
        padding: 12px 20px; 
        border: 1px solid transparent; 
        border-radius: 6px; color: #555; font-size: 14px; margin: 4px 12px;
    }
    QPushButton.navBtn:hover { background-color: #f5f7fa; color: #333; }
    QPushButton.navBtn:checked { 
        background-color: #e6f4ff; color: #1890ff; 
        font-weight: bold;
        border: 1px solid #1890ff; 
    }
    QPushButton#CustomFlowBtn:disabled, QPushButton.navBtn:disabled {
        background-color: #e0e0e0;
        color: #aaa;
        border: none;
    }

    /* 中间区域 */
    QWidget#Middle { background-color: #f4f6f9; }
    QLineEdit, QTextEdit { border: 1px solid #ccc; border-radius: 4px; padding: 8px; background: white; }
    QLineEdit:focus, QTextEdit:focus { border: 1px solid #40a9ff; }

    /* --- [新增] 运行日志滚动条美化 --- */
    ScrollBar:vertical { 
        border: none; 
        background: #f0f0f0; 
        width: 10px; /* 加宽到10px */
        margin: 0px; 
    }
    QScrollBar::handle:vertical { 
        background: #999; /* 加深颜色 */
        min-height: 20px; 
        border-radius: 5px; 
    }
    QScrollBar::handle:vertical:hover { 
        background: #777; /* 悬停变深 */
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

    /* 按钮通用 */
    QPushButton.actionBtn { background-color: #1890ff; color: white; border-radius: 4px; padding: 10px 30px; font-weight: bold; border: none; font-size: 15px; }
    QPushButton.actionBtn:hover { background-color: #40a9ff; }
    QPushButton.actionBtn:disabled { background-color: #d9d9d9; }
    QPushButton.browseBtn { background-color: #fafafa; border: 1px solid #ccc; border-radius: 4px; padding: 5px 15px; }
    QPushButton.browseBtn:hover { border-color: #40a9ff; color: #40a9ff; }

    QFrame#FormatBox { background-color: white; border: 1px solid #d9d9d9; border-radius: 8px; padding: 15px; }

    /* --- [修改] 右侧面板风格 (统一为白色卡片表格风) --- */
        /* --- [修改] 右侧面板风格 (统一为白色卡片表格风) --- */
    QWidget#RightPanel { background-color: white; border-left: 1px solid #e0e0e0; }
    QTableWidget, QTreeWidget { border: none; background-color: white; outline: none; }

    QHeaderView::section { 
        background-color: white; 
        border: none; 
        border-bottom: 2px solid #f0f0f0; 
        color: #999; 
        font-weight: bold; 
        padding: 12px 8px; /* 增加头部内边距 */
    }

    /* 列表项风格：增加行高和下划线 */
    QTableWidget::item, QTreeWidget::item { 
        padding: 8px; 
        border-bottom: 1px solid #f5f5f5; 
        color: #333;
    }
    QTreeWidget::item:selected, QTableWidget::item:selected {
        background-color: #e6f7ff;
        color: #333;
    }

    /* --- [新增] 全局弹窗样式 (覆盖 QMessageBox) --- */
    QMessageBox, QDialog { background-color: white; font-size: 14px; }
    QMessageBox QLabel { color: #333; }
    QMessageBox QPushButton { 
        background-color: #1890ff; color: white; 
        border-radius: 4px; padding: 6px 20px; min-width: 60px; 
    }
    QMessageBox QPushButton:hover { background-color: #40a9ff; }
"""


# ================= 自定义组件 =================
class ScaledImageLabel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = None
        self.opacity = 1.0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, path, opacity_val):
        self.opacity = opacity_val / 100.0
        if path and os.path.exists(path):
            self.pixmap = QPixmap(path)
        else:
            self.pixmap = None
        self.update()

    def paintEvent(self, event):
        if not self.pixmap: return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(self.opacity)
        target_rect = self.rect()
        scaled = self.pixmap.scaled(target_rect.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
        x = (target_rect.width() - scaled.width()) // 2
        y = 0
        painter.drawPixmap(x, y, scaled)

# 用于强制设置 TreeWidget 行高的委托类
class RowHeightDelegate(QStyledItemDelegate):
    def __init__(self, height, parent=None):
        super().__init__(parent)
        self.height = height

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(self.height)
        return size
# 基础文件列表（用于普通Tab）
class FileListWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)

        top = QWidget()
        top.setStyleSheet("background:white; border-bottom:1px solid #eee;")
        th = QHBoxLayout(top)
        self.lbl_title = QLabel("文件列表")
        self.lbl_title.setStyleSheet("font-weight:bold; font-size:14px;")
        self.lbl_count = QLabel("0 项")
        self.lbl_count.setStyleSheet("color:#888;")
        th.addWidget(self.lbl_title)
        th.addStretch()
        th.addWidget(self.lbl_count)
        self.layout.addWidget(top)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.verticalHeader().setDefaultSectionSize(45)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setHorizontalHeaderLabels(["文件名称", "状态", "详情/结果", "查看"])
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 80)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.layout.addWidget(self.table)

        self.file_rows = {}
        self.chunks_cache = {}
        self.file_paths = {}
        self.table.cellClicked.connect(self.on_cell_clicked)

    def on_cell_clicked(self, row, col):
        if col == 3:
            filename_item = self.table.item(row, 0)
            if not filename_item: return
            fname = filename_item.text().split(" ", 1)[1]

            # 如果是查看碎片详情
            if fname in self.chunks_cache:
                dlg = ChunkInspector(fname, self)
                dlg.update_data(self.chunks_cache[fname])
                dlg.exec()
                return

            # 如果是打开文件/文件夹
            fpath = self.file_paths.get(fname)
            if fpath and os.path.exists(fpath):
                try:
                    # --- [修改] 使用 subprocess 替代 os.startfile 以防止 COM 冲突崩溃 ---
                    import subprocess
                    norm_path = os.path.normpath(fpath)

                    if os.path.isfile(norm_path):
                        # 如果是文件，使用 /select 参数在资源管理器中直接选中它
                        subprocess.Popen(f'explorer /select,"{norm_path}"')
                    else:
                        # 如果是文件夹，直接打开
                        subprocess.Popen(f'explorer "{norm_path}"')
                except Exception as e:
                    print(f"无法打开路径: {e}")

    def init_files(self, files, mode="normal"):
        self.chunks_cache = {}
        self.file_paths = {}
        self.table.setRowCount(0)
        self.file_rows = {}
        self.lbl_count.setText(f"{len(files)} 项")
        for i, f in enumerate(files):
            self.file_rows[f] = i
            self.table.insertRow(i)
            icon = "📄" if f.endswith(".pdf") else "📝"
            self.table.setItem(i, 0, QTableWidgetItem(f"{icon} {f}"))
            st = QTableWidgetItem("等待中")
            st.setForeground(QColor("#999"))
            self.table.setItem(i, 1, st)
            self.table.setItem(i, 2, QTableWidgetItem("-"))
            if mode == "clean":
                op = QTableWidgetItem("🔍")
                op.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, 3, op)

    def update_chunk_info(self, filename, chunks):
        self.chunks_cache[filename] = chunks
        row = self.file_rows.get(filename)
        if row is None: return
        if not self.table.item(row, 3):
            op = QTableWidgetItem("🔍")
            op.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, op)

    def update_status(self, filename, status_code, remark=None, result_path=None):
        row = self.file_rows.get(filename)
        if row is None: return
        st_item = self.table.item(row, 1)
        if status_code > 0:
            if status_code == 1:
                st_item.setText("🔵 进行中")
                st_item.setForeground(QColor("#1890ff"))
            elif status_code == 2:
                st_item.setText("✅ 完成")
                st_item.setForeground(QColor("#52c41a"))
            elif status_code == 3:
                st_item.setText("❌ 失败")
                st_item.setForeground(QColor("#ff4d4f"))
            elif status_code == 4:
                st_item.setText("⏭️ 跳过")
                st_item.setForeground(QColor("#faad14"))
            elif status_code == 5:
                st_item.setText("⚠️ 推迟")
                st_item.setForeground(QColor("#faad14"))
        if remark:
            self.table.item(row, 2).setText(remark)
        if result_path:
            self.file_paths[filename] = result_path
            op = QTableWidgetItem("🔍")
            op.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, op)
            self.table.scrollToItem(st_item)
    def terminate_running_items(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            # 检查文本是否包含"进行中" (兼容带图标的情况)
            if item and "进行中" in item.text():
                item.setText("🛑 已终止")
                item.setForeground(QColor("#ff4d4f"))

#专门用于自定义工作流的树形列表
class WorkflowTreeListWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)

        top = QWidget()
        top.setStyleSheet("background:white; border-bottom:1px solid #eee;")
        th = QHBoxLayout(top)
        self.lbl_title = QLabel("流程进度监控")
        self.lbl_title.setStyleSheet("font-weight:bold; font-size:14px;")
        th.addWidget(self.lbl_title)
        self.layout.addWidget(top)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)

        self.tree.setHeaderLabels(["任务/步骤", "状态", "详情/结果", "查看"])
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, 80)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tree.setItemDelegate(RowHeightDelegate(45, self.tree))
        self.layout.addWidget(self.tree)
        self.tree.itemClicked.connect(self.on_item_clicked)#绑定信号
        self.file_nodes = {}
        self.step_nodes = {}
        self.result_paths = {}

    def init_workflow(self, files, step_names):
        self.tree.clear()
        self.file_nodes = {}
        self.step_nodes = {}

        for f in files:
            # 父节点：文件名
            file_node = QTreeWidgetItem(self.tree)
            file_node.setText(0, f)
            file_node.setText(1, "等待中")
            file_node.setExpanded(True)
            self.file_nodes[f] = file_node

            # 子节点：各个步骤
            for i, s_name in enumerate(step_names):
                step_node = QTreeWidgetItem(file_node)
                step_node.setText(0, f"Step {i + 1}: {s_name}")
                step_node.setText(1, "⏳")
                step_node.setForeground(1, QColor("#999"))
                self.step_nodes[f"{f}_{i}"] = step_node

    def update_step_status(self, filename, step_idx, status_code, remark=""):
        key = f"{filename}_{step_idx}"
        node = self.step_nodes.get(key)
        if not node: return
        # 状态码定义: 1=进行中, 2=完成, 3=失败, 4=跳过
        if status_code == 1:
            node.setText(1, "🔄")
            node.setForeground(1, QColor("#1890ff"))
        elif status_code == 2:
            node.setText(1, "✅")  # 简化显示
            node.setForeground(1, QColor("#52c41a"))

            # 处理路径和备注
            display_text = remark
            real_path = ""
            if "|" in str(remark):
                parts = str(remark).split("|", 1)
                display_text = parts[0]
                real_path = parts[1]

            node.setText(2, display_text)
            node.setToolTip(2, display_text)

            # 设置查看按钮
            if real_path and os.path.exists(real_path):
                node.setText(3, "🔍")
                node.setData(3, Qt.ItemDataRole.UserRole, real_path)

        elif status_code == 3:
            node.setText(1, "❌")
            node.setForeground(1, QColor("#ff4d4f"))
            node.setText(2, str(remark))
        elif status_code == 4:
            node.setText(1, "⏭️")  # 跳过图标
            node.setForeground(1, QColor("#faad14"))  # 橙色
            node.setText(2, str(remark))
        elif status_code == 5:
            node.setText(1, "⚠️")  # 设置图标
            node.setForeground(1, QColor("#faad14"))  # 黄色
            node.setText(2, str(remark))

        # 2.更新父节点显示逻辑：[1]-[2]-[3]
        parent = self.file_nodes.get(filename)
        if parent:
            progress_str = ""
            is_dead = False  # 标记是否已经挂了
            # 遍历该文件下的所有步骤节点
            child_count = parent.childCount()
            for i in range(child_count):
                child = parent.child(i)
                txt = child.text(1)  # 获取状态图标

                if "✅" in txt:
                    progress_str += f"[{i + 1}]-"
                elif "⏭️" in txt:
                    progress_str += f"[{i + 1}]-"
                elif "❌" in txt:
                    progress_str += "X"
                    is_dead = True
                    break  #
                    progress_str += f"({i + 1})..."
                elif "⚠️" in txt:
                    progress_str += f"({i + 1}待)..."
                # 进行中
                else:
                    pass
            # 去掉末尾的短横线
            progress_str = progress_str.rstrip("-")

            if is_dead:
                parent.setText(1, "🚫 中止")
                parent.setForeground(1, QColor("#ff4d4f"))
            elif "..." in progress_str:
                parent.setText(1, "🔵 处理中")
                parent.setForeground(1, QColor("#1890ff"))
            elif len(progress_str) > 0:
                # 检查是否全部完成
                if progress_str.count(f"[{child_count}]"):
                    parent.setText(1, "✅ 完成")
                    parent.setForeground(1, QColor("#52c41a"))
                else:
                    parent.setText(1, "🔵 处理中")

            parent.setText(2, progress_str)

    def update_chunk_data(self, filename, step_idx, chunks):
        # 存入缓存：key = "文件名_步骤索引"
        cache_key = f"{filename}_{step_idx}"
        self.chunks_cache[cache_key] = chunks
        # 找到对应的树节点
        node = self.step_nodes.get(cache_key)
        if node:
            # 只有当状态是“进行中”且还没有查看按钮时，才强制显示放大镜
            # 注意：script_clean 运行中 status_code 是 1
            if "🔄" in node.text(1):
                node.setText(3, "🔍")
                # 标记该按钮为查看详情模式，而不是打开文件
                node.setData(3, Qt.ItemDataRole.UserRole, "VIEW_CHUNKS")

    def on_item_clicked(self, item, column):
        # 只响应第4列（索引3）的点击
        if column == 3:
            # 获取存储的路径
            data_val = item.data(3, Qt.ItemDataRole.UserRole)
            #优先检查是否是查看碎片详情
            if data_val == "VIEW_CHUNKS":
                # 反向查找 filename 和 step_idx
                target_key = None
                for key, node in self.step_nodes.items():
                    if node == item:
                        target_key = key
                        break

                if target_key and target_key in self.chunks_cache:
                    # 弹出详情窗口 (ChunkInspector 已在文件中定义)
                    fname = target_key.split("_", 1)[0]  # 提取文件名用于显示
                    dlg = ChunkInspector(fname, self)
                    dlg.update_data(self.chunks_cache[target_key])
                    dlg.exec()
                return
            path = data_val
            if path and isinstance(path, str) and os.path.exists(path):
                try:
                    # 使用 subprocess
                    import subprocess
                    norm_path = os.path.normpath(path)
                    if os.path.isfile(norm_path):
                        subprocess.Popen(f'explorer /select,"{norm_path}"')
                    else:
                        subprocess.Popen(f'explorer "{norm_path}"')
                except Exception as e:
                    print(f"打开失败: {e}")
            elif path:
                print(f"路径不存在: {path}")
    def terminate_running_steps(self):
        # 1. 遍历所有步骤节点
        for node in self.step_nodes.values():
            if "进行中" in node.text(1):
                node.setText(1, "🛑 已终止")
                node.setForeground(1, QColor("#ff4d4f"))

        # 2. 遍历所有父文件节点
        for node in self.file_nodes.values():
            if "处理中" in node.text(1) or "等待" in node.text(1):
                node.setText(1, "🛑 已终止")
                node.setForeground(1, QColor("#ff4d4f"))

# ================= 线程与日志 =================
class Worker(QThread):
    sig_done = pyqtSignal()
    sig_data = pyqtSignal(dict)

    def __init__(self, func, *args):
        super().__init__()
        self.func = func
        self.args = args

    def run(self):
        def callback(data_dict):
            self.sig_data.emit(data_dict)

        new_args = list(self.args)
        new_args.append(callback)
        try:
            self.func(*new_args)
        except Exception as e:
            self.sig_data.emit({"type": "log", "msg": f"[SYS_ERR]::{e}\n"})
        finally:
            self.sig_done.emit()


class WorkflowWorker(QThread):
    sig_log = pyqtSignal(str)
    sig_status = pyqtSignal(str)
    sig_step_update = pyqtSignal(str, int, int, str)  # file, step_idx, status, remark
    sig_chunk_update = pyqtSignal(str, int, list)
    sig_done = pyqtSignal()

    def __init__(self, steps, paths, configs):
        super().__init__()
        self.steps = steps  # List of step IDs
        self.paths = paths  # {in, out, cache}
        self.configs = configs
        self.abort = False
        self.trace_map = {}

    def run(self):
        # 初始输入
        current_in = self.paths['in']
        final_output = self.paths['out']
        cache_root = self.paths['cache']
        if not os.path.exists(cache_root): os.makedirs(cache_root)

        self.sig_log.emit(f"🚀 自定义工作流启动！共 {len(self.steps)} 个步骤")

        # 判断初始文件类型
        input_files = []
        first_step = self.steps[0] if self.steps else 0

        # 根据第一步的功能决定扫描什么文件
        scan_ext = '.pdf'
        if first_step == 3:  # 如果第一步是 LLM清洗 (Clean)，则扫描 Markdown
            scan_ext = '.md'

        input_files = []  # 移到外面初始化

        if os.path.exists(current_in):
            # 递归扫描
            for root, _, fs in os.walk(current_in):
                for f in fs:
                    if f.lower().endswith(scan_ext):
                        input_files.append(f)
                        # 如果是第一次运行，记录绝对路径到 trace_map
                        if f not in self.trace_map:
                            self.trace_map[f] = os.path.join(root, f)
            # MinerU
            if first_step == 2 and not input_files:
                input_files = [f for f in os.listdir(current_in) if os.path.isdir(os.path.join(current_in, f))]

        # 步骤名称映射
        step_name_map = {0: "Extract", 1: "SI", 2: "MinerU", 3: "Clean", 4: "Keyword"}
        self.file_map = {f: f for f in input_files}
        self.target_names = {f: f for f in input_files}

        # ---------------- 核心循环 ----------------
        for i, step_id in enumerate(self.steps):
            if self.abort: break

            step_name = step_name_map.get(step_id, f"Step{i}")
            self.sig_log.emit(f"\n>>> [Step {i + 1}/{len(self.steps)}] 正在执行: {step_name}...")
            self.sig_status.emit(f"🔄 正在执行步骤 {i + 1}: {step_name}")

            # 确定当前步骤输出目录
            if i == len(self.steps) - 1:
                current_out = final_output
            else:
                current_out = os.path.join(cache_root, f"Step{i + 1}_{step_name}_Out")
                if not os.path.exists(current_out): os.makedirs(current_out)
            if i > 0:
                pass
            # 调用对应脚本
            try:
                self.invoke_script_for_workflow(i, step_id, current_in, current_out)
            except Exception as e:
                self.sig_log.emit(f"❌ 步骤 {step_name} 发生错误: {e}")
                break

            unid_dir = os.path.join(current_out, "Unidentified")
            if os.path.exists(unid_dir):
                isolate_path = current_out + "_Unidentified"
                try:
                    # 如果隔离目录已存在，先清理掉
                    if os.path.exists(isolate_path):
                        shutil.rmtree(isolate_path)

                    # 移动文件夹
                    shutil.move(unid_dir, isolate_path)
                    self.sig_log.emit(f"    🧹 已将未识别文件移出工作流: {os.path.basename(isolate_path)}")
                except Exception as e:
                    self.sig_log.emit(f"    ⚠️ 隔离未识别文件失败: {e}")

            # 准备下一步的输入
            current_in = current_out

            # 特殊流转处理
            if step_id == 2:  # MinerU 输出包含子文件夹，需要定位到 markdown
                md_dir = os.path.join(current_out, "Markdown数据")
                if os.path.exists(md_dir):
                    current_in = md_dir
                    self.sig_log.emit(f"    ℹ️ 自动定位 MinerU 结果: {md_dir}")

            elif step_id == 1:  # SI 输出是文件夹，下一步如果是 MinerU 刚好支持
                pass

        self.sig_log.emit("\n🎉 工作流全部完成！")
        self.sig_done.emit()

    def clean_filename(self, text, max_len=100):
        if not text: return "Unknown"
        text = str(text).replace('\n', ' ').replace('\r', '')
        text = re.sub(r'[\\/*?:"<>|]', "", text)
        text = re.sub(r'\s+', " ", text).strip()
        if len(text) > max_len:
            text = text[:max_len].strip()
        text = text.rstrip(".")
        return text

    def invoke_script_for_workflow(self, step_seq_idx, step_id, inp, outp):
        # 建立临时查找表：绝对路径 -> 原始UI Key
        path_to_key = {}
        for k, v in self.trace_map.items():
            if v:
                abs_p = os.path.abspath(v)
                path_to_key[abs_p] = k

        # 2. 定义回调
        def wf_callback(data):
            msg_type = data.get("type")
            if msg_type == "log":
                self.sig_log.emit(data.get("msg", ""))
                return

            curr_file = data.get("file", "")

            original_key = None

            # (A) 绝对路径精准匹配
            if curr_file:
                abs_curr = os.path.abspath(curr_file)
                original_key = path_to_key.get(abs_curr)

            # (B) 文件名匹配 (针对路径变化的情况)
            if not original_key and curr_file:
                c_name = os.path.basename(curr_file)
                for k, v in self.trace_map.items():
                    if v and os.path.basename(v) == c_name:
                        original_key = k
                        break

            # (C) [新增] 文件夹/主名模糊匹配 (解决 MinerU 报告文件夹名的问题)
            # 场景：TraceMap 记录的是 "xxx.pdf"，但 MinerU 报告正在处理 "xxx" (同名文件夹)
            if not original_key and curr_file:
                c_base = os.path.basename(curr_file)  # 假设这是文件夹名
                for k, v in self.trace_map.items():
                    if v:
                        v_name = os.path.basename(v)
                        v_stem = os.path.splitext(v_name)[0]  # 取出 pdf 的主名
                        # 如果 回调名 == PDF主名 (例如 "Title" == "Title")
                        if c_base == v_stem:
                            original_key = k
                            break

            # 如果找不到 original_key，说明这个文件可能在之前的步骤已经失败并被剔除，
            # 或者是不在初始列表里的无关文件，直接忽略，不更新UI
            if not original_key:
                # [可选] 打开这行注释可以调试为什么匹配不到
                if msg_type in ["file_start", "file_done"]:
                   self.sig_log.emit(f"[Debug] 未匹配的回调: {curr_file}")
                return
            if msg_type == "log":
                self.sig_log.emit(data.get("msg", ""))
                return
            if msg_type == "chunk_update":
                chunks = data.get("chunks", [])
                # 发送给 UI：(原始文件名, 当前步骤在工作流中的序号, 碎片数据)
                self.sig_chunk_update.emit(original_key, step_seq_idx, chunks)
                return

            result_path = data.get("result_path", "")
            remark = data.get("remark", "")

            # 发送状态给 UI
            def send(code, txt):
                self.sig_step_update.emit(original_key, step_seq_idx, code, txt)

            if msg_type == "file_start":
                send(1, "")

            elif msg_type == "file_done":
                # --- [修正点：优先信任缓存目录 outp] ---
                new_path = ""

                # 1. 尝试从 result_path 或 remark 获取文件名
                candidate = result_path
                if not candidate and remark:
                    # 清洗干扰字符
                    clean = remark.replace("➜", "").replace("->", "").replace("成功", "").replace(":", "").strip()
                    # 如果看起来像文件名
                    if clean.lower().endswith(".pdf") and len(clean) < 200:
                        candidate = clean

                # 2. 构建绝对路径 (常规逻辑)
                if candidate:
                    if os.path.isabs(candidate):
                        new_path = candidate
                    else:
                        new_path = os.path.join(outp, candidate)

                # 3.SI 步骤
                # 用户确认：即使无 SI，脚本也会把文件复制到 outp
                if step_id == 1:
                    trace_source_path = self.trace_map.get(original_key)
                    if trace_source_path:
                        target_filename = os.path.basename(trace_source_path)
                        # 取文件名的前 40 个字符作为特征码 (应对截断)
                        target_feature = target_filename[:40]

                        # 1. 脚本返回路径有效
                        if new_path and os.path.exists(new_path):
                            pass
                            # 2. 脚本没返回，深度搜索 outp
                        else:
                            found_in_sub = False
                            for root, dirs, files in os.walk(outp):
                                for f in files:
                                    # [关键修改]：不仅比对全名，还比对特征码
                                    # 如果文件名以特征码开头，且是pdf，就认为是同一个文件
                                    if f.endswith(".pdf") and (f == target_filename or f.startswith(target_feature)):
                                        new_path = os.path.join(root, f)
                                        found_in_sub = True
                                        if not remark: remark = "已归档"
                                        break
                                if found_in_sub: break

                            # 3. 实在找不到，才回退到原路径
                            if not found_in_sub:
                                if trace_source_path and os.path.exists(trace_source_path):
                                    new_path = trace_source_path
                                    if not remark: remark = "未移动"

                # 4. MinerU 目录修正找.md
                if step_id == 2:
                    # 如果 MinerU 返回的是文件夹，进去找 MD
                    search_root = new_path if (new_path and os.path.isdir(new_path)) else outp
                    # 只有当 new_path 无效或者是指向文件夹时，才去搜索
                    if not new_path or os.path.isdir(new_path):
                        found_md = False
                        # 这里的搜索需要谨慎，最好只搜该文件对应的子目录
                        # 如果 original_key 对应的 PDF 主名是 X，我们优先找 X 文件夹下的 MD
                        pdf_stem = os.path.splitext(os.path.basename(self.trace_map[original_key]))[0]

                        for root, dirs, files in os.walk(search_root):
                            # 优化：如果目录名包含 pdf 主名，命中率更高
                            if pdf_stem in root or True:
                                for f in files:
                                    if f.endswith(".md") and "readme" not in f.lower():
                                        new_path = os.path.join(root, f)
                                        found_md = True
                                        break
                            if found_md: break

                # --- [最终判定] ---
                if new_path and os.path.exists(new_path):
                    abs_path = os.path.abspath(new_path)
                    self.trace_map[original_key] = abs_path
                    path_to_key[abs_path] = original_key

                    final_remark = f"{remark}|{abs_path}" if "|" not in str(remark) else remark
                    send(2, final_remark)
                else:
                    self.sig_log.emit(f"❌ [系统] 步骤{step_id}产物丢失，已在 {outp} 深度搜索但未找到。")
                    send(3, "产物丢失")
                    if original_key in self.trace_map:
                        del self.trace_map[original_key]

            elif msg_type == "file_error":
                # --- [失败：阻断后续步骤] ---
                send(3, data.get("msg", "Error"))
                # 关键：从映射表中删除。这样下一步骤遍历 trace_map 准备输入时，
                # 或者脚本运行产生回调时，都无法再关联到这个文件，变相实现了“终止该文件的后续步骤”
                if original_key in self.trace_map:
                    del self.trace_map[original_key]

            elif msg_type == "file_skip":
                msg_text = data.get("msg", "Skip")
                send(4, msg_text)

                # 智能重连逻辑
                is_success_skip = any(k in msg_text for k in ["已处理", "已归档", "exist", "跳过", "已存在"])
                if is_success_skip:
                    # 如果是 Step 1 (Extract)，输入和输出文件名不同，必须通过特征重连
                    if step_seq_idx == 0:
                        original_path = self.trace_map.get(original_key)
                        # 只有当原始路径存在，且输出目录也存在时才尝试寻找
                        if original_path and os.path.exists(original_path) and os.path.exists(outp):
                            found_new_path = None
                            try:
                                # 策略：通过文件大小和前1KB内容快速匹配 (比全量MD5快)
                                src_size = os.path.getsize(original_path)

                                # 遍历输出目录寻找匹配的文件
                                for root, _, files in os.walk(outp):
                                    for f in files:
                                        if not f.lower().endswith(".pdf"): continue
                                        candidate = os.path.join(root, f)

                                        # 1. 简单过滤：大小必须一致
                                        if os.path.getsize(candidate) != src_size: continue

                                        # 2. 深度过滤：读取头部字节比对
                                        with open(original_path, 'rb') as f1, open(candidate, 'rb') as f2:
                                            if f1.read(1024) == f2.read(1024):
                                                found_new_path = os.path.abspath(candidate)
                                                break
                                    if found_new_path: break
                            except:
                                pass

                            if found_new_path:
                                # 更新追踪表：将 Key 指向新的改名后的文件
                                self.trace_map[original_key] = found_new_path
                                # 更新反向查找表
                                path_to_key[found_new_path] = original_key
                                # 同时更新 UI 显示，让用户知道它关联到了哪个新文件
                                send(2, f"{msg_text}|{found_new_path}") # 状态改为完成绿色
                            else:
                                # 没找到对应文件，只能保留原状 (可能会导致下一步未匹配，但比直接删除好)
                                pass
                else:
                    # 如果是真正的错误跳过 (如 "无DOI" 等)，则从追踪表中移除
                    if original_key in self.trace_map:
                        del self.trace_map[original_key]

        # 3. 执行脚本
        # 这里保持你原有的调用逻辑
        if step_id == 0:
            script_extract.run_from_gui(inp, outp, self.configs.get("ex_fmt"), current_config.get("deepseek_key"),
                                        wf_callback)
        elif step_id == 1:
            script_si.run_from_gui(inp, outp, current_config.get("chrome_data_dir"), current_config.get("deepseek_key"),
                                   wf_callback)
        elif step_id == 2:
            script_mineru.run_from_gui(current_config.get("mineru_token"), inp, outp, wf_callback)
        elif step_id == 3:
            script_clean.run_from_gui(current_config.get("deepseek_key"), inp, outp, self.configs.get("ds_prompt"),
                                      current_config.get("gemini_key"), self.configs.get("model"), wf_callback)
        elif step_id == 4:
            script_keyword.run_from_gui(inp, outp, self.configs.get("kw_str"), wf_callback)

class GenKeywordThread(QThread):
    result_signal = pyqtSignal(str)

    def __init__(self, api_key, prompt):
        super().__init__()
        self.api_key = api_key;
        self.prompt = prompt

    def run(self):
        try:
            res = script_keyword.generate_keywords_with_llm(self.api_key, self.prompt)
            self.result_signal.emit(res)
        except Exception:
            self.result_signal.emit("生成失败，请检查API Key或网络")


# 设置对话框
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 全局设置")
        self.setMinimumWidth(600)
        self.setStyleSheet(
            "QDialog { background-color: #fdfdfd; font-size: 14px; } QLabel { font-weight: bold; color: #444; } QLineEdit { border: 1px solid #ccc; padding: 6px; border-radius: 4px; }")
        layout = QFormLayout(self)
        layout.setSpacing(15)

        self.chrome_data_edit = QLineEdit(current_config.get("chrome_data_dir", ""))
        self.chrome_data_edit.setPlaceholderText("留空则自动创建")
        btn_chrome = QPushButton("选择")
        btn_chrome.clicked.connect(lambda: self.sel_dir(self.chrome_data_edit))
        hb_chrome = QHBoxLayout()
        hb_chrome.addWidget(self.chrome_data_edit);
        hb_chrome.addWidget(btn_chrome)
        layout.addRow("Chrome数据路径:", hb_chrome)

        self.proxy_edit = QLineEdit(current_config.get("proxy", ""))
        self.mineru_token_edit = QLineEdit(current_config.get("mineru_token", ""))
        self.mineru_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.deepseek_key_edit = QLineEdit(current_config.get("deepseek_key", ""))
        self.deepseek_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_key_edit = QLineEdit(current_config.get("gemini_key", ""))
        self.gemini_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

        layout.addRow("网络代理:", self.proxy_edit)
        layout.addRow("MinerU Token:", self.mineru_token_edit)
        layout.addRow("DeepSeek Key:", self.deepseek_key_edit)
        layout.addRow("Gemini Key:", self.gemini_key_edit)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addRow(line)

        self.sidebar_img_edit = QLineEdit(current_config.get("sidebar_img", ""))
        btn_sidebar = QPushButton("选图")
        btn_sidebar.clicked.connect(lambda: self.sel_img(self.sidebar_img_edit))
        hb_sidebar = QHBoxLayout()
        hb_sidebar.addWidget(self.sidebar_img_edit);
        hb_sidebar.addWidget(btn_sidebar)
        self.sidebar_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.sidebar_opacity_slider.setRange(0, 100)
        self.sidebar_opacity_slider.setValue(int(current_config.get("sidebar_opacity", 100)))
        layout.addRow("侧边栏图片:", hb_sidebar)
        layout.addRow("透明度:", self.sidebar_opacity_slider)

        self.log_img_edit = QLineEdit(current_config.get("log_img", ""))
        btn_log = QPushButton("选图")
        btn_log.clicked.connect(lambda: self.sel_img(self.log_img_edit))
        hb_log = QHBoxLayout()
        hb_log.addWidget(self.log_img_edit);
        hb_log.addWidget(btn_log)
        self.log_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.log_opacity_slider.setRange(0, 100)
        self.log_opacity_slider.setValue(int(current_config.get("log_opacity", 20)))
        layout.addRow("日志背景:", hb_log)
        layout.addRow("透明度:", self.log_opacity_slider)

        save_btn = QPushButton("保存并应用")
        save_btn.setFixedHeight(40)
        save_btn.setStyleSheet("background-color: #1890ff; color: white; border-radius: 5px;")
        save_btn.clicked.connect(self.save_and_close)
        layout.addRow(save_btn)

    def sel_dir(self, edit):
        p = QFileDialog.getExistingDirectory(self, "选文件夹", edit.text())
        if p: edit.setText(p)

    def sel_img(self, edit):
        p, _ = QFileDialog.getOpenFileName(self, "选图片", "", "Images (*.png *.jpg *.jpeg)")
        if p: edit.setText(p)

    def save_and_close(self):
        current_config.update({
            "chrome_data_dir": self.chrome_data_edit.text().strip(), "proxy": self.proxy_edit.text().strip(),
            "mineru_token": self.mineru_token_edit.text().strip(),
            "deepseek_key": self.deepseek_key_edit.text().strip(),
            "gemini_key": self.gemini_key_edit.text().strip(),
            "sidebar_img": self.sidebar_img_edit.text().strip(), "sidebar_opacity": self.sidebar_opacity_slider.value(),
            "log_img": self.log_img_edit.text().strip(), "log_opacity": self.log_opacity_slider.value()
        })
        save_config(current_config)
        self.accept()


# 碎片详情 (保持原样)
class ChunkInspector(QDialog):
    def __init__(self, filename, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"🔍 碎片详情: {filename}")
        self.resize(800, 500)
        self.layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.verticalHeader().setDefaultSectionSize(45)
        self.table.setHorizontalHeaderLabels(["ID", "状态", "Input Tk", "Output Tk", "LLM返回内容"])
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.layout.addWidget(self.table)
        self.chunks_data = []

    def update_data(self, chunks):
        self.chunks_data = chunks
        self.table.setRowCount(len(chunks))
        for i, c in enumerate(chunks):
            self.table.setItem(i, 0, QTableWidgetItem(str(c.get('id', ''))))
            status_map = {0: "⏳ 等待", 1: "🔄 进行中", 2: "✅ 成功", 3: "❌ 失败"}
            s_item = QTableWidgetItem(status_map.get(c.get('status'), "?"))
            if c.get('status') == 1:
                s_item.setForeground(QColor("#1890ff"))
            elif c.get('status') == 2:
                s_item.setForeground(QColor("green"))
            elif c.get('status') == 3:
                s_item.setForeground(QColor("red"))
            self.table.setItem(i, 1, s_item)
            self.table.setItem(i, 2, QTableWidgetItem(str(c.get('in_tok', 0))))
            self.table.setItem(i, 3, QTableWidgetItem(str(c.get('out_tok', 0))))
            full_content = c.get('content', '')
            display_text = full_content[:50].replace('\n', ' ') + "..." if len(full_content) > 50 else full_content
            c_item = QTableWidgetItem(display_text)
            c_item.setToolTip(full_content)
            self.table.setItem(i, 4, c_item)


# ================= 主窗口 =================
class MainWindowV12(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("文献工具箱 v1.2 自定义可用")
        self.resize(1500, 900)
        self.setStyleSheet(STYLES)

        self.workers = {}
        # 跟踪自定义流程的向导状态
        self.wiz_step_index = 0  # 0: Builder, 1+: Config Pages
        self.wiz_active_steps = []  # 用户选中的步骤ID列表
        self.wiz_configs = {}  # 收集的配置

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==================== 1. Left Sidebar ====================
        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(300)
        sl = QVBoxLayout(self.sidebar)
        sl.setContentsMargins(15, 30, 15, 20)
        sl.setSpacing(8)
        sl.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("科研文献\n自动化处理系统")
        title.setObjectName("SidebarTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #2c3e50; padding: 20px 10px;")
        sl.addWidget(title)

        # [新增] 左上角自定义流程按钮
        self.btn_custom = QPushButton("🛠️ 自定义流程")
        self.btn_custom.setObjectName("CustomFlowBtn")
        self.btn_custom.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_custom.clicked.connect(self.switch_to_custom_workflow)
        sl.addWidget(self.btn_custom)
        sl.addSpacing(0)

        self.nav_btns = []
        self.create_nav("📂 文献提取与整理", 0, sl)
        self.create_nav("🌐 自动抓取 SI", 1, sl)
        self.create_nav("⚡ MinerU 清洗", 2, sl)
        self.create_nav("✨ LLM 二次清洗", 3, sl)
        self.create_nav("🔍 PDF 关键词筛选", 4, sl)

        sl.addSpacing(15)
        self.img_label = ScaledImageLabel()
        self.update_sidebar_image()
        sl.addWidget(self.img_label)

        footer = QWidget()
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(0, 10, 0, 0)
        fl.addStretch()
        lbl_author = QLabel("by: 刘三")
        lbl_author.setStyleSheet("color:#888; font-size:12px;")
        fl.addWidget(lbl_author)
        fl.addSpacing(20)
        btn_set = QPushButton("⚙️ 设置")
        btn_set.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_set.setStyleSheet(
            "border: 1px solid #ddd; padding: 4px 12px; color: #666; border-radius: 4px; background:white;")
        btn_set.clicked.connect(self.open_settings)
        fl.addWidget(btn_set)
        fl.addStretch()
        sl.addWidget(footer)
        main_layout.addWidget(self.sidebar)

        # ==================== 2. Middle (Configuration + Logs) ====================
        self.mid = QWidget()
        self.mid.setObjectName("Middle")
        self.mid.setFixedWidth(600)
        ml = QVBoxLayout(self.mid)
        ml.setContentsMargins(30, 30, 30, 30)
        ml.setSpacing(20)

        self.lbl_head = QLabel("功能配置")
        self.lbl_head.setStyleSheet("font-size:20px; font-weight:bold;")
        ml.addWidget(self.lbl_head)

        # Stack: 0-4=常规功能, 5=WorkFlowBuilder, 6+=WorkFlowConfigs
        self.stack = QStackedWidget()
        self.stack.addWidget(self.page_extract())  # 0
        self.stack.addWidget(self.page_si())  # 1
        self.stack.addWidget(self.page_mineru())  # 2
        self.stack.addWidget(self.page_clean())  # 3
        self.stack.addWidget(self.page_keyword())  # 4
        self.stack.addWidget(self.page_workflow_builder())  # 5 (自定义流程首页)

        # 预留配置页面的位置 (6, 7, 8...)
        self.wiz_config_widgets = []

        ml.addWidget(self.stack)

        btns = QHBoxLayout()
        self.btn_run = QPushButton("🚀 开始运行")
        self.btn_run.setMinimumHeight(45)
        self.btn_run.setProperty("class", "actionBtn")
        self.btn_run.clicked.connect(self.start_task)

        # 这里的停止按钮在自定义流程模式下会变成"下一步"
        self.btn_stop = QPushButton("🛑 停止")
        self.btn_stop.setMinimumHeight(45)
        self.btn_stop.setProperty("class", "actionBtn")
        self.btn_stop.setStyleSheet("background-color: #ff4d4f;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_or_next)  # 绑定双重功能

        btns.addWidget(self.btn_run)
        btns.addWidget(self.btn_stop)
        ml.addLayout(btns)

        ml.addWidget(QLabel("运行日志:"))
        self.log_stack = QStackedWidget()
        # 0-4 常规日志
        for _ in range(5):
            log_box = QTextEdit()
            log_box.setReadOnly(True)
            log_box.setStyleSheet("background:white; border:1px solid #ddd; font-family:Consolas; color:#555;")
            self.log_stack.addWidget(log_box)
        # 5 自定义流程日志
        self.wf_log_box = QTextEdit()
        self.wf_log_box.setReadOnly(True)
        self.wf_log_box.setStyleSheet("background:white; border:1px solid #ddd; font-family:Consolas; color:#000;")
        self.log_stack.addWidget(self.wf_log_box)

        ml.addWidget(self.log_stack)
        main_layout.addWidget(self.mid)

        # ==================== 3. Right (File List Stack) ====================
        self.right_stack = QStackedWidget()
        self.right_stack.setObjectName("RightPanel")

        self.file_lists = []
        # 0-4: 常规列表
        for i in range(5):
            fl_widget = FileListWidget()
            self.file_lists.append(fl_widget)
            self.right_stack.addWidget(fl_widget)

        # 5: 自定义流程树形列表
        self.wf_tree = WorkflowTreeListWidget()
        self.right_stack.addWidget(self.wf_tree)

        main_layout.setStretch(0, 0)
        main_layout.setStretch(1, 0)
        main_layout.setStretch(2, 1)
        main_layout.addWidget(self.right_stack)

        self.switch_nav(0)  # 默认首页

    # ================= 页面构建 =================
    def page_extract(self):
        w = QWidget();
        l = QVBoxLayout(w);
        l.setAlignment(Qt.AlignmentFlag.AlignTop);
        l.setSpacing(15)
        self.ex_in = self.add_path(l, "输入文件夹:", "ex_input")
        self.ex_out = self.add_path(l, "输出文件夹:", "ex_output")
        gb = QFrame();
        gb.setObjectName("FormatBox");
        gl = QVBoxLayout(gb)
        gl.addWidget(QLabel("📝 自定义命名格式"))
        gl.addWidget(QLabel(
            "[1]年份 [2]期刊 [3]标题 [4]一作 [5]类型 [6]卷号<br/>"
            "[7]期号 [8]页码 [9]DOI [10]出版商 [11]ISSN",
            styleSheet="color:#888; font-size:12px; word-wrap:break-word;"
        ))
        self.ex_fmt = QLineEdit();
        self.ex_fmt.setText(current_config.get("ex_format", "[1][2][5][3]"))
        gl.addWidget(self.ex_fmt);
        l.addWidget(gb)
        return w

    def page_si(self):
        w = QWidget();
        l = QVBoxLayout(w);
        l.setAlignment(Qt.AlignmentFlag.AlignTop);
        l.setSpacing(15)
        l.addWidget(QLabel("功能: 自动抓取 PDF 对应的 SI 文件"))
        self.si_in = self.add_path(l, "输入文件夹:", "si_input")
        self.si_out = self.add_path(l, "输出文件夹:", "si_output")
        l.addWidget(QLabel("⚠️ 请确保已在设置中安装 Chrome 浏览器", styleSheet="color:#e6a23c; margin-top:10px;"))
        return w

    def page_mineru(self):
        w = QWidget();
        l = QVBoxLayout(w);
        l.setAlignment(Qt.AlignmentFlag.AlignTop);
        l.setSpacing(15)
        l.addWidget(QLabel("🔑 Token: 已在设置中配置", styleSheet="color: #2da44e; font-weight: bold; padding: 10px 0;"))
        self.mi_in = self.add_path(l, "输入目录:", "mi_input")
        self.mi_out = self.add_path(l, "保存目录:", "mi_output")
        return w

    def page_clean(self):
        w = QWidget();
        l = QVBoxLayout(w);
        l.setAlignment(Qt.AlignmentFlag.AlignTop);
        l.setSpacing(15)
        l.addWidget(QLabel("🔑 API Key: 请在【设置】中配置 DeepSeek 或 Gemini Key",
                           styleSheet="color: #2da44e; font-weight: bold; padding: 10px 0;"))

        self.ds_prompt = self.add_path(l, "提示词文件:", "ds_prompt", False)
        self.ds_in = self.add_path(l, "Markdown目录:", "ds_input", True, lambda p: self.scan_files(3, p, ".md"))
        self.ds_out = self.add_path(l, "输出目录:", "ds_output")

        # [新增] 模型选择下拉框
        l.addWidget(QLabel("🤖 选择模型:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "deepseek-chat",
            "gemini-3-pro-preview",
            "gemini-2.5-flash",
            "gemini-2.5-pro"
        ])
        # 读取上次选择 (可选)
        last_model = current_config.get("last_clean_model", "deepseek-chat")
        idx = self.model_combo.findText(last_model)
        if idx >= 0: self.model_combo.setCurrentIndex(idx)

        # 美化下拉框
        self.model_combo.setFixedHeight(40)
        self.model_combo.setStyleSheet("""
                    /* 主输入框样式 */
                    QComboBox { 
                        border: 1px solid #ccc; 
                        border-radius: 6px; 
                        padding-left: 10px; 
                        background-color: white;   /* 必须设置背景色 */
                        color: #333;
                        font-size: 14px;
                    }

                    /* 下拉箭头区域 */
                    QComboBox::drop-down {
                        subcontrol-origin: padding;
                        subcontrol-position: top right;
                        width: 30px;
                        border-left: 1px solid #eee;
                        border-top-right-radius: 6px;
                        border-bottom-right-radius: 6px;
                        background-color: #fafafa;
                    }

                    /* 下拉箭头图标 (可选，用字符代替图片) */
                    QComboBox::down-arrow {
                        width: 0; 
                        height: 0; 
                        border-left: 5px solid transparent;
                        border-right: 5px solid transparent;
                        border-top: 6px solid #666;
                        margin-top: 2px;
                    }

                    /* 核心修复：下拉列表容器 */
                    QComboBox QAbstractItemView {
                        background-color: white;  /* 【关键】防止透明重影 */
                        border: 1px solid #ccc;
                        selection-background-color: #e6f7ff; /* 选中项背景 */
                        selection-color: #333;    /* 选中项文字颜色 */
                        outline: none;            /* 去掉虚线框 */
                        padding: 4px;
                    }
                """)

        # 使用 Delegate 增加选项高度
        from PyQt6.QtWidgets import QStyledItemDelegate
        delegate = QStyledItemDelegate()
        self.model_combo.setItemDelegate(delegate)
        from PyQt6.QtWidgets import QListView
        self.model_combo.setView(QListView())
        l.addWidget(self.model_combo)

        return w

    def page_keyword(self):
        w = QWidget();
        l = QVBoxLayout(w);
        l.setAlignment(Qt.AlignmentFlag.AlignTop);
        l.setSpacing(15)
        l.addWidget(QLabel("1. 需求描述"));
        self.kw_text = QTextEdit();
        self.kw_text.setFixedHeight(80);
        self.kw_text.setStyleSheet("border: 1px solid #ccc; border-radius: 4px; padding: 8px;")
        l.addWidget(self.kw_text)
        btn = QPushButton("✨ 生成关键词");
        btn.setStyleSheet("background:#8250df; color:white; border-radius:4px; padding:8px; font-weight:bold;")
        btn.clicked.connect(self.gen_kw);
        l.addWidget(btn)
        l.addWidget(QLabel("2. 关键词结果"));
        self.kw_res = QTextEdit();
        self.kw_res.setFixedHeight(60);
        self.kw_res.setStyleSheet("border: 1px solid #ccc; border-radius: 4px; padding: 8px;")
        l.addWidget(self.kw_res)
        path_row = QHBoxLayout();
        path_row.setSpacing(15)
        in_col = QVBoxLayout();
        in_col.setSpacing(5);
        in_col.addWidget(QLabel("源文件夹:"))
        self.kw_in_edit = QLineEdit();
        self.kw_in_edit.setText(current_config.get("kw_input", ""))
        in_btn = QPushButton("📂");
        in_btn.setProperty("class", "browseBtn")
        in_btn.clicked.connect(
            lambda: self.open_f(self.kw_in_edit, "kw_input", True, lambda p: self.scan_files(4, p, ".pdf")))
        hb1 = QHBoxLayout();
        hb1.setSpacing(5);
        hb1.addWidget(self.kw_in_edit);
        hb1.addWidget(in_btn);
        in_col.addLayout(hb1)
        out_col = QVBoxLayout();
        out_col.setSpacing(5);
        out_col.addWidget(QLabel("输出位置:"))
        self.kw_out_edit = QLineEdit();
        self.kw_out_edit.setText(current_config.get("kw_output", ""))
        out_btn = QPushButton("📂");
        out_btn.setProperty("class", "browseBtn")
        out_btn.clicked.connect(lambda: self.open_f(self.kw_out_edit, "kw_output", True))
        hb2 = QHBoxLayout();
        hb2.setSpacing(5);
        hb2.addWidget(self.kw_out_edit);
        hb2.addWidget(out_btn);
        out_col.addLayout(hb2)
        path_row.addLayout(in_col);
        path_row.addLayout(out_col);
        l.addSpacing(15);
        l.addLayout(path_row)
        return w
    # [新增] 自定义流程构建页
    def page_workflow_builder(self):
        w = QWidget();
        l = QVBoxLayout(w);
        l.setAlignment(Qt.AlignmentFlag.AlignTop);
        l.setSpacing(10)
        l.addWidget(QLabel("🔧 流程编排", styleSheet="font-size:16px; font-weight:bold; color:#8250df;"))

        self.wf_list = QListWidget()
        self.wf_list.setStyleSheet("border:1px solid #ccc; border-radius:4px; padding:5px; font-size: 14px;")
        self.wf_list.setFixedHeight(70)
        self.wf_list.setFlow(QListView.Flow.LeftToRight)
        self.wf_list.setSpacing(10)
        l.addWidget(self.wf_list)

        h_btn = QHBoxLayout()
        self.wf_combo = QComboBox()
        self.wf_combo.addItems(
            ["📂 文献提取与整理", "🌐 自动抓取 SI", "⚡ MinerU 清洗", "✨ LLM 二次清洗", "🔍 PDF 关键词筛选"])
        self.wf_combo.setFixedHeight(40)
        self.wf_combo.setStyleSheet("""
                    /* 主输入框样式 */
                    QComboBox { 
                        border: 1px solid #ccc; 
                        border-radius: 6px; 
                        padding-left: 10px; 
                        background-color: white;   /* 必须设置背景色 */
                        color: #333;
                        font-size: 14px;
                    }

                    /* 下拉箭头区域 */
                    QComboBox::drop-down {
                        subcontrol-origin: padding;
                        subcontrol-position: top right;
                        width: 30px;
                        border-left: 1px solid #eee;
                        border-top-right-radius: 6px;
                        border-bottom-right-radius: 6px;
                        background-color: #fafafa;
                    }

                    /* 下拉箭头图标 (可选，用字符代替图片) */
                    QComboBox::down-arrow {
                        width: 0; 
                        height: 0; 
                        border-left: 5px solid transparent;
                        border-right: 5px solid transparent;
                        border-top: 6px solid #666;
                        margin-top: 2px;
                    }

                    /* 核心修复：下拉列表容器 */
                    QComboBox QAbstractItemView {
                        background-color: white;  /* 【关键】防止透明重影 */
                        border: 1px solid #ccc;
                        selection-background-color: #e6f7ff; /* 选中项背景 */
                        selection-color: #333;    /* 选中项文字颜色 */
                        outline: none;            /* 去掉虚线框 */
                        padding: 4px;
                    }
                """)
        btn_add = QPushButton("➕");
        btn_add.setFixedWidth(40);
        btn_add.clicked.connect(self.add_wf_step)
        btn_del = QPushButton("➖");
        btn_del.setFixedWidth(40);
        btn_del.clicked.connect(self.del_wf_step)
        h_btn.addWidget(self.wf_combo, 2);
        h_btn.addWidget(btn_add);
        h_btn.addWidget(btn_del)
        l.addLayout(h_btn)

        l.addSpacing(10)
        self.wf_in = self.add_path(l, "🟢 初始输入文件夹:", "wf_input")
        self.wf_cache = self.add_path(l, "📦 中间缓存文件夹 (自动创建):", "wf_cache")
        self.wf_out = self.add_path(l, "🔴 最终输出文件夹:", "wf_output")
        if not self.wf_cache.text(): self.wf_cache.setText(os.path.join(os.getcwd(), "Workflow_Cache"))
        return w

    def add_wf_step(self):
        if self.wf_list.count() >= 5: return QMessageBox.warning(self, "提示", "最多5个步骤")
        text = self.wf_combo.currentText()
        map_id = {"📂": 0, "🌐": 1, "⚡": 2, "✨": 3, "🔍": 4}
        step_id = 0
        for k, v in map_id.items():
            if k in text: step_id = v; break
        for i in range(self.wf_list.count()):
            item_id = self.wf_list.item(i).data(Qt.ItemDataRole.UserRole)
            if item_id == step_id:
                return QMessageBox.warning(self, "提示", f"步骤 '{text}' 已经添加过了，不能重复添加！")
        icon_char = text.split(" ")[0]  # 获取字符串第一个空格前的部分(即图标)
        item = QListWidgetItem(f"{self.wf_list.count() + 1}. {icon_char}")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)  # 居中显示
        item.setData(Qt.ItemDataRole.UserRole, step_id)
        self.wf_list.addItem(item)

    def del_wf_step(self):
        row = self.wf_list.currentRow()
        if row >= 0: self.wf_list.takeItem(row)
        for i in range(self.wf_list.count()):
            it = self.wf_list.item(i)
            txt = it.text().split(". ", 1)[1]
            it.setText(f"{i + 1}. {txt}")

    # ================= 逻辑控制 =================
    def update_sidebar_image(self):
        self.img_label.set_image(current_config.get("sidebar_img"), current_config.get("sidebar_opacity", 100))

    def create_nav(self, text, idx, layout):
        btn = QPushButton(text)
        btn.setProperty("class", "navBtn")
        btn.setCheckable(True)
        btn.clicked.connect(lambda: self.switch_nav(idx))
        self.nav_btns.append(btn)
        layout.addWidget(btn)

    def switch_nav(self, idx):
        # 恢复自定义按钮样式
        self.btn_custom.setStyleSheet("border: 2px solid transparent;")

        # 切换常规 Tab
        for i, b in enumerate(self.nav_btns): b.setChecked(i == idx)

        # UI 重置
        self.stack.setCurrentIndex(idx)
        self.log_stack.setCurrentIndex(idx)
        self.right_stack.setCurrentIndex(idx)
        self.lbl_head.setText(self.nav_btns[idx].text().strip() if idx < len(self.nav_btns) else "功能配置")

        # 按钮逻辑重置
        is_running = idx in self.workers and self.workers[idx].isRunning()
        self.btn_run.setVisible(True)
        self.btn_run.setEnabled(not is_running)
        self.btn_stop.setText("🛑 停止")
        self.btn_stop.setStyleSheet("background-color: #ff4d4f;")
        self.btn_stop.setEnabled(is_running)

        # 断开所有自定义流程的旧连接
        try:
            self.btn_stop.clicked.disconnect(self.stop_or_next)
        except:
            pass
        try:
            self.btn_stop.clicked.disconnect(self.stop_task)
        except:
            pass
        try:
            self.btn_run.clicked.disconnect()
        except:
            pass
        self.btn_run.clicked.connect(self.start_task)

        self.btn_run.setText("🚀 开始运行")
        self.btn_stop.clicked.connect(self.stop_task)

        # 尝试自动扫描
        current_list_widget = self.file_lists[idx]
        if current_list_widget.table.rowCount() == 0 and not is_running:
            path = "";
            ext = ".pdf"
            if idx == 0:
                path = self.ex_in.text()
            elif idx == 1:
                path = self.ex_in.text() #抓取SI，你可能会抓到.doc
            elif idx == 2:
                path = self.ex_in.text()
            elif idx == 3:
                path = self.ex_in.text(); ext = ".md"
            elif idx == 4:
                path = self.ex_in.text()
            self.scan_files(idx, path, ext)

    def switch_to_custom_workflow(self):
        # UI 切换
        for b in self.nav_btns: b.setChecked(False)
        self.btn_custom.setStyleSheet("background-color: #6a3fb8; border: 2px solid #fff;") # 高亮
        is_running = 5 in self.workers and self.workers[5].isRunning()

        if is_running:
            # 如果正在运行，恢复状态
            self.lbl_head.setText("🚀 流程运行中...")
            self.stack.setCurrentIndex(5 + self.wiz_step_index)  # 恢复到之前的配置页或运行页
            self.log_stack.setCurrentIndex(5)
            self.right_stack.setCurrentIndex(5)

            # 恢复按钮状态为“停止”
            self.btn_run.setVisible(True)
            self.btn_run.setText("⬅ 上一步")
            self.btn_run.setEnabled(False)  # 运行中禁止上一步

            self.btn_stop.setText("🛑 停止运行")
            self.btn_stop.setStyleSheet("background-color: #ff4d4f; font-weight: bold;")
            self.btn_stop.setEnabled(True)

            # 重新绑定信号
            try:
                self.btn_stop.clicked.disconnect()
            except:
                pass
            try:
                self.btn_run.clicked.disconnect()
            except:
                pass
            self.btn_stop.clicked.connect(self.stop_or_next)
            # 运行中不需要绑定 run 的上一页功能

        else:
            # 如果没运行，才执行重置逻辑 (原有代码)
            self.lbl_head.setText("🛠️ 自定义流程配置")
            self.wiz_step_index = 0
            self.wiz_active_steps = []

            # 清理之前的动态配置页
            while self.stack.count() > 6:
                w = self.stack.widget(6)
                self.stack.removeWidget(w)
                w.deleteLater()

            self.stack.setCurrentIndex(5)
            self.log_stack.setCurrentIndex(5)
            self.right_stack.setCurrentIndex(5)

            # 按钮逻辑变换
            self.btn_run.setVisible(True)
            self.btn_run.setText("⬅ 上一步")
            self.btn_run.setEnabled(False)
            self.btn_stop.setText("下一步 ➡")
            self.btn_stop.setStyleSheet("background-color: #1890ff; font-weight: bold;")
            self.btn_stop.setEnabled(True)

            try:
                self.btn_stop.clicked.disconnect()
            except:
                pass
            try:
                self.btn_run.clicked.disconnect()
            except:
                pass
            self.btn_run.clicked.connect(self.go_prev_wizard_step)
            self.btn_stop.clicked.connect(self.stop_or_next)


    def stop_or_next(self):
        # 如果是常规模式，或者是工作流正在运行中，则是"停止"
        is_workflow_running = 5 in self.workers and self.workers[5].isRunning()
        if self.stack.currentIndex() < 5 or is_workflow_running:
            self.stop_task()
            return

        # 否则是“下一步”逻辑
        self.go_next_wizard_step()

    def go_next_wizard_step(self):
        # 1. 如果在 Builder 页 (Index 0 for wizard)
        if self.wiz_step_index == 0:
            # 校验输入
            if self.wf_list.count() == 0:
                # [修改] 直接使用标准弹窗，它会自动应用 STYLES 中的样式
                QMessageBox.warning(self, "提示", "请至少添加一个步骤！")
                return
            if not self.wf_in.text() or not self.wf_out.text():
                # [修改] 直接使用标准弹窗
                QMessageBox.warning(self, "提示", "请设置输入输出路径！")
                return
            while self.stack.count() > 6:
                w = self.stack.widget(6)
                self.stack.removeWidget(w)
                w.deleteLater()
            # 收集步骤
            self.wiz_active_steps = []
            step_names = []
            for i in range(self.wf_list.count()):
                it = self.wf_list.item(i)
                sid = it.data(Qt.ItemDataRole.UserRole)
                self.wiz_active_steps.append(sid)
                step_names.append(it.text().split(". ", 1)[1])

            # 初始化右侧树形列表
            folder = self.wf_in.text()
            if os.path.exists(folder):
                unique_files = {} # 用于去重：文件名 -> 完整路径

                for root, _, fs in os.walk(folder):
                    for f in fs:
                        if f.lower().endswith(".pdf"):
                            full_path = os.path.join(root, f)

                            # === [核心修改] 去重逻辑 ===
                            if f not in unique_files:
                                unique_files[f] = full_path
                            else:
                                # 如果遇到同名文件，保留路径更短的那个（通常是根目录的）
                                # 这样UI显示的就和脚本实际处理的是同一个文件了
                                if len(full_path) < len(unique_files[f]):
                                    unique_files[f] = full_path

                # 提取去重后的文件名并排序
                files = sorted(list(unique_files.keys()))
                self.wf_tree.init_workflow(files, step_names)

            # 动态生成配置页
            self.generate_config_pages()

        # 2. 页面跳转
        self.wiz_step_index += 1
        self.btn_run.setEnabled(True)

        # 计算 Stack 中的实际索引 (5是Builder，6是第一个配置页)
        target_stack_idx = 5 + self.wiz_step_index

        if target_stack_idx < self.stack.count():
            # 还有配置页
            self.stack.setCurrentIndex(target_stack_idx)
            self.lbl_head.setText(f"步骤配置 ({self.wiz_step_index}/{self.stack.count() - 6})")
            if target_stack_idx == self.stack.count() - 1:
                self.btn_stop.setText("🚀 开始运行")
                self.btn_stop.setStyleSheet("background-color: #ff4d4f; color: white; font-weight: bold;")
            else:
                self.btn_stop.setText("下一步 ➡")
                self.btn_stop.setStyleSheet("background-color: #1890ff; color: white; font-weight: bold;")
        else:
            if "开始运行" not in self.btn_stop.text():
                self.btn_stop.setText("🚀 开始运行")
                self.btn_stop.setStyleSheet("background-color: #ff4d4f; color: white; font-weight: bold;")
                self.lbl_head.setText("准备就绪")
                # 此时不运行，等待用户再次点击红色按钮
                return

                # 按钮已经是红色了，说明用户确认运行
            self.start_workflow_run()

    def go_prev_wizard_step(self):
        if self.wiz_step_index > 0:
            self.wiz_step_index -= 1
            self.stack.setCurrentIndex(5 + self.wiz_step_index)
            self.btn_stop.setText("下一步 ➡")
            self.btn_stop.setStyleSheet("background-color: #1890ff; color: white; font-weight: bold;")

            # 更新标题和按钮状态
            if self.wiz_step_index == 0:
                self.lbl_head.setText("🛠️ 自定义流程配置")
                self.btn_run.setEnabled(False)  # 回到首页，禁用上一步
            else:
                self.lbl_head.setText(f"步骤配置 ({self.wiz_step_index}/{self.stack.count() - 6})")

    def generate_config_pages(self):
        # 根据选中的步骤动态添加配置页到 Stack
        # 0:Extract, 1:SI(无参), 2:MinerU(无参), 3:Clean, 4:Keyword

        has_extract = 0 in self.wiz_active_steps
        has_clean = 3 in self.wiz_active_steps
        has_keyword = 4 in self.wiz_active_steps

        if has_extract:
            p = QWidget()
            l = QVBoxLayout(p)
            l.setAlignment(Qt.AlignmentFlag.AlignTop)

            # 标题
            l.addWidget(QLabel("📂 [提取整理] 配置", styleSheet="font-size:16px; font-weight:bold; margin-bottom:10px;"))

            #使用 FormatBox 容器包裹
            gb = QFrame()
            gb.setObjectName("FormatBox")  # 关键：继承 CSS 样式
            gl = QVBoxLayout(gb)

            gl.addWidget(QLabel("📝 自定义命名格式"))
            gl.addWidget(QLabel(
                "[1]年份 [2]期刊 [3]标题 [4]一作 [5]类型 [6]卷号<br/>" 
                "[7]期号 [8]页码 [9]DOI [10]出版商 [11]ISSN",
                styleSheet="color:#888; font-size:12px;"
            ))

            self.wf_ex_fmt = QLineEdit(current_config.get("ex_format", "[1][2][5][3]"))
            gl.addWidget(self.wf_ex_fmt)

            l.addWidget(gb)  # 将卡片添加到布局
            self.stack.addWidget(p)

        if has_keyword:
            p = QWidget()
            l = QVBoxLayout(p)
            l.setAlignment(Qt.AlignmentFlag.AlignTop)
            l.addWidget(QLabel("🔍 [关键词] 配置", styleSheet="font-size:16px; font-weight:bold; margin-bottom:10px;"))

            # 仿照布局
            l.addWidget(QLabel("1. 需求描述"))
            self.wf_kw_req = QTextEdit()  # 改名，避免与独立功能的 self.kw_text 冲突
            self.wf_kw_req.setFixedHeight(80)
            self.wf_kw_req.setPlaceholderText("请输入筛选需求...")
            # 继承输入框样式
            self.wf_kw_req.setStyleSheet("border: 1px solid #ccc; border-radius: 4px; padding: 8px;")
            l.addWidget(self.wf_kw_req)

            btn_gen = QPushButton("✨ 生成关键词")
            btn_gen.setStyleSheet("background:#8250df; color:white; border-radius:4px; padding:8px; font-weight:bold;")

            # 绑定生成逻辑
            def run_kw_custom():
                k = current_config.get("deepseek_key")
                u = self.wf_kw_req.toPlainText()
                if not k or not u:
                    return QMessageBox.warning(self, "错误", "缺 DeepSeek Key 或需求描述")
                # 必须把线程存为 self 属性防止被垃圾回收
                self.kw_thread_custom = GenKeywordThread(k, u)
                self.kw_thread_custom.result_signal.connect(self.wf_kw_res.setText)
                self.kw_thread_custom.start()

            btn_gen.clicked.connect(run_kw_custom)
            l.addWidget(btn_gen)

            l.addWidget(QLabel("2. 关键词结果 (实际用于筛选)"))
            self.wf_kw_res = QTextEdit()  # 改名，用于接收结果
            self.wf_kw_res.setFixedHeight(60)
            self.wf_kw_res.setStyleSheet("border: 1px solid #ccc; border-radius: 4px; padding: 8px;")
            l.addWidget(self.wf_kw_res)
            # -------------------------------

            self.stack.addWidget(p)

        if has_clean:
            p = QWidget();
            l = QVBoxLayout(p);
            l.setAlignment(Qt.AlignmentFlag.AlignTop)
            l.addWidget(QLabel("✨ [LLM清洗] 配置", styleSheet="font-size:16px; font-weight:bold;"))
            l.addWidget(QLabel("提示词文件:"))
            h = QHBoxLayout()
            self.wf_ds_prompt = QLineEdit(current_config.get("ds_prompt", ""))
            btn = QPushButton("📂");
            btn.clicked.connect(lambda: self.sel_file(self.wf_ds_prompt))
            h.addWidget(self.wf_ds_prompt);
            h.addWidget(btn);
            l.addLayout(h)
            l.addWidget(QLabel("选择模型:"))
            self.wf_model_combo = QComboBox()
            self.wf_model_combo.addItems([
            "deepseek-chat",
            "gemini-3-pro-preview",
            "gemini-2.5-flash",
            "gemini-2.5-pro"
            ])
            self.wf_model_combo.setCurrentText(current_config.get("last_clean_model", "deepseek-chat"))
            self.wf_model_combo.setFixedHeight(40)
            self.wf_model_combo.setStyleSheet("""
                                /* 主输入框样式 */
                                QComboBox { 
                                    border: 1px solid #ccc; 
                                    border-radius: 6px; 
                                    padding-left: 10px; 
                                    background-color: white;   /* 必须设置背景色 */
                                    color: #333;
                                    font-size: 14px;
                                }

                                /* 下拉箭头区域 */
                                QComboBox::drop-down {
                                    subcontrol-origin: padding;
                                    subcontrol-position: top right;
                                    width: 30px;
                                    border-left: 1px solid #eee;
                                    border-top-right-radius: 6px;
                                    border-bottom-right-radius: 6px;
                                    background-color: #fafafa;
                                }

                                /* 下拉箭头图标 (可选，用字符代替图片) */
                                QComboBox::down-arrow {
                                    width: 0; 
                                    height: 0; 
                                    border-left: 5px solid transparent;
                                    border-right: 5px solid transparent;
                                    border-top: 6px solid #666;
                                    margin-top: 2px;
                                }

                                /* 核心修复：下拉列表容器 */
                                QComboBox QAbstractItemView {
                                    background-color: white;  /* 【关键】防止透明重影 */
                                    border: 1px solid #ccc;
                                    selection-background-color: #e6f7ff; /* 选中项背景 */
                                    selection-color: #333;    /* 选中项文字颜色 */
                                    outline: none;            /* 去掉虚线框 */
                                    padding: 4px;
                                }
                            """)

            l.addWidget(self.wf_model_combo)
            self.stack.addWidget(p)

    def start_workflow_run(self):
        modules = [script_extract, script_si, script_mineru, script_clean, script_keyword]
        for m in modules:
            if m: m.abort_flag = False
        # 收集配置
        configs = {}
        if hasattr(self, 'wf_ex_fmt'): configs['ex_fmt'] = self.wf_ex_fmt.text()
        if hasattr(self, 'wf_kw_res'):
            configs['kw_str'] = self.wf_kw_res.toPlainText()
        if hasattr(self, 'wf_ds_prompt'):
            configs['ds_prompt'] = self.wf_ds_prompt.text()
            configs['model'] = self.wf_model_combo.currentText()

        # 运行中
        self.btn_stop.setText("🛑 停止运行")
        self.btn_stop.setStyleSheet("background-color: #ff4d4f;")
        self.lbl_head.setText("🚀 流程运行中...")
        self.btn_run.setEnabled(False)

        # 启动 Worker
        paths = {'in': self.wf_in.text(), 'out': self.wf_out.text(), 'cache': self.wf_cache.text()}
        worker = WorkflowWorker(self.wiz_active_steps, paths, configs)

        worker.sig_log.connect(lambda s: self.append_log(5, s + "\n"))
        worker.sig_status.connect(lambda s: self.lbl_head.setText(s))
        worker.sig_step_update.connect(self.wf_tree.update_step_status)
        worker.sig_done.connect(lambda: self.on_task_finished(5))
        worker.sig_chunk_update.connect(self.wf_tree.update_chunk_data)

        self.workers[5] = worker
        worker.start()
        for btn in self.nav_btns:
            btn.setEnabled(False)

    # ================= 通用辅助 =================
    def add_path(self, layout, label, key, is_dir=True, cb=None):
        l = QLabel(label);
        layout.addWidget(l)
        h = QHBoxLayout();
        edit = QLineEdit();
        edit.setText(current_config.get(key, ""))
        btn = QPushButton("📂");
        btn.setFixedWidth(40);
        btn.setProperty("class", "browseBtn")
        btn.clicked.connect(lambda: self.open_f(edit, key, is_dir, cb))
        h.addWidget(edit);
        h.addWidget(btn);
        layout.addLayout(h)
        return edit

    def open_f(self, edit, key, is_dir, cb=None):
        p = QFileDialog.getExistingDirectory(self) if is_dir else QFileDialog.getOpenFileName(self)[0]
        if p:
            edit.setText(p);
            current_config[key] = p;
            save_config(current_config)
            if cb: cb(p)

    def sel_file(self, edit):
        f, _ = QFileDialog.getOpenFileName(self, "选文件")
        if f: edit.setText(f)

    def open_settings(self):
        if SettingsDialog(self).exec(): self.update_sidebar_image()

    def gen_kw(self):
        k = current_config.get("deepseek_key");
        u = self.kw_text.toPlainText()
        if not k or not u: return QMessageBox.warning(self, "错", "缺Key或需求")
        self.kw_thread = GenKeywordThread(k, u);
        self.kw_thread.result_signal.connect(self.kw_res.setText);
        self.kw_thread.start()

    def scan_files(self, idx, path, ext):
        if os.path.exists(path):
            files = sorted([f for f in os.listdir(path) if f.endswith(ext)])
            self.file_lists[idx].init_files(files, "clean" if (idx == 2 or idx == 3) else "normal")

    def append_log(self, idx, text):
        try:
            box = self.wf_log_box if idx == 5 else self.log_stack.widget(idx)
            box.moveCursor(QTextCursor.MoveOperation.End)
            box.insertPlainText(text)
            box.moveCursor(QTextCursor.MoveOperation.End)
        except:
            pass

    def on_data_received(self, data, idx):
        # 处理常规 Tab 的消息
        msg_type = data.get("type")
        target_list = self.file_lists[idx]
        if msg_type == "log":
            self.append_log(idx, data.get("msg", "") + "\n")
        elif msg_type == "scan_result":
            target_list.init_files(data.get("files", []), data.get("mode", "normal"))
        elif msg_type == "file_start":
            target_list.update_status(data.get("file"), 1)
        elif msg_type == "file_done":
            target_list.update_status(data.get("file"), 2, data.get("remark", ""), data.get("result_path"))
        elif msg_type == "file_error":
            target_list.update_status(data.get("file"), 3, data.get("msg", ""))
        elif msg_type == "file_skip":
            target_list.update_status(data.get("file"), 4, data.get("msg", ""))
        elif msg_type == "file_deferred":
            target_list.update_status(data.get("file"), 5, data.get("remark", "推迟"))
        elif msg_type == "chunk_update":
            target_list.update_chunk_info(data.get("file"), data.get("chunks"))

    def on_task_finished(self, idx):
        #无论哪个任务结束，都恢复所有侧边栏按钮
        self.btn_custom.setEnabled(True)
        for btn in self.nav_btns:
            btn.setEnabled(True)
        if hasattr(self, 'stopping_dlg') and self.stopping_dlg.isVisible():
            if idx == 5:
                # 自定义流程
                self.wf_tree.terminate_running_steps()
            elif idx < 5:
                # 常规功能流程 (0-4)
                self.file_lists[idx].terminate_running_items()
            self.stopping_dlg.accept()  # 关闭弹窗，解除阻塞
            self.append_log(idx, ">>> 任务已强制停止.\n")
            if idx in self.workers: del self.workers[idx]
            return
        if idx in self.workers: del self.workers[idx]
        if idx == 5:
            # 工作流结束，重置按钮状态
            self.btn_stop.setText("下一步 ➡")
            self.btn_stop.setStyleSheet("background-color: #1890ff; font-weight: bold;")
            self.lbl_head.setText("工作流执行完毕")
            QMessageBox.information(self, "完成", "自定义流程所有步骤执行完毕！")
            self.switch_to_custom_workflow()
            return

        if self.stack.currentIndex() == idx:
            self.btn_run.setEnabled(True)
            self.btn_stop.setEnabled(False)
        self.append_log(idx, "\n>>> 任务已结束.\n")

    def start_task(self):
        idx = self.stack.currentIndex()
        if idx == 5: return  # 自定义流程走单独逻辑
        if idx in self.workers and self.workers[idx].isRunning(): return

        # 重置对应模块的中断标志
        modules = [script_extract, script_si, script_mineru, script_clean, script_keyword]
        if idx < len(modules) and modules[idx]: modules[idx].abort_flag = False

        try:
            worker = None
            if idx == 0:
                # 传入 current_config.get("deepseek_key")
                worker = Worker(script_extract.run_from_gui, self.ex_in.text(), self.ex_out.text(), self.ex_fmt.text(),
                                current_config.get("deepseek_key"))
            elif idx == 1:
                worker = Worker(script_si.run_from_gui, self.si_in.text(), self.si_out.text(),
                                current_config.get("chrome_data_dir"), current_config.get("deepseek_key"))
            elif idx == 2:
                worker = Worker(script_mineru.run_from_gui, current_config.get("mineru_token"), self.mi_in.text(),
                                self.mi_out.text())
            elif idx == 3:
                i = self.ds_in.text();
                self.scan_files(idx, i, ".md")
                current_config["last_clean_model"] = self.model_combo.currentText();
                save_config(current_config)
                worker = Worker(script_clean.run_from_gui, current_config.get("deepseek_key"), i, self.ds_out.text(),
                                self.ds_prompt.text(), current_config.get("gemini_key"), self.model_combo.currentText())
            elif idx == 4:
                self.scan_files(idx, self.kw_in_edit.text(), ".pdf")
                worker = Worker(script_keyword.run_from_gui, self.kw_in_edit.text(), self.kw_out_edit.text(),
                                self.kw_res.toPlainText())

            if worker:
                worker.sig_data.connect(lambda d: self.on_data_received(d, idx))
                worker.sig_done.connect(lambda: self.on_task_finished(idx))
                self.workers[idx] = worker
                worker.start()
                self.btn_run.setEnabled(False)
                self.btn_stop.setEnabled(True)
                self.btn_custom.setEnabled(False)
        except Exception as e:
            QMessageBox.warning(self, "启动错误", str(e))

    def stop_task(self):
        idx = self.stack.currentIndex()
        modules = [script_extract, script_si, script_mineru, script_clean, script_keyword]

        # 停止常规任务
        if idx < len(modules) and modules[idx]:
            modules[idx].abort_flag = True

        # 停止工作流
        if idx >= 5:
            if 5 in self.workers: self.workers[5].abort = True
            for m in modules:
                if m: m.abort_flag = True

        self.btn_stop.setEnabled(False)
        self.append_log(idx, "\n>>> 正在停止...\n")
        if idx >= 5 or (idx in self.workers and self.workers[idx].isRunning()):
            self.stopping_dlg = QDialog(self)
            self.stopping_dlg.setWindowTitle("请稍候")
            self.stopping_dlg.setFixedSize(300, 120)
            # 去掉右上角关闭按钮，强制用户等待
            self.stopping_dlg.setWindowFlags(self.stopping_dlg.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

            layout = QVBoxLayout(self.stopping_dlg)
            layout.addWidget(QLabel("🛑 正在停止任务，请等待后台清理...", alignment=Qt.AlignmentFlag.AlignCenter))

            # 阻塞主界面，直到在 on_task_finished 中调用 accept()
            self.stopping_dlg.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindowV12()
    w.show()
    sys.exit(app.exec())