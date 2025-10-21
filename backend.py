# email_scraper_98.py
# Upgraded backend with high-accuracy email extraction (~98% recall target)
# Integrates with your frontend unchanged (WebSocket "/ws", /jobs, /job/{id}, etc.)

import webbrowser
import threading
import uvicorn
import argparse
import asyncio
import csv
import html
import io
import json
import logging
import math
import mimetypes
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.parse
import base64
import sqlite3
import uuid
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress, asynccontextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Callable

# External APIs
DASHBOARD_URL = "https://royalblue-goldfish-140935.hostingersite.com/api.php"
SECRET_KEY = "scraper_sync_123"

def send_to_dashboard(job_id: str, status: str, results: dict):
    """Send job results to dashboard API"""
    try:
        import requests
        payload = {
            "secret_key": SECRET_KEY,
            "job_id": job_id,
            "status": status,
            "results": results
        }
        r = requests.post(DASHBOARD_URL, json=payload, timeout=8)
        if r.status_code == 200:
            logging.info("Job %s sent to dashboard successfully.", job_id)
        else:
            logging.warning("Dashboard response for job %s: %s", job_id, r.text)
    except Exception as e:
        logging.exception("Failed to send job %s to dashboard: %s", job_id, e)

# optional heavy libs
try:
    from playwright.async_api import async_playwright, TimeoutError as PlayTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except Exception:
    AIOHTTP_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except Exception:
    REQUESTS_AVAILABLE = False

try:
    import dns.resolver
    DNSPY_AVAILABLE = True
except Exception:
    DNSPY_AVAILABLE = False

# Optional file extraction libs
try:
    import pdfminer.high_level as pdfminer_high
    PDFMINER_AVAILABLE = True
except Exception:
    PDFMINER_AVAILABLE = False

try:
    import docx
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except Exception:
    OPENPYXL_AVAILABLE = False

try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

# Web framework
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

# ---------------------------
# Configuration & Defaults
# ---------------------------
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = int(os.environ.get("PORT", 8000))
DEFAULT_DATA_DIR = Path.cwd() / "data"
DEFAULT_RESULTS_DIR = DEFAULT_DATA_DIR / "results"
DEFAULT_JOB_STORE = DEFAULT_DATA_DIR / "jobs.json"
DEFAULT_LOG_DIR = DEFAULT_DATA_DIR / "logs"

HOST = DEFAULT_HOST
PORT = DEFAULT_PORT
DATA_DIR = DEFAULT_DATA_DIR
RESULTS_DIR = DEFAULT_RESULTS_DIR
LOG_DIR = DEFAULT_LOG_DIR
JOB_STORE = DEFAULT_JOB_STORE

# ensure directories
for p in (DATA_DIR, RESULTS_DIR, LOG_DIR):
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

# Logger
LOG = logging.getLogger("email_scraper_98")
LOG.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
LOG.addHandler(ch)
try:
    fh = logging.FileHandler(LOG_DIR / "scraper.log", encoding="utf-8")
    fh.setFormatter(formatter)
    LOG.addHandler(fh)
except Exception:
    pass

# ---------------------------
# Constants & Regex
# ---------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.90 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
]

# Primary email regex (good balance between recall & precision)
EMAIL_RE = re.compile(
    r'(?:[a-zA-Z0-9_.+%-]+)@(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}', re.I
)

MAILTO_RE = re.compile(r'mailto:([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+)', re.I)
URL_RE = re.compile(r'https?://[^\s\'"<>]+', re.I)

# Disposable sources
DISPOSABLE_SOURCES = [
    "https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf",
]
DEFAULT_DISPOSABLE = {"mailinator.com", "10minutemail.com", "tempmail.com", "guerrillamail.com", "trashmail.com", "yopmail.com"}

# ---------------------------
# Database for user management
# ---------------------------
class Database:
    def __init__(self, db_path="scraper.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_active TEXT,
                is_blocked INTEGER DEFAULT 0,
                total_jobs INTEGER DEFAULT 0,
                total_emails_scraped INTEGER DEFAULT 0
            )
        """)
        
        # Activity table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                job_id TEXT,
                urls TEXT,
                total_emails INTEGER DEFAULT 0,
                status TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        # Jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                status TEXT NOT NULL,
                count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                results TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def register_user(self, user_id: str, name: str, created_at: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO users (id, name, created_at, last_active, is_blocked, total_jobs, total_emails_scraped)
            VALUES (?, ?, ?, ?, COALESCE((SELECT is_blocked FROM users WHERE id = ?), 0), 
                    COALESCE((SELECT total_jobs FROM users WHERE id = ?), 0),
                    COALESCE((SELECT total_emails_scraped FROM users WHERE id = ?), 0))
        """, (user_id, name, created_at, datetime.now().isoformat(), user_id, user_id, user_id))
        
        conn.commit()
        conn.close()
    
    def update_user_activity(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE users SET last_active = ? WHERE id = ?
        """, (datetime.now().isoformat(), user_id))
        
        conn.commit()
        conn.close()
    
    def is_user_blocked(self, user_id: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT is_blocked FROM users WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        return bool(result['is_blocked']) if result else False
    
    def block_user(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("UPDATE users SET is_blocked = 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    def unblock_user(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("UPDATE users SET is_blocked = 0 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    def get_all_users(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, name, created_at, last_active, is_blocked, total_jobs, total_emails_scraped
            FROM users ORDER BY created_at DESC
        """)
        
        users = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return users
    
    def get_user_activity(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM activity WHERE user_id = ? ORDER BY timestamp DESC LIMIT 50
        """, (user_id,))
        
        activities = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return activities
    
    def log_activity(self, user_id: str, user_name: str, job_id: str, urls: str, total_emails: int, status: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO activity (user_id, user_name, job_id, urls, total_emails, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, user_name, job_id, urls, total_emails, status, datetime.now().isoformat()))
        
        # Update user stats
        if status == "completed":
            cursor.execute("""
                UPDATE users 
                SET total_jobs = total_jobs + 1, 
                    total_emails_scraped = total_emails_scraped + ?
                WHERE id = ?
            """, (total_emails, user_id))
        
        conn.commit()
        conn.close()
    
    def create_job(self, job_id: str, user_id: str, count: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO jobs (id, user_id, status, count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (job_id, user_id, "queued", count, now, now))
        
        conn.commit()
        conn.close()
    
    def update_job(self, job_id: str, status: str, results: str = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        if results:
            cursor.execute("""
                UPDATE jobs SET status = ?, updated_at = ?, results = ? WHERE id = ?
            """, (status, now, results, job_id))
        else:
            cursor.execute("""
                UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?
            """, (status, now, job_id))
        
        conn.commit()
        conn.close()
    
    def get_all_jobs(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")
        jobs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jobs
    
    def get_recent_activity(self, limit: int = 100):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM activity ORDER BY timestamp DESC LIMIT ?
        """, (limit,))
        
        activities = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return activities

