# 国内节点部署指南

## 为什么需要国内节点

GitHub Actions 的运行机器出口 IP 在海外:

1. **微信公众号**是多个国内美术馆的首发渠道,但抓公众号需要持久的微信登录态(WeWe RSS 需要扫码登录),Actions 的无状态环境跑不了
2. 部分国内官网从海外访问慢或不稳定

所以国内源由一台你自己的常开设备捕获,数据最终汇合同一个 GitHub 仓库。海外源由 Actions 抓,两边互不干扰(Actions 只写 overseas 数据,国内节点只写 cn 数据)。

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
3. 添加要监控的公众号,建议清单(来自你的信息源库):
   - 天目里美术馆(BY ART MATTERS)
   - 成都 A4 美术馆
   - 广东时代美术馆
   - 上海当代艺术博物馆(PSA)
   - 黄边站 HB Station
   - 敦煌当代美术馆
   - 北京德国文化中心·歌德学院(中国)
4. 每个公众号会生成一个 feed 地址(形如 `http://<设备IP>:4000/feeds/xxxx.xml`)
5. 把地址填进主仓库 `config/sources.yml`,**region 必须是 `cn`**,然后推送到 GitHub

## 第三步:配置 changedetection.io(官网页面监控)

1. 浏览器打开 `http://<设备IP>:5000`
2. 添加要监控的页面,推荐先加这几个国内机构驻留页:
   - `https://www.byartmatters.com/residency`(天目里驻留页)
   - `https://www.a4artmuseum.com/zh/a4-residencyartcenter/`(A4 驻留艺术中心)
   - `https://www.goethe.de/ins/cn/zh/kul/res.html`(歌德学院驻留项目)
   - `https://www.dunhuangartmuseum.com/895439641007`(敦煌当代驻留)
3. 每个页面用 CSS 选择器锁定"招募/驻留"列表区域(避免监控整页被新闻更新骚扰);不熟悉选择器就先用默认整页监控,收到过噪音后再收紧
4. 通知方式选 **Telegram**,填 bot token 和 chat id(和主仓库用同一个 bot 即可)

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
# 加入这一行(每 30 分钟):
*/30 * * * * ~/art-opportunity-radar/cn-node/run_cron.sh
```

## 日常维护

- **微信掉线**:WeWe RSS 界面会显示登录状态,掉线后重新扫码
- **看日志**:`tail -f ~/radar-cn.log`
- **更新代码**:`cd ~/art-opportunity-radar && git pull`(run_cron.sh 每次也会自动 pull)
