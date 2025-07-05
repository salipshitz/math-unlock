#!/usr/bin/env bash
# One-shot installer for the “math-lock” quiz.
# It sets up:
#   • a launchd (macOS’s built-in scheduler/daemon manager) job every 20 min
#   • SleepWatcher (a tiny utility) to run the quiz each time the Mac unlocks

set -euo pipefail

### 1. Where will we keep the Python file?  ###################################
LOCK_DIR="$HOME/.math_lock"
LOCK_PY="$LOCK_DIR/math_lock.py"

mkdir -p "$LOCK_DIR"

# If the user is running the installer from the same folder as math_lock.py,
# copy it in; otherwise assume they’ve already put it there.
if [[ ! -f "$LOCK_PY" ]]; then
  if [[ -f "$(dirname "$0")/math_lock.py" ]]; then
    cp "$(dirname "$0")/math_lock.py" "$LOCK_PY"
  else
    echo " ❗  math_lock.py not found. Put it in $LOCK_DIR and rerun." >&2
    exit 1
  fi
fi
chmod 755 "$LOCK_PY"

PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo " ❗  python3 not found. Install Xcode Command Line Tools or Homebrew Python." >&2
  exit 1
fi

### 2. Ensure Homebrew exists (needed for SleepWatcher)  ######################
if ! command -v brew >/dev/null 2>&1; then
  echo " → Installing Homebrew (this can take a couple of minutes)…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

### 3. Install & start SleepWatcher (runs scripts at wake/unlock) #############
if ! brew list --formula | grep -q '^sleepwatcher$'; then
  echo " → Installing SleepWatcher…"
  brew install sleepwatcher
fi

echo " → Creating ~/.wakeup script…"
cat > "$HOME/.wakeup" <<EOF
#!/usr/bin/env bash
"$PYTHON_BIN" "$LOCK_PY"
EOF
chmod 700 "$HOME/.wakeup"

echo " → Starting SleepWatcher daemon…"
brew services restart sleepwatcher >/dev/null

### 4. Create launchd job for 20-minute intervals #############################
PLIST="$HOME/Library/LaunchAgents/com.mathlock.quiz.plist"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>com.mathlock.quiz</string>

  <!-- What to run -->
  <key>ProgramArguments</key> <array>
      <string>$PYTHON_BIN</string>
      <string>$LOCK_PY</string>
  </array>

  <!-- Fire at login AND every 1 200 s (20 min) -->
  <key>RunAtLoad</key>        <true/>
  <key>StartInterval</key>    <integer>1200</integer>

  <!-- Throw output into /tmp so nothing clutters user folders -->
  <key>StandardOutPath</key>  <string>/tmp/mathlock.out</string>
  <key>StandardErrorPath</key><string>/tmp/mathlock.err</string>
</dict>
</plist>
EOF

echo " → Loading launchd job…"
launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"

echo
echo "✅  Math-lock is now active."
echo "   • Pops up every Mac unlock (handled by SleepWatcher)."
echo "   • Pops up every 20 minutes while logged in (handled by launchd)."
echo "   Remove:  launchctl unload \"$PLIST\" && brew services stop sleepwatcher"
