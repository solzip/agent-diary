#!/bin/bash
# ============================================================
# Claude Code Working Diary — Auto Installer
# ============================================================
# Cross-platform: macOS, Linux, Windows (Git Bash / MSYS2)
#
# Usage:
#   chmod +x install.sh   # (Linux/macOS only)
#   ./install.sh
#
# Uninstall:
#   ./install.sh --uninstall
# ============================================================

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
HOOKS_DIR="$CLAUDE_DIR/hooks"
DIARY_DIR="${CLAUDE_DIARY_DIR:-$HOME/working-diary}"
SETTINGS_FILE="$CLAUDE_DIR/settings.json"

# ── OS 감지 ──
IS_WINDOWS=false
PYTHON_CMD=""
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]] || [[ -n "$WINDIR" ]]; then
    IS_WINDOWS=true
fi

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║     📓 Claude Code Working Diary — Auto Installer       ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Auto-generates daily diary & weekly summary.           ║"
echo "║  일일 작업일지 & 주간 요약이 자동 생성됩니다.            ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── 제거 모드 / Uninstall ──
if [ "$1" = "--uninstall" ]; then
    echo -e "${YELLOW}🗑️  Uninstall mode / 제거 모드${NC}"
    echo ""

    if [ -f "$HOOKS_DIR/working-diary.py" ]; then
        rm -f "$HOOKS_DIR/working-diary.py"
        echo -e "  ${GREEN}✓${NC} Removed $HOOKS_DIR/working-diary.py"
    fi
    if [ -f "$HOOKS_DIR/weekly-summary.py" ]; then
        rm -f "$HOOKS_DIR/weekly-summary.py"
        echo -e "  ${GREEN}✓${NC} Removed $HOOKS_DIR/weekly-summary.py"
    fi

    echo ""
    echo -e "${YELLOW}⚠️  Please manually remove the Stop Hook from ~/.claude/settings.json${NC}"
    echo -e "  Or use /hooks command inside Claude Code."
    echo ""

    # cron 제거 (Unix only)
    if [ "$IS_WINDOWS" = false ] && crontab -l 2>/dev/null | grep -q "weekly-summary.py"; then
        crontab -l 2>/dev/null | grep -v "weekly-summary.py" | crontab -
        echo -e "  ${GREEN}✓${NC} Removed cron job"
    fi

    echo ""
    echo -e "${GREEN}✅ Uninstall complete! Diary data preserved at $DIARY_DIR${NC}"
    exit 0
fi

# ── [1/5] 사전 검사 / Prerequisites ──
echo -e "${BLUE}[1/5] Checking prerequisites...${NC}"

# Python 감지 (python3 우선, 없으면 python)
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}❌ Python not found. Please install Python 3.6+${NC}"
    echo "   https://www.python.org/downloads/"
    exit 1
fi

PY_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo -e "  ${GREEN}✓${NC} $PYTHON_CMD $PY_VERSION"

# jq 확인 (선택)
if command -v jq &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} jq installed"
else
    echo -e "  ${YELLOW}△${NC} jq not installed (optional)"
fi

# Claude 디렉토리
if [ ! -d "$CLAUDE_DIR" ]; then
    echo -e "  ${YELLOW}△${NC} Creating ~/.claude/ ..."
    mkdir -p "$CLAUDE_DIR"
fi
echo -e "  ${GREEN}✓${NC} ~/.claude directory OK"

if [ "$IS_WINDOWS" = true ]; then
    echo -e "  ${CYAN}ℹ${NC} Windows detected — using '$PYTHON_CMD', skipping cron"
fi

# ── [2/5] 디렉토리 생성 / Create directories ──
echo ""
echo -e "${BLUE}[2/5] Creating directories...${NC}"

mkdir -p "$HOOKS_DIR"
echo -e "  ${GREEN}✓${NC} $HOOKS_DIR"

mkdir -p "$DIARY_DIR"
mkdir -p "$DIARY_DIR/weekly"
echo -e "  ${GREEN}✓${NC} $DIARY_DIR"
echo -e "  ${GREEN}✓${NC} $DIARY_DIR/weekly"

# ── [3/5] 스크립트 복사 / Copy scripts ──
echo ""
echo -e "${BLUE}[3/5] Installing hook scripts...${NC}"

cp "$SCRIPT_DIR/hooks/working-diary.py" "$HOOKS_DIR/working-diary.py"
cp "$SCRIPT_DIR/hooks/weekly-summary.py" "$HOOKS_DIR/weekly-summary.py"

if [ "$IS_WINDOWS" = false ]; then
    chmod +x "$HOOKS_DIR/working-diary.py"
    chmod +x "$HOOKS_DIR/weekly-summary.py"
fi
echo -e "  ${GREEN}✓${NC} working-diary.py → $HOOKS_DIR/"
echo -e "  ${GREEN}✓${NC} weekly-summary.py → $HOOKS_DIR/"

