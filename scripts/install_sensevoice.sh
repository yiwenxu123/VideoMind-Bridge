#!/usr/bin/env bash
# SenseVoice 一键安装 / 体检（VideoMind Bridge 默认 ASR 链的第一级）
#
# 为什么需要它：默认 ASR 链是 sensevoice -> faster_whisper -> dashscope，
# 而 sensevoice 的依赖故意不进主 venv（sherpa-onnx 体积大）。它依赖三样仓库外的东西：
#   1) 专用解释器  ~/.cache/sensevoice/venv/bin/python   （已装 sherpa-onnx + soundfile）
#   2) 模型目录    ~/.cache/sherpa-onnx/sense-voice       （model.int8.onnx + tokens.txt）
#   3) 转写脚本    src/core/asr/scripts/sensevoice_transcribe.py（仓库内，无需下载）
# 缺任何一样，/api/v1/capabilities 里 sensevoice 就会是 available=false（2026-11 起会真探测依赖）。
#
# 用法：
#   scripts/install_sensevoice.sh                 安装/补全（幂等：已就绪则跳过）
#   scripts/install_sensevoice.sh --check         只体检，不下载不安装（未就绪时退出码 1）
#   scripts/install_sensevoice.sh --force         重装依赖 + 重下模型
#   scripts/install_sensevoice.sh --skip-model    只准备解释器，不碰模型
#   scripts/install_sensevoice.sh --index-url URL 指定 pip 源（国内镜像可用）
#
# 可用环境变量覆盖默认值：
#   VMB_SENSEVOICE_VENV         默认 ~/.cache/sensevoice/venv
#   VMB_SENSEVOICE_MODEL_DIR    默认 ~/.cache/sherpa-onnx/sense-voice
#   VMB_SENSEVOICE_MODEL_URL    默认 k2-fsa 官方 release 包（也可给本地 tar.bz2 路径）
#   VMB_SENSEVOICE_BASE_PYTHON  用于创建 venv 的基础解释器，默认 python3
#   VMB_SENSEVOICE_PIP_INDEX    等价于 --index-url
#   VMB_SENSEVOICE_PIP_PKGS     默认 "sherpa-onnx soundfile"
#
# 退出码：0 已就绪；1 未就绪（缺项）；2 参数错误；3 安装过程中失败

set -uo pipefail

VENV_DIR="${VMB_SENSEVOICE_VENV:-$HOME/.cache/sensevoice/venv}"
MODEL_DIR="${VMB_SENSEVOICE_MODEL_DIR:-$HOME/.cache/sherpa-onnx/sense-voice}"
MODEL_URL="${VMB_SENSEVOICE_MODEL_URL:-https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2}"
BASE_PYTHON="${VMB_SENSEVOICE_BASE_PYTHON:-python3}"
PIP_INDEX="${VMB_SENSEVOICE_PIP_INDEX:-}"
# 已验证版本：sherpa-onnx 1.13.8（现有机器）与 2.0.3（2026-11-24 新装实测，转写脚本兼容）。
PIP_PKGS="${VMB_SENSEVOICE_PIP_PKGS:-sherpa-onnx>=1.13.8 soundfile}"

CHECK_ONLY=0
FORCE=0
SKIP_MODEL=0

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TRANSCRIBE_SCRIPT="$ROOT_DIR/src/core/asr/scripts/sensevoice_transcribe.py"

ok()   { echo "  [OK]    $*"; }
miss() { echo "  [MISS]  $*"; }
info() { echo; echo "==> $*"; }
warn() { echo "  [WARN]  $*"; }
die()  { echo "  [FAIL]  $*" >&2; exit 3; }

usage() {
  sed -n "4,30p" "$0" | sed "s/^# \{0,1\}//"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --check)      CHECK_ONLY=1 ;;
    --force)      FORCE=1 ;;
    --skip-model) SKIP_MODEL=1 ;;
    --index-url)  shift; PIP_INDEX="${1:-}" ;;
    -h|--help)    usage; exit 0 ;;
    *)            echo "未知参数: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

