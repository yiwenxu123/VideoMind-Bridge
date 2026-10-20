// VideoMind Gateway PM2 配置（本机服务形态）
// 用法:
//   pm2 start ecosystem.config.cjs
//   pm2 save
//
// 说明:
// - interpreter 指向项目 .venv；换环境先执行 uv sync --extra dev
// - 代理变量显式清空：避免继承 WorkBuddy/Qoder 会话代理，会话结束后 ECONNREFUSED
// - VMB_ASR_CHAIN 默认本地 SenseVoice 优先，faster-whisper 兜底
const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
const PYTHON =
  process.env.VMB_PYTHON ||
  [
    path.join(ROOT, ".venv", "bin", "python"),
    path.join(ROOT, ".venv", "Scripts", "python.exe"),
  ].find((candidate) => fs.existsSync(candidate));

if (!PYTHON) {
  throw new Error("找不到项目 .venv Python，请先运行 uv sync --extra dev");
}

module.exports = {
  apps: [
    {
      name: "videomind-api",
      script: "main.py",
      interpreter: PYTHON,
      cwd: ROOT,
      args: "--api --host 127.0.0.1 --port 8787",
      env: {
        VMB_ASR_CHAIN: process.env.VMB_ASR_CHAIN || "sensevoice,faster_whisper",
        VMB_WHISPER_MODEL: process.env.VMB_WHISPER_MODEL || "base",
        NODE_OPTIONS: "",
        NODE_PATH: "",
        HTTP_PROXY: "",
        HTTPS_PROXY: "",
        http_proxy: "",
        https_proxy: "",
        ALL_PROXY: "",
        all_proxy: "",
      },
      autorestart: true,
      max_restarts: 10,
      min_uptime: "5s",
      time: true,
      out_file: path.join(process.env.HOME, ".pm2-logs", "videomind-api.log"),
      error_file: path.join(process.env.HOME, ".pm2-logs", "videomind-api-error.log"),
    },
  ],
};