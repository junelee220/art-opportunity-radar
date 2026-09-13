# 国内节点部署指南

## 这个模块现在只剩一个职责:微信公众号

2026-09 复核实测:国内美术馆官网(A4 是 WordPress、敦煌当代是 Squarespace)**海外 IP 都能直接访问**,已由 GitHub Actions 抓取(见 config/sources.yml),不再需要国内设备。歌德学院/天目里等反爬站点另归 changedetection.io 待办。

**唯一必须设备的场景是微信公众号**:抓公众号需要持久的微信登录态(WeWe RSS 需扫码登录),GitHub Actions 的无状态环境跑不了。

## 实施前的选型(未实施,待你决定)

| 方案 | 成本 | 维护量 | 时效 |
|---|---|---|---|
| A. 免费云容器跑 WeWe RSS(Railway/Render/Fly.io) | 0 元 | 每 1–3 个月重新扫码 | 分钟级 |
| B. 付费托管服务(wechat2rss 类) | ¥5–15/月 | 零 | 分钟级 |
| C. 闲置安卓手机 + Termux | 0 元 | 低 | 分钟级 |
| D. 主力电脑 Docker(不要求 24h) | 0 元 | 低 | 开机时段 |
| E. 人肉:微信星标 + 置顶 | 0 元 | 零 | 实时(人刷) |

参考量级:这 9 个号一年约发 20–40 条机会,匹配方向的可能 5–10 条。以下部署流程适用于 A/C/D(自跑 WeWe RSS 的任何形态)。

## 需要监控的公众号清单(2026-09 梳理)

**官网自动化无门(公众号是唯一源,优先)**:
- 天目里美术馆(BY ART MATTERS)— 官网 Vue SPA
- 黄边站 HB Station — 无稳定官网
- 瑞士文化基金会上海 — 中文专项信息发公众号
- 起承艺术中心(昆山)— 官网缺位,方向高度匹配(新媒体/开源硬件)
- 上海当代艺术博物馆(PSA)— 青策计划首发
- 广东时代美术馆 — 腹地计划,官网弱更新

**官网反爬,公众号替代**:
- 歌德学院(中国)— goethe.de 403

**官网已接,公众号快几小时~1 天(低优先)**:
- 成都 A4 美术馆、敦煌当代美术馆

以下部署流程以本机 Docker 为例(云容器同理:镜像一致,数据卷持久即可)。

## 硬件要求

任何常开设备:旧笔记本 / NAS / 树莓派 / 迷你主机。Ubuntu 或 Debian,安装 Docker(含 compose 插件):

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

## 第一步:启动两个容器

```bash
cd ~/art-opportunity-radar/cn-node
docker compose up -d
```

## 第二步:配置 WeWe RSS(公众号 → RSS)

1. 浏览器打开 `http://<设备IP>:4000`
2. 按界面提示**扫码登录微信**(保持登录态,掉线需重新扫码)
3. 添加要监控的公众号(清单见上方「公众号监控清单」,优先加"唯一源"那 6 个)
4. 每个公众号会生成一个 feed 地址(形如 `http://<设备IP>:4000/feeds/xxxx.xml`)
5. 把地址填进主仓库 `config/sources.yml`,**region 必须是 `cn`**,然后推送到 GitHub

## 第三步:配置 changedetection.io(反爬官网监控)

> 2026-09 更新:A4/敦煌官网已直连 Actions,**此服务现在只负责反爬站点**(需要浏览器渲染的),监控目标:歌德学院驻留页 `https://www.goethe.de/ins/cn/zh/kul/res.html`、天目里 `https://www.byartmatters.com/residency`。没有这些需求时可暂不部署。

1. 浏览器打开 `http://<设备IP>:5000`
2. 添加上面两个页面,用 CSS 选择器锁定"招募/驻留"列表区域(不熟悉选择器就先整页监控,收到噪音后再收紧)
3. 通知方式选 **Telegram**,填 bot token 和 chat id(和主仓库用同一个 bot 即可)

## 第四步:GitHub 同步

1. 在 GitHub 创建 **Fine-grained PAT**:Settings → Developer settings → Fine-grained tokens,权限只给本仓库的 **Contents: Read and write**
2. 设备上配置 git 凭证(推荐把 PAT 写进 remote):
   ```bash
   cd ~/art-opportunity-radar
   git remote set-url origin https://<你的用户名>:<PAT>@github.com/<用户名>/<仓库名>.git
   ```
3. 创建环境变量文件 `~/radar-env`:
   ```bash
   cat > ~/radar-env <<'EOF'
   export TELEGRAM_BOT_TOKEN="..."
   export TELEGRAM_CHAT_ID="..."
   export AI_API_KEY="..."
   export AI_BASE_URL="https://api.deepseek.com/v1"   # 国内直连,推荐 DeepSeek
   export AI_MODEL="deepseek-chat"
   export TELEGRAM_PROXY="http://127.0.0.1:7890"       # 设备上没有代理就删掉这行
   EOF
   chmod 600 ~/radar-env
   ```
4. 首次运行测试:
   ```bash
   ~/art-opportunity-radar/cn-node/run_cron.sh
   tail -20 ~/radar-cn.log
   ```

## 第五步:加入 crontab

```bash
   crontab -e
   # 加入这一行(每 5 天:每月 1/6/11/16/21/26 号 11:00,月末到月初间隔 3–6 天浮动):
   0 11 1,6,11,16,21,26 * * ~/art-opportunity-radar/cn-node/run_cron.sh
```

## 日常维护

- **微信掉线**:WeWe RSS 界面会显示登录状态,掉线后重新扫码
- **看日志**:`tail -f ~/radar-cn.log`
- **更新代码**:`cd ~/art-opportunity-radar && git pull`(run_cron.sh 每次也会自动 pull)
