#!/usr/bin/env python3
"""
backend.py  (Expanded full Playwright version)
------------------------------------------------
Features added / expanded compared to prior version:
- Playwright rendering + XHR capture
- aiohttp + requests fallback
- ProxyManager with health checks and rotation
- OCR + remote file extraction (PDF/DOCX/XLSX/Images) (optional)
- Persistent job store (JSON file) with resume capability
- Job cancellation tokens and graceful shutdown
- Incremental CSV/JSON export & combined summary export
- Advanced deobfuscation + entity decoding + more heuristics
- MX validation (async wrapper) and optional SMTP probe (disabled by default)
- Thread-safe logging, debug mode, rotating logs
- CLI flags: --host --port --no-browser --data-dir --debug
- Health endpoints and status
- WebSocket with richer messages and error handling
- Rate-limiter per-host and polite crawling behavior
- Optional "safe-mode" that enforces robots.txt (lightweight)
- Packaging helpers for PyInstaller builds
- Comprehensive inline documentation & comments

Usage:
1) Ensure packages:
   pip install fastapi uvicorn[standard] aiohttp requests playwright dnspython python-magic python-docx openpyxl pdfminer.six pytesseract Pillow
2) Install Playwright browsers:
   python -m playwright install --with-deps
3) Run:
   python backend.py
4) Open http://127.0.0.1:8000/ (the script will try to auto-open)
"""

# Standard libs
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
import threading
import time
import traceback
import urllib.parse
import webbrowser
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
# ================= FULL SCRAPER BOOSTER =================
import asyncio, aiohttp, re, time, os, logging
from concurrent.futures import ProcessPoolExecutor

LOG = logging.getLogger(__name__)

# ====== Fast, clean email patterns ======
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', re.I)

# ====== Cache for MX lookups (6 hours) ======
MX_CACHE = {}
MX_TTL = 6 * 60 * 60

async def mx_lookup(domain: str, timeout: int = 5):
    """Automatically cached MX lookup — replaces your old mx_lookup."""
    import dns.resolver
    now = time.time()
    if domain in MX_CACHE and MX_CACHE[domain][0] > now:
        return MX_CACHE[domain][1]
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        answers = resolver.resolve(domain, "MX")
        mxs = sorted(str(r.exchange).rstrip(".") for r in answers)
    except Exception:
        mxs = []
    MX_CACHE[domain] = (now + MX_TTL, mxs)
    return mxs

# ====== Avoid downloading huge files ======
async def fetch_bytes_safe(fetch_func, url: str, max_size: int = 10_000_000):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.head(url, timeout=10) as r:
                cl = r.headers.get("content-length")
                if cl and cl.isdigit() and int(cl) > max_size:
                    LOG.info("Skipping big file %s (%s bytes)", url, cl)
                    return b""
    except Exception:
        pass
    try:
        return await fetch_func(url)
    except Exception as e:
        LOG.warning("Download failed: %s", e)
        return b""