# ---------- 1. 体检 ----------
info "1/4 体检（解释器 / 依赖 / 模型 / 转写脚本）"
echo "  解释器路径: $VENV_DIR/bin/python"
echo "  模型目录:   $MODEL_DIR"
echo "  转写脚本:   $TRANSCRIBE_SCRIPT"

HAVE_VENV=0
[ -x "$VENV_DIR/bin/python" ] && HAVE_VENV=1
HAVE_DEPS=0
if [ "$HAVE_VENV" = 1 ]; then
  if "$VENV_DIR/bin/python" -c "import sherpa_onnx, soundfile" >/dev/null 2>&1; then
    HAVE_DEPS=1
  fi
fi
HAVE_MODEL=0
if [ -f "$MODEL_DIR/model.int8.onnx" ] && [ -f "$MODEL_DIR/tokens.txt" ]; then
  HAVE_MODEL=1
fi
HAVE_SCRIPT=0
[ -f "$TRANSCRIBE_SCRIPT" ] && HAVE_SCRIPT=1

if [ "$HAVE_VENV" = 1 ]; then ok "专用解释器存在"; else miss "专用解释器缺失: $VENV_DIR"; fi
if [ "$HAVE_DEPS" = 1 ]; then ok "解释器可 import sherpa_onnx + soundfile"; else miss "解释器缺少 sherpa-onnx/soundfile"; fi
if [ "$HAVE_MODEL" = 1 ]; then ok "模型文件齐全（model.int8.onnx + tokens.txt）"; else miss "模型文件缺失: $MODEL_DIR"; fi
if [ "$HAVE_SCRIPT" = 1 ]; then ok "转写脚本存在"; else miss "转写脚本缺失: $TRANSCRIBE_SCRIPT"; fi

if [ "$CHECK_ONLY" = 1 ]; then
  echo
  if [ "$HAVE_VENV" = 1 ] && [ "$HAVE_DEPS" = 1 ] && [ "$HAVE_MODEL" = 1 ] && [ "$HAVE_SCRIPT" = 1 ]; then
    echo "结论: SenseVoice 就绪（--check 未做任何改动）"
    exit 0
  fi
  echo "结论: SenseVoice 未就绪。去掉 --check 重跑本脚本即可安装。"
  exit 1
fi

echo
if [ "$HAVE_VENV" = 1 ] && [ "$HAVE_DEPS" = 1 ] && [ "$HAVE_MODEL" = 1 ] && [ "$HAVE_SCRIPT" = 1 ] && [ "$FORCE" = 0 ]; then
  echo "已就绪，无需安装（要用 --force 强制重装）。"
  exit 0
fi

TMP_DIR="$(mktemp -d)" || die "无法创建临时目录"
trap "rm -rf $TMP_DIR" EXIT

# ---------- 2. 解释器 + 依赖 ----------
if [ "$HAVE_VENV" = 0 ] || [ "$HAVE_DEPS" = 0 ] || [ "$FORCE" = 1 ]; then
  if [ "$HAVE_VENV" = 0 ] || [ "$FORCE" = 1 ]; then
    info "2/4 创建专用 venv（$BASE_PYTHON -m venv）"
    command -v "$BASE_PYTHON" >/dev/null 2>&1 || die "找不到基础解释器: $BASE_PYTHON（可用 VMB_SENSEVOICE_BASE_PYTHON 指定）"
    mkdir -p "$(dirname "$VENV_DIR")" || die "无法创建目录: $(dirname "$VENV_DIR")"
    "$BASE_PYTHON" -m venv "$VENV_DIR" || die "创建 venv 失败"
    HAVE_VENV=1
  fi
  info "安装 Python 依赖: $PIP_PKGS"
  PIP_ARGS=(-m pip install --disable-pip-version-check)
  if [ -n "$PIP_INDEX" ]; then
    PIP_ARGS+=(--index-url "$PIP_INDEX")
  fi
  "$VENV_DIR/bin/python" "${PIP_ARGS[@]}" $PIP_PKGS || die "pip 安装失败（网络问题可加 --index-url 换源）"
  "$VENV_DIR/bin/python" -c "import sherpa_onnx, soundfile" >/dev/null 2>&1 || die "依赖装完仍无法 import，请看上面的 pip 输出"
  HAVE_DEPS=1
