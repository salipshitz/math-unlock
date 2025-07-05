#!/usr/bin/env bash
# Installs "math-lock" so it runs at every unlock AND every 20 min, without looping.
set -euo pipefail

# ─── paths ──────────────────────────────────────────────────────────────────────
LOCK_DIR="$HOME/.math_lock"
PY_SRC="$(dirname "$0")/math_lock.py"          # expected next to this installer
PY_FILE="$LOCK_DIR/math_lock.py"
WRAP="$LOCK_DIR/run_once.sh"
MONITOR="$LOCK_DIR/screen_monitor.py"
PLIST="$HOME/Library/LaunchAgents/com.mathlock.quiz.plist"
INTERVAL=1200      # 20 min
THROTTLE=15        # minimum seconds between runs
PYTHON="$(command -v python3)"

[[ -z $PYTHON ]] && { echo "python3 not found"; exit 1; }

# ─── copy python code ───────────────────────────────────────────────────────────
mkdir -p "$LOCK_DIR"
[[ -f $PY_SRC ]] || { echo "math_lock.py not found beside installer"; exit 1; }
cp "$PY_SRC" "$PY_FILE"
chmod 755 "$PY_FILE"

# ─── create screen monitor daemon ──────────────────────────────────────────────
cat >"$MONITOR" <<'EOF'
#!/usr/bin/env python3
"""Monitor for screen wake events and trigger math lock."""
import subprocess
import time
import os
from Quartz import CGDisplayIsAsleep, CGMainDisplayID

def is_screen_asleep():
    """Check if the main display is asleep."""
    try:
        return CGDisplayIsAsleep(CGMainDisplayID())
    except:
        return False

def should_run_math_lock():
    """Check throttling to see if we should run the math lock."""
    stamp_file = "/tmp/.math_lock_last"
    throttle_seconds = 15
    
    if os.path.exists(stamp_file):
        try:
            with open(stamp_file, 'r') as f:
                last_run = int(f.read().strip())
            if time.time() - last_run < throttle_seconds:
                return False
        except:
            pass
    
    # Update timestamp
    with open(stamp_file, 'w') as f:
        f.write(str(int(time.time())))
    
    return True

def run_math_lock():
    """Run the math lock if throttling allows."""
    if should_run_math_lock():
        try:
            subprocess.run(["/usr/bin/python3", os.path.expanduser("~/.math_lock/math_lock.py")])
        except Exception as e:
            print(f"Error running math lock: {e}")

def main():
    """Monitor screen sleep/wake cycle."""
    was_asleep = is_screen_asleep()
    
    while True:
        time.sleep(1)  # Check every second
        
        try:
            currently_asleep = is_screen_asleep()
            
            # If screen just woke up (was asleep, now awake)
            if was_asleep and not currently_asleep:
                print(f"Screen woke up at {time.strftime('%Y-%m-%d %H:%M:%S')}")
                run_math_lock()
            
            was_asleep = currently_asleep
            
        except Exception as e:
            print(f"Error in monitor loop: {e}")
            time.sleep(5)  # Wait longer on error

if __name__ == "__main__":
    main()
EOF
chmod 755 "$MONITOR"

# ─── wrapper for manual execution ──────────────────────────────────────────────
cat >"$WRAP" <<EOF
#!/usr/bin/env bash
set -euo pipefail

# More robust throttling using lockfile
LOCK_FILE="/tmp/.math_lock_running"
STAMP_FILE="/tmp/.math_lock_last"
THROTTLE_SECONDS=$THROTTLE

# Check if already running
if [[ -f "\$LOCK_FILE" ]]; then
    # Check if the process is actually running
    if ps -p "\$(cat "\$LOCK_FILE")" >/dev/null 2>&1; then
        exit 0  # Already running
    else
        rm -f "\$LOCK_FILE"  # Stale lock file
    fi
fi

# Create lock file with current PID
echo \$\$ > "\$LOCK_FILE"

# Function to cleanup on exit
cleanup() {
    rm -f "\$LOCK_FILE"
}
trap cleanup EXIT

# Check throttle timing
now=\$(date +%s)
if [[ -f "\$STAMP_FILE" ]]; then
    last=\$(cat "\$STAMP_FILE")
    elapsed=\$((now - last))
    if [[ \$elapsed -lt \$THROTTLE_SECONDS ]]; then
        exit 0  # Too soon
    fi
fi

# Update timestamp
echo \$now > "\$STAMP_FILE"

# Run the math lock
"$PYTHON" "$PY_FILE"
EOF
chmod 700 "$WRAP"

# ─── clean old helpers ──────────────────────────────────────────────────────────
launchctl unload "$PLIST" >/dev/null 2>&1 || true
brew services stop sleepwatcher >/dev/null 2>&1 || true

# ─── launchd job with screen monitor and interval ──────────────────────────────
cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.mathlock.quiz</string>
  
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$MONITOR</string>
  </array>
  
  <key>RunAtLoad</key>
  <true/>
  
  <key>KeepAlive</key>
  <true/>
  
  <key>StandardOutPath</key>
  <string>/tmp/mathlock.out</string>
  
  <key>StandardErrorPath</key>
  <string>/tmp/mathlock.err</string>
  
  <key>ProcessType</key>
  <string>Interactive</string>
</dict>
</plist>
EOF

# ─── create separate plist for 20-minute interval ──────────────────────────────
INTERVAL_PLIST="$HOME/Library/LaunchAgents/com.mathlock.interval.plist"
cat >"$INTERVAL_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.mathlock.interval</string>
  
  <key>ProgramArguments</key>
  <array>
    <string>$WRAP</string>
  </array>
  
  <key>StartInterval</key>
  <integer>$INTERVAL</integer>
  
  <key>StandardOutPath</key>
  <string>/tmp/mathlock_interval.out</string>
  
  <key>StandardErrorPath</key>
  <string>/tmp/mathlock_interval.err</string>
</dict>
</plist>
EOF

# Load both plists
launchctl load "$PLIST"
launchctl load "$INTERVAL_PLIST"

echo "✅ math-lock active — fires each screen wake & every 20 min."
echo "📋 To remove: "
echo "   launchctl unload \"$PLIST\" && rm -f \"$PLIST\""
echo "   launchctl unload \"$INTERVAL_PLIST\" && rm -f \"$INTERVAL_PLIST\""
echo "   rm -rf \"$LOCK_DIR\""
echo "🔍 To debug: tail -f /tmp/mathlock.out /tmp/mathlock.err"