import shutil
import hashlib
import re
import json
import urllib.parse
from pathlib import Path
import requests
import difflib
import sys
import time
import fitz
from openai import OpenAI

API_KEY = ""  # <--- 请在这里填入你的 DeepSeek API Key
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
# ==========================================
# 1. 基础工具函数
# ==========================================

def get_file_md5(file_path):
    md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                md5.update(chunk)
        return md5.hexdigest()
    except Exception:
        return "error_hash"


def clean_title_text(text):
    if not text: return "Unknown"
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    text = re.sub(r'sub(\d+)sub', r'\1', text, flags=re.IGNORECASE)
    text = re.sub(r'sup([\+\-])sup', r'\1', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'([a-zA-Z])\s+(\d)', r'\1\2', text)
    text = re.sub(r'(Li)\s+(\+)', r'\1\2', text)
    text = text.replace("\n", " ").replace("\r", "")
    return text.strip()


def clean_filename(text):
    if not text: return "Unknown"
    text = str(text).replace('\n', ' ').replace('\r', '')
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = re.sub(r'\s+', " ", text).strip()
    text = text.rstrip(".")
    return text


def is_chinese_text(text):
    if not text: return False
    # 统计中文字符
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    total_len = len(text)

    # 策略 1: 绝对数量。如果前几页提取出了超过 50 个中文字，基本就是中文文献
    if len(chinese_chars) > 50:
        return True

    # 策略 2: 密度。如果总字数不多（可能是图片型PDF提取出的乱码），但中文占比高
    # 移除空格和常见标点干扰
    clean_t = re.sub(r'\s+', '', text)
    if len(clean_t) > 10 and (len(chinese_chars) / len(clean_t)) > 0.2:
        return True

    return False


# ==========================================
# 2. DOI 识别逻辑
# ==========================================

def determine_article_type(title, first_page_text, metadata=None):
    title_lower = title.lower() if title else ""
    text_sample = first_page_text[:3000].lower() if first_page_text else ""
    if metadata:
        journal_lower = str(metadata.get('journal', '')).lower()
        if 'review' in journal_lower:
            return "Review"
    review_keywords_title = ["review", "progress in", "overview", "perspective", "recent advances", "summary"]
    review_keywords_text = ["review article", "minireview", "mini-review", "in this review", "this review summarizes",
                            "comprehensive review", "This review", "this review"]
    is_crs_review = False
    if metadata:
        # Crossref 类型通常是 'journal-article', 'review-article' 等
        if 'review' in str(metadata.get('crs_type', '')).lower():
            is_crs_review = True

    has_text_keyword = False
    # 检查标题
    if 'review' in title_lower: has_text_keyword = True
    for kw in review_keywords_title:
        if kw in title_lower:
            has_text_keyword = True
            break
    # 检查正文
    if not has_text_keyword:
        for kw in review_keywords_text:
            if kw in text_sample:
                has_text_keyword = True
                break

    # 最终逻辑：只要有一个满足即可
    if is_crs_review or has_text_keyword:
        return "Review"

    return "Research"


def clean_doi_string(doi_raw):
    if not doi_raw: return None
    # 移除常见的 URL 前缀
    doi = re.sub(r'https?://(dx\.)?doi\.org/', '', doi_raw, flags=re.IGNORECASE)
    doi = doi.replace("DOI:", "").replace("doi:", "").strip()

    # 修复 PDF 提取时常见的 DOI 中间出现空格的问题
    doi = re.sub(r'\s+/', '/', doi)
    doi = re.sub(r'/\s+', '/', doi)

    # 处理 Science Advances 等特殊情况
    if "sciadv." in doi and "10.1126" not in doi:
        doi = "10.1126/" + doi

    # 清理尾部标点
    doi = doi.rstrip('.').rstrip(',').rstrip(';').rstrip('-')

    # 提取标准 DOI 格式
    match = re.search(r'(10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+)', doi)
    return match.group(1) if match else doi


