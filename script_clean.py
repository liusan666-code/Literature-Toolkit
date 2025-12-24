import os
import glob
import time
import json
import shutil
import tiktoken
import sys
from datetime import datetime
from openai import OpenAI

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

# ================= Configuration Area =================
API_KEY = ""
GEMINI_KEY = ""
BASE_URL = "https://api.deepseek.com"

INPUT_FOLDER = r""
OUTPUT_FOLDER = r""
PROMPT_FILE = ""
HISTORY_FILE = ""

# Model Config
CURRENT_PROVIDER = "deepseek"
MODEL_NAME = "deepseek-chat"
TEMPERATURE = 0.1
MAX_OUTPUT_TOKENS = 8000
SAFE_CHUNK_SIZE = 6000

# Pricing Config
PRICE_INPUT_MISS = 2.0
PRICE_INPUT_HIT = 0.2
PRICE_OUTPUT = 3.0
# ===========================================

client = None
gemini_client = None
enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text):
    return len(enc.encode(text))


def load_system_prompt():
    if not os.path.exists(PROMPT_FILE):
        return None
    with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
        return f.read()


# --- History Management ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_record(filename, stats, cost):
    current_history = load_history()
    current_history[filename] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cost_cny": round(cost, 4),
        "tokens": stats
    }
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_history, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # --- Progress Management ---


def get_progress_file(output_folder, filename):
    temp_dir = os.path.join(output_folder, ".temp_progress")
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    return os.path.join(temp_dir, f"{filename}.progress.json")


def load_progress(progress_file, source_size):
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get("source_size") == source_size:
                    return data
        except:
            pass
    return None


def save_progress(progress_file, source_size, chunks_data, stats):
    data = {
        "source_size": source_size,
        "updated_at": str(datetime.now()),
        "processed_chunks": chunks_data,
        "current_stats": stats
    }
    try:
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except:
        pass


def delete_progress(progress_file):
    if os.path.exists(progress_file):
        try:
            os.remove(progress_file)
        except:
            pass


# -------------------

def smart_split_text(text, max_token_limit, logger=None):
    total_tokens = count_tokens(text)
    if total_tokens <= max_token_limit:
        return [text]

    if logger: logger(f"   -> 文件过长 ({total_tokens} tokens), 切分中...")
    chunks, current_chunk, current_length = [], [], 0
    paragraphs = text.split('\n\n')

    for para in paragraphs:
        para_tokens = count_tokens(para)
        if para_tokens > max_token_limit:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk, current_length = [], 0
            chunks.append(para)
            continue

        if current_length + para_tokens + 20 > max_token_limit:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_length = para_tokens
        else:
            current_chunk.append(para)
            current_length += para_tokens

    if current_chunk: chunks.append("\n\n".join(current_chunk))
    if logger: logger(f"   -> 切分成 {len(chunks)} 块")
    return chunks


def clean_chunk_with_llm(chunk_text, system_prompt, chunk_index, total_chunks, logger=None):
    """清洗单个片段，包含重试逻辑"""
    global client, gemini_client, MODEL_NAME, CURRENT_PROVIDER

    ds_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": chunk_text}
    ]

    retries = 3
    for attempt in range(retries):
        try:
            # 仅使用 logger，严禁 print
            msg = f"      [Chunk {chunk_index + 1}/{total_chunks}] (Try {attempt + 1}/{retries}) Requesting ({CURRENT_PROVIDER})..."
            if logger: logger(msg)

            start_time = time.time()
            content = ""
            input_tokens = 0;
            output_tokens = 0;
            cache_hit = 0;
            cache_miss = 0;
            total_tokens_usage = 0

            # --- Provider Branch ---
            if CURRENT_PROVIDER == "gemini":
                if not HAS_GENAI: raise ImportError("Module 'google-genai' not found.")
                if not gemini_client: raise ValueError("Gemini Client not initialized")

                # Gemini 调用
                response = gemini_client.models.generate_content(
                    model=MODEL_NAME,
                    contents=chunk_text,
                    config=types.GenerateContentConfig(
                        temperature=TEMPERATURE,
                        system_instruction=system_prompt
                    )
                )
                content = response.text
                if response.usage_metadata:
                    input_tokens = response.usage_metadata.prompt_token_count
                    output_tokens = response.usage_metadata.candidates_token_count
                    total_tokens_usage = response.usage_metadata.total_token_count
                    cache_miss = input_tokens

            else:  # DeepSeek
                if not client: raise ValueError("DeepSeek Client not initialized")
                response = client.chat.completions.create(
                    model=MODEL_NAME, messages=ds_messages,
                    temperature=TEMPERATURE, stream=False, max_tokens=MAX_OUTPUT_TOKENS
                )
                content = response.choices[0].message.content
                usage_dict = response.usage.model_dump()
                input_tokens = usage_dict.get('prompt_tokens', 0)
                output_tokens = usage_dict.get('completion_tokens', 0)
                cache_hit = usage_dict.get('prompt_cache_hit_tokens', 0)
                cache_miss = usage_dict.get('prompt_cache_miss_tokens', input_tokens)
                total_tokens_usage = usage_dict.get('total_tokens', 0)

            duration = time.time() - start_time

            # Skip Logic
            if content and "<<<SKIP_REF_CHUNK>>>" in content:
                log_res = f" ⏭️ (Skipped) | In: {input_tokens} | Out: 0"
                if logger: logger(log_res)
                return "", {'hit': cache_hit, 'miss': cache_miss, 'output': 0, 'total': total_tokens_usage}

            if output_tokens == 0 and (not content or not content.strip()):
                if not content: raise ValueError("Empty content returned")

            success_res = f" ✅ ({duration:.1f}s) | In: {input_tokens} | Out: {output_tokens}"
            if logger: logger(success_res)

            return content, {'hit': cache_hit, 'miss': cache_miss, 'output': output_tokens, 'total': total_tokens_usage}

        except Exception as e:
            if logger: logger(f"\n      ⚠️ Request Error: {e}")
            if attempt < retries - 1:
                time.sleep(5)
            else:
                if logger: logger("      ❌ Max retries reached.")

    return None, None