# ---------------------------
# Utilities / Helpers
# ---------------------------
def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def safe_filename(name: str, maxlen: int = 220) -> str:
    return "".join(c if c.isalnum() or c in "-_. " else "_" for c in name)[:maxlen]

def ensure_str(s: Any) -> str:
    return "" if s is None else str(s)

async def async_backoff_sleep(attempt: int):
    await asyncio.sleep(min(10, (2 ** attempt) * 0.25))

THREAD_POOL = ThreadPoolExecutor(max_workers=6)

# ---------------------------
# Disposable domains cache
# ---------------------------
DISPOSABLE_CACHE_FILE = DATA_DIR / ".disposable_cache.json"

def load_disposable_local() -> Set[str]:
    if DISPOSABLE_CACHE_FILE.exists():
        try:
            arr = json.loads(DISPOSABLE_CACHE_FILE.read_text(encoding="utf-8"))
            return set(arr)
        except Exception:
            LOG.exception("Failed to read disposable cache")
    return set(DEFAULT_DISPOSABLE)

def update_disposable_now() -> Set[str]:
    domains = set(DEFAULT_DISPOSABLE)
    if REQUESTS_AVAILABLE:
        for src in DISPOSABLE_SOURCES:
            try:
                r = requests.get(src, timeout=8, headers={"User-Agent": USER_AGENTS[0]})
                if r.status_code == 200:
                    for ln in r.text.splitlines():
                        ln = ln.strip()
                        if not ln or ln.startswith("#"):
                            continue
                        p = ln.split()[0]
                        if '.' in p:
                            domains.add(p.lower())
            except Exception:
                LOG.debug("Disposable source fetch failed: %s", src)
    try:
        DISPOSABLE_CACHE_FILE.write_text(json.dumps(sorted(list(domains))), encoding="utf-8")
    except Exception:
        LOG.debug("Failed to write disposable cache")
    LOG.info("Disposable domains updated. Count=%d", len(domains))
    return domains

DISPOSABLE_DOMAINS = load_disposable_local()
def _bg_disposable_update():
    try:
        updated = update_disposable_now()
        global DISPOSABLE_DOMAINS
        DISPOSABLE_DOMAINS = updated
    except Exception:
        LOG.exception("bg disposable update failed")
threading.Thread(target=_bg_disposable_update, daemon=True).start()

# ---------------------------
# Advanced deobfuscation (expanded)
# ---------------------------
def _decode_fromcharcodes(text: str) -> str:
    # handle String.fromCharCode(65,66,67) and fromCharCode sequences
    def repl(m):
        nums = re.findall(r'\d+', m.group(1))
        try:
            return ''.join(chr(int(n)) for n in nums)
        except Exception:
            return m.group(0)
    text = re.sub(r'String\.fromCharCode\(\s*([^\)]+)\)', repl, text, flags=re.I)
    return text

def _unescape_js_percent_hex(text: str) -> str:
    # decode \xNN and percent-encoded sequences
    try:
        text = re.sub(r'\\x([0-9A-Fa-f]{2})', lambda m: chr(int(m.group(1), 16)), text)
    except Exception:
        pass
    try:
        text = urllib.parse.unquote(text)
    except Exception:
        pass
    return text

def _concat_quoted_parts(text: str) -> str:
    # combine 'a'+'@'+'b.com' -> a@b.com
    try:
        text = re.sub(r"(?:'|\")([^'\"]+)(?:'|\")\s*\+\s*(?:'|\")([^'\"]+)(?:'|\")", lambda m: m.group(1) + m.group(2), text)
    except Exception:
        pass
    return text

def _decode_base64_snippets(text: str) -> str:
    # find long base64-like chunks and try to decode when they contain @ after decoding
    added = []
    for b64 in set(re.findall(r'([A-Za-z0-9+/]{16,}={0,2})', text)):
        try:
            dec = base64.b64decode(b64 + '==' if len(b64) % 4 else b64).decode('utf-8', errors='ignore')
            if '@' in dec and len(dec) < 1000:
                added.append(dec)
        except Exception:
            pass
    if added:
        text += "\n" + "\n".join(added)
    return text

