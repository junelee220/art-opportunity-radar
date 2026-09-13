# 艺术机会雷达 · Art Opportunity Radar

监控全球艺术驻留 / 基金 / Open Call 的自动化雷达。抓取 → 关键词初筛 → AI 判读打分 → 数据库沉淀 → Telegram + 邮件通知 + 网页雷达。

专为跨学科创作者定制,三个方向:独立出版 / 小志 / 图像叙事、媒体考古 / 数字人文 / 开源硬件、空间实践 / 公共空间。

## 架构

```text
海外源(RSS/Atom,~35 个)
        │
        ▼
GitHub Actions(每 5 天,cron 调度)
        │
        ▼
Python 管道:抓取 → URL 去重 → 关键词矩阵初筛 → 云端 LLM 结构化打分
        │
        ├──► data/opportunities.json(git 自动 commit,历史可回溯)
        │
        ├──► Telegram(每轮 HIGH / MAYBE 批量推送)
        ├──► 邮件(HIGH 摘要,Resend)
        │
        └──► GitHub Pages 雷达页(倒计时高亮 + 筛选)

国内源(微信公众号 + 国内美术馆官网,~13 个)
        │
        ▼
国内常开设备(见 cn-node/README.md)
WeWe RSS + changedetection.io + 同一 Python 管道(--region cn --push)
        │
        └──► 同一仓库 data/,同一 Telegram
```

## 5 分钟部署

```bash
# 1. 在 GitHub 上建一个【公开】仓库(如 art-opportunity-radar)
# 2. 把本项目所有文件推上去
# 3. 仓库 Settings → Secrets and variables → Actions → Secrets 配置:

#   TELEGRAM_BOT_TOKEN   找 @BotFather 创建 bot 获得
#   TELEGRAM_CHAT_ID     先和 bot 对话,再访问
#                        https://api.telegram.org/bot<TOKEN>/getUpdates 取 chat_id
#   AI_API_KEY           任一 OpenAI 兼容服务(OpenAI / DeepSeek / Gemini 兼容端点)
#   EMAIL_API_KEY        Resend.com API key(不要邮件可跳过)
#   EMAIL_FROM           如 radar@resend.dev
#   EMAIL_TO             你的邮箱

# 4. (可选)Settings → Secrets and variables → Actions → Variables 配置:
#   AI_BASE_URL   非 OpenAI 官方时填,如 https://api.deepseek.com/v1
#   AI_MODEL      默认 gpt-4o-mini,可改 deepseek-chat 等

# 5. Actions 标签页 → radar → Run workflow 手动触发第一次
# 6. Settings → Pages → Source 选 GitHub Actions
```

## Secrets 一览

| 变量 | 用途 | 必需 |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram 推送 | 用 TG 则必填 |
| `TELEGRAM_CHAT_ID` | Telegram 推送 | 用 TG 则必填 |
| `AI_API_KEY` | LLM 打分 | 建议填(缺失时降级为纯关键词) |
| `AI_BASE_URL` / `AI_MODEL` | 换模型用(Variables) | 可选 |
| `EMAIL_API_KEY` / `EMAIL_FROM` / `EMAIL_TO` | HIGH 摘要邮件 | 可选 |

## 本地开发

```bash
pip install -r requirements.txt
python src/main.py --dry-run          # 抓取+初筛,不调 AI 不发通知,打印结果
python src/main.py --region overseas   # 完整跑海外源
python -m http.server -d frontend 8080 # 本地预览雷达页
```

## 目录结构

```text
├── .github/workflows/radar.yml   # 定时引擎 + 数据 commit + Pages 部署
├── config/
│   ├── sources.yml               # 信息源(加源只改这里)
│   └── keywords.yml              # 关键词矩阵(调灵敏度只改这里)
├── src/
│   ├── main.py                   # 入口:--dry-run / --region / --push
│   ├── scraper.py                 # 并发抓取 + 去重
│   ├── analyzer.py                # 关键词初筛 + LLM 打分
│   └── notifier.py                # Telegram + 邮件
├── frontend/index.html            # 雷达页(零依赖单页)
├── data/                          # opportunities.json / seen_urls.json / archive/
└── cn-node/                       # 国内设备部署(微信公众号 + 国内官网)
```

## 国内源(微信公众号等)

见 [cn-node/README.md](cn-node/README.md)。核心:国内源需要一台国内常开设备跑 WeWe RSS + changedetection.io,用同一套管道 `--region cn --push` 把数据写回本仓库。

## FAQ

**定时任务会停吗?** 仓库 60 天无任何活动时 GitHub 自动禁用 scheduled workflow。本系统每次有新数据都会自动 commit,正常运行不会触发;若长期停摆,去 Actions 页面手动 Enable。

**多久能收到通知?** cron 每 5 天跑一次(每月 1/6/11/16/21/26 号,UTC 03:00;标准 cron 无法跨月精确计 5 天,月末到月初间隔会浮动 3–6 天),GitHub 高峰期调度另有小时级延迟。注意:临近截止(<5 天)的机会可能来不及发现,赶 deadline 的话建议调回更高频率。

**怎么加信息源?** 编辑 `config/sources.yml`,加一条 name/url/type/region/tier 即可,下次运行自动生效。国内源加 `region: cn`。

**误报太多/漏报?** 调 `config/keywords.yml`:误报加 block_words 或提高 `keyword_min_score`;漏报降低阈值或加 trigger/media 词。AI 打分不准再调 `ai_relevance_notify`。

**想全私有?** Phase 3 选项:换 Ollama 本地推理 + Tailscale 组网,当前架构预留了 `AI_BASE_URL`,指向本地 OpenAI 兼容端点即可。