else
  info "2/4 解释器与依赖已就绪，跳过"
fi

# ---------- 3. 模型 ----------
if [ "$HAVE_MODEL" = 0 ] && [ "$SKIP_MODEL" = 0 ]; then
  info "3/4 下载模型（约 230MB，来源：k2-fsa 官方 release）"
  if [ -f "$MODEL_URL" ]; then
    echo "  从本地文件复制: $MODEL_URL"
    cp "$MODEL_URL" "$TMP_DIR/model.tar.bz2" || die "复制本地模型包失败"
  else
    echo "  URL: $MODEL_URL"
    curl -fL --retry 3 --connect-timeout 20 -o "$TMP_DIR/model.tar.bz2" "$MODEL_URL" || die "下载失败（可设 VMB_SENSEVOICE_MODEL_URL 指向镜像/本地包）"
  fi
  tar -xjf "$TMP_DIR/model.tar.bz2" -C "$TMP_DIR" || die "解压失败（需要 bzip2/tar，macOS 自带）"
  SRC_MODEL="$(find "$TMP_DIR" -name model.int8.onnx -print -quit)"
  [ -n "$SRC_MODEL" ] || die "模型包里没找到 model.int8.onnx"
  mkdir -p "$MODEL_DIR" || die "无法创建模型目录: $MODEL_DIR"
  cp "$SRC_MODEL" "$MODEL_DIR/model.int8.onnx" || die "复制模型失败"
  cp "$(dirname "$SRC_MODEL")/tokens.txt" "$MODEL_DIR/tokens.txt" || die "复制 tokens.txt 失败"
  HAVE_MODEL=1
else
  if [ "$HAVE_MODEL" = 1 ]; then
    info "3/4 模型已就绪，跳过"
  else
    warn "3/4 按 --skip-model 跳过模型下载（此时 SenseVoice 不会可用）"
  fi
fi

# ---------- 4. 自检 ----------
info "4/4 自检（用 1 秒静音 wav 真跑一次转写）"
if [ "$HAVE_MODEL" = 1 ] && [ "$HAVE_SCRIPT" = 1 ]; then
  TMP_WAV="$TMP_DIR/selftest_16k.wav"
  "$VENV_DIR/bin/python" - "$TMP_WAV" <<PY || die "生成测试 wav 失败"
import sys, wave
path = sys.argv[1]
w = wave.open(path, "wb")
w.setnchannels(1)
w.setsampwidth(2)
w.setframerate(16000)
w.writeframes(bytes(32000))
w.close()
PY
  SENSEVOICE_MODEL_DIR="$MODEL_DIR" "$VENV_DIR/bin/python" "$TRANSCRIBE_SCRIPT" "$TMP_WAV" >"$TMP_DIR/selftest.out" 2>"$TMP_DIR/selftest.err"
  RC=$?
  if [ "$RC" -eq 0 ]; then
    ok "自检通过：$(tail -1 "$TMP_DIR/selftest.out")"
  else
    echo "  自检输出:" >&2
    sed "s/^/    /" "$TMP_DIR/selftest.err" >&2
    die "自检失败（退出码 $RC）"
  fi
else
  warn "缺少模型或脚本，跳过自检"
fi

echo
echo "完成。当前配置下 SenseVoice 将被视为可用："
echo "  VMB_SENSEVOICE_PYTHON=$VENV_DIR/bin/python"
echo "  VMB_SENSEVOICE_MODEL_DIR=$MODEL_DIR"
echo "提示：仅当专用解释器真的能 import sherpa_onnx 时，/api/v1/capabilities 才会报 available=true。"
echo "服务在跑的话重启一次让它重新探测：pm2 restart videomind-api（或重启你自己的进程）。"
exit 0
