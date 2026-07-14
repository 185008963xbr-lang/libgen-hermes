#!/usr/bin/env python3
"""
Hermes 端 LibGen API 调用辅助脚本
用法:
  # 搜索并下载第一本
  python3 hermes_api.py "历史学与社会理论" pdf 1
  
  # 只搜索不下载
  python3 hermes_api.py "历史学与社会理论" --search-only
"""
import sys, os, json, time, urllib.request, zipfile, io

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "libgen-hermes")
OUTPUT_DIR = os.environ.get("LIBGEN_OUTPUT", os.path.expanduser("~/Desktop"))

def trigger_search(query, fmt="", download_index="1", limit="10"):
    """Trigger GitHub Actions workflow."""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/dispatches"
    payload = {
        "event_type": "search_book",
        "client_payload": {
            "query": query,
            "format": fmt,
            "download_index": download_index,
            "result_limit": limit,
        }
    }
    req = urllib.request.Request(url, 
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "hermes-libgen",
        },
        method="POST"
    )
    resp = urllib.request.urlopen(req)
    return resp.status == 204

def get_latest_run():
    """Get the latest workflow run."""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs?event=repository_dispatch&per_page=1"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "hermes-libgen",
    })
    data = json.loads(urllib.request.urlopen(req).read())
    runs = data.get("workflow_runs", [])
    if runs:
        return runs[0]
    return None

def wait_for_completion(run_id, timeout=300):
    """Poll until run completes."""
    start = time.time()
    while time.time() - start < timeout:
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs/{run_id}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "hermes-libgen",
        })
        data = json.loads(urllib.request.urlopen(req).read())
        status = data.get("status")
        conclusion = data.get("conclusion")
        if status == "completed":
            return conclusion == "success"
        print(f"  等待中... ({status})", flush=True)
        time.sleep(10)
    return False

def download_artifact(run_id, output_dir):
    """Download artifact zip and extract."""
    # Get artifact list
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs/{run_id}/artifacts"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "hermes-libgen",
    })
    data = json.loads(urllib.request.urlopen(req).read())
    artifacts = data.get("artifacts", [])
    if not artifacts:
        print("❌ 没有 Artifact")
        return False
    
    # Download first artifact
    art = artifacts[0]
    dl_url = art["archive_download_url"]
    req2 = urllib.request.Request(dl_url, headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "User-Agent": "hermes-libgen",
    })
    zip_data = urllib.request.urlopen(req2).read()
    
    # Extract
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        zf.extractall(output_dir)
    
    # List extracted files
    files = os.listdir(output_dir)
    print(f"\n✅ 下载完成! 文件在: {output_dir}")
    for f in files:
        if f.endswith((".pdf", ".epub", ".mobi")):
            fpath = os.path.join(output_dir, f)
            print(f"  📄 {f} ({os.path.getsize(fpath)//1024}KB)")
    return True

def search_only(query, fmt=""):
    """Search only, return results."""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/dispatches"
    payload = {
        "event_type": "search_book",
        "client_payload": {
            "query": query,
            "format": fmt,
            "download_index": "0",
            "result_limit": "10",
        }
    }
    req = urllib.request.Request(url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "hermes-libgen",
        },
        method="POST"
    )
    urllib.request.urlopen(req)
    print(f"✅ 搜索已触发: {query}")
    print(f"   去 https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/actions 查看结果")

if __name__ == "__main__":
    if not GITHUB_TOKEN or not GITHUB_OWNER:
        print("⚠️ 请设置环境变量:")
        print("  export GITHUB_TOKEN=github_pat_xxx")
        print("  export GITHUB_OWNER=your_username")
        sys.exit(1)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    query = sys.argv[1]
    fmt = sys.argv[2] if len(sys.argv) > 2 else ""
    idx = sys.argv[3] if len(sys.argv) > 3 else "1"

    if "--search-only" in sys.argv:
        search_only(query, fmt)
        sys.exit(0)

    print(f"🔍 搜索: {query}")
    if fmt:
        print(f"   格式: {fmt}")
    
    # Trigger
    ok = trigger_search(query, fmt, idx)
    if not ok:
        print("❌ 触发失败")
        sys.exit(1)
    print("✅ 已触发 GitHub Actions")

    # Wait for run
    time.sleep(5)
    run = get_latest_run()
    if not run:
        print("❌ 找不到运行记录")
        sys.exit(1)
    
    run_id = run["id"]
    print(f"   运行ID: {run_id}")
    print(f"   等待完成...")
    
    success = wait_for_completion(run_id)
    if not success:
        print("❌ 运行失败或超时")
        sys.exit(1)
    
    print("✅ 运行完成, 下载 Artifact...")
    download_artifact(run_id, OUTPUT_DIR)
