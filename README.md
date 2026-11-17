# 米家Web版（Mijia-Web）

本地运行的米家设备控制面板：浏览器打开 `http://127.0.0.1:8765`，用手机米家 App 扫码登录，即可在电脑上查看和控制米家设备。Flask 后端 + Vue 3 前端，构建产物随仓库提供，运行时不需要 Node。

设计借鉴开源项目 mihome-pc 的架构思路，全部代码为独立实现；MIT 许可证。

一个实例对应一个米家账号：登录后所有设备都来自这个账号。要让多个人各自登录自己的账号，需各跑一个实例（不同端口）。

## 一、选择安装方式

| 平台 | 方式 | 适合 | 是否需要装 Python |
| --- | --- | --- | --- |
| Windows | 绿色版 zip | 不想装任何环境，双击即用 | 否（包内自带） |
| macOS | 通用 zip（Intel + Apple Silicon） | 同上，首次启动自动下载免安装 Python | 否（没有就自动下） |
| 群晖 / 飞牛 NAS | Docker 镜像 | 7×24 常驻，不受电脑关机影响 | 否（容器内自带） |
| Linux / 其他 | 源码运行 | 想自己掌控环境 | 是 |

## 二、Windows 绿色版

1. 从 Releases 下载 `Mijia-Web-Windows-<版本号>.zip`（如 `Mijia-Web-Windows-0.2.0.zip`），解压到任意目录。
2. 双击 `启动.bat`。看到 `[完成] 服务已在后台运行` 且浏览器自动打开即成功。
3. 关闭黑色窗口不影响服务（后台运行）；停止服务双击 `停止.bat`。
4. 浏览器没自动打开时，手动访问 `http://127.0.0.1:8765`。

登录态在 `%LOCALAPPDATA%\Mijia-Web`，不在解压目录里，更新或重装不会掉登录。
杀毒软件若提示，是 Python 运行环境被误报，选"允许/信任"即可。

## 三、macOS 版

1. 从 Releases 下载 `Mijia-Web-macOS-<版本号>.zip`（如 `Mijia-Web-macOS-0.2.0.zip`），解压到"下载"或"文稿"等你有写权限的目录（不要直接放 `/Applications`）。
2. 首次使用前，打开"终端"执行下面一行，去掉系统的隔离标记（把路径换成你的实际位置）：
   ```
   xattr -cr "/你的路径/米家Web版-macOS-v<版本号>"
   ```
3. 双击 `启动.command`。首次会自动完成：检测系统 Python（3.10~3.13）；没有则按你的芯片自动下载免安装 Python 并校验，解压到应用内 `runtime/`；创建 `.venv` 并安装依赖；启动服务并打开浏览器。首次安装依赖需几分钟，之后启动只需几秒。
4. 停止服务双击 `停止.command`。

若双击仍被拦截，右键文件选"打开"。登录态在 `~/Library/Application Support/Mijia-Web`，不写应用目录。详细常见问题见包内 `使用说明.txt`。

## 四、群晖 / 飞牛 NAS（Docker）

优势：常驻运行，不依赖电脑开机；登录态与数据存在 NAS 上，重建容器不丢。

1. 在 NAS 共享文件夹建一个目录（如 `docker/mijia-web`），里面再建空的子目录 `data`。
2. 打开 NAS 的 Docker 管理界面（群晖叫 Container Manager，飞牛叫 Docker），用 Compose / 项目功能新建项目，来源选"创建 docker-compose.yml"。
3. 粘贴仓库根目录 `docker-compose.yml` 的内容，按注释改两处：`ports` 的左侧端口、`volumes` 的左侧数据目录路径。
4. 勾选创建后立即启动，等容器状态为"运行中"。
5. 浏览器打开 `http://NAS的IP:端口`。

升级：把 compose 里 `image` 的标签改成新版本号，重新部署（自动拉新镜像并重建容器）。回滚同理改回旧版本号。完整的图形界面步骤、公网配置、注意事项见 `docs/NAS部署说明.md`。

