import os
import shutil
import sys
import re
import time
from pathlib import Path
from pypdf import PdfReader
from openai import OpenAI

# ================= 停止标记 =================
abort_flag = False


# ================= 功能 1: 调用 DeepSeek 生成关键词 =================
def generate_keywords_with_llm(api_key, user_requirement):
    """
    根据用户的描述，让 DeepSeek 生成推荐的关键词
    """
    if not api_key:
        return "错误：未配置 API Key"

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    prompt = f"""
    你是一个专业的科研助手。用户想在海量文献中筛选出特定的论文。
    用户的需求是："{user_requirement}"

    请根据这个需求，提取出最核心的关键词（Keywords）。
    要求：
    1. 只需有英文关键词（全称和缩写），不要有中文关键词。
    2. 关键词之间用英文逗号 "," 分隔。
    3. 不要输出任何解释性文字，只输出关键词列表。
    4. 数量控制在 10 个左右，覆盖面要广但要精准。

    例如用户搜“锂硫电池”，你输出：
    Lithium-sulfur batteries, Li-S, Li-S batteries, sulfur cathode, polysulfide, shuttle effect
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            stream=False
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"API 调用失败: {str(e)}"


# ================= 功能 2: 扫描 PDF 并复制 =================

def contains_keyword(text, keywords):
    """检查文本中是否包含任一关键词"""
    if not text: return False
    text = text.lower()
    for kw in keywords:
        if kw.lower().strip() in text:
            return True
    return False


def run_scan(input_folder, output_folder, keywords_str, signal_callback=None):
    """
    主扫描逻辑
    """

    # 日志封装 helper
    def log_msg(text):
        print(text)
        if signal_callback:
            try:
                signal_callback({"type": "log", "msg": text})
            except:
                pass

    # 1. 解析关键词
    keywords = [k.strip() for k in keywords_str.replace("，", ",").split(",") if k.strip()]

    if not keywords:
        log_msg(">>> ❌ 错误：关键词列表为空，无法开始扫描。")
        return

    source_path = Path(input_folder)
    target_path = Path(output_folder)

    if not source_path.exists():
        log_msg(f">>> ❌ 源文件夹不存在: {input_folder}")
        return

    target_path.mkdir(parents=True, exist_ok=True)

    log_msg(f"==========================================")
    log_msg(f"🎯 筛选关键词: {keywords}")
    log_msg(f"📂 扫描目录: {input_folder}")
    log_msg(f"📂 输出目录: {output_folder}")
    log_msg(f"==========================================\n")

    # 获取所有 PDF 文件
    all_files = list(source_path.rglob('*.pdf'))
    total_files = len(all_files)

    # [GUI同步] 发送扫描结果，确保列表显示正确
    if signal_callback:
        signal_callback({
            "type": "scan_result",
            "files": [f.name for f in all_files],
            "mode": "normal"
        })

    log_msg(f"开始扫描 {total_files} 个文件...")

    count_found = 0
    count_scanned = 0

    # 扫描前N页
    CHECK_PAGES = 3

    for file_path in all_files:
        # 停止检测
        if getattr(sys.modules[__name__], 'abort_flag', False):
            log_msg(">>> 🛑 检测到停止信号，正在退出扫描...")
            break

        count_scanned += 1
        filename = file_path.name

        # [GUI同步] 状态：开始处理
        if signal_callback:
            signal_callback({"type": "file_start", "file": filename})

        if count_scanned % 10 == 0:
            print(f"    ...已扫描 {count_scanned}/{total_files} 个文件")

        is_match = False
        match_source = ""

        # --- 第一步：检查文件名 ---
        if contains_keyword(filename, keywords):
            is_match = True
            match_source = "文件名匹配"
        else:
            # --- 第二步：检查内容 ---
            try:
                reader = PdfReader(file_path)
                num_pages = len(reader.pages)
                pages_to_read = min(num_pages, CHECK_PAGES)
                extracted_text = ""
                for i in range(pages_to_read):
                    page_text = reader.pages[i].extract_text()
                    if page_text:
                        extracted_text += page_text + "\n"

                if contains_keyword(extracted_text, keywords):
                    is_match = True
                    match_source = "内容匹配"
            except Exception:
                pass

        # --- 第三步：处理结果 ---
        if is_match:
            try:
                # 防止重名覆盖
                dest_file = target_path / filename
                if dest_file.exists():
                    stem = dest_file.stem
                    suffix = dest_file.suffix
                    dest_file = target_path / f"{stem}_copy{suffix}"

                shutil.copy2(file_path, dest_file)
                count_found += 1

                log_msg(f"✅ [{match_source}] 发现: {filename}")

                # [GUI同步] 状态：完成 (绿色 ✅) + 备注
                if signal_callback:
                    signal_callback({
                        "type": "file_done",
                        "file": filename,
                        "remark": f"✅ 匹配 ({match_source})"
                    })

            except Exception as e:
                log_msg(f"❌ 复制失败 {filename}: {e}")
                if signal_callback:
                    signal_callback({"type": "file_error", "file": filename, "msg": "复制失败"})
        else:
            # [GUI同步] 状态：跳过 (黄色 ⏭️) + 备注
            # 注意：这里用 file_skip 对应主程序中的 Status Code 4 (跳过)
            if signal_callback:
                signal_callback({
                    "type": "file_skip",
                    "file": filename,
                    "msg": "❌ 未匹配"
                })

    log_msg("\n" + "=" * 50)
    log_msg(f"扫描结束 | 总扫描: {count_scanned} | 命中并复制: {count_found}")
    log_msg(f"文件已保存在: {output_folder}")


# GUI 调用接口
def run_from_gui(input_folder, output_folder, keywords_str, signal_callback=None):
    # 注意：signal_callback 放在最后，因为 Worker 会自动追加
    run_scan(input_folder, output_folder, keywords_str, signal_callback)


if __name__ == "__main__":
    pass