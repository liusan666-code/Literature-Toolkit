import os
import time
import requests
import json
import zipfile
import io
import shutil
import hashlib
import logging
import sys
from pathlib import Path
from pypdf import PdfWriter, PdfReader

# ================= 配置区域 =================
# 请替换为你的实际 Token
API_TOKEN = ""

# 输入：包含子文件夹（[年份] [期刊] [题目]）的根目录
INPUT_ROOT_DIR = r""

# 输出：最终结果存放的根目录
OUTPUT_ROOT_DIR = r""

# 临时目录：存放合并后的大PDF
TEMP_MERGED_DIR = os.path.join(OUTPUT_ROOT_DIR, "00_Merged_PDFs")

# 历史记录文件路径
HISTORY_FILE = os.path.join(OUTPUT_ROOT_DIR, "processing_historymineru.json")

MODEL_VERSION = "vlm"
BATCH_SIZE = 10
# ===========================================

# 屏蔽 pypdf 的红色警告
logger = logging.getLogger("pypdf")
logger.setLevel(logging.ERROR)

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_TOKEN}"
}


# --- 辅助函数 ---
def format_size(size_bytes):
    """将字节转换为易读格式"""
    if size_bytes == 0: return "0B"
    size_name = ("B", "KB", "MB", "GB")
    i = 0
    while size_bytes >= 1024 and i < len(size_name) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f}{size_name[i]}"