def advanced_deobfuscate(text: str) -> str:
    if not text:
        return ""
    t = text
    # common textual replacements
    seq = [
        (r'\[at\]', '@'), (r'\(at\)', '@'), (r'\{at\}', '@'), (r'\sat\s', '@'),
        (r'\[dot\]', '.'), (r'\(dot\)', '.'), (r'\{dot\}', '.'), (r'\sdot\s', '.'),
        (r'&commat;', '@'), (r'&#64;', '@'), (r'&#46;', '.'),
    ]
    for pat, repl in seq:
        t = re.sub(pat, repl, t, flags=re.I)

    # decode HTML numeric entities
    try:
        t = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), t)
        t = re.sub(r'&#([0-9]+);', lambda m: chr(int(m.group(1))), t)
    except Exception:
        pass

    # remove zero-width
    t = ''.join(ch for ch in t if ord(ch) not in (8203, 8204, 8205))

    # fromCharCode and other JS encodings
    t = _decode_fromcharcodes(t)
    t = _unescape_js_percent_hex(t)
    t = _concat_quoted_parts(t)
    t = _decode_base64_snippets(t)

    # unescape JS unescape()
    try:
        for m in re.findall(r'unescape\([\'"]([^\'"]+)[\'"]\)', t, flags=re.I):
            try:
                t += '\n' + urllib.parse.unquote(m)
            except Exception:
                pass
    except Exception:
        pass

    # collapse whitespace
    t = re.sub(r'\s+', ' ', t)
    return t

def extract_emails(text: str) -> Set[str]:
    if not text:
        return set()
    t = advanced_deobfuscate(text)
    found = set(re.findall(EMAIL_RE, t))
    return {e.strip() for e in found if e and len(e) < 320}

# ---------------------------
# Proxy Manager
# ---------------------------
@dataclass
class ProxyInfo:
    url: str
    last_ok: Optional[float] = None
    last_fail: Optional[float] = None
    fails: int = 0

class ProxyManager:
    def __init__(self, proxies: Optional[List[str]] = None):
        self._proxies: List[ProxyInfo] = [ProxyInfo(p) for p in (proxies or [])]
        self._idx = 0
        self._lock = threading.Lock()

    def load_from_text(self, text: str):
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        self._proxies = [ProxyInfo(p) for p in lines]
        self._idx = 0
        LOG.info("Loaded %d proxies", len(self._proxies))

    def add(self, proxy: str):
        with self._lock:
            self._proxies.append(ProxyInfo(proxy))

    def get_next(self) -> Optional[str]:
        with self._lock:
            if not self._proxies:
                return None
            p = self._proxies[self._idx % len(self._proxies)]
            self._idx += 1
            return p.url

    def mark_success(self, proxy_url: str):
        with self._lock:
            for p in self._proxies:
                if p.url == proxy_url:
                    p.last_ok = time.time()
                    p.fails = 0

    def mark_failure(self, proxy_url: str):
        with self._lock:
            for p in self._proxies:
                if p.url == proxy_url:
                    p.last_fail = time.time()
                    p.fails += 1

# ---------------------------
# Playwright Pool
# ---------------------------
class PlaywrightPool:
    def __init__(self, headless: bool = True, max_contexts: int = 3, logger: logging.Logger = LOG):
        self.headless = headless
        self.max_contexts = max_contexts
        self._pw = None
        self._browser = None
        self._contexts: deque = deque()
        self._lock = asyncio.Lock()
        self._inited = False
        self._logger = logger

    async def init(self):
        if self._inited:
            return
        if not PLAYWRIGHT_AVAILABLE:
            self._logger.warning("Playwright not installed.")
            return
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        for _ in range(self.max_contexts):
            try:
                ctx = await self._browser.new_context()
                self._contexts.append(ctx)
            except Exception:
                pass
        self._inited = True
        self._logger.info("PlaywrightPool initialized contexts=%d", len(self._contexts))

    async def get_context(self):
        await self.init()
        async with self._lock:
            if self._contexts:
                return self._contexts.popleft()
            return await self._browser.new_context()

    async def release_context(self, ctx):
        async with self._lock:
            try:
                if len(self._contexts) < self.max_contexts:
                    self._contexts.append(ctx)
                else:
                    await ctx.close()
            except Exception:
                pass

    async def close(self):
        if not self._inited:
            return
        while self._contexts:
            ctx = self._contexts.popleft()
            try:
                await ctx.close()
            except Exception:
                pass
        try:
            await self._browser.close()
        except Exception:
            pass
        try:
            await self._pw.stop()
        except Exception:
            pass
        self._inited = False
        self._logger.info("PlaywrightPool closed")

# ---------------------------
# File extractors
# ---------------------------
def extract_text_from_pdf_bytes(b: bytes) -> str:
    if not PDFMINER_AVAILABLE:
        return ""
    try:
        with io.BytesIO(b) as bio:
            text = pdfminer_high.extract_text(bio)
            return text or ""
    except Exception:
        LOG.debug("PDF extraction failed", exc_info=True)
    return ""

def extract_text_from_docx_bytes(b: bytes) -> str:
    if not DOCX_AVAILABLE:
        return ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(b)
            tmp.flush()
            tmp_path = tmp.name
        docx_obj = docx.Document(tmp_path)
        t = "\n".join(p.text for p in docx_obj.paragraphs)
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return t
    except Exception:
        LOG.debug("DOCX extraction failed", exc_info=True)
    return ""

def extract_text_from_xlsx_bytes(b: bytes) -> str:
    if not OPENPYXL_AVAILABLE:
        return ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(b)
            tmp.flush()
            tmp_path = tmp.name
        import openpyxl as ox
        wb = ox.load_workbook(tmp_path, read_only=True)
        rows = []
        for sh in wb.worksheets:
            for row in sh.iter_rows(values_only=True):
                for c in row:
                    if c:
                        rows.append(str(c))
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return "\n".join(rows)
    except Exception:
        LOG.debug("XLSX extraction failed", exc_info=True)
    return ""