def match_doi_pattern(text):
    # 策略1: 允许 DOI 中间有空格
    pattern_loose = r'(?:^|[^0-9])(10\.\d{4,9}\s*/\s*[-._;()/:a-zA-Z0-9]+)'
    # 策略2: URL 模式
    pattern_url = r'doi\.org/(10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+)'

    matches = re.findall(pattern_loose, text) + re.findall(pattern_url, text)
    valid_dois = []
    for m in matches:
        # 移除匹配到的字符串中的空格和换行，还原 DOI
        clean_m = m.replace(" ", "").replace("\n", "").replace("\r", "")
        doi = clean_doi_string(clean_m)
        # 排除日期格式误判 (e.g. 10.10.2023) 且确保包含斜杠
        if doi and "/" in doi and len(doi) > 7 and not re.match(r'^\d{2}\.\d{2}\.\d{4}', doi):
            valid_dois.append(doi)

    return list(dict.fromkeys(valid_dois)) if valid_dois else []


def extract_doi_with_strategies(text):
    if not text: return []
    candidates = []
    # 策略 1: 原文
    res1 = match_doi_pattern(text)
    if res1: candidates.extend(res1)
    # 策略 2: 去除换行
    res2 = match_doi_pattern(text.replace('\n', '').replace('\r', ''))
    if res2: candidates.extend(res2)

    # 去重并保持顺序
    return list(dict.fromkeys(candidates))

def extract_dois_from_pdf_links(doc):
    try:
        # 遍历前 3 页的超链接
        for i in range(min(3, len(doc))):
            page = doc[i]
            links = page.get_links()
            for link in links:
                uri = link.get("uri", "")
                if "doi.org" in uri or "10." in uri:
                    doi_list = match_doi_pattern(uri)
                    # 取列表第一个元素
                    if doi_list: return doi_list[0]
    except:
        pass
    return None


def infer_doi_from_filename(filename):
    filename = str(filename).lower()

    # --- 策略 1: 修复用 @ 替换 / 的情况
    normalized_name = filename.replace("@", "/")

    # --- 策略 2: 匹配标准 DOI ---
    match_doi = re.search(r'(10\.\d{4,9}/[-._;()/:a-z0-9]+)', normalized_name)
    if match_doi:
        # 清理一下匹配结果，防止末尾带上 .pdf 等后缀
        doi = match_doi.group(1)
        # 移除末尾多余的标点
        doi = doi.rstrip('.').rstrip('_').rstrip('-')
        return doi

    # --- 策略 3: 匹配 Science/Nature 特殊格式 ---
    match_sci = re.search(r'(sciadv\.[a-z0-9]+)', filename)
    if match_sci: return f"10.1126/{match_sci.group(1)}"

    match_nat = re.search(r'(s\d{5}-\d{3}-\d{5}-\w)', filename)
    if match_nat: return f"10.1038/{match_nat.group(1)}"

    # --- 策略 4: 匹配 Elsevier PII 格式 (解决 1-s2.0-S... 文件) ---
    if "1-s2.0-" in filename:
        # 尝试提取 S 开头的一串
        match_pii = re.search(r'(s\d{4}-?\d{3,4}[\(\d\)]?[\d\w\-]*)', filename)
        if match_pii:
            pii_raw = match_pii.group(1)
            # 这是一个强行尝试，大部分 Elsevier PII 对应的 DOI 就是 10.1016/PII
            return f"10.1016/{pii_raw}"

    return None


def extract_metadata_from_pdf_properties(doc):
    try:
        meta = doc.metadata
        if not meta: return None

        # 检查 Subject 和 Keywords
        subject = meta.get('subject', '')
        keywords = meta.get('keywords', '')

        combined = f"{subject} {keywords}"
        if '10.' in combined:
            doi_list = match_doi_pattern(combined)
            # 取列表第一个元素
            if doi_list: return ('doi', doi_list[0])

        title = meta.get('title', '')
        if title and len(title) > 20 and 'untitled' not in title.lower():
            if not any(x in title.lower() for x in ['microsoft', 'word', 'latex', 'pdf']):
                return ('title', title)
    except:
        pass
    return None


# ==========================================
# 3. 网络请求与 PDF 处理
# ==========================================

def get_first_author(data):
    author_list = data.get('author', [])
    first_author = "Unknown"
    if author_list:
        for auth in author_list:
            if auth.get('sequence') == 'first':
                first_author = auth.get('family', 'Unknown')
                break
        if first_author == "Unknown" and len(author_list) > 0:
            first_author = author_list[0].get('family', 'Unknown')
    return first_author


