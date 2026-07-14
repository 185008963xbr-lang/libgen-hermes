#!/usr/bin/env python3
"""
LibGen Search & Download Engine — runs on GitHub Actions
Usage:
  python libgen_search.py search <query> [--format pdf] [--limit 10]
  python libgen_search.py dl <md5> <output_dir>
  python libgen_search.py batch <booklist.txt> <output_dir>
"""
import sys, os, re, json, time, urllib.request, urllib.parse

MIRRORS_SEARCH = [
    "https://libgen.li/index.php",
    "https://libgen.bz/search.php",
    "https://libgen.is/search.php",
    "https://libgen.rs/search.php",
    "https://libgen.st/search.php",
]

DOWNLOAD_PROVIDERS = [
    "https://libgen.li/get.php?md5={md5}",
    "https://library.lol/main/{md5}",
    "https://download.library.lol/main/{md5}",
    "https://libgen.li/ads.php?md5={md5}",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=timeout).read()

def search(query, fmt="", limit=10):
    results = []
    for mirror in MIRRORS_SEARCH:
        log(f"搜索: {mirror}")
        try:
            if "libgen.li" in mirror:
                params = {"req": query, "topics": "l", "columns": "t,a,s,y,p,i", "objects": "f,e,s", "res": str(limit)}
            else:
                params = {"req": query, "lg_topic": "libgen", "open": "0", "view": "simple", "res": str(limit), "phrase": "1"}
            qs = urllib.parse.urlencode(params, doseq=True)
            url = f"{mirror}?{qs}"
            html = http_get(url, timeout=15).decode("utf-8", errors="replace")

            # Try to find MD5 + title rows
            rows = re.findall(r'md5=([a-f0-9]{32})[^"]*"[^>]*>([^<]+)</a>', html)
            if rows:
                seen = set()
                for md5, title in rows:
                    md5 = md5.lower()
                    if md5 not in seen:
                        seen.add(md5)
                        results.append({"md5": md5, "title": title.strip(), "author": "", "extension": "", "size": ""})
                log(f"  → {len(results)} 条")
                return results

            # Try full table format
            rows2 = re.findall(
                r'<tr[^>]*>.*?<td[^>]*>.*?md5=([a-f0-9]+)[^<]*<[^>]*>([^<]+)</a>.*?<td[^>]*>([^<]*)</td>.*?<td[^>]*>([^<]*)</td>.*?<td[^>]*>([^<]*)</td>',
                html, re.DOTALL
            )
            if rows2:
                for r2 in rows2:
                    md5, title, author, ext, size = [x.strip() for x in r2]
                    if fmt and ext.lower() != fmt.lower():
                        continue
                    results.append({"md5": md5.lower(), "title": title, "author": author, "extension": ext.lower(), "size": size})
                log(f"  → {len(results)} 条")
                return results

            log("  → 未解析到结果")
        except Exception as e:
            log(f"  ⚠️ {str(e)[:60]}")
    return results

def get_download_url(md5):
    for tmpl in DOWNLOAD_PROVIDERS:
        url = tmpl.format(md5=md5)
        try:
            data = http_get(url, timeout=15)
            if len(data) > 50 * 1024:
                if b"<html" not in data[:100]:
                    return url
                html_text = data.decode("utf-8", errors="replace")
                for m in re.finditer(r'href="([^"]*main/[^"]+)"', html_text):
                    direct = m.group(1)
                    if direct.startswith("http"):
                        return direct
                    return "https://library.lol" + direct
        except:
            continue
    return ""

def download(md5, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    dl_url = get_download_url(md5)
    if not dl_url:
        log(f"  ❌ 无法获取下载链接")
        return False
    log(f"  下载中...")
    try:
        data = http_get(dl_url, timeout=60)
        if len(data) < 50 * 1024:
            log(f"  ⚠️ 太小 ({len(data)} bytes)")
            return False
        ext = ".bin"
        if data[:4] == b"%PDF":
            ext = ".pdf"
        elif data[:2] == b"PK":
            ext = ".epub"
        path = os.path.join(output_dir, f"{md5}{ext}")
        with open(path, "wb") as f:
            f.write(data)
        log(f"  ✅ {path} ({len(data)//1024}KB)")
        return True
    except Exception as e:
        log(f"  ❌ {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "search":
        query = sys.argv[2]
        fmt = ""
        limit = 10
        for i, arg in enumerate(sys.argv[3:]):
            if arg == "--format" and i + 4 < len(sys.argv):
                fmt = sys.argv[i + 4]
            if arg == "--limit" and i + 4 < len(sys.argv):
                limit = int(sys.argv[i + 4])
        results = search(query, fmt, limit)
        print(json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, indent=2))
    elif cmd == "dl":
        md5 = sys.argv[2].lower().strip()
        out_dir = sys.argv[3] if len(sys.argv) > 3 else "."
        ok = download(md5, out_dir)
        print(json.dumps({"success": ok, "md5": md5}, ensure_ascii=False))
    elif cmd == "batch":
        list_file = sys.argv[2]
        out_dir = sys.argv[3] if len(sys.argv) > 3 else "."
        with open(list_file) as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        report = []
        for line in lines:
            parts = [p.strip() for p in line.split("|")]
            if re.match(r'^[a-f0-9]{32}$', parts[0].lower()):
                md5 = parts[0].lower()
            else:
                log(f"搜索: {parts[0]}")
                results = search(parts[0], limit=5)
                if results:
                    md5 = results[0]["md5"]
                else:
                    report.append({"query": parts[0], "status": "not_found"})
                    continue
            ok = download(md5, out_dir)
            report.append({"query": parts[0], "md5": md5, "status": "success" if ok else "failed"})
        with open(os.path.join(out_dir, "download_report.json"), "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        log(f"完成: {sum(1 for r in report if r['status']=='success')}/{len(report)}")