def calculate_cost(stats):
    # [修改] 如果是 Gemini，费用记为 0
    if CURRENT_PROVIDER == "gemini":
        return 0.0

    cost = (stats['miss'] * PRICE_INPUT_MISS +
            stats['hit'] * PRICE_INPUT_HIT +
            stats['output'] * PRICE_OUTPUT) / 1_000_000
    return cost


def main(gui_key=None, gui_input=None, gui_output=None, gui_prompt_file=None,
         signal_callback=None, gui_gemini_key=None, gui_model="deepseek-chat"):
    global API_KEY, GEMINI_KEY, INPUT_FOLDER, OUTPUT_FOLDER, PROMPT_FILE, HISTORY_FILE
    global client, gemini_client, MODEL_NAME, CURRENT_PROVIDER

    # Logger Wrapper
    def log_msg(text):
        if signal_callback:
            try:
                signal_callback({"type": "log", "msg": text})
            except:
                pass

    def update_chunk_details(filename, chunks_status):
        if signal_callback:
            signal_callback({"type": "chunk_update", "file": filename, "chunks": chunks_status})

    # 1. Receive Params
    if gui_key: API_KEY = gui_key
    if gui_gemini_key: GEMINI_KEY = gui_gemini_key
    if gui_input: INPUT_FOLDER = gui_input
    if gui_output: OUTPUT_FOLDER = gui_output
    if gui_prompt_file: PROMPT_FILE = gui_prompt_file

    # 2. Determine Model
    MODEL_NAME = gui_model
    if "gemini" in MODEL_NAME.lower():
        CURRENT_PROVIDER = "gemini"
    else:
        CURRENT_PROVIDER = "deepseek"

    HISTORY_FILE = os.path.join(OUTPUT_FOLDER, "cleaning_history.json")
    if not os.path.exists(OUTPUT_FOLDER): os.makedirs(OUTPUT_FOLDER)

    # 3. Init Clients
    if CURRENT_PROVIDER == "deepseek":
        if not API_KEY:
            log_msg("❌ Error: DeepSeek API Key missing")
            return
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        log_msg(f"🔮 Mode: DeepSeek ({MODEL_NAME})")

    elif CURRENT_PROVIDER == "gemini":
        if not HAS_GENAI:
            log_msg("❌ Error: Module 'google-genai' not found.")
            return
        if not GEMINI_KEY:
            log_msg("❌ Error: Gemini API Key missing")
            return
        gemini_client = genai.Client(api_key=GEMINI_KEY)
        log_msg(f"✨ Mode: Google Gemini ({MODEL_NAME})")

    system_prompt = load_system_prompt()
    if not system_prompt:
        log_msg("❌ Error: Prompt file empty or not found")
        return

    history_data = load_history()
    log_msg(f"📚 读取历史记录, 包含 {len(history_data)} 个文件.")

    md_files = glob.glob(os.path.join(INPUT_FOLDER, "*.md"))
    log_msg(f"📂 已扫描 {len(md_files)} 个文件待处理\n")

    if signal_callback:
        signal_callback({
            "type": "scan_result",
            "files": [os.path.basename(f) for f in md_files],
            "mode": "clean"
        })

    session_cost = 0.0

    for file_path in md_files:
        if getattr(sys.modules[__name__], 'abort_flag', False):
            log_msg(">>> 🛑 检测到停止信号，正在安全退出...")
            break

        file_name = os.path.basename(file_path)
        output_path = os.path.join(OUTPUT_FOLDER, file_name)

        if file_name in history_data:
            old_stats = history_data[file_name].get("tokens", {'total': 0})
            old_cost = history_data[file_name].get("cost_cny", 0)
            remark = f"{old_stats.get('total', 0)} Tk (¥{old_cost})"
            if signal_callback:
                signal_callback({"type": "file_skip", "file": file_name, "msg": "已完成", "remark": remark})
            log_msg(f"⏭️  [已记录] 跳过: {file_name}")
            continue

        if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
            if signal_callback:
                signal_callback({"type": "file_skip", "file": file_name, "msg": "已存在"})
            log_msg(f"⏭️  [文件已存在] 跳过: {file_name}")
            continue

        log_msg(f"🔄 处理: {file_name}")
        if signal_callback:
            signal_callback({"type": "file_start", "file": file_name})

        try:
            file_size = os.path.getsize(file_path)
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()
            chunks = smart_split_text(raw_text, SAFE_CHUNK_SIZE, logger=log_msg)

            chunks_status = [{
                "id": i + 1,
                "status": 0,
                "msg": "等待中",
                "in_tok": 0,
                "out_tok": 0,
                "content": ""
            } for i in range(len(chunks))]
            update_chunk_details(file_name, chunks_status)

            progress_file = get_progress_file(OUTPUT_FOLDER, file_name)
            progress_data = load_progress(progress_file, file_size)

            final_content = []
            file_stats = {'hit': 0, 'miss': 0, 'output': 0, 'total': 0}
            start_index = 0

            if progress_data:
                final_content = progress_data.get("processed_chunks", [])
                file_stats = progress_data.get("current_stats", file_stats)
                start_index = len(final_content)
                if start_index > 0:
                    log_msg(f"   ⏩ 检测到上次进度，从第 {start_index + 1} 个片段继续...")
                    for i in range(start_index):
                        chunks_status[i]["status"] = 2
                        chunks_status[i]["msg"] = "已从缓存加载"
                        if i < len(final_content):
                            chunks_status[i]["content"] = final_content[i]
                    update_chunk_details(file_name, chunks_status)

            all_success = True
            for i in range(start_index, len(chunks)):
                if getattr(sys.modules[__name__], 'abort_flag', False):
                    log_msg(">>> 🛑 停止中，已保存当前进度...")
                    all_success = False
                    break

                chunk = chunks[i]
                chunks_status[i]["status"] = 1
                chunks_status[i]["msg"] = "清洗中..."
                update_chunk_details(file_name, chunks_status)

                cleaned_text, usage = clean_chunk_with_llm(chunk, system_prompt, i, len(chunks), logger=log_msg)

                if usage is not None:
                    if cleaned_text: final_content.append(cleaned_text)
                    file_stats['hit'] += usage['hit']
                    file_stats['miss'] += usage['miss']
                    file_stats['output'] += usage['output']
                    file_stats['total'] += usage['total']

                    save_progress(progress_file, file_size, final_content, file_stats)

                    chunks_status[i]["status"] = 2
                    chunks_status[i]["msg"] = "成功"
                    chunks_status[i]["in_tok"] = usage['miss']  # 或 usage['hit'] + usage['miss']
                    chunks_status[i]["out_tok"] = usage['output']
                    chunks_status[i]["content"] = cleaned_text  # 实时回显内容

                    update_chunk_details(file_name, chunks_status)

                    current_cost = calculate_cost(file_stats)
                    if CURRENT_PROVIDER == "gemini":
                        remark_str = f"{file_stats['total']} Tokens"
                    else:
                        remark_str = f"{file_stats['total']} Tk (¥{current_cost:.2f})"

                    if signal_callback:
                        signal_callback({"type": "file_update", "file": file_name, "remark": remark_str})
                else:
                    all_success = False
                    log_msg(f"   ❌ 片段 {i + 1} 最终失败。")
                    chunks_status[i]["status"] = 3
                    chunks_status[i]["msg"] = "失败"
                    update_chunk_details(file_name, chunks_status)
                    break

            if all_success and len(final_content) <= len(chunks):
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write("\n\n".join(final_content))

                cost = calculate_cost(file_stats)
                session_cost += cost
                save_record(file_name, file_stats, cost)
                delete_progress(progress_file)

                if CURRENT_PROVIDER == "gemini":
                    final_remark = f"{file_stats['total']} Tokens"
                    log_msg(f"   💰 费用: -- | 总Token: {file_stats['total']}")
                else:
                    final_remark = f"{file_stats['total']} Tk (¥{cost:.2f})"
                    log_msg(f"   💰 费用: ¥{cost:.4f} | 总Token: {file_stats['total']}")

                log_msg(f"   💾 处理完成")
                log_msg("-" * 50)

                if signal_callback:
                    signal_callback({"type": "file_done", "file": file_name, "remark": final_remark})
            else:
                if not getattr(sys.modules[__name__], 'abort_flag', False):
                    log_msg(f"   ⚠️ 当前文件未全部完成 (进度已保存)")
                    if signal_callback:
                        signal_callback({"type": "file_error", "file": file_name, "msg": "未完成"})

        except Exception as e:
            log_msg(f"❌ 严重错误: {e}")
            if signal_callback:
                signal_callback({"type": "file_error", "file": file_name, "msg": str(e)})

    log_msg(f"\n🎉 本次运行结束！新增花费: ¥{session_cost:.4f}")


def run_from_gui(api_key, input_folder, output_folder, prompt_file, gemini_key, model, signal_callback=None):
    main(api_key, input_folder, output_folder, prompt_file, signal_callback, gemini_key, model)


if __name__ == "__main__":
    main()