def extract_text_from_image_bytes(b: bytes) -> str:
    if not OCR_AVAILABLE:
        return ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b)
            tmp.flush()
            tmp_path = tmp.name
        img = Image.open(tmp_path)
        text = pytesseract.image_to_string(img)
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return text or ""
    except Exception:
        LOG.debug("Image OCR failed", exc_info=True)
    return ""

def extract_text_from_bytes(b: bytes, url: str) -> str:
    url = url or ""
    ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf_bytes(b)
    if ext == ".docx":
        return extract_text_from_docx_bytes(b)
    if ext in (".xlsx", ".xls"):
        return extract_text_from_xlsx_bytes(b)
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff"):
        return extract_text_from_image_bytes(b)
    try:
        return b.decode("utf-8", errors="ignore")
    except Exception:
        return ""

# ---------------------------
# Validation (MX lookup)
# ---------------------------
def mx_lookup_sync(domain: str, timeout: int = 5) -> List[str]:
    if not DNSPY_AVAILABLE:
        return []
    try:
        ans = dns.resolver.resolve(domain, 'MX', lifetime=timeout)
        exch = [r.exchange.to_text() for r in ans]
        return exch
    except Exception:
        return []

async def mx_lookup(domain: str, timeout: int = 5) -> List[str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(THREAD_POOL, mx_lookup_sync, domain, timeout)

# ---------------------------
# FetcherExpanded
# ---------------------------
class FetcherExpanded:
    def __init__(self, playwright_pool: Optional[PlaywrightPool] = None, timeout: int = 20, ua_rotation: bool = True, proxy_manager: Optional[ProxyManager] = None):
        self.playwright_pool = playwright_pool
        self.timeout = timeout
        self.ua_rotation = ua_rotation
        self.proxy_manager = proxy_manager or ProxyManager()

    def _choose_ua(self) -> str:
        if not self.ua_rotation:
            return USER_AGENTS[0]
        return USER_AGENTS[int(time.time() * 1000) % len(USER_AGENTS)]

    async def _inject_fetch_capture(self, page):
        try:
            await page.add_init_script(
                """
                (() => {
                  if (window.__cap_wrapped) return;
                  window.__cap_wrapped = true;
                  window.__capturedXHR = window.__capturedXHR || [];
                  const _fetch = window.fetch;
                  window.fetch = function(...args) {
                    return _fetch.apply(this, args).then(res => {
                      try { res.clone().text().then(t=>window.__capturedXHR.push(t)).catch(()=>{}); } catch(e) {}
                      return res;
                    });
                  };
                  const _open = XMLHttpRequest.prototype.open;
                  XMLHttpRequest.prototype.open = function() {
                    this.addEventListener('load', function(){
                      try { window.__capturedXHR.push(this.responseText || '') } catch(e){}
                    });
                    return _open.apply(this, arguments);
                  };
                })();
                """
            )
        except Exception:
            LOG.debug("Failed to inject fetch capture script", exc_info=True)

    async def fetch_with_playwright(self, url: str, capture_xhr: bool = True, click_reveal: bool = False) -> Tuple[str, List[str]]:
        """Return (combined_text, list_of_captured_xhr_texts)"""
        if not PLAYWRIGHT_AVAILABLE or not self.playwright_pool:
            return "", []
        ctx = await self.playwright_pool.get_context()
        page = await ctx.new_page()
        xhr_texts: List[str] = []
        script_texts: List[str] = []
        try:
            ua = self._choose_ua()
            try:
                await ctx.set_extra_http_headers({"User-Agent": ua})
            except Exception:
                pass

            if capture_xhr:
                async def on_resp(resp):
                    try:
                        if resp.status != 200:
                            return
                        ctype = resp.headers.get("content-type", "").lower()
                        if any(x in ctype for x in ("application/json", "application/javascript", "text/", "application/xml")):
                            try:
                                t = await resp.text()
                                xhr_texts.append(t)
                            except Exception:
                                pass
                    except Exception:
                        pass

                page.on("response", on_resp)
                await self._inject_fetch_capture(page)

            try:
                await page.goto(url, timeout=self.timeout * 1000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=min(self.timeout * 1000, 10000))
                except Exception:
                    pass
                await asyncio.sleep(0.9)
            except PlayTimeoutError:
                LOG.debug("Playwright timeout for %s", url)
            except Exception as e:
                LOG.debug("Playwright goto exception %s -> %s", url, e)

            if click_reveal:
                try:
                    btns = await page.query_selector_all("text=/show|reveal|email|contact|@/i")
                    for b in btns[:4]:
                        try:
                            await b.click(timeout=1500)
                            await asyncio.sleep(0.25)
                        except Exception:
                            pass
                except Exception:
                    pass

            collected_texts: List[str] = []
            try:
                html_content = await page.content()
                collected_texts.append(html_content or "")
            except Exception:
                pass

            try:
                body_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
                if body_text:
                    collected_texts.append(body_text)
            except Exception:
                pass

            try:
                dom_dump = await page.evaluate(
                    """() => {
                        function collect(node){
                          let out = [];
                          if(node.nodeType === Node.TEXT_NODE){
                            out.push(node.textContent || '');
                          } else {
                            if(node.attributes){
                              for(const a of node.attributes) out.push(a.value || '');
                            }
                            const children = node.shadowRoot ? Array.from(node.shadowRoot.childNodes) : Array.from(node.childNodes || []);
                            for(const c of children) out = out.concat(collect(c));
                          }
                          return out;
                        }
                        return collect(document.documentElement).join('\\n');
                    }"""
                )
                if dom_dump:
                    collected_texts.append(dom_dump)
            except Exception:
                pass

            try:
                for frame in page.frames:
                    try:
                        fhtml = await frame.content()
                        if fhtml:
                            collected_texts.append(fhtml)
                        ftext = await frame.evaluate("() => document.body ? document.body.innerText : ''")
                        if ftext:
                            collected_texts.append(ftext)
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                scripts = await page.query_selector_all("script")
                for s in scripts[:80]:
                    try:
                        txt = await s.inner_text()
                        if txt:
                            script_texts.append(txt)
                    except Exception:
                        pass
                try:
                    jsonld = await page.evaluate(
                        """() => Array.from(document.querySelectorAll('script[type="application/ld+json"]')).map(s=>s.textContent).join('\\n')"""
                    )
                    if jsonld:
                        collected_texts.append(jsonld)
                except Exception:
                    pass
            except Exception:
                pass

            try:
                captured_in_page = await page.evaluate("() => (window.__capturedXHR || []).slice(0,50).join('\\n')")
                if captured_in_page:
                    xhr_texts.append(captured_in_page)
            except Exception:
                pass

            combined = "\n".join(collected_texts + script_texts + xhr_texts)
            try:
                await page.context.close()
            except Exception:
                pass
            await self.playwright_pool.release_context(ctx)
            return combined, xhr_texts
        except Exception as e:
            LOG.debug("Playwright fetch failed %s -> %s", url, e)
            with suppress(Exception):
                await page.close()
            with suppress(Exception):
                await self.playwright_pool.release_context(ctx)
            return "", []

    async def fetch_with_aiohttp(self, url: str) -> str:
        if not AIOHTTP_AVAILABLE:
            return ""
        headers = {"User-Agent": self._choose_ua()}
        try:
            conn = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(headers=headers, connector=conn) as sess:
                async with sess.get(url, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        try:
                            return await resp.text()
                        except Exception:
                            raw = await resp.read()
                            return raw.decode(errors="ignore")
        except Exception as e:
            LOG.debug("aiohttp fetch error %s -> %s", url, e)
        return ""

    def fetch_with_requests(self, url: str) -> str:
        if not REQUESTS_AVAILABLE:
            return ""
        headers = {"User-Agent": self._choose_ua()}
        try:
            r = requests.get(url, timeout=self.timeout, headers=headers)
            if r.status_code == 200:
                return r.text
        except Exception as e:
            LOG.debug("requests fetch error %s -> %s", url, e)
        return ""

    async def fetch_bytes(self, url: str) -> bytes:
        if AIOHTTP_AVAILABLE:
            headers = {"User-Agent": self._choose_ua()}
            try:
                conn = aiohttp.TCPConnector(ssl=False)
                async with aiohttp.ClientSession(headers=headers, connector=conn) as sess:
                    async with sess.get(url, timeout=self.timeout) as resp:
                        if resp.status == 200:
                            return await resp.read()
            except Exception:
                pass
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(THREAD_POOL, lambda: self.fetch_bytes_requests_sync(url))

    def fetch_bytes_requests_sync(self, url: str) -> bytes:
        if not REQUESTS_AVAILABLE:
            return b""
        try:
            r = requests.get(url, timeout=self.timeout)
            if r.status_code == 200:
                return r.content
        except Exception:
            pass
        return b""

    async def fetch(self, url: str, click_reveal: bool = False) -> str:
        content = ""
        if PLAYWRIGHT_AVAILABLE and self.playwright_pool:
            try:
                content, _ = await self.fetch_with_playwright(url, capture_xhr=True, click_reveal=click_reveal)
                if content:
                    return content
            except Exception:
                LOG.debug("playwright exception", exc_info=True)
        if AIOHTTP_AVAILABLE:
            try:
                content = await self.fetch_with_aiohttp(url)
                if content:
                    return content
            except Exception:
                pass
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(THREAD_POOL, self.fetch_with_requests, url)
        return content or ""

# ---------------------------
# ScraperEngine
# ---------------------------
class ScraperEngine:
    def __init__(
        self,
        playwright_pool: Optional[PlaywrightPool] = None,
        concurrency: int = 6,
        email_limit: int = 30,
        timeout: int = 30,
        rate_delay: float = 0.08,
        proxy_manager: Optional[ProxyManager] = None,
        safe_mode: bool = False,
        enable_ocr: bool = True,
        enable_smtp_probe: bool = False,
        contact_depth: int = 2,
    ):
        self.playwright_pool = playwright_pool
        self.concurrency = concurrency
        self.email_limit = email_limit
        self.timeout = timeout
        self.rate_delay = rate_delay
        self.proxy_manager = proxy_manager or ProxyManager()
        self.safe_mode = safe_mode
        self.enable_ocr = enable_ocr and OCR_AVAILABLE
        self.enable_smtp_probe = enable_smtp_probe
        self.contact_depth = contact_depth
        self.fetcher = FetcherExpanded(self.playwright_pool, timeout=self.timeout, ua_rotation=True, proxy_manager=self.proxy_manager)
        self.results: Dict[str, List[str]] = {}
        self._cancel_event = asyncio.Event()
        self._host_rate: Dict[str, float] = {}

    def cancel(self):
        self._cancel_event.set()

    async def _polite_wait(self, url: str):
        host = urllib.parse.urlparse(url).netloc
        min_delay = 0.12
        last = self._host_rate.get(host, 0)
        elapsed = time.time() - last
        if elapsed < min_delay:
            await asyncio.sleep(min_delay - elapsed)
        self._host_rate[host] = time.time()

    async def _gather_from_html(self, base_url: str, html_content: str) -> Tuple[Set[str], Set[str]]:
        emails = set()
        contact_links = set()
        if not html_content:
            return emails, contact_links

        for m in re.findall(MAILTO_RE, html_content):
            emails.add(m)

        emails |= extract_emails(html_content)

        for href in re.findall(r'href\s*=\s*["\']([^"\']+)["\']', html_content, flags=re.I):
            low = href.lower()
            if any(k in low for k in ("contact", "about", "team", "privacy", "legal", "support", "imprint", "office")):
                contact_links.add(href)
            if any(low.endswith(ext) for ext in (".pdf", ".docx", ".xlsx", ".xls", ".png", ".jpg", ".jpeg")):
                contact_links.add(href)

        for js in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', html_content, flags=re.I):
            try:
                obj = json.loads(js)
                def traverse(o):
                    found = set()
                    if isinstance(o, dict):
                        for k, v in o.items():
                            if isinstance(v, str) and "@" in v:
                                found |= set(re.findall(EMAIL_RE, v))
                            elif isinstance(v, (list, dict)):
                                found |= traverse(v)
                    elif isinstance(o, list):
                        for x in o:
                            found |= traverse(x)
                    elif isinstance(o, str):
                        if "@" in o:
                            found |= set(re.findall(EMAIL_RE, o))
                    return found
                emails |= traverse(obj)
            except Exception:
                pass

        return emails, contact_links

    async def process_one(self, raw_url: str) -> List[str]:
        if self._cancel_event.is_set():
            return []
        url = raw_url.strip()
        if not url:
            return []
        if not re.match(r'^https?://', url):
            url = "http://" + url

        await self._polite_wait(url)

        content = await self.fetcher.fetch(url, click_reveal=False)
        if not content and PLAYWRIGHT_AVAILABLE:
            content, _ = await self.fetcher.fetch_with_playwright(url, capture_xhr=True, click_reveal=True)

        if not content:
            return []

        emails = set()
        emails |= set(re.findall(MAILTO_RE, content))
        emails |= extract_emails(content)

        for m in re.findall(r'(\{[\s\S]{30,}\})', content):
            try:
                o = json.loads(m)
                def traverse_json(o2):
                    found = set()
                    if isinstance(o2, dict):
                        for k, v in o2.items():
                            if isinstance(v, str) and "@" in v:
                                found |= set(re.findall(EMAIL_RE, v))
                            else:
                                found |= traverse_json(v)
                    elif isinstance(o2, list):
                        for x in o2:
                            found |= traverse_json(x)
                    elif isinstance(o2, str):
                        if "@" in o2:
                            found |= set(re.findall(EMAIL_RE, o2))
                    return found
                emails |= traverse_json(o)
            except Exception:
                pass

        contact_links = set()
        file_links = set()
        for href in re.findall(r'href\s*=\s*["\']([^"\']+)["\']', content, flags=re.I):
            low = href.lower()
            if any(k in low for k in ("contact", "about", "team", "privacy", "legal", "support", "imprint")):
                contact_links.add(href)
            if any(low.endswith(ext) for ext in (".pdf", ".docx", ".xlsx", ".xls", ".png", ".jpg", ".jpeg")):
                file_links.add(href)

        try:
            parsed = urllib.parse.urlparse(url)
            sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
            scont = await self.fetcher.fetch(sitemap_url)
            for u in re.findall(r'<loc>([^<]+)</loc>', scont):
                if any(k in u.lower() for k in ("contact", "about", "team", "privacy", "support")):
                    contact_links.add(u)
        except Exception:
            pass

        seen = set()
        queue = deque()
        def norm_link(href):
            if re.match(r'^https?://', href):
                return href
            try:
                return urllib.parse.urljoin(url, href)
            except Exception:
                return href

        for cl in list(contact_links)[:12]:
            queue.append((norm_link(cl), 0))
        for f in list(file_links)[:12]:
            queue.append((norm_link(f), 0))

        while queue:
            if self._cancel_event.is_set():
                break
            link, d = queue.popleft()
            if link in seen or d > self.contact_depth:
                continue
            seen.add(link)
            await self._polite_wait(link)
            try:
                if any(link.lower().endswith(ext) for ext in (".pdf", ".docx", ".xlsx", ".xls", ".png", ".jpg", ".jpeg")):
                    try:
                        raw_bytes = await self.fetcher.fetch_bytes(link)
                        if raw_bytes:
                            txt = await asyncio.get_event_loop().run_in_executor(THREAD_POOL, extract_text_from_bytes, raw_bytes, link)
                            emails |= extract_emails(txt)
                    except Exception:
                        pass
                    continue
                page_text = await self.fetcher.fetch(link, click_reveal=False)
                if not page_text:
                    continue
                emails |= extract_emails(page_text)

                for href in re.findall(r'href\s*=\s*["\']([^"\']+)["\']', page_text, flags=re.I):
                    low = href.lower()
                    if any(k in low for k in ("contact", "about", "team", "privacy", "support", "imprint")):
                        nl = norm_link(href)
                        if nl not in seen and d + 1 <= self.contact_depth:
                            queue.append((nl, d + 1))
                    if any(low.endswith(ext) for ext in (".pdf", ".docx", ".xlsx", ".xls", ".png", ".jpg", ".jpeg")):
                        nl = norm_link(href)
                        if nl not in seen:
                            queue.append((nl, d + 1))
            except Exception:
                LOG.debug("BFS crawl failed for %s", link, exc_info=True)
            await asyncio.sleep(self.rate_delay)

        try:
            for m in re.findall(r'String\.fromCharCode\([^\)]+\)', content):
                try:
                    dec = _decode_fromcharcodes(m)
                    emails |= set(re.findall(EMAIL_RE, dec))
                except Exception:
                    pass
            for b64 in re.findall(r'([A-Za-z0-9+/=]{16,})', content):
                try:
                    decoded = base64.b64decode(b64 + '==' if len(b64) % 4 else b64).decode('utf-8', errors='ignore')
                    if '@' in decoded:
                        emails |= set(re.findall(EMAIL_RE, decoded))
                except Exception:
                    pass
        except Exception:
            pass

        if self.enable_ocr:
            try:
                imgs = set(re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content, flags=re.I))
                for img_src in list(imgs)[:8]:
                    if any(k in img_src.lower() for k in ("contact", "email", "info", "support")):
                        target = img_src if re.match(r'^https?://', img_src) else urllib.parse.urljoin(url, img_src)
                        try:
                            raw = await self.fetcher.fetch_bytes(target)
                            if raw:
                                txt = await asyncio.get_event_loop().run_in_executor(THREAD_POOL, extract_text_from_image_bytes, raw)
                                emails |= extract_emails(txt)
                        except Exception:
                            pass
            except Exception:
                pass

        filtered = [e for e in emails if e and e.split("@")[-1].lower() not in DISPOSABLE_DOMAINS]
        final = []
        for e in sorted(filtered):
            if len(final) >= self.email_limit:
                break
            try:
                domain = e.split("@", 1)[1]
            except Exception:
                pass
            final.append(e)

        self.results[raw_url] = final
        await self._write_incremental(raw_url, final)
        await asyncio.sleep(self.rate_delay)
        return final

    async def _write_incremental(self, url: str, emails: List[str]):
        ts = int(time.time())
        file = RESULTS_DIR / f"emails_{safe_filename(url)}_{ts}.csv"
        try:
            with open(file, "w", newline="", encoding="utf-8") as f:
                wr = csv.writer(f)
                wr.writerow([url] + emails)
        except Exception:
            LOG.debug("Failed to write incremental file", exc_info=True)

    async def run(self, urls: List[str], progress_cb: Optional[Callable] = None):
        self._cancel_event.clear()
        sem = asyncio.Semaphore(self.concurrency)
        total = len(urls)
        done = 0

        async def worker(u):
            nonlocal done
            async with sem:
                if self._cancel_event.is_set():
                    return
                res = []
                try:
                    res = await self.process_one(u)
                except Exception:
                    LOG.exception("process_one failed for %s", u)
                done += 1
                if progress_cb:
                    await progress_cb(done, total, u, res)

        await asyncio.gather(*[worker(u) for u in urls])
        return self.results

# ---------------------------
# FastAPI server & WebSocket
# ---------------------------
db = Database()
proxy_manager = ProxyManager()
play_pool = PlaywrightPool(headless=True, max_contexts=3) if PLAYWRIGHT_AVAILABLE else None
ACTIVE_WS: Set[WebSocket] = set()
SCRAPERS: Dict[str, ScraperEngine] = {}
JOB_LOCK = threading.Lock()

@asynccontextmanager
async def lifespan(app: FastAPI):
    LOG.info("✅ Backend server starting...")
    LOG.info("📊 Database initialized")
    yield
    LOG.info("🛑 Backend server shutting down...")
    if play_pool:
        try:
            await play_pool.close()
        except Exception:
            pass
    THREAD_POOL.shutdown(wait=False)

app = FastAPI(lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "playwright": PLAYWRIGHT_AVAILABLE, "aiohttp": AIOHTTP_AVAILABLE, "requests": REQUESTS_AVAILABLE})