镜像为 amd64 + arm64 多架构，x86 和 ARM 机型都支持，由 GitHub Actions 免费云端构建并推送到 `ghcr.io/xuechao188/mijia-web`。若 NAS 拉不到 GHCR 镜像，可配置镜像加速源，或把 compose 里 `image:` 换成 `build: .` 用源码本地构建。

## 五、源码运行（Linux / 自定义环境）

需要 Python 3.10~3.13。前端构建产物已随仓库提供，日常运行不需要 Node。

```bash
cd Mijia-Web
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt   # 国内可加 -i https://pypi.tuna.tsinghua.edu.cn/simple
./.venv/bin/python run.py                     # 启动并自动打开浏览器
```

无图形界面 / 服务器环境加 `MIHOME_NO_BROWSER=1` 跳过开浏览器。

## 六、登录

1. 打开页面点"登录"，用手机米家 App / 小米账号 App 扫一扫即可，无需输密码。
2. 也可切"账号密码"页签登录（触发二次验证时页面会出现验证码输入框）。
3. 登录态存在数据目录的 `mi.token`，重启自动恢复，不用重复登录。
4. 首次进入若提示"数据正在加载中"，是设备状态还在从云端同步，稍候自动消失。

## 七、公网访问（可选，按需开启）

默认只建议局域网使用。公网访问需同时做三件事：

1. 设置访问密码：环境变量 `MIHOME_ACCESS_USER` 与 `MIHOME_ACCESS_PASSWORD` 两项都填才生效。否则任何扫到端口的人都能开关你家设备。
2. 设置来源白名单：`MIHOME_ALLOWED_ORIGINS` 填你的域名或 DDNS 主机名，多个用逗号分隔。写接口只接受这些主机名，防跨站攻击。
3. 用反向代理（如 Nginx Proxy Manager）终止 HTTPS 后转发到 8765，不要在路由器上直接把 8765 映射到公网。

单实例单账号，公网部署只适合自己在外访问自己的账号，不要当作对外服务的多用户平台。NAS 场景的完整配置见 `docs/NAS部署说明.md`。

## 八、在线升级（Windows / macOS 桌面版）

右上角顶栏的版本号可以点击，打开"关于应用"窗口：显示当前版本、项目地址，以及"检测新版本 / 下载并升级 / 回滚"按钮。版本源走 GitHub Releases latest。

升级只替换源码文件，不碰数据目录、token、数据库，登录态不受影响。升级前自动备份，失败自动回滚。

NAS / Docker 版不用这个功能：改 compose 的镜像标签重新部署即可（容器内已禁用应用内升级，避免写容器可写层导致版本不一致）。

## 功能

- **扫码登录**：小米账号 QR 长轮询协议，手机扫码即登录；未登录时只显示全屏登录页
- **家庭 / 房间两级分组**：家庭在侧栏顶部切换，列表只列当前家庭的房间，同名房间天然按家庭隔离；自定义分组可跨家庭组合设备
- **分类卡片（大 / 中 / 小三尺寸）**：型号定主类别、能力兜底；读数与趋势曲线作为通用能力叠加。灯卡片直接调亮度/色温，空调/厨电有目标温度步进，传感器/插座的大卡有趋势曲线
- **卡片拖动与控件互不干扰**：滑块、按钮、步进器上按下不会触发整卡拖动；卡片空白处仍可拖动排序
- **在线优先排布**：可用设备排在前面，离线设备沉到网格底部
- **加载遮罩**：首次进入设备状态未同步完时显示转圈提示，避免"未知 / 亮度 0"的中间态
- **控制防重复点击**：控制指令执行期间锁定并显示"正在控制"，防止连点误发相反指令
- **高分屏自适应**：内容区宽度自适应铺满，无右侧留白
- 历史趋势：全量轮询顺带采样（SQLite，5 分钟一点、保留 7 天）
- 设备控制：开关、亮度、色温、模式、风速档位、摆风，控件由 MIoT spec 自动推导；多键开关逐路控制
- 分层轮询：3 秒开关跟随 + 45 秒全量读数（单请求批量读多设备）
- 场景执行：一键运行米家 App 里已建的手动场景
- 自动化管理：按家庭分组、中文摘要、改名/启停/新建/删除（写入需二次确认）
- 设备通知、事件流、天气卡片（Open-Meteo 免费接口）、自定义设备名与卡片外显值自选
- 主题系统：浅色/深色 × 7 套色彩预设 + 自定义主色，本机持久化
- **详情统一为居中双列弹框**（设备 / 自动化 / 天气同规格）
- **摄像头专项**：参数控制、云台动作、取流能力判定、能播则播（实时画面需额外取流中继，桌面版与容器均未集成）
- **红外遥控**：虚拟红外设备的命令表与温度步进控制（单向发码，不伪造状态）
- 响应式布局：宽屏铺满、窄屏自适应
- CLI 入口（`cli.py`）：脚本 / AI agent 可直接控制设备与场景

