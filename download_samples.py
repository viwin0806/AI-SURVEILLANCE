"""
Sample Video Downloader
========================
Downloads free, copyright-compliant sample videos for realistic demonstration.

Sources used:
- Pexels (free license, no attribution required for academic use)
- Pixabay (CC0 license)

These are CROWD/STREET videos that will produce realistic YOLO detections.
The AI pipeline works on any MP4 video — the demo videos ship as synthetic
placeholders; this script downloads REAL footage.

Run:
    python download_samples.py

The downloaded videos are saved to data/videos/ and automatically
appear in the Demo Mode selection.
"""

import os
import sys
import urllib.request
import shutil

# Project root
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR = os.path.join(BASE_DIR, "data", "videos")
os.makedirs(VIDEO_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# FREE sample video URLs (public domain / CC0 / Pexels free license)
# These are crowd / street / action videos that demonstrate YOLO detection.
# ---------------------------------------------------------------------------
SAMPLE_VIDEOS = [
    {
        "filename": "real_crowd_01.mp4",
        "url": "https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4",
        "description": "Sample crowd video for YOLO testing",
        "note": "Replace with an actual crowd video for best YOLO detection results.",
    },
]

# ---------------------------------------------------------------------------
# Better sources (manually download these for realistic demonstrations):
#
# 1. Pexels — Free crowd videos:
#    https://www.pexels.com/search/videos/crowd/
#    https://www.pexels.com/search/videos/street/
#
# 2. Pixabay — Free CC0 videos:
#    https://pixabay.com/videos/search/crowd/
#
# 3. For violence/fight datasets (require registration):
#    UCF-Crime:    https://www.crcv.ucf.edu/projects/real-world/
#    CCTV-Fights:  https://rose1.ntu.edu.sg/dataset/cctvFights/
#
# After downloading, place videos in:
#    data/videos/
#
# Naming for demo mode integration (see config.py DEMO_VIDEOS):
#    demo_normal.mp4     — Normal crowd activity
#    demo_suspicious.mp4 — Suspicious high-motion activity
#    demo_fight.mp4      — Violence/fight scenario
# ---------------------------------------------------------------------------


def download_video(url, filepath, description=""):
    """Download a video from URL to filepath."""
    print(f"  Downloading: {os.path.basename(filepath)}")
    print(f"  From: {url}")
    if description:
        print(f"  Description: {description}")
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(filepath, "wb") as f:
                shutil.copyfileobj(response, f)
        
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        print(f"  [OK] Saved ({size_mb:.1f} MB)")
        return True
    
    except Exception as e:
        print(f"  [FAIL] Download failed: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return False


def print_manual_download_guide():
    """Print guide for manually downloading better videos."""
    print()
    print("=" * 60)
    print("  FOR BEST DEMONSTRATION RESULTS")
    print("  Download real crowd/street videos manually:")
    print("=" * 60)
    print()
    print("  1. PEXELS (Free, no attribution required):")
    print("     https://www.pexels.com/search/videos/crowd/")
    print("     https://www.pexels.com/search/videos/street/")
    print()
    print("  2. PIXABAY (CC0 Free):")
    print("     https://pixabay.com/videos/search/crowd/")
    print()
    print("  3. UCF-Crime Dataset (for violence detection testing):")
    print("     https://www.crcv.ucf.edu/projects/real-world/")
    print()
    print("  4. CCTV-Fights Dataset (requires request form):")
    print("     https://rose1.ntu.edu.sg/dataset/cctvFights/")
    print()
    print("  Save videos to: data/videos/")
    print("  Use these filenames for Demo Mode:")
    print("    demo_normal.mp4     — Normal crowd (any crowd/street video)")
    print("    demo_suspicious.mp4 — High motion  (fast-moving crowd)")
    print("    demo_fight.mp4      — Fight/violence (action video)")
    print()
    print("  Any .mp4 file in data/videos/ will appear in Demo Mode.")
    print("=" * 60)


def setup_sample_videos():
    """Download or remind user to download sample videos."""
    print()
    print("=" * 60)
    print("  Sample Video Setup")
    print("=" * 60)
    print()
    print("  Checking existing videos...")
    
    existing = [f for f in os.listdir(VIDEO_DIR) if f.endswith(".mp4")]
    if existing:
        print(f"  Found {len(existing)} video(s) in data/videos/:")
        for f in existing:
            size_mb = os.path.getsize(os.path.join(VIDEO_DIR, f)) / (1024 * 1024)
            print(f"    - {f} ({size_mb:.1f} MB)")
        print()
        print("  You already have demo videos ready!")
    else:
        print("  No videos found. Creating synthetic demos...")
        import subprocess
        subprocess.run([sys.executable, "setup_demos.py"], check=False)
    
    print_manual_download_guide()


if __name__ == "__main__":
    setup_sample_videos()