@app.get("/")
async def root():
    try:
        return FileResponse("index.html")
    except Exception:
        return HTMLResponse("<h3>index.html not found</h3>", status_code=404)

@app.get("/admin")
async def admin_page():
    try:
        return FileResponse("admin.html")
    except Exception:
        return HTMLResponse("<h3>admin.html not found</h3>", status_code=404)

# Serve static files (CSS and JS)
@app.get("/style.css")
async def serve_css():
    try:
        return FileResponse("style.css", media_type="text/css")
    except Exception:
        raise HTTPException(status_code=404, detail="style.css not found")

@app.get("/app.js")
async def serve_js():
    try:
        return FileResponse("app.js", media_type="application/javascript")
    except Exception:
        raise HTTPException(status_code=404, detail="app.js not found")

# User management endpoints
@app.post("/api/register")
async def register_user(data: dict):
    user_id = data.get("user_id")
    name = data.get("name")
    created_at = data.get("created_at", datetime.now().isoformat())
    
    if not user_id or not name:
        raise HTTPException(status_code=400, detail="Missing user_id or name")
    
    db.register_user(user_id, name, created_at)
    return {"status": "success", "message": "User registered"}

@app.post("/api/check-blocked")
async def check_blocked(data: dict):
    user_id = data.get("user_id")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user_id")
    
    is_blocked = db.is_user_blocked(user_id)
    db.update_user_activity(user_id)
    
    return {"is_blocked": is_blocked}

