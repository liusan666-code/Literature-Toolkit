import shutil
import hashlib
import re
import json
import urllib.parse
from pathlib import Path
import requests
import difflib
import time
import os
import random
import logging
import subprocess
import sys
import glob
import collections
import math
import time
from pathlib import Path
from openai import OpenAI
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import gc
import fitz
import socket
import atexit
import psutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

try:
    from docx2pdf import convert
    import win32com.client

    HAS_DOCX_TOOLS = True
except ImportError:
    HAS_DOCX_TOOLS = False

# 全局变量存储当前 driver 的 PID
CURRENT_BROWSER_PID = None

def clean_up_chrome_on_exit():
    """程序退出时的保底清理"""
    if CURRENT_BROWSER_PID:
        try:
            proc = psutil.Process(CURRENT_BROWSER_PID)
            if proc.is_running():
                # 递归杀掉子进程
                for child in proc.children(recursive=True):
                    try: child.kill()
                    except: pass
                proc.kill()
        except:
            pass

atexit.register(clean_up_chrome_on_exit)
def find_free_port():
    """寻找一个系统当前的空闲端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]

def clear_lock_files(user_data_dir):
    """只删除 Chrome 的锁文件，保留 Cookies 和登录状态"""
    if not os.path.exists(user_data_dir): return
    # Chrome 典型的锁文件列表
    locks = ["Lockfile", "SingletonLock", "SingletonSocket", "SingletonCookie"]
    for lock_name in locks:
        target = os.path.join(user_data_dir, lock_name)
        if os.path.exists(target):
            try:
                os.remove(target)
                print(f"    -> [清理] 已移除锁文件: {lock_name}")
            except Exception as e:
                pass
API_KEY = ""
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


def clean_filename(text, max_len=100):
    if not text: return "Unknown"
    text = str(text).replace('\n', ' ').replace('\r', '')
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = re.sub(r'\s+', " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].strip()
    text = text.rstrip(".")
    return text


def is_chinese_text(text):
    if not text: return False
    return len(re.findall(r'[\u4e00-\u9fff]', text)) > 10


def format_size(size_bytes):
    """将字节转换为易读格式"""
    if size_bytes == 0: return "0B"
    size_name = ("B", "KB", "MB", "GB")
    i = 0
    while size_bytes >= 1024 and i < len(size_name) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f}{size_name[i]}"

# ==========================================
# 2. 核心逻辑
# ==========================================

def clean_title_text(text):
    if not text: return "Unknown"
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace("\n", " ").replace("\r", "")
    return text.strip()

def clean_doi_string(doi_raw):
    if not doi_raw: return None
    doi = re.sub(r'https?://(dx\.)?doi\.org/', '', doi_raw, flags=re.IGNORECASE)
    doi = doi.replace("DOI:", "").replace("doi:", "").strip()
    doi = re.sub(r'\s+/', '/', doi) # 修复空格
    if "sciadv." in doi and "10.1126" not in doi: doi = "10.1126/" + doi
    doi = doi.rstrip('.').rstrip(',').rstrip(';').rstrip('-')
    match = re.search(r'(10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+)', doi)
    return match.group(1) if match else doi

def match_doi_pattern(text):
    pattern_loose = r'(?:^|[^0-9])(10\.\d{4,9}\s*/\s*[-._;()/:a-zA-Z0-9]+)'
    pattern_url = r'doi\.org/(10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+)'
    matches = re.findall(pattern_loose, text) + re.findall(pattern_url, text)
    valid_dois = []
    for m in matches:
        clean_m = m.replace(" ", "").replace("\n", "").replace("\r", "")
        doi = clean_doi_string(clean_m)
        if doi and "/" in doi and len(doi) > 7 and not re.match(r'^\d{2}\.\d{2}\.\d{4}', doi):
            valid_dois.append(doi)
    return list(dict.fromkeys(valid_dois)) if valid_dois else []

def infer_doi_from_filename(filename):
    filename = str(filename).lower()
    normalized_name = filename.replace("@", "/")
    match_doi = re.search(r'(10\.\d{4,9}/[-._;()/:a-z0-9]+)', normalized_name)
    if match_doi: return match_doi.group(1).rstrip('.')
    match_sci = re.search(r'(sciadv\.[a-z0-9]+)', filename)
    if match_sci: return f"10.1126/{match_sci.group(1)}"
    match_nat = re.search(r'(s\d{5}-\d{3}-\d{5}-\w)', filename)
    if match_nat: return f"10.1038/{match_nat.group(1)}"
    return None

def extract_metadata_from_pdf_properties(doc):
    try:
        meta = doc.metadata
        if not meta: return None
        subject = meta.get('subject', '')
        keywords = meta.get('keywords', '')
        combined = f"{subject} {keywords}"
        if '10.' in combined:
            doi = match_doi_pattern(combined)
            if doi: return ('doi', doi[0])
        title = meta.get('title', '')
        if title and len(title) > 20 and 'untitled' not in title.lower():
             return ('title', title)
    except: pass
    return None

def extract_dois_from_pdf_links(doc):
    try:
        for i in range(min(3, len(doc))):
            page = doc[i]
            for link in page.get_links():
                uri = link.get("uri", "")
                if "doi.org" in uri or "10." in uri:
                    doi_list = match_doi_pattern(uri)
                    if doi_list: return doi_list[0]
    except: pass
    return None

def get_first_author(data):
    author_list = data.get('author', [])
    if author_list:
        return author_list[0].get('family', 'Unknown')
    return "Unknown"

def fetch_metadata_from_crossref(doi, proxies=None, logger=None):
    if not doi: return None
    doi = clean_doi_string(doi)
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
    try:
        resp = requests.get(url, headers={'User-Agent': 'RenamerBot/9.0'}, proxies=proxies, timeout=5)
        if resp.status_code == 200:
            data = resp.json()['message']
            title = clean_title_text(data.get('title', ["NoTitle"])[0])
            journal = data.get('short-container-title', [data.get('container-title', ["NoJournal"])[0]])[0]
            issued = data.get('issued', {}).get('date-parts', [[0000]])
            year = str(issued[0][0]) if issued and issued[0] else "0000"
            return {"year": year, "journal": journal, "title": title, "doi": doi, "author": get_first_author(data)}
    except: pass
    return None

def fetch_metadata_by_title_search(text, proxies=None, logger=None):
    if not text or len(text) < 10: return None
    clean_lines = [line.strip() for line in text.splitlines() if len(line) > 10][:10]
    if not clean_lines: return None
    query = " ".join(clean_lines)[:400]
    url = f"https://api.crossref.org/works?query.bibliographic={urllib.parse.quote(query)}&rows=1"
    try:
        resp = requests.get(url, headers={'User-Agent': 'RenamerBot/9.0'}, proxies=proxies, timeout=8)
        if resp.status_code == 200:
            items = resp.json().get('message', {}).get('items', [])
            if items:
                item = items[0]
                res_title = clean_title_text(item.get('title', [""])[0])
                check_t = re.sub(r'\W', '', res_title).lower()
                check_p = re.sub(r'\W', '', text[:3000]).lower()
                s = difflib.SequenceMatcher(None, check_t, check_p)
                if s.find_longest_match(0, len(check_t), 0, len(check_p)).size > len(check_t) * 0.4:
                    return {
                        "year": str(item.get('issued', {}).get('date-parts', [[0000]])[0][0]),
                        "journal": item.get('short-container-title', [item.get('container-title', ["NoJournal"])[0]])[0],
                        "title": res_title, "doi": item.get('DOI'), "author": get_first_author(item)
                    }
    except: pass
    return None

def ask_deepseek_backup(text_sample, logger=None):
    if not API_KEY: return None
    content = text_sample[:3500]
    try:
        client = OpenAI(api_key=API_KEY, base_url=DEEPSEEK_BASE_URL)
        system_prompt = "Analyze the academic paper text. Output ONE string: 1. DOI (e.g. 10.1016/...) or 2. Citation string. Output ONLY the string."
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}],
            temperature=0.1, max_tokens=100
        )
        return response.choices[0].message.content.strip().replace("DOI:", "").strip()
    except Exception as e:
        if logger: logger(f"    -> [DeepSeek] Error: {e}")
    return None

# ==========================================
# 3. SI 抓取模块
# ==========================================
class SIFetcher:
    def __init__(self, proxies=None, user_data_dir=None, logger=None):
        self.proxies = proxies
        self.logger = logger

        # 1. 严格保留你原来的 UserData 逻辑
        if user_data_dir:
            self.user_data_dir = str(Path(user_data_dir).absolute())
        else:
            # 默认在当前目录下创建 ChromeDevData，保存你的所有登录信息
            self.user_data_dir = str((Path(os.getcwd()) / "ChromeDevData").absolute())

        if not os.path.exists(self.user_data_dir):
            os.makedirs(self.user_data_dir)

        self.si_keywords = ['supporting information', 'supplementary material', 'electronic supplementary',
                            'suppl', 'data availability', 'esm', 'extended data', 'additional file', 'mmc', 'multimedia']
        self.blacklist = ['rightslink', 'copyright', 'citation', 'help', 'feedback', 'cookie', 'policy', 'reprints',
                          'full text', 'abstract', 'browse', 'search', 'register', 'login', 'next', 'prev']

        self.temp_download_dir = Path(os.getcwd()) / "temp_si_cache"
        self.temp_download_dir.mkdir(parents=True, exist_ok=True)
        self.driver = None

    def log(self, msg):
        print(msg)
        if self.logger:
            self.logger(msg)

    def _init_browser(self):
        """
        使用 undetected_chromedriver 启动，并强制注入静默下载策略
        """
        try:
            # 配置 UC 选项
            os.environ['NO_PROXY'] = 'localhost,127.0.0.1,::1'
            os.environ['no_proxy'] = 'localhost,127.0.0.1,::1'

            options = uc.ChromeOptions()
            options.add_argument("--window-size=600,600")
            options.add_argument("--no-first-run")

            # 【增强版偏好设置】
            # 试图全方位覆盖“询问保存位置”的设置
            prefs = {
                "download.default_directory": str(self.temp_download_dir.absolute()),
                "download.prompt_for_download": False,  # 关键：禁止弹窗
                "download.directory_upgrade": True,
                "safebrowsing.enabled": False,  # 关键：关闭安全浏览检查
                "safebrowsing.disable_download_protection": True,
                "plugins.always_open_pdf_externally": True,  # 强制下载PDF而不是预览
                "profile.default_content_settings.popups": 0,
                "profile.content_settings.exceptions.automatic_downloads.*.setting": 1
            }
            options.add_experimental_option("prefs", prefs)
            free_port = find_free_port()

            # 启动 UC
            self.driver = uc.Chrome(
                options=options,
                user_data_dir=self.user_data_dir,
                use_subprocess=True,
                port=free_port  # [关键修改 2] 指定端口，避开 9343 冲突
            )

            # [关键修改 3] 记录 PID，用于后续精准查杀
            try:
                self.browser_pid = self.driver.browser_pid
            except:
                try:
                    self.browser_pid = self.driver.service.process.pid
                except:
                    self.browser_pid = None
            # 【核心修复代码】启动后，使用 CDP 协议“暴力”重置下载行为
            # 这一步能解决 99% 因加载 UserData 导致的弹窗问题
            try:
                self.driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                    "behavior": "allow",
                    "downloadPath": str(self.temp_download_dir.absolute())
                })
            except Exception as e:
                self.log(f"    -> [警告] CDP 下载配置失败: {e}")

            # 调整窗口位置到右上角
            self._enforce_window_layout()

            self.driver.set_page_load_timeout(180)
            return True
        except Exception as e:
            self.log(f"    -> [启动失败] {e}")
            err_str = str(e).lower()

            if "expecting value" in err_str or \
                    "session not created" in err_str or \
                    "cannot connect to chrome" in err_str or \
                    "user data directory is already in use" in err_str:

                self.log(f"    -> [自动修复] 检测到环境锁定，执行非破坏性清理...")

                # 1. 尝试杀掉残留的 Chrome 进程 (Windows)
                try:
                    os.system("taskkill /F /IM chrome.exe /T >nul 2>&1")
                except:
                    pass

                # 2. 仅删除锁文件 (保留 Cookies 登录状态)
                clear_lock_files(self.user_data_dir)

                self.log(f"    -> [修复完成] 已释放锁，将在下次循环重试...")

            return False

    def _enforce_window_layout(self):
        try:
            target_w = 600
            target_h = 600
            target_x = 0  # 默认兜底值

            try:
                import ctypes
                user32 = ctypes.windll.user32
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(2)
                except:
                    pass
                screen_width = user32.GetSystemMetrics(0)  # 0 代表宽度

            except:
                pass  # 如果获取失败（非Windows环境等），保持默认 1200

            self.driver.set_window_rect(x=target_x, y=0, width=target_w, height=target_h)
        except:
            pass

    def reset_browser(self):
        self.close()
        time.sleep(2)
        return self._init_browser()

    def close(self):
        if self.driver:
            # 1. 获取进程 ID (PID)，用于后续强制查杀
            try:
                # undetected_chromedriver 通常有 .browser_pid 或 .service.process.pid
                pid = None
                if hasattr(self.driver, 'browser_pid'):
                    pid = self.driver.browser_pid
                elif hasattr(self.driver, 'service') and self.driver.service.process:
                    pid = self.driver.service.process.pid
            except:
                pid = None

            # 2. 尝试正常关闭
            try:
                self.driver.quit()
            except:
                pass

            # 3. [核心修改] 强制确保进程消失
            if pid:
                try:
                    proc = psutil.Process(pid)
                    if proc.is_running():
                        self.log(f"    -> [清理] 强制终止残留 Chrome 进程 (PID: {pid})...")
                        proc.kill()
                except ImportError:
                    # 如果没装 psutil，用系统命令兜底 (Windows)
                    import os
                    try:
                        os.system(f"taskkill /F /PID {pid} >nul 2>&1")
                    except: pass
                except:
                    pass

            self.driver = None

    def _simulate_human_interaction(self):
        """
        模拟人类阅读行为：随机滚动 + 鼠标轨迹
        """
        try:
            # 1. 随机滚动 (模拟阅读)
            scroll_height = random.randint(300, 700)
            for i in range(0, scroll_height, random.randint(50, 100)):
                self.driver.execute_script(f"window.scrollBy(0, {random.randint(40, 80)});")
                time.sleep(random.uniform(0.05, 0.2))

            # 2. 模拟鼠标晃动 (证明有 user_activation)
            action = ActionChains(self.driver)
            action.move_by_offset(random.randint(10, 50), random.randint(10, 50)).perform()
            time.sleep(random.uniform(0.5, 1.2))

        except Exception:
            pass

    def _check_block_status(self):
        try:
            text = self.driver.find_element(By.TAG_NAME, "body").text.lower()

            # Cloudflare 关键词
            cf_keywords = ["verify you are human", "just a moment", "checking if the site connection is secure", "cloudflare"]

            # Elsevier / ScienceDirect 关键词
            elsevier_keywords = ["access through your institution", "check access", "sciencedirect", "sign in to view"]

            if any(k in text for k in cf_keywords):
                return "CF"

            # 只有在页面极短（可能是报错页）或者明确包含拦截词时才判定为 Elsevier 拦截
            # 防止误判正常论文页
            if "sciencedirect.com" in self.driver.current_url and len(text) < 500:
                time.sleep(3)
                return "ELSEVIER_BLOCK"

            return None
        except:
            pass
        return None

    def _check_is_captcha_page(self):
        try:
            text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            keywords = ["verify you are human", "just a moment", "checking if the site connection is secure",
                        "cloudflare"]
            if any(k in text for k in keywords): return True
        except:
            pass
        return False

    def _robust_navigate(self, url):
        try:
            self.driver.get(url)
        except:
            pass

        self._enforce_window_layout()
        block_type = self._check_block_status()
        if block_type:
            self.log(f"    -> [警告] 检测到拦截 ({block_type})，请在右上角窗口手动处理！")
            self.log(f"    -> [动作] 脚本暂停，等待页面恢复正常... (手动解决后无需操作，自动继续)")

            wait_count = 0
            while True:
                time.sleep(2)
                wait_count += 2
                # 每隔 2 秒检查一次是否通过了验证
                current_block = self._check_block_status()
                if not current_block:
                    self.log("    -> [系统] 验证通过/页面恢复，继续执行！")
                    break

                # 如果是 Elsevier，可能需要你点一下刷新
                if block_type == "ELSEVIER_BLOCK" and wait_count % 10 == 0:
                    self.log("    -> [提示] 如果是空白页，请尝试在浏览器手动刷新")

        # 必须模拟人类行为
        self._simulate_human_interaction()
        return True

    def _extract_links_from_html(self, soup, base_url):
        import urllib.parse

        # [关键修改 1] 预处理：移除参考文献区域，防止误抓引用的附件 (针对 Case 2)
        # 常见 ID/Class: references, bibliography, ref-list, biblio
        for trash in soup.find_all(attrs={"id": re.compile(r"ref|biblio|citations", re.I)}):
            trash.decompose()
        for trash in soup.find_all(class_=re.compile(r"ref|biblio|citations", re.I)):
            trash.decompose()
        # ScienceDirect 特有的参考文献区域
        for trash in soup.find_all("section", {"class": "References"}):
            trash.decompose()

        candidates = []
        # 遍历所有链接
        for link in soup.find_all('a', href=True):
            href = link['href']
            # 获取文本时保留子标签空格，避免粘连
            text = link.get_text(" ", strip=True).lower()

            # 黑名单过滤
            if any(bad in href.lower() for bad in self.blacklist): continue

            full_url = urllib.parse.urljoin(base_url, href)
            lower_url = full_url.lower()
            score = 0

            # --- 基础分：扩展名 ---
            if lower_url.endswith(('.pdf', '.docx', '.doc', '.xlsx', '.xls', '.zip', '.rar', '.cif')):
                score += 10  # 提高基础分

            # --- 关键词评分 ---
            if any(kw in text for kw in self.si_keywords): score += 5
            if 'suppl' in lower_url: score += 5
            if 'media' in lower_url: score += 2
            if 'esm' in lower_url: score += 5
            if 'pubs.acs.org/doi/suppl/' in lower_url: score += 8

            # --- Elsevier/ScienceDirect 专项提权 (针对 Case 1) ---
            # mmc
            if 'mmc' in lower_url: score += 20  # 给极高分，确保排第一

            # 1-s2.0-
            if '1-s2.0-' in lower_url and 'ars.els-cdn' in lower_url: score += 20
            # 如果文字包含 Download 且链接看起来像附件，加分
            if "download" in text and score > 0:
                score += 5

            # 降权逻辑
            # 如果链接包含 "references" 或看起来像外部引用的 DOI，扣分
            if "references" in lower_url: score -= 10

            # 如果正文链接里出现了其他出版社的域名 (比如当前是在 Elsevier，却出现了 ACS 的链接)，大概率是参考文献
            # 简单判断：如果链接里有 10.xxxx 的DOI结构，但不是下载链接特征，扣分
            if "/10." in lower_url and "mmc" not in lower_url and "suppl" not in lower_url:
                score -= 5

            # Elsevier 的文章页面，如果链接指向 pubs.acs.org 或其他期刊站，大概率是引用
            if "sciencedirect.com" in base_url and "pubs.acs.org" in lower_url:
                score -= 20

            si_indicators = ['suppl', 'esm', 'moesm', 'data', 'media', 'mmc', 'appendix', '1-s2.0-']
            if ('article' in lower_url or '/articles/' in lower_url) and not any(x in lower_url for x in si_indicators):
                score -= 20

            if score > 0:
                candidates.append({'url': full_url, 'score': score, 'text': text})
        return candidates

    def _extract_links_from_local_pdf(self, pdf_path):
        self.log(f"    -> [策略] 尝试扫描本地 PDF 内嵌链接...")
        candidates = []
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                links = page.get_links()
                for link in links:
                    uri = link.get("uri")
                    if uri:
                        lower_url = uri.lower()
                        score = 0
                        # 保持原有的评分逻辑
                        if lower_url.endswith(('.pdf', '.docx', '.doc', '.zip')): score += 10
                        if 'suppl' in lower_url: score += 5

                        if score > 0:
                            self.log(f"    -> [发现] PDF内链: {uri}")
                            candidates.append({'url': uri, 'score': score, 'text': 'PDF Link'})
        except Exception as e:
            self.log(f"    -> [错误] PDF扫描失败: {e}")
        finally:
            if doc: doc.close()
        return candidates

    def _is_pdf_preview_ready(self):
        """
        [修改] 不再检测内部 DOM，改为检测 URL 特征。
        如果当前 URL 是 pdf 结尾，且页面加载完成，即认为可以进行 JS 下载。
        """
        try:
            return self.driver.execute_script(
                "return (document.readyState === 'complete') && "
                "(window.location.href.toLowerCase().indexOf('.pdf') !== -1 || "
                " document.contentType === 'application/pdf');"
            )
        except:
            return False

    def _wait_for_download(self, timeout=60, check_preview=True):
        end_time = time.time() + timeout
        while time.time() < end_time:
            if not self.temp_download_dir.exists():
                time.sleep(1)
                continue
            files = list(self.temp_download_dir.glob("*"))
            valid_files = [f for f in files if not f.name.endswith(('.crdownload', '.tmp')) and f.is_file()]
            if valid_files:
                newest_file = max(valid_files, key=lambda f: f.stat().st_ctime)
                try:
                    if newest_file.stat().st_size < 1024:
                        pass
                    else:
                        prev_size = newest_file.stat().st_size
                        time.sleep(1.5)
                        curr_size = newest_file.stat().st_size
                        if curr_size == prev_size and curr_size > 0: return newest_file
                except:
                    pass
            has_active_download = any(f.name.endswith(('.crdownload', '.tmp')) for f in files)
            if check_preview and not has_active_download and self._is_pdf_preview_ready():
                self.log("    -> [加速] 检测到 PDF 预览已就绪，跳过等待，执行 JS 提取...")
                time.sleep(5)
                return None
            time.sleep(1)
        return None

    def _clear_temp_dir(self):
        if not self.temp_download_dir.exists(): return
        for f in self.temp_download_dir.glob("*"):
            try:
                if f.is_file(): f.unlink()
            except:
                pass

    def download_si(self, doi, output_folder, file_prefix, local_pdf_path=None):
        max_retries = 3
        start_url = f"https://doi.org/{doi}"

        for attempt in range(max_retries):
            try:
                if not self.driver:
                    self.log(f"    -> [系统] 启动浏览器...")
                    if not self._init_browser():
                        return  # 启动失败直接返回

                self.log(f"    -> [SI] 访问: {doi}")
                if not self._robust_navigate(start_url):
                    self.reset_browser()
                    continue

                current_url = self.driver.current_url
                initial_soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                candidates = self._extract_links_from_html(initial_soup, current_url)

                if not candidates and local_pdf_path and os.path.exists(local_pdf_path):
                    self.log("    -> [提示] 网页未找到 SI 链接，尝试读取本地 PDF...")
                    candidates = self._extract_links_from_local_pdf(local_pdf_path)

                if not candidates:
                    self.log("    -> [放弃] 未找到链接")
                    break

                candidates.sort(key=lambda x: x['score'], reverse=True)

                processed_candidates = []
                for item in candidates[:5]:
                    url = item['url']
                    is_acs_landing = 'pubs.acs.org/doi/suppl/' in url and not url.endswith('.pdf')
                    is_direct_file = url.lower().endswith(('.pdf', '.docx', '.doc'))

                    if is_acs_landing:
                        self.log(f"    -> [SI] 进入 ACS 目录页...")
                        try:
                            self.driver.get(url)
                            self._simulate_human_interaction()
                            sub_soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                            sub_candidates = self._extract_links_from_html(sub_soup, self.driver.current_url)
                            valid_sub = [c for c in sub_candidates if
                                         c['url'].lower().endswith(('.pdf', '.docx', '.doc'))]
                            if valid_sub: processed_candidates.extend(valid_sub)
                        except:
                            pass
                    elif is_direct_file:
                        processed_candidates.append(item)

                if not processed_candidates: break

                unique_links = {}
                for c in processed_candidates:
                    if c['url'] not in unique_links: unique_links[c['url']] = c
                final_list = list(unique_links.values())
                final_list.sort(key=lambda x: x['score'], reverse=True)
                final_list = final_list[:2]
                downloaded_hashes = set()
                if local_pdf_path and os.path.exists(local_pdf_path):
                    main_pdf_hash = get_file_md5(local_pdf_path)
                    if main_pdf_hash:
                        downloaded_hashes.add(main_pdf_hash)
                success_count = 0
                for idx, item in enumerate(final_list):
                    link_url = item['url']
                    ext = ".pdf"
                    if link_url.lower().endswith(".docx"):
                        ext = ".docx"
                    elif link_url.lower().endswith(".doc"):
                        ext = ".doc"

                    safe_doi = str(doi).replace('/', '_').replace('\\', '_')
                    si_filename = f"{safe_doi}_SI{ext}" if idx == 0 else f"{safe_doi}_SI_{idx + 1}{ext}"
                    if len(si_filename) > 100: si_filename = f"SI_{idx + 1}{ext}"
                    final_save_path = output_folder / si_filename

                    self.log(f"    -> [SI] 下载中: {link_url.split('/')[-1][:30]}...")
                    try:
                        self._clear_temp_dir()
                        self.driver.get(link_url)
                        time.sleep(3)  # 先给一点反应时间
                        block = self._check_block_status()
                        if block:
                            self.log(f"    -> [拦截] 检测到 {block}，等待手动处理...")
                            # 复用 _robust_navigate 里的等待逻辑，或者简单循环等待
                            while self._check_block_status():
                                time.sleep(2)
                            self.log("    -> [恢复] 验证通过，继续...")
                        # ----------------------------------------

                        time.sleep(15)  # 减少死等时间，因为上面已经判断过了
                        downloaded_temp_file = self._wait_for_download(timeout=60)

                        if not downloaded_temp_file:
                            # [修改] 智能 JS 下载：优先提取 embed src，解决下载成 HTML 无法打开的问题
                            js_blob_download = """
                                (function() {
                                    try {
                                        console.log("尝试触发 Chrome PDF Viewer 下载按钮...");
                                        // 穿透 Shadow DOM 寻找下载按钮
                                        var viewer = document.querySelector('pdf-viewer');
                                        if (viewer) {
                                            var toolbar = viewer.shadowRoot.querySelector('viewer-toolbar');
                                            if (toolbar) {
                                                var downloadBtn = toolbar.shadowRoot.querySelector('#downloads');
                                                if (downloadBtn) {
                                                    downloadBtn.click();
                                                    console.log("已点击下载按钮");
                                                    return "clicked";
                                                }
                                            }
                                        }
                                        // 备用方案：如果没有 Viewer，可能是直接的 embed，尝试模拟键盘 Ctrl+S 通常无法通过JS实现，
                                        // 这是一个兜底：创建一个指向当前的链接并点击，不使用 fetch
                                        console.log("未找到 Viewer，尝试创建直连下载...");
                                        var a = document.createElement('a');
                                        a.href = window.location.href;
                                        a.download = ''; // 触发下载
                                        document.body.appendChild(a);
                                        a.click();
                                        document.body.removeChild(a);
                                    } catch(e) {
                                        console.error(e);
                                    }
                                })();
                            """
                            try:
                                self.driver.execute_script(js_blob_download)
                                # 执行 JS 后，再次等待文件出现在文件夹中
                                downloaded_temp_file = self._wait_for_download(timeout=30, check_preview=False)
                            except:
                                pass

                        if downloaded_temp_file and downloaded_temp_file.stat().st_size > 1024:
                            # === 修改：更稳健的去重逻辑 ===
                            temp_md5 = get_file_md5(downloaded_temp_file)

                            # 1. 检查重复
                            if temp_md5 in downloaded_hashes:
                                self.log(f"    -> [重复] 内容与本篇已下载附件完全一致(MD5)，跳过。")
                                try:
                                    downloaded_temp_file.unlink()  # 删除临时文件
                                except:
                                    pass
                                continue  # <--- 确保直接进入下一次循环

                            # 2. 记录新哈希
                            downloaded_hashes.add(temp_md5)

                            # 3. 移动文件
                            shutil.move(str(downloaded_temp_file), str(final_save_path))
                            self.log(f"    -> [SI] 保存成功: {si_filename}")
                            success_count += 1
                        else:
                            self.log(f"    -> [SI] 下载超时或文件过小")
                    except Exception as e:
                        self.log(f"    -> [SI] 异常: {e}")

                if success_count > 0: break

            except Exception as e:
                self.log(f"    -> [错误] 全局异常: {e}")
                self.reset_browser()

# ==========================================
# 6. Word 转换逻辑
# ==========================================

def convert_to_pdf_if_needed(file_list, logger=None):
    def log(msg):
        print(msg)
        if logger: logger(msg)

    if not HAS_DOCX_TOOLS: return
    for file_path in file_list:
        if file_path.suffix.lower() in ['.docx', '.doc']:
            pdf_path = file_path.with_suffix('.pdf')
            if pdf_path.exists(): continue
            log(f"    -> [格式转换] 正在将 {file_path.name} 转换为 PDF...")
            if file_path.suffix.lower() == '.docx':
                try:
                    convert(str(file_path))
                    continue
                except:
                    pass
            try:
                word = win32com.client.Dispatch("Word.Application")
                word.visible = 0
                abs_doc_path = str(file_path.resolve())
                abs_pdf_path = str(pdf_path.resolve())
                doc = word.Documents.Open(abs_doc_path)
                doc.SaveAs(abs_pdf_path, FileFormat=17)
                doc.Close()
            except:
                pass

# ==========================================
# 7. 主流程 - PDF 解析
# ==========================================

def process_pdf(file_path, proxies, logger=None):
    doc = None
    try:
        doc = fitz.open(file_path)
        text_content = []
        for i in range(min(5, len(doc))):
            text_content.append(doc[i].get_text("text"))
        full_text_sample = "\n".join(text_content)

        # 1. 中文检测
        if is_chinese_text(full_text_sample):
            return "CHINESE_DOC", None

        # 2. DOI 提取策略 (元数据 -> 文件名 -> 文本正则 -> 链接 -> 标题反查 -> DeepSeek)

        # (A) 尝试文件名
        doi_from_name = infer_doi_from_filename(file_path.name)
        if doi_from_name:
            if logger: logger(f"    -> [文件名] 识别 DOI: {doi_from_name}")
            meta = fetch_metadata_from_crossref(doi_from_name, proxies)
            if meta: return meta, full_text_sample

        # (B) 尝试 PDF 属性
        prop_res = extract_metadata_from_pdf_properties(doc)
        if prop_res and prop_res[0] == 'doi':
            meta = fetch_metadata_from_crossref(prop_res[1], proxies)
            if meta: return meta, full_text_sample

        # (C) 尝试全文正则 (取前2个候选)
        doi_candidates = match_doi_pattern(full_text_sample)[:2]
        for d in doi_candidates:
            if logger: logger(f"    -> [文本扫描] 尝试 DOI: {d} ...")
            meta = fetch_metadata_from_crossref(d, proxies)
            if meta: return meta, full_text_sample

        # (D) 尝试 PDF 内链
        doi_link = extract_dois_from_pdf_links(doc)
        if doi_link:
            meta = fetch_metadata_from_crossref(doi_link, proxies)
            if meta: return meta, full_text_sample

        # (E) 标题反查
        if full_text_sample:
            if logger: logger(f"    -> [标题搜索] 尝试 Crossref 反查...")
            meta = fetch_metadata_by_title_search(full_text_sample, proxies, logger)
            if meta: return meta, full_text_sample

        # (F) DeepSeek 兜底
        if full_text_sample and len(full_text_sample) > 200 and API_KEY:
            if logger: logger("    -> [DeepSeek] 启动智能分析...")
            ds_result = ask_deepseek_backup(full_text_sample, logger)
            if ds_result:
                if "10." in ds_result and "/" in ds_result:
                    meta = fetch_metadata_from_crossref(ds_result, proxies, logger)
                    if meta: return meta, full_text_sample
                # 假如是引用格式，尝试搜索 (此处复用 title search 的逻辑变体，或者简单跳过)
    except Exception as e:
        if logger: logger(f"    -> 解析错误: {e}")
    finally:
        if doc:
            doc.close()
            del doc

    return None, None


def has_si_mentions(pdf_path):
    doc = None
    try:
        # fitz (PyMuPDF) 提取文本
        doc = fitz.open(pdf_path)
        for page in doc:
            text = page.get_text()
            if not text: continue

            text_lower = text.lower()
            keywords = ["supporting information", "supplementary material", "supplementary data",
                        "supplemental material", "online data"]
            for kw in keywords:
                if kw in text_lower: return True, f"文中包含关键词 '{kw}'"

            pattern = r'\b(fig\.?|figure|table|movie|video|note|eq\.?|equation)s?\s+s\d+\b'
            match = re.search(pattern, text_lower)
            if match: return True, f"文中引用了 '{match.group(0)}' (明确包含 'S' 编号)"

            if "associated with this article" in text_lower and "doi" in text_lower:
                return True, "文中包含 'associated with this article' 声明"
        # ==========================================
    except Exception as e:
        return False, "无法读取文本"
    finally:
        if doc: doc.close()  # 确保释放文件
    return False, None


def main(input_folder, output_folder, proxies, chrome_data_dir=None, signal_callback=None):
    def log_msg(text):
        if signal_callback:
            try:
                signal_callback({"type": "log", "msg": text})
            except:
                print(text)
        else:
            print(text)

    source_path = Path(input_folder)
    base_target_path = Path(output_folder)
    base_target_path.mkdir(parents=True, exist_ok=True)
    history_file = base_target_path / "processing_historysi.json"

    # 加载 DOI 存档
    doi_map = {}
    # 尝试在源目录和目标目录寻找 doi_mapping.json
    possible_maps = [source_path / "doi_mapping.json", base_target_path / "doi_mapping.json"]
    for map_file in possible_maps:
        if map_file.exists():
            try:
                with open(map_file, 'r', encoding='utf-8') as f:
                    doi_map.update(json.load(f))
                log_msg(f"成功加载 DOI 存档: {map_file.name} (含 {len(doi_map)} 条记录)")
            except:
                pass
    # 传递日志回调给 SIFetcher
    history_file = base_target_path / "processing_historysi.json"
    si_fetcher = SIFetcher(proxies, user_data_dir=chrome_data_dir, logger=log_msg)
    try:
        # Elsevier 冷却机制变量
        last_elsevier_time = 0
        deferred_downloads = []  # 存储因冷却被推迟的任务

        def is_elsevier_doi(doi_str):
            if not doi_str: return False
            return doi_str.startswith("10.1016/") or "cell" in doi_str.lower()
        seen_hashes = set()
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                seen_hashes = set(json.load(f).get("hashes", []))
        except:
            pass
        stats = {"total": 0, "success": 0, "fail": 0, "skip": 0, "chinese": 0, "si_retry": 0, "no_si_confirmed": 0}
        all_files = sorted(list(source_path.rglob('*.pdf')), key=lambda x: x.name)
        log_msg(f"开始处理 {len(all_files)} 个文件 (启用 SI 智能文本校验模式)...")

        # 向 GUI 发送扫描列表
        if signal_callback:
            signal_callback({
                "type": "scan_result",
                "files": [f.name for f in all_files],
                "mode": "normal"
            })

        for file_path in all_files:
            if getattr(sys.modules[__name__], 'abort_flag', False):
                log_msg(">>> 🛑 检测到停止信号，正在安全退出...")
                break
            stats["total"] += 1
            log_msg(f"\n[{stats['total']}/{len(all_files)}] {file_path.name}")

            # 信号：开始处理
            if signal_callback:
                signal_callback({"type": "file_start", "file": str(file_path.absolute())})

            f_hash = get_file_md5(file_path)
            if f_hash in seen_hashes:
                log_msg("    -> 跳过 (已归档)")
                stats["skip"] += 1
                if signal_callback:
                    signal_callback({"type": "file_skip", "file": str(file_path.absolute()), "msg": "已归档"})
                continue
            target_doi = None
            is_chinese = False
            # 1. 优先查表 (extract 存档)
            if file_path.name in doi_map:
                target_doi = doi_map[file_path.name]
                log_msg(f"    -> [存档命中] 直接获取 DOI: {target_doi}")
            else:
                # 2. 只有没命中存档，才进行解析
                meta_res, _ = process_pdf(file_path, proxies, logger=log_msg)
                gc.collect()
                time.sleep(0.1)
                if meta_res == "CHINESE_DOC":
                    is_chinese = True
                elif meta_res and 'doi' in meta_res:
                    target_doi = meta_res['doi']
            if is_chinese:
                log_msg("    -> [分类] 中文文献，跳过 SI 抓取")
                chinese_folder = base_target_path / "中文文献"
                chinese_folder.mkdir(exist_ok=True)
                try:
                    shutil.copy2(file_path, chinese_folder / file_path.name)
                    stats["chinese"] += 1
                    seen_hashes.add(f_hash)
                    if signal_callback: signal_callback({"type": "file_done", "file": str(file_path.absolute()), "remark": "中文归档"})
                except Exception as e:
                    log_msg(f"    -> 复制失败: {e}")
                continue
            folder_name = clean_filename(file_path.stem)
            article_folder = base_target_path / folder_name
            article_folder.mkdir(exist_ok=True)
            safe_name = clean_filename(file_path.stem) + file_path.suffix
            target_file_path = article_folder / safe_name
            try:
                shutil.copyfile(file_path, target_file_path)
                shutil.copystat(file_path, target_file_path)

                # 校验一下复制后的文件大小，如果为0则报错
                if target_file_path.stat().st_size == 0:
                    raise Exception("复制后文件大小为0")
            except Exception as e:
                log_msg(f"    -> [错误] 主文件复制失败: {e}")
                stats["fail"] += 1
                if signal_callback: signal_callback({"type": "file_error", "file": str(file_path.absolute()), "msg": "IO错误"})
                continue
                # 下载 SI
            should_process_now = True
            if target_doi:
                # 判断是否为爱思唯尔 DOI
                if is_elsevier_doi(target_doi):
                    current_time = time.time()
                    time_diff = current_time - last_elsevier_time

                    # 如果距离上次访问不足 60 秒，且后面还有其他文件没处理，则推迟
                    if time_diff < 60:
                        log_msg(f"    -> [风控] Elsevier 冷却中 (仅过 {int(time_diff)}s)，推迟 SI 下载，优先处理其他文献...")
                        # 将必要信息存入元组，稍后处理
                        deferred_downloads.append({
                            "doi": target_doi,
                            "folder": article_folder,
                            "prefix": clean_filename(target_doi),
                            "local_pdf": target_file_path,
                            "original_file_name": file_path.name,
                            "hash": f_hash
                        })
                        should_process_now = False
                        # 注意：这里我们只跳过下载，但文件已经归档移动好了
                    else:
                        # 时间足够，更新计时器
                        last_elsevier_time = time.time()

                if should_process_now:
                    # 立即执行下载
                    si_fetcher.download_si(target_doi, article_folder, clean_filename(target_doi),
                                           local_pdf_path=target_file_path)

                    # 如果刚刚处理的是 Elsevier，再次更新时间（防止下载耗时很短）
                    if is_elsevier_doi(target_doi):
                        last_elsevier_time = time.time()

                # 转换与统计 (注意：如果是推迟的任务，这里暂时不会有 SI 文件，统计结果会显示无 SI)
                # 标记为 "待补录"

                if not should_process_now:
                    if signal_callback:
                        signal_callback({
                            "type": "file_deferred",
                            "file": file_path.name,
                            "remark": "Elsevier冷却中(推迟)",
                            "result_path": str(article_folder)
                        })
                    continue
                    # 转换与统计
                current_files = list(article_folder.glob("*"))
                convert_to_pdf_if_needed(current_files, logger=log_msg)

                # 统计并生成备注
                valid_files = [f for f in article_folder.glob("*") if
                               f.suffix.lower() in ['.pdf', '.docx', '.doc'] and f.stat().st_size > 1024]
                file_count = len(valid_files)

                # 计算 SI 尺寸备注
                remark_str = "无SI"

                # 1. 先获取所有候选文件
                raw_candidates = [f for f in valid_files if
                                  f.name != "paper.pdf" and f.name != target_file_path.name]

                # 2. 过滤逻辑：如果 Word 文件对应的 PDF 已存在，则在列表中隐藏 Word 文件
                si_files_found = []
                for f in raw_candidates:
                    if f.suffix.lower() in ['.doc', '.docx']:
                        # 检查是否存在同名的 .pdf 版本
                        pdf_version = f.with_suffix('.pdf')
                        if pdf_version.exists():
                            continue  # 有 PDF 版本，跳过显示这个 Word 文件
                    si_files_found.append(f)

                # 3. 按文件名排序确保顺序
                si_files_found.sort(key=lambda x: x.name)

                if si_files_found:
                    size_details = []
                    for idx, sif in enumerate(si_files_found):
                        name_display = f"SI {idx + 1}"
                        size_display = format_size(sif.stat().st_size)
                        size_details.append(f"{name_display}: {size_display}")
                    remark_str = ", ".join(size_details)
                # -------------------------------

                if si_files_found:
                    log_msg(f"    -> [完成] 成功抓取正文 + SI ({len(si_files_found)} files)")
                    stats["success"] += 1
                    seen_hashes.add(f_hash)
                    if signal_callback:
                        signal_callback({
                            "type": "file_done",
                            "file": file_path.name,
                            "remark": remark_str,
                            "result_path": str(article_folder)  # 关键：把文件夹路径传回去
                        })

                else:
                    log_msg("    -> [检测] 缺少 SI 文件，正在扫描正文寻找线索...")
                    has_evidence, evidence_msg = has_si_mentions(target_file_path)
                    if has_evidence:
                        log_msg(f"    -> [校验失败] 文中发现了 '{evidence_msg}'，但未下载到附件。")
                        log_msg("    -> [动作] 跳过记录，等待下次重试。")
                        stats["si_retry"] += 1
                        if signal_callback:
                            signal_callback({"type": "file_error", "file": str(file_path.absolute()), "msg": "缺少SI(有引用)"})
                    else:
                        log_msg(f"    -> [完成] 文中未检测到 SI 关键词，判定该文献无附件。")
                        log_msg("    -> [动作] 标记为已完成。")
                        stats["no_si_confirmed"] += 1
                        seen_hashes.add(f_hash)
                        if signal_callback:
                            signal_callback({"type": "file_done", "file": str(file_path.absolute()), "remark": "确认无SI"})
            else:
                log_msg("    -> [失败] 无法识别 DOI，不进行 SI 抓取")
                stats["fail"] += 1
                unid_folder = base_target_path / "Unidentified"
                unid_folder.mkdir(exist_ok=True)
                try:
                    shutil.copy2(file_path, unid_folder / file_path.name)
                except:
                    pass
                if signal_callback:
                    signal_callback({"type": "file_error", "file": str(file_path.absolute()), "msg": "无DOI"})

            if stats["total"] % 1 == 0:
                try:
                    with open(history_file, 'w', encoding='utf-8') as f:
                        json.dump({"hashes": list(seen_hashes)}, f)
                except:
                    pass

        if deferred_downloads:
            log_msg(f"\n>>> 开始处理推迟的 {len(deferred_downloads)} 个 Elsevier 任务...")

            def get_journal_id(doi_str):
                try:
                    # 简单处理：取 10.1016/ 后面直到第二个点之前的部分
                    # 针对 j.ensm.2020... 返回 j.ensm
                    # 针对 S0013-4686... 返回 S0013-4686
                    part = doi_str.split('10.1016/')[1]
                    if 'j.' in part:
                        return ".".join(part.split('.')[:2])
                    else:
                        return part.split('/')[0] # 兜底
                except:
                    return "unknown"

            for idx, task in enumerate(deferred_downloads):
                if getattr(sys.modules[__name__], 'abort_flag', False):
                    remaining = len(deferred_downloads) - idx
                    log_msg(f">>> 🛑 停止补录，剩余 {remaining} 个任务归入[待重试]")
                    stats["si_retry"] += remaining

                    # 遍历剩余任务，将 UI 状态从黄色刷成红色/橙色
                    if signal_callback:
                        for i in range(idx, len(deferred_downloads)):
                            skipped_task = deferred_downloads[i]
                            signal_callback({
                                "type": "file_skip",  # 或者 file_error
                                "file": skipped_task['original_file_name'],
                                "msg": "已停止(待重试)"
                            })
                    break

                log_msg(f"\n[补录 {idx+1}/{len(deferred_downloads)}] {task['original_file_name']}")

                # 冷却：判断是否需要等待
                need_wait = False

                # 如果不是最后一个，检查下一个是否也是同期刊
                if idx < len(deferred_downloads) - 1:
                    next_task = deferred_downloads[idx + 1]
                    curr_jid = get_journal_id(task['doi'])
                    next_jid = get_journal_id(next_task['doi'])

                    # 只有当 当前 和 下一个 都是 Elsevier 且 ID 相似时才等待
                    if is_elsevier_doi(task['doi']) and is_elsevier_doi(next_task['doi']):
                        if curr_jid == next_jid:
                            need_wait = True
                            log_msg(f"    -> [预判] 下一篇同属 {curr_jid}，启用冷却...")
                        else:
                            log_msg(f"    -> [预判] 期刊切换 ({curr_jid} -> {next_jid})，跳过冷却！")

                # 如果需要等待，才执行时间计算
                if need_wait:
                    current_time = time.time()
                    wait_time = 60 - (current_time - last_elsevier_time)
                    if wait_time > 0:
                        log_msg(f"    -> [冷却] 强制等待 {int(wait_time)} 秒...")
                        # 支持在 sleep 期间快速响应中断
                        for _ in range(int(wait_time)):
                            if getattr(sys.modules[__name__], 'abort_flag', False): break
                            time.sleep(1)
                        # 补齐小数部分
                        time.sleep(wait_time - int(wait_time))

                # 再次检查停止信号（防止sleep期间停止）
                if getattr(sys.modules[__name__], 'abort_flag', False):
                    remaining = len(deferred_downloads) - idx
                    stats["si_retry"] += remaining
                    break

                # 2. 执行下载
                try:
                    si_fetcher.download_si(task['doi'], task['folder'], task['prefix'], local_pdf_path=task['local_pdf'])
                    last_elsevier_time = time.time() # 更新最后访问时间

                    # 3. 补做：转换与统计
                    current_files = list(task['folder'].glob("*"))
                    convert_to_pdf_if_needed(current_files, logger=log_msg)

                    # 重新统计
                    valid_files = [f for f in task['folder'].glob("*") if
                                   f.suffix.lower() in ['.pdf', '.docx', '.doc'] and f.stat().st_size > 1024]

                    si_count = sum(1 for f in valid_files if f.name != "paper.pdf" and f.name != task['local_pdf'].name)

                    if si_count > 0:
                        # 1. 成功下载到 SI
                        remark_str = f"SI补录成功({si_count})"
                        log_msg(f"    -> [完成] 补录成功，抓取到 {si_count} 个附件。")
                        stats["success"] += 1
                        seen_hashes.add(task['hash'])  # 只有成功或确认无误时才存档

                        if signal_callback:
                            signal_callback({
                                "type": "file_done",
                                "file": task['original_file_name'],
                                "remark": remark_str,
                                "result_path": str(task['folder'])
                            })

                    else:
                        # 2. 未下载到 SI -> 启动文本校验 (防止漏抓)
                        has_evidence, evidence_msg = has_si_mentions(task['local_pdf'])

                        if has_evidence:
                            # 坏情况：文中说有SI，但没抓到 -> 标记为错误，不存档
                            log_msg(f"    -> [校验失败] 文中发现了 '{evidence_msg}'，但补录未下载到附件。")
                            stats["si_retry"] += 1  # 计入重试统计

                            if signal_callback:
                                signal_callback({
                                    "type": "file_error",  # 发送红色错误状态
                                    "file": task['original_file_name'],
                                    "msg": "补录失败(有引用)"
                                })
                            # 注意：这里不执行 seen_hashes.add，下次运行还会再试

                        else:
                            # 好情况：文中也没提SI -> 确认为真·无SI
                            log_msg(f"    -> [完成] 补录未发现附件，且文中无引用，确认无SI。")
                            stats["no_si_confirmed"] += 1
                            seen_hashes.add(task['hash'])  # 可以存档了

                            if signal_callback:
                                signal_callback({
                                    "type": "file_done",
                                    "file": task['original_file_name'],
                                    "remark": "补录后确认无SI",
                                    "result_path": str(task['folder'])
                                })

                except Exception as e:
                    log_msg(f"    -> [补录失败] {e}")
                    stats["fail"] += 1
                    if signal_callback:
                        signal_callback({
                            "type": "file_error",
                            "file": task['original_file_name'],
                            "msg": "补录异常"
                        })
    finally:
        log_msg("    -> [系统] 正在清理浏览器资源...")
        si_fetcher.close()
    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump({"hashes": list(seen_hashes)}, f)
    except:
        pass

    log_msg("\n" + "=" * 50)
    log_msg(f"处理完成 | 总数: {stats['total']}")
    log_msg(f"完美(含SI): {stats['success']} | 无SI(已确认): {stats['no_si_confirmed']}")
    log_msg(f"失败(待重试): {stats['si_retry']} | 中文/无法识别: {stats['chinese'] + stats['fail']}")


def run_from_gui(input_folder, output_folder, chrome_data_dir=None, api_key=None, signal_callback=None):
    global API_KEY
    API_KEY = api_key
    main(input_folder, output_folder, None, chrome_data_dir, signal_callback)

if __name__ == "__main__":
    pass