def fetch_metadata_from_crossref(doi, proxies=None, logger=None):
    if not doi: return None
    doi = clean_doi_string(doi)
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
    try:
        resp = requests.get(url, headers={'User-Agent': 'RenamerBot/9.0'}, proxies=proxies, timeout=5)
        if resp.status_code == 200:
            data = resp.json()['message']
            title = clean_title_text(data.get('title', ["NoTitle"])[0])
            journal_list = data.get('short-container-title', [])
            if not journal_list: journal_list = data.get('container-title', ["NoJournal"])
            journal = journal_list[0]
            issued = data.get('issued', {}).get('date-parts', [[0000]])
            year = str(issued[0][0]) if issued and issued[0] else "0000"
            author = get_first_author(data)
            volume = data.get('volume', '')
            issue = data.get('issue', '')
            doi_suffix = doi.split('/')[-1] if '/' in doi else doi
            publisher = data.get('publisher', 'UnknownPublisher')
            page = data.get('page', data.get('article-number', ''))
            issn_list = data.get('ISSN', [])
            issn = issn_list[0] if issn_list else ""
            crs_type = data.get('type', '')
            # ==============================

            return {
                "year": year, "journal": journal, "title": title, "doi": doi,
                "author": author, "volume": volume, "issue": issue, "doi_suffix": doi_suffix,
                # 新增字段
                "publisher": publisher, "page": page, "issn": issn, "crs_type": crs_type
            }
    except Exception as e:
        pass
    return None



def fetch_metadata_by_title_search(text, proxies=None, logger=None):
    if not text or len(text) < 10: return None
    noise = [
        "check for updates", "downloaded from", "university", "https://",
        "correspondence", "supplementary", "research article", "gdch",
        "international edition", "german edition", "how to cite",
        "wiley-vch", "doi.org", "angewandte", "chemie"
    ]
    lines = text.splitlines()
    clean_lines = []

    for line in lines:
        line = line.strip()
        # 忽略太短的行或纯数字/特殊符号行
        if len(line) < 10: continue
        # 忽略包含噪音词的行
        if any(n in line.lower() for n in noise): continue
        clean_lines.append(line)

    if not clean_lines: return None
    search_candidates = clean_lines[:10]
    query = " ".join(search_candidates)[:400]

    url = f"https://api.crossref.org/works?query.bibliographic={urllib.parse.quote(query)}&rows=1"
    try:
        resp = requests.get(url, headers={'User-Agent': 'RenamerBot/9.0'}, proxies=proxies, timeout=8)
        if resp.status_code == 200:
            items = resp.json().get('message', {}).get('items', [])
            if items:
                item = items[0]
                res_title = clean_title_text(item.get('title', [""])[0])

                # 比对逻辑：计算相似度
                check_t = re.sub(r'\W', '', res_title).lower()
                check_p = re.sub(r'\W', '', text[:3000]).lower()  # 扩大原文比对范围

                s = difflib.SequenceMatcher(None, check_t, check_p)
                match = s.find_longest_match(0, len(check_t), 0, len(check_p))

                # 只要标题的 40% 内容能在文中连续找到，就认为是匹配的
                if match.size > len(check_t) * 0.4:
                    journal = item.get('short-container-title', [item.get('container-title', ["NoJournal"])[0]])[0]
                    issued = item.get('issued', {}).get('date-parts', [[0000]])
                    year = str(issued[0][0]) if issued and issued[0] else "0000"
                    author = get_first_author(item)
                    return {
                        "year": year, "journal": journal, "title": res_title, "doi": item.get('DOI'),
                        "author": author, "volume": item.get('volume', ''), "issue": item.get('issue', ''),
                        "doi_suffix": item.get('DOI', '').split('/')[-1], "page": item.get('page', item.get('article-number', '')),
                        "publisher": item.get('publisher', ''),
                        "issn": item.get('ISSN', [''])[0] if item.get('ISSN') else "",
                        "crs_type": item.get('type', '')
                    }
    except:
        pass
    return None

    #通用引用搜索：处理 DeepSeek 返回的 PII 或 'Journal Vol Page' 字符串"""