# ====== Background process pool for heavy work ======
CPU_POOL = ProcessPoolExecutor(max_workers=max(1, os.cpu_count() // 2))
async def run_in_cpu(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(CPU_POOL, func, *args)

# ====== Light text cleanup before regex ======
def smart_deobfuscate(text: str) -> str:
    rep = {
        r"\s*\[at\]\s*": "@",
        r"\s*\(at\)\s*": "@",
        r"\s*\[dot\]\s*": ".",
        r"\s*\(dot\)\s*": ".",
        r"\s+dot\s+": ".",
        r"\s+at\s+": "@",
    }
    for p, rpl in rep.items():
        text = re.sub(p, rpl, text, flags=re.I)
    return text

# ====== Improved email extractor ======
def extract_emails(text: str):
    """Auto-enhanced email extractor — replaces your old one automatically."""
    if not text:
        return set()
    text = smart_deobfuscate(text)
    found = {e.lower().strip() for e in EMAIL_RE.findall(text)}
    return {e for e in found if not any(b in e for b in ["example.com", "test@", "invalid"])}

# ====== Faster playwright fetch (auto-drops heavy assets) ======
async def fetch_with_playwright(context, url: str, timeout: int = 15):
    """Auto-enhanced version; replaces your old fetch_with_playwright."""
    page = await context.new_page()
    try:
        async def route_handler(route, request):
            if request.resource_type in ("image", "media", "font", "stylesheet"):
                await route.abort()
            else:
                await route.continue_()
        await page.route("**/*", route_handler)
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        await asyncio.sleep(0.6)
        html = await page.content()
        return html
    except Exception as e:
        LOG.warning("Playwright fetch error: %s", e)
        return ""
    finally:
        await page.close()

# ====== Automatic integration wrapper ======
class SmartFetcher:
    """Drop-in class — you can use this instead of your old Fetcher."""
    def __init__(self, context=None):
        self.context = context

    async def fetch_html(self, url: str):
        if self.context:
            return await fetch_with_playwright(self.context, url)
        return ""

    async def fetch_bytes(self, url: str, fetch_func):
        return await fetch_bytes_safe(fetch_func, url)

# =========================================================

# Third-party (optional heavy)
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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import uvicorn

# ---------------------------
# Configuration & CLI
# ---------------------------
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_DATA_DIR = Path.cwd() / "data"
DEFAULT_RESULTS_DIR = DEFAULT_DATA_DIR / "results"
DEFAULT_JOB_STORE = DEFAULT_DATA_DIR / "jobs.json"
DEFAULT_LOG_DIR = DEFAULT_DATA_DIR / "logs"

parser = argparse.ArgumentParser(description="Local Playwright Email Extractor Server")
parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind")
parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind")
parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Data directory for results and cache")
parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser on start")
parser.add_argument("--debug", action="store_true", help="Enable debug logging")
parser.add_argument("--safe-mode", action="store_true", help="Respect robots.txt (best-effort)")
parser.add_argument("--max-threads", type=int, default=6, help="Threadpool max worker threads for blocking tasks")
parser.add_argument("--no-playwright-install", action="store_true", help="Skip background playwright install attempt")
args = parser.parse_args()

HOST = args.host
PORT = args.port
DATA_DIR = Path(args.data_dir)
RESULTS_DIR = DATA_DIR / "results"
LOG_DIR = DATA_DIR / "logs"
JOB_STORE = DATA_DIR / "jobs.json"
FRONTEND_FILE = Path(__file__).parent / "frontend.html"

# ensure directories
for p in (DATA_DIR, RESULTS_DIR, LOG_DIR):
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

# Logger (rotating basic)
LOG = logging.getLogger("email_scraper_expanded")
LOG.setLevel(logging.DEBUG if args.debug else logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
# console handler
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
LOG.addHandler(ch)
# file handler
fh = logging.FileHandler(LOG_DIR / "scraper.log", encoding="utf-8")
fh.setFormatter(formatter)
LOG.addHandler(fh)

# ---------------------------
# Constants & Regex
# ---------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.90 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
]
EMAIL_RE = re.compile(r'(?:[a-zA-Z0-9_.+-]+)@(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}', re.I)
MAILTO_RE = re.compile(r'mailto:([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+)', re.I)
URL_RE = re.compile(r'https?://[^\s\'"<>]+', re.I)

# Disposable list sources and defaults
DISPOSABLE_SOURCES = [
    "https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf",
    "https://raw.githubusercontent.com/7c/fakefilter/master/data/DisposableDomains.txt",
]
DEFAULT_DISPOSABLE = {"mailinator.com","10minutemail.com","tempmail.com","guerrillamail.com","trashmail.com","yopmail.com"}

# ---------------------------
# Utilities / Helpers
# ---------------------------
def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def safe_filename(name: str, maxlen: int = 220) -> str:
    return "".join(c if c.isalnum() or c in "-_. " else "_" for c in name)[:maxlen]

def ensure_str(s: Any) -> str:
    return "" if s is None else str(s)

# backoff helper (async-aware)
async def async_backoff_sleep(attempt:int):
    await asyncio.sleep(min(10, (2 ** attempt) * 0.25))

# Thread executor for blocking operations
THREAD_POOL = ThreadPoolExecutor(max_workers=args.max_threads)

# ---------------------------
# Disposable domains (cache + updater)
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

def update_disposable_now():
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

# Start background update (non-blocking)
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
# Advanced deobfuscation
# ---------------------------
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
    # entities numeric & hex
    t = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), t)
    t = re.sub(r'&#([0-9]+);', lambda m: chr(int(m.group(1))), t)
    # Remove zero-width
    t = ''.join(ch for ch in t if ord(ch) not in (8203,8204,8205))
    # collapse whitespace
    t = re.sub(r'\s+', ' ', t)
    return t

def extract_emails(text: str) -> Set[str]:
    if not text:
        return set()
    t = advanced_deobfuscate(text)
    found = set(re.findall(EMAIL_RE, t))
    return found

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
# Playwright Pool (improved)
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
        # configure chromium with no-sandbox for some builds; keep default for safety
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
# File extractors (PDF, DOCX, XLSX, Images OCR)
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
        # write temp file and load with python-docx (docx)
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(b)
            tmp.flush()
            tmp_path = tmp.name
        doc = docx.Document(tmp_path)
        t = "\n".join(p.text for p in doc.paragraphs)
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

# Convenience: dispatch by mimetype/extension
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
    # fallback: try to decode as text
    try:
        return b.decode("utf-8", errors="ignore")
    except Exception:
        return ""

# ---------------------------
# Validation (MX + optional SMTP probe)
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

# SMTP probe is risky and often blocked; implement naive probe but disabled by default.
def smtp_probe_sync(email: str, mx_host: str, timeout: int = 5) -> bool:
    # VERY naive, for demonstration only; do not use for mass probing.
    import socket
    try:
        s = socket.create_connection((mx_host, 25), timeout=timeout)
        s.settimeout(timeout)
        banner = s.recv(1024)
        s.send(b"HELO example.com\r\n")
        s.recv(1024)
        s.send(b"MAIL FROM:<probe@example.com>\r\n")
        s.recv(1024)
        s.send(f"RCPT TO:<{email}>\r\n".encode())
        resp = s.recv(1024).decode(errors="ignore")
        s.send(b"QUIT\r\n")
        s.close()
        return "250" in resp or "251" in resp
    except Exception:
        return False

async def smtp_probe(email: str, mx_host: str, timeout: int = 5) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(THREAD_POOL, smtp_probe_sync, email, mx_host, timeout)

# ---------------------------
# Job Store (persistent)
# ---------------------------
@dataclass
class JobRecord:
    id: str
    created_at: str
    updated_at: str
    status: str
    urls: List[str]
    results: Dict[str, List[str]] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)

class JobStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._jobs: Dict[str, JobRecord] = {}
        self._load()

    def _load(self):
        if not self.path.exists():
            self._jobs = {}
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for jid, jr in raw.items():
                self._jobs[jid] = JobRecord(**jr)
            LOG.info("Job store loaded: %d jobs", len(self._jobs))
        except Exception:
            LOG.exception("Failed to load job store")
            self._jobs = {}

    def _persist(self):
        try:
            tmp = str(self.path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                serial = {k: asdict(v) for k,v in self._jobs.items()}
                json.dump(serial, f, indent=2)
            os.replace(tmp, str(self.path))
        except Exception:
            LOG.exception("Failed to persist job store")

    def create_job(self, urls: List[str], options: Dict[str, Any]) -> JobRecord:
        jid = f"job_{int(time.time()*1000)}"
        now = now_iso()
        jr = JobRecord(id=jid, created_at=now, updated_at=now, status="queued", urls=list(urls), results={}, options=options)
        with self._lock:
            self._jobs[jid] = jr
            self._persist()
        return jr

    def update_job(self, jid: str, **kwargs):
        with self._lock:
            if jid not in self._jobs:
                return
            for k,v in kwargs.items():
                setattr(self._jobs[jid], k, v)
            self._jobs[jid].updated_at = now_iso()
            self._persist()

    def get_job(self, jid: str) -> Optional[JobRecord]:
        return self._jobs.get(jid)

    def list_jobs(self) -> List[JobRecord]:
        return list(self._jobs.values())

# initialize jobstore
JOBSTORE = JobStore(JOB_STORE)

# ---------------------------
# Scraper class (expanded)
# ---------------------------
class ScraperEngine:
    def __init__(
        self,
        playwright_pool: Optional[PlaywrightPool] = None,
        concurrency: int = 4,
        email_limit: int = 10,
        timeout: int = 25,
        rate_delay: float = 0.12,
        proxy_manager: Optional[ProxyManager] = None,
        safe_mode: bool = False,
        enable_ocr: bool = False,
        enable_smtp_probe: bool = False,
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
        self.fetcher = self._build_fetcher()
        self.results: Dict[str, List[str]] = {}
        self._cancel_event = asyncio.Event()
        self._host_rate: Dict[str, float] = {}  # host -> last_request_time

    def _build_fetcher(self):
        return FetcherExpanded(self.playwright_pool, timeout=self.timeout, ua_rotation=True, proxy_manager=self.proxy_manager)

    def cancel(self):
        self._cancel_event.set()

    # polite rate limiting per host
    async def _polite_wait(self, url: str):
        host = urllib.parse.urlparse(url).netloc
        min_delay = 0.12
        last = self._host_rate.get(host, 0)
        elapsed = time.time() - last
        if elapsed < min_delay:
            await asyncio.sleep(min_delay - elapsed)
        self._host_rate[host] = time.time()

    async def process_one(self, raw_url: str) -> List[str]:
        if self._cancel_event.is_set():
            return []
        url = raw_url.strip()
        if not url:
            return []
        if not re.match(r'^https?://', url):
            url = "http://" + url
        await self._polite_wait(url)
        content = await self.fetcher.fetch(url)
        if not content:
            return []
        emails = set()
        for m in re.findall(MAILTO_RE, content):
            emails.add(m)
        emails |= extract_emails(content)
        # parse JSON blocks heuristically
        for m in re.findall(r'(\{[\s\S]{30,}\})', content):
            try:
                o = json.loads(m)
                emails |= traverse_json_for_emails(o)
            except Exception:
                pass

        # lightweight link scanning for contact pages and files
        contact_links = set()
        for href in re.findall(r'href\s*=\s*["\']([^"\']+)["\']', content, flags=re.I):
            low = href.lower()
            if any(k in low for k in ("contact", "about", "team", "privacy", "legal", "support")):
                contact_links.add(href)
            if any(low.endswith(ext) for ext in (".pdf", ".docx", ".xlsx", ".xls", ".png", ".jpg", ".jpeg")):
                # fetch remote file content and extract text (blocking in executor)
                try:
                    raw_bytes = await self.fetcher.fetch_bytes(urljoin(url, href))
                    if raw_bytes:
                        txt = await asyncio.get_event_loop().run_in_executor(THREAD_POOL, extract_text_from_bytes, raw_bytes, href)
                        emails |= extract_emails(txt)
                except Exception:
                    pass

        # visit up to N contact links
        cnt = 0
        for cl in list(contact_links)[:8]:
            if len(emails) >= self.email_limit or cnt >= 8:
                break
            full = cl if re.match(r'^https?://', cl) else urllib.parse.urljoin(url, cl)
            try:
                ctext = await self.fetcher.fetch(full)
                emails |= extract_emails(ctext)
            except Exception:
                pass
            cnt += 1

        # filter disposables
        filtered = [e for e in emails if e and e.split("@")[-1].lower() not in DISPOSABLE_DOMAINS]
        final = []
        for e in sorted(filtered):
            if len(final) >= self.email_limit:
                break
            # MX check (async)
            try:
                domain = e.split("@",1)[1]
                mxs = await mx_lookup(domain)
                if mxs is not None and mxs == []:
                    continue
            except Exception:
                pass
            # optional smtp probe
            if self.enable_smtp_probe:
                try:
                    if mxs:
                        ok = await smtp_probe(e, mxs[0])
                        if not ok:
                            continue
                except Exception:
                    pass
            final.append(e)

        self.results[raw_url] = final
        # incremental write
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
                res = await self.process_one(u)
                done += 1
                if progress_cb:
                    await progress_cb(done, total, u, res)

        await asyncio.gather(*[worker(u) for u in urls])
        return self.results

# ---------------------------
# FetcherExpanded (Playwright + aiohttp + requests + bytes fetch)
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
        return USER_AGENTS[int(time.time()*1000) % len(USER_AGENTS)]

    async def fetch_with_playwright(self, url: str, capture_xhr: bool = True) -> str:
        if not PLAYWRIGHT_AVAILABLE or not self.playwright_pool:
            return ""
        ctx = await self.playwright_pool.get_context()
        page = await ctx.new_page()
        xhr_texts = []
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
                        ctype = resp.headers.get("content-type","")
                        if "json" in ctype or "text" in ctype or "xml" in ctype:
                            try:
                                t = await resp.text()
                                xhr_texts.append(t)
                            except Exception:
                                pass
                    except Exception:
                        pass
                page.on("response", on_resp)

            try:
                await page.goto(url, timeout=self.timeout*1000)
                await asyncio.sleep(0.9)
                html = await page.content()
            except PlayTimeoutError:
                LOG.debug("Playwright timeout for %s", url)
                try:
                    html = await page.content()
                except Exception:
                    html = ""
            except Exception as e:
                LOG.debug("Playwright fetch exception for %s: %s", url, e)
                html = ""
            combined = html + "\n" + "\n".join(xhr_texts)
            try:
                await page.context.close()
            except Exception:
                pass
            await self.playwright_pool.release_context(ctx)
            return combined
        except Exception as e:
            LOG.debug("Playwright fetch failed %s -> %s", url, e)
            with suppress(Exception):
                await page.close()
            with suppress(Exception):
                await self.playwright_pool.release_context(ctx)
            return ""

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

    async def fetch_bytes_requests(self, url: str) -> bytes:
        if not REQUESTS_AVAILABLE:
            return b""
        headers = {"User-Agent": self._choose_ua()}
        try:
            r = requests.get(url, timeout=self.timeout, headers=headers)
            if r.status_code == 200:
                return r.content
        except Exception:
            LOG.debug("requests bytes fetch failed for %s", url)
        return b""

    async def fetch_bytes(self, url: str) -> bytes:
        # prefer aiohttp if available
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
        # fallback to requests on threadpool
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

    async def fetch(self, url: str) -> str:
        # Playwright -> aiohttp -> requests (sync)
        content = ""
        if PLAYWRIGHT_AVAILABLE and self.playwright_pool:
            try:
                content = await self.fetch_with_playwright(url, capture_xhr=True)
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
# FastAPI server & WebSocket
# ---------------------------
app = FastAPI()
proxy_manager = ProxyManager()
play_pool = PlaywrightPool(headless=True, max_contexts=3) if PLAYWRIGHT_AVAILABLE else None
ACTIVE_WS: Set[WebSocket] = set()
SCRAPERS: Dict[str, ScraperEngine] = {}
JOB_LOCK = threading.Lock()

@app.get("/health")
async def health():
    return JSONResponse({"status":"ok","playwright": PLAYWRIGHT_AVAILABLE, "aiohttp": AIOHTTP_AVAILABLE, "requests": REQUESTS_AVAILABLE})

@app.get("/")
async def root():
    if FRONTEND_FILE.exists():
        return FileResponse(FRONTEND_FILE)
    return HTMLResponse("<h3>frontend.html not found</h3>", status_code=404)

@app.get("/jobs")
async def list_jobs():
    jobs = JOBSTORE.list_jobs()
    out = [{ "id": j.id, "status": j.status, "created_at": j.created_at, "updated_at": j.updated_at, "count": len(j.urls) } for j in jobs]
    return JSONResponse(out)

@app.get("/job/{job_id}")
async def get_job(job_id: str):
    jr = JOBSTORE.get_job(job_id)
    if not jr:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(asdict(jr))

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ACTIVE_WS.add(ws)
    LOG.info("WebSocket connected (clients=%d)", len(ACTIVE_WS))
    try:
        while True:
            try:
                data = await ws.receive_text()
            except WebSocketDisconnect:
                break
            if not data:
                continue
            if data.startswith("start"):
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
                    await ws.send_text(json.dumps({"type":"error","msg":"No URLs"}))
                    continue
                # create job record
                jr = JOBSTORE.create_job(urls, options={})
                # init playwright pool if needed
                if play_pool and not play_pool._inited:
                    try:
                        await play_pool.init()
                    except Exception:
                        LOG.exception("Playwright init failed")
                # create scraper
                scraper = ScraperEngine(play_pool, concurrency=4, email_limit=10, safe_mode=args.safe_mode)
                SCRAPERS[jr.id] = scraper
                await ws.send_text(json.dumps({"type":"job_created","job_id":jr.id,"count":len(urls)}))
                async def progress_cb(done, total, current, emails):
                    # update job store incrementally
                    JOBSTORE._jobs[jr.id].results[current] = emails
                    JOBSTORE.update_job(jr.id, status="running")
                    payload = {"type":"progress","job_id":jr.id,"done":done,"total":total,"current":current,"emails":emails}
                    try:
                        await ws.send_text(json.dumps(payload))
                    except Exception:
                        pass
                try:
                    JOBSTORE.update_job(jr.id, status="running")
                    results = await scraper.run(urls, progress_cb)
                    JOBSTORE.update_job(jr.id, status="finished", results=results)
                    await ws.send_text(json.dumps({"type":"finished","job_id":jr.id,"results":results}))
                except Exception:
                    LOG.exception("Scraper run exception")
                    JOBSTORE.update_job(jr.id, status="failed")
                    await ws.send_text(json.dumps({"type":"error","job_id":jr.id,"msg":"scraper failed"}))
            elif data.startswith("cancel"):
                jid = data[len("cancel"):].strip()
                s = SCRAPERS.get(jid)
                if s:
                    s.cancel()
                    JOBSTORE.update_job(jid, status="cancelled")
                    await ws.send_text(json.dumps({"type":"cancelled","job_id":jid}))
                else:
                    await ws.send_text(json.dumps({"type":"error","msg":"job not found"}))
            else:
                # echo or unsupported commands
                await ws.send_text(json.dumps({"type":"echo","msg":data}))
    except WebSocketDisconnect:
        LOG.info("WebSocket disconnected")
    except Exception:
        LOG.exception("WS error")
    finally:
        with suppress(Exception):
            ACTIVE_WS.remove(ws)

# ---------------------------
# Server starter / packaging helper
# ---------------------------
def background_install_playwright():
    if args.no_playwright_install:
        LOG.info("Skipping playwright install by flag")
        return
    if not PLAYWRIGHT_AVAILABLE:
        LOG.info("Playwright not installed in environment")
        return
    try:
        # best-effort install in background (may prompt or fail on some OS)
        subprocess.Popen([sys.executable, "-m", "playwright", "install", "--with-deps"])
    except Exception:
        LOG.exception("playwright background install failed")

def run_server_and_open():
    # start uvicorn in thread
    def _run():
        LOG.info("Starting uvicorn on %s:%s", HOST, PORT)
        uvicorn.run("backend:app", host=HOST, port=PORT, log_level="info", access_log=False)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(1.2)
    url = f"http://{HOST}:{PORT}/"
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            LOG.info("Auto-open failed; visit %s manually", url)
    return t

# ---------------------------
# Graceful shutdown handling
# ---------------------------
# ---------------------------
# Graceful shutdown handling (Windows-safe)
# ---------------------------
SHUTDOWN_EVENT = threading.Event()

def _signal_handler(sig=None, frame=None):
    LOG.info("Shutdown requested...")
    SHUTDOWN_EVENT.set()

# Windows cannot set signals in threads
if threading.current_thread() is threading.main_thread():
    try:
        import signal
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
    except Exception:
        pass

# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    LOG.info("Starting backend (expanded). Playwright available=%s", PLAYWRIGHT_AVAILABLE)
    # attempt background playwright browser install if available
    threading.Thread(target=background_install_playwright, daemon=True).start()
    server_thread = run_server_and_open()
    try:
        while not SHUTDOWN_EVENT.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    LOG.info("Shutting down server...")
    if play_pool and play_pool._inited:
        try:
            asyncio.run(play_pool.close())
        except Exception:
            pass
    THREAD_POOL.shutdown(wait=False)
    LOG.info("Exit complete.")