## 配置

| 环境变量 | 说明 | 默认 |
| --- | --- | --- |
| `MIHOME_DATA_DIR` | 数据目录（缓存/事件/日志/token） | 平台用户数据目录 |
| `MIHOME_PORT` | 端口 | 8765 |
| `MIHOME_HOST` | 监听地址；容器/反代场景设 `0.0.0.0` | 127.0.0.1 |
| `MIHOME_NO_BROWSER` | 设为 1 跳过自动开浏览器（服务器/容器用） | 空 |
| `MIHOME_CITY` | 天气城市 | 合肥 |
| `MIHOME_LOG_LEVEL` | 日志级别 | INFO |
| `MIHOME_ACCESS_USER` / `MIHOME_ACCESS_PASSWORD` | Basic 认证账号密码，两项都设才启用 | 空 |
| `MIHOME_ALLOWED_ORIGINS` | 写接口来源白名单，多个域名逗号分隔 | 本机地址 |
| `MIHOME_UPDATE_REPO` | 在线升级仓库 `owner/repo`，留空禁用检测 | xuechao188/Mijia-Web |
| `MIHOME_UPDATE_TOKEN` | 可选 GitHub token（抬高限流 / 私有仓库） | 空 |
| `MIHOME_GITHUB_URL` | 关于窗口展示的项目主页 | 按仓库自动拼 |
| `MIHOME_UPDATE_AUTO_RESTART` | 升级后是否自动重启并刷新页面 | 开 |

## CLI（AI agent / 脚本）

```bash
./.venv/bin/python cli.py devices            # 列出设备
./.venv/bin/python cli.py on 123456789       # 开设备
./.venv/bin/python cli.py toggle 123456789 on2   # 多键开关第 2 路
./.venv/bin/python cli.py set 123456789 2 3 50   # 写属性
./.venv/bin/python cli.py scenes             # 列出手动场景
./.venv/bin/python cli.py scene 987654       # 执行场景
./.venv/bin/python cli.py --json devices     # JSON 输出（给程序）
```

## 测试

```bash
for f in tests/test_*.py; do ./.venv/bin/python "$f"; done
for f in tests/test_*.js; do node "$f"; done
cd web && npm run build    # vue-tsc 类型检查 + Vite 打包到 ../static/vue/
```

## 打包

```bash
python build_windows.py    # 生成 dist/米家Web版-Windows-v<版本>.zip
python build_macos.py      # 生成 dist/米家Web版-macOS-v<版本>.zip
```

Docker 多架构镜像由 `.github/workflows/docker-publish.yml` 在推送 `v<版本>` tag 时自动构建推送到 GHCR，无需本地安装 Docker。

## 免责声明

本项目为非官方第三方客户端，与小米公司及米家官方无任何隶属或合作关系。仅供学习交流与个人使用；登录凭据只存本机数据目录，不上传任何第三方。