def search_crossref_by_bibliographic_query(query_string, proxies=None, logger=None):
    if not query_string or len(query_string) < 5: return None
    url = f"https://api.crossref.org/works?query.bibliographic={urllib.parse.quote(query_string)}&rows=1"
    try:
        resp = requests.get(url, headers={'User-Agent': 'RenamerBot/9.0'}, proxies=proxies, timeout=8)
        if resp.status_code == 200:
            items = resp.json().get('message', {}).get('items', [])
            if items:
                item = items[0]
                # 提取标准元数据返回
                return {
                    "year": str(item.get('issued', {}).get('date-parts', [[0000]])[0][0]),
                    "journal": item.get('short-container-title', [item.get('container-title', ["NoJournal"])[0]])[0],
                    "title": clean_title_text(item.get('title', [""])[0]),
                    "doi": item.get('DOI'),
                    "author": get_first_author(item),
                    "volume": item.get('volume', ''), "issue": item.get('issue', ''),
                    "doi_suffix": item.get('DOI', '').split('/')[-1],
                    "page": item.get('page', item.get('article-number', '')),
                    "publisher": item.get('publisher', ''),
                    "issn": item.get('ISSN', [''])[0] if item.get('ISSN') else "",
                    "crs_type": item.get('type', '')
                }
    except:
        pass
    return None


def ask_deepseek_backup(text_sample, logger=None):
    if not API_KEY: return None
    content = text_sample[:3500]

    try:
        client = OpenAI(api_key=API_KEY, base_url=DEEPSEEK_BASE_URL)
        system_prompt = (
            "Analyze the academic paper text. Output ONE string strictly following this priority:\n"
            "1. DOI (e.g., '10.1016/j.ssi.1996.02.001')\n"
            "2. PII (e.g., 'S0167-2738(96)00000-0')\n"
            "3. Citation (e.g., 'Solid State Ionics 86-88 (1996) 49-54')\n"
            "Output ONLY the string. No explanations."
        )
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}],
            temperature=0.1, max_tokens=100
        )
        return response.choices[0].message.content.strip().replace("DOI:", "").strip()
    except Exception as e:
        if logger: logger(f"    -> [DeepSeek] Error: {e}")
    return None

def process_pdf(file_path, proxies, logger=None):
    doc = None
    try:
        # 打开 PDF
        doc = fitz.open(file_path)

        # 1. 提取文本前5页
        text_content = []
        # 遍历前 5 页
        for i in range(min(5, len(doc))):
            page_text = doc[i].get_text("text")
            if page_text:
                text_content.append(page_text)

        full_text_sample = "\n".join(text_content)

        # 2. 判断是否为中文文献
        if is_chinese_text(full_text_sample):
            if logger: logger("    -> 检测到中文内容，归类为中文文献")
            return "CHINESE_DOC", None

        # 3. 提取 DOI
        # (A) 从元数据
        doi = None
        prop_res = extract_metadata_from_pdf_properties(doc)
        if prop_res and prop_res[0] == 'doi': doi = prop_res[1]

        # (B) 从文本
        doi_candidates = []
        if not doi and full_text_sample:  # 这里的 doi 变量是指前面元数据提取的结果
            doi_candidates = extract_doi_with_strategies(full_text_sample)

        if doi:
            doi_candidates.insert(0, doi)
        # 逻辑：第1个失败 -> 找第2个 -> 失败/无第2个 -> 结束DOI流程
        target_dois = doi_candidates[:2]

        for d in target_dois:
            if logger: logger(f"    -> 尝试 DOI: {d} ...")
            meta_dict = fetch_metadata_from_crossref(d, proxies, logger)
            if meta_dict:
                return meta_dict, full_text_sample
            if logger: logger(f"    -> 查询失败，尝试下一个 (最多试2次)...")

        # (C) 从页面超链接 (PyMuPDF)
        if not doi:
            doi = extract_dois_from_pdf_links(doc)

        # 4. 联网查询
        if doi:
            if logger: logger(f"    -> 提取到 DOI: {doi}，正在获取详情...")
            meta_dict = fetch_metadata_from_crossref(doi, proxies, logger)
            if meta_dict:
                return meta_dict, full_text_sample

        # 5. 标题模糊反查 (如果没有 DOI)
        if full_text_sample:
            if logger: logger(f"    -> 尝试标题模糊反查...")
            # 这里的 fetch_metadata_by_title_search 需要使用我上一条回答中修复过的版本(搜索前10行)
            meta_dict = fetch_metadata_by_title_search(full_text_sample, proxies, logger)
            if meta_dict:
                return meta_dict, full_text_sample
        # 6. deepseek
        if full_text_sample and len(full_text_sample) > 200 and API_KEY:
            if logger: logger("    -> [DeepSeek] 启动智能兜底分析...")
            ds_result = ask_deepseek_backup(full_text_sample, logger)

            if ds_result:
                # 情况 A: 看起来像 DOI (包含 10.xxxx/xxxx)
                if "10." in ds_result and "/" in ds_result:
                    if logger: logger(f"    -> [DeepSeek] 识别到 DOI: {ds_result}")
                    meta_dict = fetch_metadata_from_crossref(ds_result, proxies, logger)
                    if meta_dict: return meta_dict, full_text_sample

                # 情况 B: 是 PII 或 引用字符串 -> 走通用 bibliographic 搜索
                else:
                    if logger: logger(f"    -> [DeepSeek] 识别到引用信息: {ds_result}")
                    meta_dict = search_crossref_by_bibliographic_query(ds_result, proxies, logger)
                    if meta_dict: return meta_dict, full_text_sample

    except Exception as e:
        if logger: logger(f"    -> PDF解析错误: {e}")
    finally:
        # 确保关闭文件句柄，防止文件被占用无法移动
        if doc:
            doc.close()

    return None, None