@app.get("/api/users")
async def get_users():
    users = db.get_all_users()
    return {"users": users}

@app.post("/api/block-user")
async def block_user(data: dict):
    user_id = data.get("user_id")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user_id")
    
    db.block_user(user_id)
    return {"status": "success", "message": "User blocked"}

@app.post("/api/unblock-user")
async def unblock_user(data: dict):
    user_id = data.get("user_id")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user_id")
    
    db.unblock_user(user_id)
    return {"status": "success", "message": "User unblocked"}

@app.post("/api/activity")
async def log_activity(data: dict):
    user_id = data.get("user_id")
    user_name = data.get("user_name")
    job_id = data.get("job_id")
    urls = data.get("urls")
    total_emails = data.get("total_emails", 0)
    status = data.get("status")
    
    if not user_id or not user_name:
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    db.log_activity(user_id, user_name, job_id, urls, total_emails, status)
    return {"status": "success"}

@app.get("/api/activity")
async def get_activity():
    activities = db.get_recent_activity()
    return {"activities": activities}

@app.get("/api/user-activity/{user_id}")
async def get_user_activity(user_id: str):
    activities = db.get_user_activity(user_id)
    return {"activities": activities}

@app.get("/jobs")
async def list_jobs():
    jobs = db.get_all_jobs()
    for job in jobs:
        if job.get("results"):
            try:
                job["results"] = json.loads(job["results"])
            except:
                job["results"] = {}
    return jobs