# ── [4/5] settings.json 업데이트 / Register Hook ──
echo ""
echo -e "${BLUE}[4/5] Registering Claude Code Stop Hook...${NC}"

if [ -f "$SETTINGS_FILE" ]; then
    cp "$SETTINGS_FILE" "${SETTINGS_FILE}.backup.$(date +%Y%m%d%H%M%S)"
    echo -e "  ${GREEN}✓${NC} Backed up existing settings.json"
fi

$PYTHON_CMD << PYEOF
import json
import os

settings_file = os.path.expanduser("~/.claude/settings.json")
hooks_dir = os.path.expanduser("~/.claude/hooks")

settings = {}
if os.path.exists(settings_file):
    try:
        with open(settings_file, "r") as f:
            settings = json.load(f)
    except json.JSONDecodeError:
        settings = {}

if "hooks" not in settings:
    settings["hooks"] = {}

if "Stop" not in settings["hooks"]:
    settings["hooks"]["Stop"] = []

diary_hook_exists = False
for matcher_group in settings["hooks"]["Stop"]:
    for hook in matcher_group.get("hooks", []):
        cmd = hook.get("command", "")
        if "working-diary.py" in cmd:
            diary_hook_exists = True
            break

if not diary_hook_exists:
    diary_hook = {
        "hooks": [
            {
                "type": "command",
                "command": "${PYTHON_CMD} {0}/working-diary.py".format(
                    hooks_dir.replace(os.sep, "/")
                )
            }
        ]
    }
    settings["hooks"]["Stop"].append(diary_hook)
    print("  ✓ Stop Hook registered (working-diary)")
else:
    print("  △ Stop Hook already registered")

with open(settings_file, "w") as f:
    json.dump(settings, f, indent=2, ensure_ascii=False)

print(f"  ✓ {settings_file} saved")
PYEOF

# ── [5/5] Cron / Scheduler ──
echo ""
echo -e "${BLUE}[5/5] Weekly summary scheduling...${NC}"
echo ""

if [ "$IS_WINDOWS" = true ]; then
    echo -e "  ${YELLOW}△${NC} Windows: cron not available."
    echo -e "  ${CYAN}ℹ${NC} Run manually: $PYTHON_CMD ~/.claude/hooks/weekly-summary.py"
    echo -e "  ${CYAN}ℹ${NC} Or use Windows Task Scheduler for automation."
else
    echo -e "  Schedule weekly summary every Friday 18:00? (crontab)"
    echo ""
    read -p "  Register cron job? (y/N): " SETUP_CRON

    if [ "$SETUP_CRON" = "y" ] || [ "$SETUP_CRON" = "Y" ]; then
        CRON_CMD="0 18 * * 5 $PYTHON_CMD $HOOKS_DIR/weekly-summary.py --cron >> $DIARY_DIR/weekly/cron.log 2>&1"
        (crontab -l 2>/dev/null | grep -v "weekly-summary.py"; echo "$CRON_CMD") | crontab -
        echo -e "  ${GREEN}✓${NC} Cron registered: every Friday 18:00"
    else
        echo -e "  ${YELLOW}△${NC} No cron. Manual: $PYTHON_CMD ~/.claude/hooks/weekly-summary.py"
    fi
fi

# ── .gitignore ──
if [ ! -f "$DIARY_DIR/.gitignore" ]; then
    cat > "$DIARY_DIR/.gitignore" << 'EOF'
.session_counts.json
weekly/cron.log
EOF
    echo ""
    echo -e "  ${GREEN}✓${NC} .gitignore created"
fi

# ── 완료 / Done ──
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              🎉 Installation complete!                   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  📁 Diary path:      ${CYAN}$DIARY_DIR/${NC}"
echo -e "  📁 Weekly path:     ${CYAN}$DIARY_DIR/weekly/${NC}"
echo -e "  ⚙️  Hook script:     ${CYAN}$HOOKS_DIR/working-diary.py${NC}"
echo -e "  ⚙️  Settings:        ${CYAN}$SETTINGS_FILE${NC}"
echo ""
echo -e "  ${YELLOW}Usage:${NC}"
echo -e "  • Just use Claude Code as usual!"
echo -e "  • Diary is auto-recorded when each session ends."
echo -e "  • View diary:  ${CYAN}cat ~/working-diary/\$(date +%Y-%m-%d).md${NC}"
echo -e "  • Weekly:      ${CYAN}$PYTHON_CMD ~/.claude/hooks/weekly-summary.py${NC}"
echo ""
echo -e "  ${YELLOW}Configuration:${NC}"
echo -e "  • Language:    CLAUDE_DIARY_LANG=ko|en  (default: ko)"
echo -e "  • Timezone:    CLAUDE_DIARY_TZ_OFFSET=9 (default: 9 = KST)"
echo -e "  • Diary path:  CLAUDE_DIARY_DIR=~/your-path"
echo -e "  • Uninstall:   ${CYAN}./install.sh --uninstall${NC}"
echo ""