# ==========================================
# 4. 命名生成器
# ==========================================

def generate_custom_name(meta_dict, atype, format_str):
    raw_data = {
        "1": clean_filename(meta_dict['year']),
        "2": clean_filename(meta_dict['journal']),
        "3": clean_filename(meta_dict['title']),
        "4": clean_filename(meta_dict['author']),
        "5": atype,
        "6": clean_filename(meta_dict['volume']),
        "7": clean_filename(meta_dict['issue']),
        "8": clean_filename(meta_dict['page']),
        "9": clean_filename(meta_dict['doi_suffix']),
        "10": clean_filename(meta_dict['publisher']),
        "11": clean_filename(meta_dict['issn'])
    }
    data_map = {}
    for key, val in raw_data.items():
        if key == "3":
            data_map[key] = val
        else:
            data_map[key] = f"[{val}]" if val else ""
    # 3. 处理格式字符串
    if not format_str or not format_str.strip():
        format_str = "[1][2][5][3]"

    temp_format = format_str
    for key, val in data_map.items():
        if key != "3":
            temp_format = temp_format.replace(f"[{key}]", val)

    # 4. 处理标题长度限制
    current_len = len(temp_format)
    max_total_len = 180
    allowed_title_len = max_total_len - current_len + 3
    if allowed_title_len < 30: allowed_title_len = 30

    safe_title = data_map["3"]
    if len(safe_title) > allowed_title_len:
        safe_title = safe_title[:allowed_title_len].strip() + "..."

    # 5. 生成最终文件名
    final_name = temp_format.replace("[3]", safe_title)
    final_name = re.sub(r'\s+', ' ', final_name).strip()
    return final_name + ".pdf"

# ==========================================
# 5. 主函数
# ==========================================

def try_copy(src, dst, stats, seen_hashes, f_hash, logger=None):
    def log(msg):
        if logger:
            logger(msg)
        else:
            print(msg)

    try:
        shutil.copy2(src, dst)
        log(f"    -> 成功: {dst.name}")
        seen_hashes.add(f_hash)
    except Exception as e:
        log(f"    -> [错误] 复制失败: {e}")
        try:
            parent = dst.parent
            shutil.copy2(src, parent / "Safe_Name_Article.pdf")
            log("    -> [重试] 已保存为 Safe_Name_Article.pdf")
            seen_hashes.add(f_hash)
        except:
            stats["fail"] += 1


def save_history(path, hashes):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({"hashes": list(hashes)}, f)
    except:
        pass