# --- 历史记录管理函数 ---
def load_history():
    """读取已完成的任务列表"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data.get("completed_folders", []))
        except Exception as e:
            return set()
    return set()


def save_history(completed_set):
    """保存已完成的任务列表"""
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump({"completed_folders": list(completed_set)}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        pass


# -----------------------

def get_folder_structure(root_dir, logger=None):
    """遍历目录获取任务"""
    targets = []
    if not os.path.exists(root_dir):
        if logger: logger(f"❌ 输入目录不存在: {root_dir}")
        return []

    for item in os.listdir(root_dir):
        full_path = os.path.join(root_dir, item)

        # 1. 情况A：是文件夹 -> 原有逻辑（合并内部PDF）
        if os.path.isdir(full_path):
            pdfs = [f for f in os.listdir(full_path) if f.lower().endswith('.pdf')]
            if pdfs:
                targets.append({
                    "type": "folder",  # [新增] 标记类型
                    "folder_name": item,
                    "folder_path": full_path,
                    "files": pdfs
                })

        # 2. 情况B：是PDF文件 -> 新增逻辑（直接上传）
        elif os.path.isfile(full_path) and item.lower().endswith('.pdf'):
            # 使用文件名（无后缀）作为任务名
            task_name = os.path.splitext(item)[0]
            targets.append({
                "type": "file",  # [新增] 标记类型
                "folder_name": task_name,  # 保持键名一致方便后续处理
                "file_path": full_path
            })

    return targets


def merge_pdfs_in_task(task_info, logger=None):
    """合并 PDF (带详细提示版)"""
    merger = PdfWriter()
    folder_path = task_info['folder_path']
    folder_name = task_info['folder_name']
    files = task_info['files']

    # --- 筛选与排序逻辑 ---
    main_file = None
    si_files = []

    for f in files:
        if folder_name in f or "SI" not in f:
            if main_file is None:
                main_file = f
            else:
                si_files.append(f)
        else:
            si_files.append(f)

    si_files.sort()
    merge_list = []
    if main_file:
        merge_list.append(main_file)
    merge_list.extend(si_files)

    if not merge_list:
        if logger: logger(f"   ⚠️ 跳过空文件夹: {folder_name}")
        return None

    if logger:
        logger(f"   🔨 正在合并: {folder_name}")
        logger(f"      -> 正文: {main_file if main_file else '未识别到明显正文'}")
        logger(f"      -> 附件: {len(si_files)} 个")

    try:
        for filename in merge_list:
            filepath = os.path.join(folder_path, filename)
            merger.append(filepath)

        if not os.path.exists(TEMP_MERGED_DIR):
            os.makedirs(TEMP_MERGED_DIR)

        output_filename = f"{folder_name}.pdf"
        output_path = os.path.join(TEMP_MERGED_DIR, output_filename)

        merger.write(output_path)
        page_count = len(merger.pages)
        merger.close()
        return output_path, page_count
    except Exception as e:
        if logger: logger(f"   ❌ 合并失败 {folder_name}: {e}")
        return None, 0  # [修改] 返回空元组


def process_single_pdf(task_info, logger=None):
    """处理单文件任务：仅读取页数，不合并"""
    src_path = task_info['file_path']
    name = task_info['folder_name']

    try:
        # 读取页数用于备注显示
        reader = PdfReader(src_path)
        page_count = len(reader.pages)
        return src_path, page_count
    except Exception as e:
        if logger: logger(f"❌ 读取PDF失败 {name}: {e}")
        return None, 0
def create_batch_upload_urls(file_paths, logger=None):
    """第一步：申请上传链接"""
    url = "https://mineru.net/api/v4/file-urls/batch"
    files_info = []

    for path in file_paths:
        if getattr(sys.modules[__name__], 'abort_flag', False):
            if logger: logger(">>> 🛑 检测到停止信号，正在安全退出...")
            break
        file_name = os.path.basename(path)
        data_id = hashlib.md5(file_name.encode('utf-8')).hexdigest()
        files_info.append({"name": file_name, "data_id": data_id})

    data = {"files": files_info, "model_version": MODEL_VERSION}

    try:
        res = requests.post(url, headers=HEADERS, json=data)
        if res.status_code == 200 and res.json().get("code") == 0:
            return res.json()["data"]
        else:
            if logger: logger(f"❌ 申请API失败: {res.text}")
            return None
    except Exception as e:
        if logger: logger(f"❌ 请求异常: {e}")
        return None


def upload_files(file_paths, file_urls, logger=None):
    """第二步：上传文件"""
    if logger: logger(f"🚀 正在上传 {len(file_paths)} 个文件...")
    for i, file_path in enumerate(file_paths):
        upload_url = file_urls[i]
        try:
            with open(file_path, 'rb') as f:
                requests.put(upload_url, data=f)
        except Exception as e:
            if logger: logger(f"   ❌ 上传失败 {os.path.basename(file_path)}: {e}")


def wait_for_completion(batch_id, logger=None):
    """第三步：等待完成"""
    url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
    if logger: logger(f"⏳ 等待解析 (Batch: {batch_id})...")

    while True:
        if getattr(sys.modules[__name__], 'abort_flag', False):
            if logger: logger(">>> 🛑 检测到停止信号，正在安全退出...")
            break
        try:
            res = requests.get(url, headers=HEADERS)
            if res.status_code == 200:
                data = res.json().get("data", {})
                results = data.get("extract_result", [])

                not_done = [r for r in results if r["state"] in ["pending", "waiting-file", "running", "converting"]]

                if not not_done:
                    if logger: logger(f"✅ 解析完成！")
                    return results

                # 仅在控制台打印进度条，不发送给 GUI 避免刷屏
                print(f"   ...剩余 {len(not_done)} 个文件处理中", end="\r")
            time.sleep(5)
        except Exception as e:
            time.sleep(10)


def process_results(results, completed_set, logger=None, signal_callback=None, page_counts=None):
    """第四步：下载、整理并记录历史"""
    full_data_dir = os.path.join(OUTPUT_ROOT_DIR, "完整数据")
    md_only_dir = os.path.join(OUTPUT_ROOT_DIR, "Markdown数据")

    for d in [full_data_dir, md_only_dir]:
        if not os.path.exists(d):
            os.makedirs(d)

    if logger: logger(f"📥 正在下载并处理...")

    newly_completed = 0

    for item in results:
        file_name = item.get("file_name")  # xxx.pdf
        state = item.get("state")
        zip_url = item.get("full_zip_url")

        base_name = os.path.splitext(file_name)[0]  # 原始文件夹名

        if state != "done" or not zip_url:
            if logger: logger(f"⚠️ 解析失败/未完成: {base_name} (状态: {state})")
            # GUI更新失败
            if signal_callback:
                signal_callback({"type": "file_error", "file": base_name, "msg": f"Status: {state}"})
            continue

        # 1. 下载并解压
        extract_path = os.path.join(full_data_dir, base_name)
        download_size = 0
        try:
            resp = requests.get(zip_url)
            download_size = len(resp.content)  # 获取大小用于备注
            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                z.extractall(extract_path)
        except Exception as e:
            if logger: logger(f"❌ 下载/解压出错 {base_name}: {e}")
            if signal_callback:
                signal_callback({"type": "file_error", "file": base_name, "msg": "下载失败"})
            continue

        # 2. 提取 Markdown
        found_md = False
        for root, dirs, files in os.walk(extract_path):
            for file in files:
                if file.endswith(".md"):
                    src_md = os.path.join(root, file)
                    dst_md = os.path.join(md_only_dir, f"{base_name}.md")
                    shutil.copy2(src_md, dst_md)
                    found_md = True
                    break

        # 3. 记录
        if found_md:
            completed_set.add(base_name)
            save_history(completed_set)
            newly_completed += 1
            if logger: logger(f"   ✅ 已完成: {base_name}")
            if logger: logger(f"💾 已更新历史记录，新增 {newly_completed} 条。")

            # 备注显示下载数据大小
            p_count = page_counts.get(base_name, "?") if page_counts else "?"

            if signal_callback:
                signal_callback({
                    "type": "file_done",
                    "file": base_name,
                    "remark": f"{p_count} 页",  # [修改] 显示页数
                    "result_path": os.path.join(md_only_dir, f"{base_name}.md")  # [新增] 返回MD文件绝对路径
                })
        else:
            if logger: logger(f"   ⚠️ 未找到Markdown: {base_name}")
            if signal_callback:
                signal_callback({"type": "file_error", "file": base_name, "msg": "无MD文件"})


def main(gui_token=None, gui_input=None, gui_output=None, signal_callback=None):
    global API_TOKEN, INPUT_ROOT_DIR, OUTPUT_ROOT_DIR, TEMP_MERGED_DIR, HISTORY_FILE
    task_page_counts = {}
    # 定义日志发送器
    def log_msg(text):
        print(text)
        if signal_callback:
            try:
                signal_callback({"type": "log", "msg": text})
            except:
                pass

    # 参数覆盖
    if gui_token: API_TOKEN = gui_token
    if gui_input: INPUT_ROOT_DIR = gui_input
    if gui_output: OUTPUT_ROOT_DIR = gui_output

    TEMP_MERGED_DIR = os.path.join(OUTPUT_ROOT_DIR, "00_Merged_PDFs")
    HISTORY_FILE = os.path.join(OUTPUT_ROOT_DIR, "processing_historymineru.json")

    HEADERS["Authorization"] = f"Bearer {API_TOKEN}"

    if not API_TOKEN:
        log_msg("❌ 请先设置 API_TOKEN")
        return

    # 0. 加载历史
    completed_tasks = load_history()
    log_msg(f"📚 已读取历史记录，之前已完成 {len(completed_tasks)} 个任务。")

    # 1. 扫描
    all_folders = get_folder_structure(INPUT_ROOT_DIR, logger=log_msg)

    # 向 GUI 发送扫描列表
    if signal_callback:
        signal_callback({
            "type": "scan_result",
            "files": [t['folder_name'] for t in all_folders],
            "mode": "normal"
        })

    # 2. 过滤
    tasks_to_do = []
    for t in all_folders:
        if t['folder_name'] in completed_tasks:
            # 标记为已完成
            if signal_callback:
                signal_callback({"type": "file_skip", "file": t['folder_name'], "msg": "已完成"})
        else:
            tasks_to_do.append(t)

    log_msg(f"📊 扫描到 {len(all_folders)} 个目录，剩余 {len(tasks_to_do)} 个待处理。")

    if not tasks_to_do:
        log_msg("🎉 所有任务均已完成！")
        return

    # 3. 合并 PDF (标记状态为进行中)
    log_msg("\n🔄 阶段一：合并 PDF...")
    merged_pdf_paths = []
    for task in tasks_to_do:
        if getattr(sys.modules[__name__], 'abort_flag', False): break

        # GUI 状态变蓝
        if signal_callback:
            signal_callback({"type": "file_start", "file": task['folder_name']})

        # --- [修改开始] 分支判断 ---
        if task.get('type') == 'file':
            # === 分支1：单文件直接处理 ===
            final_path, p_count = process_single_pdf(task, logger=log_msg)
            if final_path:
                merged_pdf_paths.append(final_path)
                task_page_counts[task['folder_name']] = p_count
            else:
                if signal_callback:
                    signal_callback({"type": "file_error", "file": task['folder_name'], "msg": "读取失败"})

        else:
            # === 分支2：文件夹合并 (原有逻辑) ===
            expected_output = os.path.join(TEMP_MERGED_DIR, f"{task['folder_name']}.pdf")
            if os.path.exists(expected_output):
                log_msg(f"   ⏩ 使用已合并缓存: {task['folder_name']}")

                # 读取缓存文件的页数（为了显示正确，不然是空的）
                try:
                    reader = PdfReader(expected_output)
                    p_count = len(reader.pages)
                except:
                    p_count = "?"

                merged_pdf_paths.append(expected_output)
                task_page_counts[task['folder_name']] = p_count
            else:
                merged_path, p_count = merge_pdfs_in_task(task, logger=log_msg)
                if merged_path:
                    merged_pdf_paths.append(merged_path)
                    task_page_counts[task['folder_name']] = p_count
                else:
                    if signal_callback:
                        signal_callback({"type": "file_error", "file": task['folder_name'], "msg": "合并失败"})
    # 4. 批量提交
    log_msg(f"\n🔄 阶段二：开始批量处理 {len(merged_pdf_paths)} 个文件...")
    for i in range(0, len(merged_pdf_paths), BATCH_SIZE):
        if getattr(sys.modules[__name__], 'abort_flag', False): break

        batch_files = merged_pdf_paths[i: i + BATCH_SIZE]
        log_msg(f"\n   -> 批次 {i // BATCH_SIZE + 1} ({len(batch_files)} 文件)...")

        res_data = create_batch_upload_urls(batch_files, logger=log_msg)
        if not res_data: continue

        upload_files(batch_files, res_data["file_urls"], logger=log_msg)
        results = wait_for_completion(res_data["batch_id"], logger=log_msg)

        process_results(results, completed_tasks, logger=log_msg, signal_callback=signal_callback, page_counts=task_page_counts) # [修改] 传入 page_counts)

    log_msg("\n🎉 全部流程结束！")


def run_from_gui(api_token, input_folder, output_folder, signal_callback=None):
    main(api_token, input_folder, output_folder, signal_callback)


if __name__ == "__main__":
    main()