@app.get("/job/{job_id}")
async def get_job(job_id: str):
    jobs = db.get_all_jobs()
    job = next((j for j in jobs if j["id"] == job_id), None)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.get("results"):
        try:
            job["results"] = json.loads(job["results"])
        except:
            job["results"] = {}
    
    return job

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ACTIVE_WS.add(ws)
    LOG.info("WebSocket connected (clients=%d)", len(ACTIVE_WS))
    
    current_user_id = "anonymous"
    current_user_name = "Anonymous User"
    
    try:
        while True:
            try:
                data = await ws.receive_text()
            except WebSocketDisconnect:
                break
            if not data:
                continue
            
            # Handle user registration
            if data.startswith("user_id:"):
                try:
                    user_data = json.loads(data[8:])
                    current_user_id = user_data.get("user_id", "anonymous")
                    current_user_name = user_data.get("user_name", "Anonymous User")
                    
                    # Check if user is blocked
                    if db.is_user_blocked(current_user_id):
                        await ws.send_text(json.dumps({
                            "type": "error",
                            "msg": "Your account has been blocked. Please contact the administrator."
                        }))
                    else:
                        db.update_user_activity(current_user_id)
                except Exception as e:
                    LOG.exception("User ID parsing failed")
            
            # Handle job start
            elif data.startswith("start"):
                payload = data[len("start"):].strip()
                urls = []
                try:
                    parsed = json.loads(payload)
                    if isinstance(parsed, list):
                        urls = [str(x).strip() for x in parsed if str(x).strip()]
                    elif isinstance(parsed, str):
                        urls = [l.strip() for l in parsed.splitlines() if l.strip()]
                except Exception:
                    if "\n" in payload:
                        urls = [l.strip() for l in payload.splitlines() if l.strip()]
                    elif "," in payload:
                        urls = [l.strip() for l in payload.split(",") if l.strip()]
                    else:
                        urls = [payload.strip()]

                if not urls:
                    await ws.send_text(json.dumps({"type": "error", "msg": "No URLs"}))
                    continue

                # Check if user is blocked before starting job
                if db.is_user_blocked(current_user_id):
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "msg": "Your account has been blocked. Please contact the administrator."
                    }))
                    continue

                # Create job record
                job_id = f"job_{uuid.uuid4().hex[:8]}"
                db.create_job(job_id, current_user_id, len(urls))
                
                # Init playwright pool if needed
                if play_pool and not play_pool._inited:
                    try:
                        await play_pool.init()
                    except Exception:
                        LOG.exception("Playwright init failed")

                # Create scraper engine
                scraper = ScraperEngine(play_pool, concurrency=6, email_limit=30, timeout=30, safe_mode=False, enable_ocr=True)
                SCRAPERS[job_id] = scraper
                await ws.send_text(json.dumps({"type": "job_created", "job_id": job_id, "count": len(urls)}))

                async def progress_cb(done, total, current, emails):
                    try:
                        db.update_job(job_id, "running")
                    except Exception:
                        pass
                    payload = {"type": "progress", "job_id": job_id, "done": done, "total": total, "current": current, "emails": emails}
                    try:
                        await ws.send_text(json.dumps(payload))
                    except Exception:
                        pass

                try:
                    db.update_job(job_id, "running")
                    results = await scraper.run(urls, progress_cb)
                    
                    # Count total emails
                    total_emails = sum(len(v) for v in results.values())
                    
                    # Log activity
                    db.log_activity(
                        current_user_id,
                        current_user_name,
                        job_id,
                        ", ".join(urls[:3]) + ("..." if len(urls) > 3 else ""),
                        total_emails,
                        "completed"
                    )
                    
                    db.update_job(job_id, "finished", json.dumps(results))
                    try:
                        await ws.send_text(json.dumps({"type": "finished", "job_id": job_id, "results": results}))
                    except Exception:
                        pass
                    
                    # Send to external dashboard
                    try:
                        send_to_dashboard(job_id, "finished", results)
                    except Exception:
                        pass
                        
                except Exception:
                    LOG.exception("Scraper run exception")
                    db.update_job(job_id, "failed")
                    db.log_activity(current_user_id, current_user_name, job_id, ", ".join(urls[:3]), 0, "failed")
                    try:
                        await ws.send_text(json.dumps({"type": "error", "job_id": job_id, "msg": "scraper failed"}))
                    except Exception:
                        pass

            elif data.startswith("cancel"):
                jid = data[len("cancel"):].strip()
                s = SCRAPERS.get(jid)
                if s:
                    s.cancel()
                    db.update_job(jid, "cancelled")
                    await ws.send_text(json.dumps({"type": "cancelled", "job_id": jid}))
                else:
                    await ws.send_text(json.dumps({"type": "error", "msg": "job not found"}))
            else:
                # echo unknown
                await ws.send_text(json.dumps({"type": "echo", "msg": data}))

    except WebSocketDisconnect:
        LOG.info("WebSocket disconnected")
    except Exception:
        LOG.exception("WS error")
    finally:
        with suppress(Exception):
            ACTIVE_WS.remove(ws)

if __name__ == "__main__":
    LOG.info("🚀 Starting Email Scraper Backend Server")
    LOG.info("📍 Backend: http://localhost:%s", PORT)
    LOG.info("🔌 WebSocket: ws://localhost:%s/ws", PORT)
    LOG.info("👑 Admin Dashboard: http://localhost:%s/admin", PORT)
    LOG.info("\n⚡ Server is running... Press CTRL+C to stop\n")
    
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