def main(input_folder, output_folder, proxies, name_format=None, signal_callback=None):
    source_path = Path(input_folder)
    target_path = Path(output_folder)
    target_path.mkdir(parents=True, exist_ok=True)
    history_file = target_path / "processing_historyex.json"
    map_file = target_path / "doi_mapping.json"
    doi_map = {}
    if map_file.exists():
        try:
            with open(map_file, 'r', encoding='utf-8') as f:
                doi_map = json.load(f)
        except:
            pass

    # 定义安全的日志函数
    def log_msg(text):
        print(text)
        if signal_callback:
            try:
                signal_callback({"type": "log", "msg": text})
            except:
                pass

    try:
        seen_hashes = set()
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                seen_hashes = set(json.load(f).get("hashes", []))
        except:
            pass

        stats = {"total": 0, "success": 0, "fail": 0, "skip_hash": 0, "chinese": 0}
        # 1. 获取所有 PDF
        raw_files = list(source_path.rglob('*.pdf'))

        # 2. 按文件名去重 (保留路径最短的那个，通常是根目录的)
        unique_files = {}
        for p in raw_files:
            if p.name not in unique_files:
                unique_files[p.name] = p
            else:
                # 如果发现同名文件，保留路径更短的（偏向于保留主目录文件，忽略子目录备份）
                if len(str(p)) < len(str(unique_files[p.name])):
                    unique_files[p.name] = p

        # 3. 排序 (只处理去重后的列表)
        all_files = sorted(list(unique_files.values()), key=lambda p: p.name)

        log_msg(f"开始处理 {len(all_files)} 个文件...")
        log_msg(f"当前命名格式: {name_format if name_format else '默认 ([1][2][5][3])'}")

        if signal_callback:
            try:
                signal_callback({
                    "type": "scan_result",
                    "files": [f.name for f in all_files],
                    "mode": "normal"
                })
            except:
                pass

        for file_path in all_files:
            if getattr(sys.modules[__name__], 'abort_flag', False):
                log_msg(">>> 🛑 检测到停止信号...")
                break
            stats["total"] += 1
            log_msg(f"[{stats['total']}/{len(all_files)}] {file_path.name}")

            if signal_callback:
                try:
                    signal_callback({"type": "file_start", "file": file_path.name})
                except:
                    pass

            f_hash = get_file_md5(file_path)
            if f_hash in seen_hashes:
                log_msg("    -> 跳过 (已处理)")
                stats["skip_hash"] += 1
                if signal_callback:
                    try:
                        signal_callback({"type": "file_skip", "file": file_path.name, "msg": "已存在"})
                    except:
                        pass
                continue

            # 传递 log_msg 给 process_pdf 以便显示详细步骤
            meta_dict, first_page_txt = process_pdf(file_path, proxies, logger=log_msg)

            if meta_dict == "CHINESE_DOC":
                new_name = f"中文-{clean_filename(file_path.stem)}.pdf"
                stats["chinese"] += 1
                try_copy(file_path, target_path / new_name, stats, seen_hashes, f_hash, logger=log_msg)
                if signal_callback:
                    try:
                        signal_callback({"type": "file_done", "file": file_path.name, "remark": f"➜ {new_name}"})
                    except:
                        pass

            elif meta_dict:
                atype = determine_article_type(meta_dict['title'], first_page_txt, meta_dict)
                new_name = generate_custom_name(meta_dict, atype, name_format)
                if 'doi' in meta_dict:
                    doi_map[new_name] = meta_dict['doi']
                stats["success"] += 1
                try_copy(file_path, target_path / new_name, stats, seen_hashes, f_hash, logger=log_msg)
                if signal_callback:
                    try:
                        signal_callback({"type": "file_done", "file": file_path.name, "remark": f"➜ {new_name}"})
                    except:
                        pass

            else:
                log_msg("    -> [失败] 无法识别，复制原文件")
                try:
                    unid = target_path / "Unidentified"
                    unid.mkdir(exist_ok=True)
                    shutil.copy2(file_path, unid / f"Unidentified - {file_path.name}")
                    stats["fail"] += 1
                except:
                    pass
                if signal_callback:
                    try:
                        signal_callback({"type": "file_error", "file": file_path.name, "msg": "无法识别"})
                    except:
                        pass

            if stats["total"] % 1 == 0:
                save_history(history_file, seen_hashes)
                # === [新增修改 3] 定期保存 mapping ===
                try:
                    with open(map_file, 'w', encoding='utf-8') as f:
                        json.dump(doi_map, f, indent=4, ensure_ascii=False)
                except:
                    pass
                # ===================================

            save_history(history_file, seen_hashes)
            # 循环结束后最后保存一次
            try:
                with open(map_file, 'w', encoding='utf-8') as f:
                    json.dump(doi_map, f, indent=4, ensure_ascii=False)
            except:
                pass

        save_history(history_file, seen_hashes)
        log_msg("\n" + "=" * 50)
        log_msg(f"处理完成 | 总数: {stats['total']} | 成功: {stats['success']} | 失败: {stats['fail']}")

    except Exception as e:
        log_msg(f"❌ 严重错误: {e}")

def run_from_gui(input_folder, output_folder, name_format=None, api_key=None, signal_callback=None):
    global API_KEY
    API_KEY = api_key
    # ...
    main(input_folder, output_folder, None, name_format, signal_callback)


if __name__ == "__main__":
    input_dir = r"C:\Test\Input"
    output_dir = r"C:\Test\Output"
    main(input_dir, output_dir, None)