"""
Demo Video Setup Script
========================
Downloads or creates sample demo videos for the surveillance system.

Since we can't distribute copyrighted footage, this script:
1. Checks for existing demo videos in data/videos/
2. If none found, creates synthetic demo videos using OpenCV
   that demonstrate the pipeline capabilities

The synthetic videos contain moving shapes that simulate:
- Normal crowd activity (people walking)
- Suspicious activity (fast/erratic movement)
- Fight/violence scenario (chaotic multi-directional motion)
"""

import os
import sys
import cv2
import numpy as np
import random

# Add project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


def create_demo_video(filepath, scenario="normal", duration=15, fps=25,
                      width=640, height=480):
    """
    Create a synthetic demo video with moving rectangles simulating people.
    
    Args:
        filepath: Output video path
        scenario: "normal", "suspicious", or "fight"
        duration: Video duration in seconds
        fps: Frames per second
        width: Video width
        height: Video height
    """
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(filepath, fourcc, fps, (width, height))
    
    if not writer.isOpened():
        print(f"  Error: Could not create video writer for {filepath}")
        return False
    
    total_frames = duration * fps
    
    # Create "people" (rectangles with different colors)
    if scenario == "normal":
        num_people = random.randint(3, 6)
        speed_range = (1, 3)
        direction_change_prob = 0.02
        bg_color = (30, 35, 40)
        text = "DEMO: Normal Crowd Activity"
    elif scenario == "suspicious":
        num_people = random.randint(5, 10)
        speed_range = (3, 8)
        direction_change_prob = 0.08
        bg_color = (25, 30, 45)
        text = "DEMO: Suspicious High-Motion Activity"
    elif scenario == "fight":
        num_people = random.randint(4, 8)
        speed_range = (5, 15)
        direction_change_prob = 0.15
        bg_color = (20, 20, 35)
        text = "DEMO: Violence/Fight Scenario"
    else:
        num_people = 4
        speed_range = (1, 3)
        direction_change_prob = 0.02
        bg_color = (30, 35, 40)
        text = "DEMO"
    
    # Initialize people
    people = []
    person_colors = [
        (0, 180, 0), (0, 0, 200), (200, 150, 0), (150, 0, 150),
        (0, 200, 200), (200, 100, 50), (100, 200, 100), (200, 50, 100),
        (50, 100, 200), (200, 200, 50),
    ]
    
    for i in range(num_people):
        pw = random.randint(25, 45)
        ph = random.randint(50, 90)
        people.append({
            "x": random.randint(50, width - 50),
            "y": random.randint(50, height - 50),
            "w": pw,
            "h": ph,
            "dx": random.uniform(-speed_range[1], speed_range[1]),
            "dy": random.uniform(-speed_range[1], speed_range[1]),
            "color": person_colors[i % len(person_colors)],
        })
    
    for frame_idx in range(total_frames):
        # Create background with some noise
        frame = np.full((height, width, 3), bg_color, dtype=np.uint8)
        
        # Add subtle background texture
        noise = np.random.randint(0, 15, (height, width, 3), dtype=np.uint8)
        frame = cv2.add(frame, noise)
        
        # Draw ground/floor area
        cv2.rectangle(frame, (0, height - 80), (width, height), (40, 45, 50), -1)
        
        # Add some static "buildings/structures" in background
        for bx in range(0, width, 120):
            bh = random.randint(100, 250) if frame_idx == 0 else 180
            cv2.rectangle(frame, (bx + 5, height - 80 - bh), 
                         (bx + 100, height - 80), (45, 50, 55), -1)
            cv2.rectangle(frame, (bx + 5, height - 80 - bh), 
                         (bx + 100, height - 80), (55, 60, 65), 1)
        
        # Update and draw people
        for person in people:
            # Random direction changes
            if random.random() < direction_change_prob:
                person["dx"] = random.uniform(-speed_range[1], speed_range[1])
                person["dy"] = random.uniform(-speed_range[1], speed_range[1])
            
            # In fight scenario, people move toward each other periodically
            if scenario == "fight" and frame_idx % 30 < 15:
                # Move toward center cluster
                cx = width // 2
                cy = height // 2
                dx = (cx - person["x"]) * 0.03
                dy = (cy - person["y"]) * 0.03
                person["dx"] = dx + random.uniform(-3, 3)
                person["dy"] = dy + random.uniform(-3, 3)
            
            # Update position
            person["x"] += person["dx"]
            person["y"] += person["dy"]
            
            # Bounce off walls
            if person["x"] < 10 or person["x"] > width - person["w"] - 10:
                person["dx"] *= -1
                person["x"] = max(10, min(width - person["w"] - 10, person["x"]))
            if person["y"] < 10 or person["y"] > height - person["h"] - 10:
                person["dy"] *= -1
                person["y"] = max(10, min(height - person["h"] - 10, person["y"]))
            
            x, y = int(person["x"]), int(person["y"])
            w, h = person["w"], person["h"]
            
            # Draw person (body rectangle + head circle)
            cv2.rectangle(frame, (x, y + 15), (x + w, y + h), person["color"], -1)
            cv2.circle(frame, (x + w // 2, y + 10), 12, person["color"], -1)
            
            # Draw "limbs" for more human-like appearance
            if abs(person["dx"]) > 2 or abs(person["dy"]) > 2:
                # Arms swinging
                arm_offset = int(5 * np.sin(frame_idx * 0.3))
                cv2.line(frame, (x, y + 25), (x - 10, y + 45 + arm_offset), person["color"], 2)
                cv2.line(frame, (x + w, y + 25), (x + w + 10, y + 45 - arm_offset), person["color"], 2)
        
        # Draw text overlay
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (width, 30), (0, 0, 0), -1)
        frame = cv2.addWeighted(overlay, 0.6, frame, 0.4, 0)
        cv2.putText(frame, text, (10, 22), cv2.FONT_HERSHEY_SIMPLEX,
                   0.6, (200, 200, 200), 1)
        
        # Frame counter
        time_str = f"Frame: {frame_idx}/{total_frames}"
        cv2.putText(frame, time_str, (width - 180, 22),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
        
        writer.write(frame)
    
    writer.release()
    return True


def setup_demo_videos():
    """Create all demo videos."""
    os.makedirs(config.VIDEO_DIR, exist_ok=True)
    
    demos = [
        {
            "filename": "demo_normal.mp4",
            "scenario": "normal",
            "duration": 20,
            "description": "Normal crowd walking activity",
        },
        {
            "filename": "demo_suspicious.mp4",
            "scenario": "suspicious",
            "duration": 20,
            "description": "Suspicious fast/erratic movement",
        },
        {
            "filename": "demo_fight.mp4",
            "scenario": "fight",
            "duration": 20,
            "description": "Violence/fight scenario with chaotic motion",
        },
    ]
    
    print("=" * 50)
    print("  Demo Video Generator")
    print("=" * 50)
    print()
    
    created = 0
    for demo in demos:
        filepath = os.path.join(config.VIDEO_DIR, demo["filename"])
        
        if os.path.exists(filepath):
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            print(f"  [OK] {demo['filename']} already exists ({size_mb:.1f} MB)")
            continue
        
        print(f"  Creating {demo['filename']} ({demo['description']})...")
        success = create_demo_video(
            filepath,
            scenario=demo["scenario"],
            duration=demo["duration"],
        )
        
        if success:
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            print(f"    [OK] Created ({size_mb:.1f} MB)")
            created += 1
        else:
            print(f"    [FAIL] Failed to create")
    
    print()
    if created > 0:
        print(f"  Created {created} demo video(s)")
    print(f"  Video directory: {os.path.abspath(config.VIDEO_DIR)}")
    print()
    print("  TIP: You can also place your own MP4 videos in the")
    print("  data/videos/ directory for more realistic demonstrations.")
    print("  Real CCTV footage or crowd videos will produce better")
    print("  YOLO detections than synthetic demo videos.")
    print()


if __name__ == "__main__":
    setup_demo_videos()
