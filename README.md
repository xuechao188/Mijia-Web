# 米家Web版（Mijia-Web）

本地运行的米家设备控制面板。Flask + 纯静态前端，浏览器访问 http://127.0.0.1:8765。
设计借鉴开源项目 mihome-pc 的架构思路，全部代码为独立实现；并补齐了参考项目
文档中标注的未实现功能、规避了其已知 bug。

## 快速开始

```bash
cd Mijia-Web
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt   # 国内可加 -i https://pypi.tuna.tsinghua.edu.cn/simple
./.venv/bin/python run.py                     # 启动并自动打开浏览器
```

1. 默认进入「扫码登录」页：打开米家 App / 小米账号 App 扫一扫即可，无需输密码
2. 也可切「账号密码」页签登录（如触发二次验证，页面会出现验证码输入框）
3. 登录态存在本机数据目录 `mi.token`，重启自动恢复，不用重复登录

## 部署到虚拟主机（对外访问）

先说结论：**可以部署，但当前是单账号实例，不能让多个人各自登录自己的米家账号共用一套。
** 需要多租户就得每人跑一个实例，或另做会话级重构（见下方「复用边界」）。

构建产物 `static/vue/` 已随仓库提供，运行时只需要 Python + `requirements.txt`，
不需要 Node。Node 仅在改前端后重新 `npm ci && npm run build` 时需要。

### 三种部署方式

| 场景 | 做法 | 适用 |
| --- | --- | --- |
| 本机自用（默认） | 直接 `python3 run.py`，什么都不用配 | 只绑 127.0.0.1，无密码也能安全使用 |
| 公网单账号自用 | 环境变量配域名白名单 + 访问密码 + 持久化数据目录 | 你自己在外面用手机/别的电脑访问 |
| 多人各自登录自己的账号 | 每用户一个进程/容器，反向代理按子域名分发 | 当前架构不支持单实例多账号 |

### 公网单账号配置

```bash
export MIHOME_DATA_DIR=/var/lib/Mijia-Web       # 必须持久化；token/缓存/日志都在这里
export MIHOME_HOST=0.0.0.0                    # 只让反向代理连 8765 时可保持 127.0.0.1
export MIHOME_PORT=8765
export MIHOME_ALLOWED_ORIGINS=mihome.example.com
export MIHOME_ACCESS_USER=admin
export MIHOME_ACCESS_PASSWORD='换一个长密码'
export MIHOME_NO_BROWSER=1
./.venv/bin/python run.py
```

- `MIHOME_ALLOWED_ORIGINS` 是写接口的来源白名单，多个域名用逗号分隔；
  配了密码也不能绕过它。主机名匹配，所以 HTTPS 在反代终止也不会误杀。
- `MIHOME_ACCESS_*` 两项都设置才开启 Basic 认证；任何请求都需要密码，否则
  任何人访问到端口就能开关你家的灯。token 文件会收紧为 `0600`。
- 所有会改状态的接口只接受 POST（GET 一律 405），避免被 `<img src>` 之类的
  跨站请求触发；本机 CLI 与前端本来就走 POST，不受影响。
- 建议用 Nginx/TLS 终止 HTTPS 后反代到 `127.0.0.1:8765`，并限制来源 IP。
  直接把 8765 端口映射到公网不可取。
- CLI 连公网实例时先设同样的 `MIHOME_ACCESS_USER/PASSWORD`，再用
  `python3 cli.py --base https://你的域名 ping`；本机直连不需要这些变量。
- 子路径部署（如 `https://example.com/mijia/`）需要改 `web/vite.config.ts`
  的 `base` 后重新构建；仓库里的产物按域名根目录构建。

### 复用边界（重要）

- 进程内只有**一个全局账号/服务缓存**（`services/state.py`），所有设备、家庭、
  自动化、事件都取自这一份缓存；登录或扫码会覆盖全体的登录态。
  所以「别人打开域名，登录自己的米家账号」在单实例里做不到。
- 浏览器侧的 `mi-home`、`mi-*` 偏好按域名存 localStorage，不属于账号；
  切账号后家庭选不中会自动回落到第一个家庭，不会串设备数据，但也不是按账号隔离。
- 未登录时所有读接口返回空/失败提示，不会崩；首次访问会进入扫码登录页。

### 发布到 GitHub 前的检查

- 仓库根目录已有 `.gitignore`：`_probe/`（含真实摄像头 token / go2rtc 密码）、
  `.venv/`、`web/node_modules/`、token/缓存/数据库/日志全部排除。
- 测试中的真实账号 ID 已换成占位值；家庭名仍是示例数据，无凭据价值。
- `static/vendor-pico.css` 自带 MIT 署名；登录页橘猫位图为 AI 生成，可自由使用。
- 运行 `python3 tests/test_deploy.py` 与全量测试确认守卫生效。
- 本项目采用 MIT 许可证（见 `LICENSE`），公开仓库地址：
  `https://github.com/xuechao188/Mijia-Web`。

### 在线升级（GitHub Releases）

右上角顶栏的**版本号**（如 `v0.1.0`）可以点击，打开「关于应用」窗口：显示当前版本、
项目地址，以及「检测新版本 / 下载并升级 / 回滚」按钮。版本源固定走 GitHub Releases 的
latest，不依赖本地电脑常驻。

**开启方式**（不配置也能用，只是点检测会提示尚未配置）：

```bash
# 必需：你的仓库，格式 owner/repo
export MIHOME_UPDATE_REPO=yourname/yourrepo
# 可选：抬高 GitHub API 速率限制 / 读私有仓库
export MIHOME_UPDATE_TOKEN=ghp_xxx
# 可选：关于窗口里展示的主页，留空自动拼 https://github.com/<owner>/<repo>
export MIHOME_GITHUB_URL=https://github.com/yourname/yourrepo
# 可选：升级后不自动重启（默认会自动重启并刷新页面）
export MIHOME_UPDATE_AUTO_RESTART=0
```

**发布一个新版本给客户端升级**，三步：

1. 改 `config.py` 里的 `VERSION = "0.2.0"`（版本号要比当前大）。
2. 重新构建前端：`cd web && npm run build`，产物写进 `static/vue/`。
3. 把整个程序目录打成 `Mijia-Web-0.2.0.zip`（资产名必须是
   `Mijia-Web-<版本号>.zip`），作为附件上传到该版本的 GitHub Release 并发布。
   压缩包内路径以程序根目录为基准，例如 `app.py`、`routes/auth.py`、
   `static/vue/assets/xxx.js`、`web/src/App.vue`。

客户端点「检测新版本」→ 比对 tag 与本地 `VERSION` → 有新版本时点「下载并升级」，
后端自动下载、校验 sha256（Release 资产带 `digest` 时）、解压覆盖，覆盖前把旧文件
整包备份到数据目录 `updates/backup/`，失败自动回滚。升级完成后自动重启服务并刷新页面；
如需退回，在关于窗口点「回滚到升级前」。

安全边界：升级只写白名单内的前后端源码/产物（`app.py`、`config.py`、`routes/`、
`services/`、`static/`、`web/src/` 等），绝不碰数据目录、token、数据库、`.git`、
`.venv`、`node_modules`；下载只接受 GitHub 官方域名、有体积上限、逐项做 zip-slip
与符号链接校验。写接口沿用同源守卫与可选 Basic 认证。

> 当前状态：升级机制已实现并通过 90 项专项测试 + 全量回归；首个基线版本 `0.1.0`
> 已发布到 `https://github.com/xuechao188/Mijia-Web`，配置里已内置仓库地址，克隆后
> 直接可用。点「检测新版本」即可比对 GitHub 上的 latest Release。

### 遇到「code:-127 client withdraw」？

这个错误有两种完全不同的成因，别再一律当成"风控、等等就好"：

**一、请求身份不一致（本项目已修复，最常见）**

`miservice` 库把库作者自己的 `UserId/8816080` 与 DeviceId 写死在云端请求
UA 里；小米会核对 UA 身份与 cookie/token 里的 userId，不一致就返回
HTTP 429 + `{"code":-127,"message":"client withdraw","result":{"wait_second":30}}`。
带的 `wait_second` 很容易误判为限流，**实际是拒绝非法客户端，等多久都不会恢复**。

本项目在 `services/mi_patch.py` 里按当前 token 的真实 `deviceId/userId`
动态重写 UA（保留 `PROTOCAL-HTTP2` 头，去掉会 401），云端调用自动生效。
验证：把 UA 里的身份换成真实值后，设备列表立即返回 96 台。

**二、真正的频率风控**（高频调用 / 反复登录）

本项目内置应对，不需要人工干预：

- 登录验证拉设备列表被 -127 拦截时**不判登录失败**，先进主界面显示
  「正在从云端同步设备列表…」，后台按递增间隔（30/60/90/120/180 秒）补拉
- 任何云端调用撞 -127 即进入**全局冷却门**：冷却期内批量读/列表刷新直接
  跳过（沿用缓存值），避免轮询持续撞墙、反复续期封禁
- 未登录但本机有 token 时，每 3 分钟静默重试恢复登录；解除后自动
  进入主界面，登录页会显示「正在恢复登录…」
- 设备指纹持久化（`device_id` 文件），不再每次启动随机生成，降低风控概率

风控期通常 10~30 分钟，期间让程序自己等即可（不要反复重启/重新扫码）。

## 功能

- **扫码登录**：小米账号 QR 长轮询协议，手机扫码即登录；未登录时只显示全屏登录页
- **家庭 / 房间两级分组**：家庭只在侧栏顶部切换（米家 App 的做法），列表里只列
  当前家庭的房间，因此同名房间天然按家庭隔离；家庭选择记在本机。没有归属家庭的
  设备（云端 `home` 为空，如手环）不进房间列表，否则「全部设备 N + 未分配 1」
  对不上账；自定义分组可跨家庭组合设备，点设备详情即可
  加入/移出分组，分组保存在本机 `groups.json`
- **顶栏动作组**：主题（外观浮层）、刷新设备、退出登录都收在顶栏右端，侧栏只管
  导航；外观浮层贴着按钮展开，点面板外或按 Esc 即收起。标签栏锁死不换行
  （1000~1200 这一段只剩几像素余量，否则「设备」会被折成两行），
  挤不下时先由面包屑让位，1180 以下状态读数整条收起，不给半截省略号
- **分类卡片（大 / 中 / 小三尺寸）**：型号定主类别、能力兜底；读数与趋势曲线作为
  通用能力叠加，所以插排、屏显开关也能显示温湿度。灯卡片直接调亮度/色温
  （仅当该设备 spec 支持时出现滑杆），空调/厨电有目标温度步进，传感器/插座
  的大卡有趋势曲线。点开卡片抽屉可看全部读数、全部控件与
  6 小时 / 24 小时 / 7 天趋势切换
- **卡片视觉**：每类设备一枚类型线性图标 + 类型色（灯琥珀 / 插座蓝 / 摄像头紫 /
  传感器绿），设备开启时图标底色填满；名称两行截断、悬停看全名；状态行只读
  一件事（已开启 / 已关闭 / N 路开 / 离线），没状态能力的设备回落显示房间名。
  离线设备不渲染开关与控件（点了也不会成功），尺寸按有无读数收到小卡或中卡；
  除头部外没有任何内容块的卡自动收成单格，不占两列空白
- **在线优先排布**：可用的设备始终排在前面，离线设备统一沉到网格底部，两组内部
  各自保留拖拽顺序，首屏不会被点不动的卡片占住
- 历史趋势：全量轮询顺带采样传感器读数（SQLite，5 分钟一点、保留 7 天、
  查询按时间桶降采样），不额外请求云端；数据目录不可写时自动回退临时库
- 中文本地化：产品名与多键开关标签（`Left Switch Service` → 左键）自动翻译
- 设备控制：开关、亮度、色温、模式、风速档位、摆风，控件由 MIoT spec 自动推导
- 多键开关逐路控制：墙壁双键/三键每一路独立开关（借鉴 MiHome-Windows #2 教训）
- mesh 设备状态保鲜：每 5 分钟主动刷新设备列表（借鉴 #34 教训，对齐米家 App 行为）
- 3 秒开关跟随 + 45 秒全量读数（分层轮询，单请求批量读 N 台设备）
- 场景执行：一键运行米家 App 里已建的手动场景（AppSceneService 接口）
- 自动化（智能场景）管理：`GetSceneList(scene_type=1)` 拉取全部自动化（实测
  信地 19 / 西山银杏 44 / 临时 2），按家庭分组、显示启停状态与「当…且…执行…」
  中文摘要；点开抽屉看触发/条件/动作明细与原始 JSON。支持**改名、启停、新建、删除**：
  新建采用「复制现有自动化」模板（保留触发/条件/动作，默认停用，可先看完整 payload），
  删除需手动输入完整名称复核；所有写入都要二次确认、带 `confirm: true`，
  成功后自动从云端刷新。详见下方「自动化云端写入」
- 自定义设备名（仅本机显示，可一键恢复云端名）
- 卡片外显值自选（最多 2 项，如温度/功率）；产品名兜底（不露英文型号）
- 主题系统（Pico CSS）：浅色/深色 × 7 套色彩预设（蓝/薄荷青/紫/珊瑚/玫瑰/晴空青/琥珀）
  + 自定义主色拾色器，即时切换、本机持久化
- 事件流：所有操作与失败原因落 SQLite
- 天气卡片（替代顶部固定横幅）：Open-Meteo 免费接口（无需 key），与设备共用
  小/中/大三种尺寸；小卡温度+天气，中卡加体感/今日高低温/空气质量/风速，
  大卡加湿度/降水/日出日落与 24 小时温度曲线；点开抽屉看完整读数、逐小时
  预报并可切换城市，10 分钟刷新、接口失败时回退上一次数据并标注
- 设备缓存秒开 + 上次在线时间；房间分组与搜索（可搜自定义名/型号/产品名）
- **详情统一为居中双列弹框**（设备 / 自动化 / 天气三处同规格，920px、高不过 86vh、
  760px 以下收成一列）：
  - 设备：左列「状态 → 控制 → 摄像头」，右列「历史趋势 → 显示名称 → 自定义分组」，
    列内自上而下即阅读顺序
  - 控制区只在「在线且有可写项」时出现，离线或没得操作时整块不放（不再留一句「控制项已隐藏」）
  - 历史趋势在确实没有采样时整块不出现；「还没拉到」与「确实没有」靠 `historyReady` 区分，
    避免每次打开先闪一下再出现
  - 自动化：「只读的触发 / 动作明细 | 写入（改名、启停）与删除」
  - 天气：「当前读数与城市 / 尺寸设置 | 24 小时温度曲线与逐时采样」
- 摄像头专项（点开摄像头卡片）：
  - **参数控制**：夜视、录像模式、宽动态、时间水印、画面翻转等按 MIoT spec 自动暴露为
    真实控件（英文枚举值已中文化：Off/On/Auto → 关闭/开启/自动）
  - **云台 / 动作**：完全按设备 spec 的动作动态生成——有 `pan-left`/`tilt-up`/`zoom-in`
    等就铺成方向盘，其余非破坏性动作给通用按钮；`format`（格式化存储卡）等破坏性动作
    一律不暴露，未知动作保守隐藏
  - **取流能力判定（点了才判）**：面板打开不做任何检测、不摆状态条，只留一句占位文案。
    点「获取实时画面」时后端才判这台能不能在 PC 上出画面，结论分四种——`可跨网络播放`
    （CS2/MTP 新固件，PC 端有实现）、`需同局域网` / `仅支持局域网`（老 TUTK 固件，PC 端
    没有跨网络实现）、`不支持取流`（spec 里没有 p2p-stream）。
    判定依据全部可复核：设备 `localip` 与本机出口地址比对 → 向设备 32761 发 TUTK
    局域网广播包实测可达性 → 云端 `miss_get_vendor` 取厂商类型。结果按 did 缓存
    10 分钟
  - **实时画面（播不了才弹窗）**：能播就直接播；播不了弹一次说明——弹窗里给结论、
    原因、需要满足的条件（含设备与本机各自网段）、设备原始返回，底部一个
    「我已连到同一网络 / 重新检测」加「知道了」。判定为只能局域网时不会去打那次必然
    失败的 `start-p2p-stream`；用户关掉弹窗后，占位文案会留在「需在同一局域网内才能
    播放」，不再重复解释。若设备返回 http/hls/rtsp 直链则自动播放，绝不伪造播放器
- 红外遥控（卡片直接按，详情有完整遥控盘）：
  - 米家的红外遥控是**虚拟设备**（`did=ir.*`、`model=miir.*`，parent 是带发射器的
    小爱音箱），**没有 on 属性**，控制面在 MIoT **动作**（`turn-on` / `volume-up` /
    `temperature-up`…）与 `ir-mode` / `ir-temperature` 两个**只写属性**上；
    自定义遥控（`miir.remote.*`、`miir.wifispeaker.*`）连 spec 都没有，按键表存在云端
    （`/v2/irdevice/controller/keys`），按一下走 `/key/click` 由音箱发码。
    本项目两条通道都接：品类遥控生成命令表（电源/模式/风速/音量/频道/静音/输入源，
    模式翻成中文），**温度是一条「－ 26°C ＋」步进**而不是十几个 °C 按钮；自定义遥控
    铺按键网格；卡片上摆前 4 个常用按钮，点一下即发，成功回执「已发送：音量 ＋」
  - 温度步进：`ir-temperature` 的 `value-range` 解析成 `ir.temp`（min/max/step/default），
    走 `POST /api/ir/temp` 下发**绝对值**（越界、非整数、非步长一律 400）；± 挪的是
    本机记的最后一次发送值（localStorage），组标题标「本机记录」，请求期间锁键防连点乱序
  - 只发码、不伪造状态：红外是单向的，云端读不回「现在是开还是关」，所以不摆开关、
    不做选中态，界面只回「发出去了没有」；空调状态栏也不编一个「26°C 制冷」出来
  - 纯遥控类空壳（米家侧没配按键）如实说明并收成单格；离线时按钮全部禁用并解释原因
  - 按键表按 did 缓存 6 小时（`ir_keys.json`），后台单飞预取、串行带间隔，不阻塞 3 秒轮询
- CLI 入口（`cli.py`）：脚本 / AI agent 可直接控制设备与场景

## 补齐的参考项目未实现项

| 项 | 实现 |
|---|---|
| 失败可操作提示 | `services/hints.py` 的 `failure_hint_for()` 按错误类型给建议（原属定时模块，定时规则下线后独立成模块） |
| 缓存上次在线时间 | `devcache` 的 `last_seen`，只在设备详情弹框里显示（卡片上不铺，避免和在线状态打架） |
| 开关跟随 4s → 3s | 前端 `pollQuick` 3 秒间隔 |
| 数据目录外置 | `MIHOME_DATA_DIR` 或平台用户数据目录，程序目录可只读 |
| 跨平台 | 无 Windows 专属 API，macOS / Linux / Windows 同一套代码 |

## 规避的参考项目已知 bug

- 指示灯 `on` 误当电源位 → 属性按 service 分组映射，附属服务永不映射电源
- 拿 spec 的 `description` 当能力标识符 → 它其实是英文显示名（"Switch Status"），
  标准标识符只在 property URN 第 4 段；`device_list("full")` 只返回 `model`
  没有 `type`，必须用 model 兜底拉 spec，否则全部设备退化成猜测态
- 能力判定二态导致设备开关永久消失 → 三态（True/False/None），猜测不落盘
- 红外遥控「能显示、点不动」→ 这类虚拟设备没有 `on` 属性，控制面在 MIoT 动作
  （`turn-on`/`volume-up`/`temperature-up`）与云端按键表上；只认「on 属性 + 属性
  白名单 + 摄像头动作」等于把账号里 8 台红外设备全判成「没有能力」。
  现在两条通道都接，并且 `miir.*` 在分类里排第一位（否则 `miir.light.*` 会被
  `/light/` 判成灯、`miir.aircondition.*` 会被判成空调）
- 云端返回空 spec 被当成拉取失败 → 空 dict 表示「确认无能力」（个别老设备），
  与网络失败的 None 区分，否则缓存永远落不了盘
- 写路由 405 → 所有写接口显式 `methods=["GET","POST"]`
- 乐观更新被旧轮询盖回 → 版本号竞态防护（与网络快慢无关）
- 半截 JSON 覆盖好缓存 / token 备份 → 全部原子写（tmp + os.replace）
- 测试污染生产缓存 → 测试用 `MIHOME_DATA_DIR` 重定向到临时目录
- 只在定期刷新时应用房间映射 → 登录 / 恢复 / 扫码三条路径都要补；其中扫码
  是 async 协程，不能调同步 `cloud.call`（自己等自己死锁），改为直接 await
  `home_list()` 再复用纯函数
- 房间名做扁平分组 → 不同家庭存在同名房间（厨房/客厅/卫生间），必须带家庭
  id/name 做两级 key；房间 dids 里的 `xxx.s3` 要归一化到主 did，但
  `blt.3.xxx` / `lumi.xxx` 本身是真实 did，不能按 "." 截断
- 按「能力优先」给设备定类别 → 带温湿度的插排被当温度计、空气炸锅被当空调、
  智能门锁被当摄像头。改为型号定主类别，传感器读数作为通用能力叠加到任何卡片
- SQLite 建表失败后把半截连接缓存起来 → 后续一直 `no such table`。连接必须
  建表/索引全部成功后再缓存，并提供临时目录回退
- 3 秒轮询重建 DOM 打断滑杆拖动 → 交互中的设备保留原节点（`holdDid`），
  松手后再刷新；抽屉滑杆同理

## 自测修复的 bug（2026-11-12 全面测试轮）

- 同源守卫对 DNS rebinding 失效 → 改本地源白名单（127.0.0.1/localhost/[::1]）
- quick 轮询丢弃多键开关各路状态（on1/on2 弹回）→ 前后端都按"on 系"键合并
- `last_seen` 被离线设备刷成"刚刚在线"、被磁盘旧值反向覆盖 → 只记在线 + 只补缺不覆盖
- CLI 场景执行缺 home_id 直接失败 → 路由层自动反查
- 事件流 innerHTML 未转义（设备名可注入）→ 全部 textContent
- 抽屉内开关后状态不刷新、搜索匹配不到自定义名/型号、"开着"统计不含多键 → 已修
- **重启恢复登录从未生效**：MiAccount 构造后 token 恒为 None（惰性加载），
  restore 提前退出 → 显式读磁盘 token；并加 token 备份写回（防网络抖动弄丢好 token）
- 未登录时仍显示大量登录后内容 → 全屏登录页（扫码/密码两页签）

## 卡片「左上角白圆圈」（2026-11-13）

现象：每张卡片的左上角都有一个 18px 白圆圈。

根因：单键开关为了走流内布局被写成 `.mini-switch.in-head { position: static }`，
而开关旋钮是 `.mini-switch::after` 的绝对定位元素——`static` 不建立包含块，
旋钮以最近的定位祖先（`.device-card`，`position: relative`）为参照，
被 `top:3px; left:3px` 甩到了卡片左上角；开启态 `left:23px`，所以圆圈还会左右跳。

修复：改成 `position: relative; top: 0; right: 0`，按钮仍在流内，旋钮重新被按钮框住。
同时补 `tests/test_css.py`：只要某选择器有绝对定位伪元素，它就绝不允许被 `position: static`。

## 登录页的小猫（2026-11-13）

登录页卡片底部养了一只纯 SVG 的面包猫（蹲坐 / loaf 姿势），跟着登录状态换表情：

| 状态 | 触发 | 表现 |
| --- | --- | --- |
| idle | 等待 | 圆眼、微笑、慢慢呼吸 + 偶尔眨眼、尾巴轻摆 |
| wait | 二维码已就绪 / 已扫码待确认 | 头微微抬起、尾巴摆得更快 |
| ok | 登录成功 | 眯成两道弯月、跳一下再落地、尾巴立起 |
| err | 二维码过期 / 出错 | 耳朵向外垂（飞机耳）、眉毛压下、嘴角向下、尾巴垂着 |

- 几何全在 `static/login_cat.js` 的 `svg()` 里，颜色走 CSS 变量（`--cat-fur` / `--cat-ink` / `--cat-pink`），
  浅色与深色主题共用一套线条，不用两套图。
- 点一下会抖尾巴；鼠标悬停时头轻抬。
- 所有动效都在 `prefers-reduced-motion` 下关掉。
- 有个坑：pico 里有 `svg:not([fill]){fill:currentColor}`，深色主题下 currentColor 是白色，
  没写 fill 的形状会糊成一片白（眼睛变成白球）。所以 svg 根元素写死 `fill="none"`，
  每个形状自己声明 fill/stroke；`tests/test_css.py` 盯着这条防线。
- 另外 `.mini-*` 之外的元素都别用裸类名（`glint` / `eyeball` 这类），pico 会按标签兜底染色。

## 目录结构

```
Mijia-Web/
├─ app.py            Flask 装配 + 后台保活循环（刷新列表/静默恢复）+ 同源守卫
├─ config.py         路径/端口/轮询参数（数据目录外置）
├─ logx.py           统一日志（数据目录 logs/，按天轮转）
├─ run.py            启动入口（自动开浏览器）
├─ services/
│  ├─ cloud.py       云端调用执行器（超时真取消）
│  ├─ devices.py     登录/设备列表/spec/设备视图（三态能力、属性分组）
│  ├─ qrauth.py      扫码登录（QR 长轮询、token 构造落盘）
│  ├─ live.py        批量读、写属性、版本竞态防护
│  ├─ devcache.py    设备缓存 + last_seen
│  ├─ evtlog.py      事件流 SQLite
│  ├─ hints.py       云端异常 → 可操作中文提示
│  ├─ notices.py     设备通知（米家消息中心未读、去重、已读同步）
│  ├─ weather.py     Open-Meteo 天气（当前/逐时/今日/AQI + 缓存与失败回退）
│  └─ automations.py 自动化列表/中文摘要/编辑/创建/删除 payload 与写入
├─ routes/           HTTP 层（auth/devices/live/misc/scenes/automations/layout/camera/notices/…）
├─ static/           旧前端（原生 JS + Pico CSS，无构建；camera_panel.js 含摄像头面板）
│  └─ vue/           Vue 3 构建产物（index.html + assets/，Flask 直接托管）
├─ web/              Vue 3 + Vite + TS 源码（src/styles 七层样式、stores、components）
└─ tests/            回归测试 4379 项（卡片/图标/分组/历史/天气/自动化/摄像头/取流能力/红外遥控/小猫/spec/缓存/竞态/API/样式不变量/Vue 主题、动效、登录、设备网格、详情增强、其余面板、设备通知与 unslop 视觉不变量）
```

## 自动化云端写入

2026-11-13 用信地「门厅 有人到访按门铃…」这条**已停用**自动化做过四组受控测试，
每步都读回比对并即时还原，最终与测试前快照零差异：

| 阶段 | 操作 | 结果 |
|---|---|---|
| ① | 等值回写（changes 为空） | `wrapped` 报 `scene name is nil or all spaces`；`flat` 成功，内容零改动 |
| ② | 改名 → 读回 → 还原 → 读回 | 云端名称真实变化并成功还原 |
| ③ | `enable` 切换 → 读回 → 还原 → 读回 | 启停真实变化并成功还原 |
| ④ | 新建一条停用测试自动化 → 7 种参数读回确认可见 → `Delete` → 复查 | 创建返回新 `scene_id` 且列表可见，删除后 7 种参数均无残留，24 条快照与创建前完全一致 |

接口事实：

- `POST /appgateway/miot/appsceneservice/AppSceneService/Edit` 的 payload 必须
  **平铺**：scene 的 33 个字段直接放顶层，外加 `home_id` / `owner_uid`；
  成功返回 `{"scene_id":…, "activated":false, "trigger_order":0}`。
  `{"scene_info": {...}}` 包装会被判名称为空。
- `Create` / `CreateScene` / `Add` / `Enable` 等 22 个候选路由实测 404。
  **新建其实是 `Edit` + 不带 `scene_id`**（或 `"0"`）：必须带有效 `scene_trigger`
  与 `scene_action`，且 `temporary` 必须为 `false`（`true` 会让条目在任何列表参数下
  都不可见）；`scene_id: ""` 会被网关判 `unexpected end of JSON input`，空触发条件
  会被 `CheckTriggerConditionAction` 判 `scene trigger not exist`。
- 删除走 `POST /appgateway/miot/appsceneservice/AppSceneService/Delete`，参数
  `scene_id` + `home_id` + `owner_uid`，返回 `true`；实测能真实删除新建条目。
- 写入链路（PC 端已开放，全部要求 `confirm: true`，缺确认返回 400 且不发请求）：

  | HTTP 接口 | 作用 | 守卫 |
  |---|---|---|
  | `POST /api/automations/apply` | 改名 / 启停 | 白名单字段、等值改动不发请求 |
  | `POST /api/automations/create` | 新建 | 复制模板、默认停用、`temporary=false`、`enable` 必须为布尔 |
  | `POST /api/automations/delete` | 删除 | `scene_id` + **名称精确复核**（路由层与服务层双重校验） |
  | `POST /api/automations/{create,delete}/preview` | 只生成本地 payload | 返回 `sent: false`，绝不外呼 |

  前端每次写入都要 `window.confirm` 二次确认，删除还要求手动输入完整自动化名称；
  写入成功后强制从云端刷新列表。`create_supported` / `delete_supported` 均为 `true`。
  新建采用「复制现有自动化」模板：凭空构造 trigger/action 需要设备 did/model/spec，
  界面无法填写且会被服务端判空触发，所以只列出含有效触发与动作的条目做模板。

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
for f in tests/test_*.py; do ./.venv/bin/python "$f"; done   # 3974 项
for f in tests/test_*.js; do node "$f"; done                 # 405 项
# Vue 3 前端
./.venv/bin/python tests/test_vue_theme.py     # 138 项（七层顺序/浅深令牌/预设色值交叉校验/首帧预涂/unslop 视觉不变量）
./.venv/bin/python tests/test_vue_login.py     # 273 项（新旧纯逻辑逐项比对/状态机分支/端点与组件接线）
./.venv/bin/python tests/test_vue_devices.py   # 1964 项（新旧设备逻辑运行时比对 + 组件/样式/中文文案静态不变量）
./.venv/bin/python tests/test_vue_detail.py    # 255 项（摄像头同源比对 + 取流能力与弹窗 + 组件/端点/样式不变量 + 定时模块已拆除）
./.venv/bin/python tests/test_vue_panels.py    # 510 项（304 项天气/场景/自动化/日志运行时比对 + 组件/端点/样式不变量）
./.venv/bin/python tests/test_notices.py       # 77 项（同步/去重/已读语义 + 接口 + 通知标签与系统通知接线）
./.venv/bin/python tests/test_ir.py            # 99 项（红外识别/命令表/温度步进与校验/按键缓存/视图/接口越权/前端接线）
./.venv/bin/python tests/test_vue_ir.py        # 85 项（52 项运行时比对：分类/尺寸/快捷按钮/副标题/图标与旧版一致 + 组件样式静态不变量）
cd web && npm run build                        # vue-tsc 类型检查 + Vite 打包到 ../static/vue/

# 天气相关
./.venv/bin/python tests/test_weather_api.py   # 40 项（逐时解析/缓存/重试/接口）
node tests/test_weather_card.js                # 72 项（三尺寸渲染/抽屉/DOM 桩）
# 自动化相关
./.venv/bin/python tests/test_automations.py   # 156 项（解析/编辑/创建/删除 payload/确认守卫/HTTP 路由，云端全打桩）
# 摄像头相关
./.venv/bin/python tests/test_camera.py        # 22 项（动作收集/参数控件/枚举中文化/取流/动作安全校验）
./.venv/bin/python tests/test_camera_cap.py    # 45 项（取流能力判定：wan/lan/lan_only/offline/无入口/无证据/缓存/局域网广播包/接口前置判定）
# 样式不变量
./.venv/bin/python tests/test_css.py           # 20 项（绝对定位伪元素宿主不能被 static 化/旋钮边界/卡片裁剪/小猫 SVG 染色与心情钩子）
node tests/test_login_cat.js                   # 87 项（猫的几何结构/心情判定/气泡与节流/四态可区分）
node tests/test_camera_panel.js                # 17 项（动作分类/方向盘/破坏性动作过滤/渲染）
```

## Vue 3 迁移进度（哑光石墨 / Matte Graphite）

参考 `wbr664393425-lgtm/scaffold-master` 的 DESIGN.md 与手写设计系统，把前端从
原生 JS + Pico CSS 迁到 Vue 3 + Vite + TS。**后端 Flask 一个 API 都不改**，
旧 `static/` 原样保留可一键切回。类名、令牌名、七层顺序与 7 套预设机制与上游同源：
⑧ 曾按 unslop 收敛为哑光石墨，⑨ 起把「浮层玻璃」单独请回来——顶栏、抽屉、下拉、
外观面板、提示走半透明 + `backdrop-filter`，设备卡片与阅读面板保持实色，
读数不为磨砂质感让路。动效同理只加在「移动的东西」上：入场、转场、落定与等待
各有固定语态，卡片本体不做常驻动画。

| 步骤 | 状态 | 内容 |
| --- | --- | --- |
| ① 骨架 | 完成 | `web/` 工程、`outDir=../static/vue`、`base=/static/vue/`；`config.UI_FLAVOR` 控制新旧入口，产物缺失自动回退 |
| ② 主题 | 完成 | 七层样式、Pinia 主题 store、7 套预设 + 自定义主色 + 密度 + 旧 localStorage 迁移 |
| ③ 登录 | 完成 | 扫码/密码双页签、2.5 秒二维码轮询、6 秒恢复检查、登录猫四态、OTP、退出登录 |
| ④ 设备网格 | 完成 | 设备纯逻辑迁 TS、Pinia 数据层、主壳 / 卡片网格 / 详情弹框、第 4-7 层样式实装、构建产物入库；保留旧界面 P0 全部修复 |
| ⑤ 详情增强 | 完成 | 摄像头专项收进新版详情；纯逻辑迁 TS 并交叉校验，新增独立详情数据层，第 4-6 层补齐控件与骨架样式（原二级定时面板已按 ⑪ 整体拆除） |
| ⑥ 其余面板 | 完成 | 场景执行、自动化列表 / 新建 / 详情写入、事件流、天气三尺寸卡与详情弹框；纯逻辑迁 TS 并交叉校验，新增独立面板数据层。场景列表改成等宽砖块：68px 高、按名称匹配线性图标、同名场景补序号，按下有水波、执行中转圈、成功轻震 |
| ⑦ 收口 | 完成 | 19 个 headless 场景 + 8 张截图全量视觉复核（零 console 报错、零溢出、零裁切、零横向溢出）、构建产物幂等、`vue`/`legacy` 两态入口与新旧资源全 200；默认入口已切为 `vue`，legacy 仅作应急回退 |
| ⑧ unslop | 完成 | 按 `heydamir/unslop` 九 passes 重构新版 Vue 界面：去玻璃 / 渐变 / 光晕 / 彩色投影，收敛到一条中性色阶 + 单一强调色；统一线性图标、字重、4px 栅格、分级圆角与一次性动效；3550 项回归零失败 |
| ⑨ 玻璃与动效 | 完成 | ① 材质：`.m-glass / -strong / -rail` 三档玻璃配方回到第 3 层，玻璃只由浮层使用，卡片与表格仍是实色；不支持 `backdrop-filter` 或系统要求降低透明度时自动退回实色。② 动效：GSAP 只经 `motion/` 入口，统一「放 / 导 / 结 / 停摆」四语态——卡片错峰入场、主标签页淡出落下、抽屉回弹拉出、读数数字滚动、主题切换扫光、拖拽 FLIP 补位、未连通与同步中缓慢呼吸；`prefers-reduced-motion` 下全部直接进终态。③ 布局仪器化：统计条拆成读数格 + 在线率微槽，格间发丝线、数字等宽（格数与分组在 ⑪ 重做）；侧栏选中位改成一根只移动、不参与布局的竖条（几何量在 DOM 里量，房间增删不跑偏）；窄屏（<980）侧栏收起后，家庭切换移到顶栏最左、面包屑让位，菜单改向左展开；底部曾加一条深色铭牌（同步语态 / 家庭与视图 / 时钟），已按 ⑩ 的反馈整条拆除 |

| ⑩ 设备通知 | 完成 | 接入米家消息中心（`/v2/message/v2/typelist`）后台轮询未读消息，按 `msg_id` 落盘去重；顶部新增「通知」标签（排在日志前）+ 未读角标，右下角卡片提醒，可一键开启浏览器系统通知；同时拆掉常驻底栏黑条，灯具切模式后回读亮度/色温 |
| ⑪ 范围统计与减法 | 完成 | 统计条改读当前家庭/房间/搜索结果，并按 照明 / 环境 / 传感器 / 其它 分组（空组不占格）；定时规则整条下线（自动化可覆盖同一诉求）：前后端路由、调度器、详情块、统计格、CLI 与旧界面入口全部删除 |
| ⑫ 计数格即筛选 | 完成 | 统计条每格改成按钮：点「照明 / 环境 / 传感器 / 其它」只看该类，点「在线」只看在线设备，再点一次或点「设备」回全部；卡片筛选与读数分开（点完条不塌），换家庭/房间时自动归零 |

```bash
# 默认即新版 Vue，直接启动
python run.py
# 应急回退旧版（仅排障用）
MIJIA_UI=legacy python run.py
```

前端只需一次性 `cd web && npm ci && npm run build`，产物入库后开机只跑
`python run.py`，**不需要 Node 常驻服务**。不引 Vue Router（沿用 tab 切组件）；
GSAP 只作动效引擎，且只经 `web/src/motion/` 一个入口调用，组件不直接 import。
原有后端与旧前端测试全部保留，新增 `test_vue_theme.py`（159 项）、
`test_vue_motion.py`（81 项）、`test_vue_login.py`（273 项）、
`test_vue_devices.py`（1788 项）、`test_vue_detail.py`（255 项）、
`test_vue_panels.py`（510 项）、`test_notices.py`（77 项）与
`test_hints.py`（6 项）盯住新版不变量。

### ⑧ unslop 设计方向与九遍改动

| 行 | 内容 |
| --- | --- |
| 产品 | 给家里有多台小米设备的人，在一块桌面屏幕上按房间查看与控制设备状态 |
| 性格 | 克制、可核对、带仪表感 |
| 世界 | 家庭配电箱与夜间客厅的仪表面板，哑光中性石墨带一点暖灰 |
| 高光时刻 | 设备卡的实时读数与温湿度曲线、天气卡的 24 小时曲线；颜色只出现在这两处与选择位 |
| 签名细节 | 在线状态小圆点，只用于状态位，不做装饰 |

九遍按顺序落地：① 间距收 4px 栅格、侧栏 256 / 顶栏 56；② 颜色换成中性色阶，7 套预设只决定唯一强调色；③ 图标统一 `.ui-ico`（16px / 1.5 描边），`✕ ◐ ▾ − +` 全部替换；④ 文案去箭头、去掉「珍珠玻璃」品牌副标；⑤ 字重落 400/500、去掉全大写眉标与负字距；⑥ 面板宽度放到 1440、保持桌面应用比例；⑦ 分级圆角、计数改安静等宽文字、状态点去光晕；⑧ 移除颗粒层、指针光晕、登录页两团漫射光与天气卡渐变；⑨ 删除三组无限循环猫动效，只留状态触发的一次性动作，全站一条缓动曲线。

视觉不变量由 `test_vue_theme.py` 盯住：无 `backdrop-filter`、无色相渐变、无 `radial-gradient`、无 `mix-blend-mode`、无 `infinite`、字重不超 500、胶囊只留给开关轨道。

### ③ 登录链路要点

- 纯逻辑与副作用分离：`web/src/login/cat.ts`（猫的几何 / 台词 / 心情判定）与
  `core.ts`（轮询分支、状态文案、恢复判定、节拍常量）都不碰 DOM；
  `stores/auth.ts` 只负责 fetch、定时器与状态；组件只渲染。
- 与旧界面同源：`tests/test_vue_login.py` 用 Node 直接加载 TS 模块，把
  `svg()` / `moodOf()` / `pupilShift()` / `pickLine()` 与 `static/login_cat.js`
  逐项比对，防止两套实现漂移。
- 登录成功先进 `entering` 态，由 `LoginCat.playIn(700, finishEnter)` 让猫跳完再收页；
  `playIn` 只生效一次，重复回调直接放行。
- 样式走第 7 层 `pages.css`：卡片用 `--surface` + `--glass-line` + `--e3`，
  主操作色跟随 7 套预设；二维码底板在深色主题下也保持纯白。
- 运行时验收覆盖 13+ 场景：等待扫码 / 过期 / 出错 / 登录成功 / 取码失败 /
  已登录 / 恢复中 / 页签停启轮询 / 点猫 / 刷新 / 密码失败与 OTP / 密码成功 /
  深色切换 / 退出登录。

### ④ 设备网格与抽屉要点

- 纯逻辑同源：`static/cards.js`（分类/尺寸）、`device_icons.js`（13 类 SVG）、
  `groups.js`（家庭房间树）、`card_types.js`（读数/标签/曲线/控件）迁到
  `web/src/devices/*.ts`；`tests/test_vue_devices.py` 用 Node 直接加载 TS，
  与旧模块逐项比对 1518 项，零漂移。
- 数据层：`stores/devices.ts` 覆盖 `/api/devices`、`/api/live`（quick/full）、
  `/api/layout`、`/api/groups`、`/api/history`、`/api/switch`、`/api/set`；
  版本竞态、乐观更新回滚、自定义名/外显值本地持久化、拖拽顺序与尺寸覆盖、
  3s 快轮询 + 45s 全量轮询。**后端一个 API 都没改**。
- 组件：`App.vue` 主壳 + 侧栏 + 顶栏 + 设备网格 + 详情弹框；卡片只渲染
  `buildCard()` 算好的模型，不自己判断内容预算。
- P0 修复原样保留：类型图标与类型色、名称两行、状态区重排、离线零控件、
  空壳收口成 1×1、固定 128px 行高；`mini-switch` 宿主默认 `position: relative`，
  杜绝「左上角白圆点」复发。
- 第 4-7 层样式实装：组件 / 仪器 / 外壳 / 页面各司其职，颜色只取语义令牌，
  浅深与 7 套预设自动跟随；表格密度令牌 `--row-h` 不参与卡片行高。
### ⑤ 详情增强要点

- 定时规则已按 ⑪ 整体下线：设备详情右列不再有「定时」块，`stores/detail.ts`
  只剩摄像头专项，`/api/sched*` 与 `services/scheduler.py` 一并删除。
- 摄像头专项：`PTZ_SYMBOLS` / `SAFE_ACTION` / `DENY_ACTION` / 方向盘五格顺序
  与 `static/camera_panel.js` 逐项比对；破坏性动作（format / pop-up …）仍只进
  `denied`，模板里一律不渲染。取流仍「尽力尝试」，拿不到可播地址就如实说明并
  折叠展示原始返回，绝不伪造播放器。
- 数据层独立：`stores/detail.ts` 只管 `/api/camera/*`，
  ④ 已验收的 `stores/devices.ts` 一行不改；取流结果按 did 缓存，抽屉关闭再打开
  不会丢状态。失败提示复用设备 store 的全局 toast。
- 验收修正：方向盘五格三列与旧版同源，未擅自改成十字；取流失败只在点「获取实时
  画面」后弹窗说明，面板里不常驻状态条。
- 同源测试：`tests/test_vue_detail.py` 用 Node 直接加载 TS，与旧
  `camera_panel.js` 的 `classify()` / `applyStream()` 逐项比对，另查组件接线、
  端点、样式钩子、「旧前端零牵连」，以及定时模块在前后端与旧界面都不再有残留。
- 场景 / 自动化 / 日志 / 天气卡片在 ⑥ 迁入新版；旧界面随时可回退。

### ⑥ 其余面板要点

- 纯逻辑同源迁移：`web/src/panels/weather.ts` 与旧 `weather_card.js` 的
  `kindOf` / `iconSvg` / `aqiGrade` / `fieldsFor` / `tempText` / `pctText` /
  `hourlySeries` / `hourlyLabels` / `tempRange` 逐项运行时比对；`scenes.ts` /
  `automations.ts` / `events.ts` 把旧 `app.js` 里散在 DOM 函数中的 payload 形状、
  模板筛选、四个详情区块、确认文案与文案拼接收敛成纯函数，另用源码文本断言
  锁住端点与轮询节奏。
- 数据层独立：`stores/panels.ts` 只管 `/api/scenes*`、`/api/automations*`、
  `/api/events`、`/api/weather`；④⑤ 的 `devices.ts` / `detail.ts` 一行不改。
  15 秒 / 5 分钟 / 10 分钟轮询节奏照搬旧版，退出登录一并停掉。
- 写入守卫：改名 / 启停 / 新建 / 删除都先二次确认，请求一律带 `confirm: true`，
  删除还要完整输入自动化名称复核；组件不直接发请求。
- 场景砖：`panels/sceneIcons.ts` 只按名称关键词挑一枚线性图标（睡 / 帘 / 空调 /
  离家 / 回家 / 影 / 灯），词序先长后短，猜不到用闪电兜底，不改场景名、不加控件；
  同名场景（米家常见复制出来的几条「灯全关」）从第 2 条起标 `×2`。砖块 68px 高、
  `auto-fill minmax(208px,1fr)` 等宽排布，窄屏 620 以下三列 60px。动效全部走
  `motion/`：`scenePress` 从指尖扩散水波（半径取到最远角，圆盖满整块不露切边）、
  `spin` 只在 `busy` 期间转（CSS 不写 infinite）、`sceneSettle` 成功才轻震一下，
  并在结束时清掉内联 transform，否则会压住 hover 上浮。
- 天气卡回到设备网格首位（仅「全部设备 + 无搜索」时显示），三尺寸信息预算、
  24 小时曲线与欧洲 AQI 分档与旧版一致；城市与卡片尺寸仍只存本机。
  详情弹框补完整读数、逐时条与刷新 / 恢复默认城市。
- 三种抽屉互斥：设备 / 自动化 / 天气共用右侧栏，打开一种会收起另外两种；
  统计条只读当前家庭/房间范围，并按常用类型分组；这些计数格本身也是筛选入口（见 ⑪ ⑫）。
- 自动化列表不折叠、按家庭隔离：进入 tab 直接铺满当前家庭的全部条目，由页面整体
  滚动（不再套 420px 内嵌滚动区）；`stores/panels.ts` 的 `automations` 仍存云端全量，
  界面只渲染 `scopedAutomations`——顶部选了哪个家庭就只列哪一家，两边都有 `home_id`
  时只认 id（同名家庭不串门），条数与启用数、模板下拉、空态文案都跟着收窄。
  旧界面没有家庭切换器，仍按家庭分组展示。
- 「预览请求内容」只在本机拼装请求体、绝不写入米家：先说清发往哪个端点、改了哪几项
  （`name`/`enable` 翻成「名称/状态」），再附完整 JSON；什么都没改时前端直接提示
  「当前没有改动」，不再拿空 patch 去请求后端、把「patch 必须是非空对象」甩给用户。
- 同源测试：`tests/test_vue_panels.py` 用 Node 直接加载 TS 与旧模块比对，
  另查组件接线、端点、写入守卫、样式钩子与「旧前端零牵连」。

### ⑦ 设备通知要点

- 数据来源：米家「消息中心」的未读消息，接口 `POST /app/v2/message/v2/typelist`
  （body 传 `{}`），返回 `{"messages": [...]}`。每条带 `msg_id` / `type` /
  `title` / `content` / `did` / `ctime`，`params.body` 里还有 `event`、`model`
  与 `homeRoomExtra{homeName, roomName}`。实测 `type=6` 是设备消息（门铃、门锁
  超时未关、清扫完成、电量低、烟机久开），`type=13` 是自动化/场景执行结果。
- **只读不写**：这个接口只回未读消息，同一账号多端共享已读态。系统不去调
  云端「标记已读」，免得把用户手机上的小红点清掉；本地由 `services/notices.py`
  按 `msg_id` 去重落盘（`notices.db`），首次同步把现存未读当历史（`seen=1`），
  之后到达的才算新通知；云端不再列出、本机还标未读的，说明在手机上读过了，
  本地跟着清。
- 节奏：后端每 `config.NOTICE_POLL_S`（15 秒）拉一次，未登录或小米风控冷却
  （-127）期间直接跳过；前端每 10 秒轮 `/api/notices`，只打本机接口。
- 界面：顶部标签「通知」排在「日志」前，未读数做成标签上的角标；面板逐条给
  标题、设备 · 房间 · 家庭、类型与时间，点一条即清红点并跳到对应设备详情。
  右下角最多压 3 张卡片，9 秒自己收，新到的才弹（6 小时内的），补跑的历史只
  进列表不震。
- 浏览器系统通知需用户手势授权：面板与卡片里都有「开启浏览器通知」，授权后
  用 `new Notification()` 推送，`tag` 取 `msg_id`，同一条不会堆两条；点击通知
  回到窗口并打开对应设备。浏览器不支持或已屏蔽时如实写在面板上。

### ⑧ 灯具联动与底栏收口

- 灯具切「模式」时云端会连带改亮度和色温（吊灯切「傍晚」会把色温推到暖白）。
  写入成功后 `DeviceDrawer` 清掉滑块临时值，并调用 `store.settleDevice()` 做
  两拍回读（600ms / 2200ms）：第一拍拿模式落地后的联动值，第二拍兜设备侧慢
  上报。拉杆松手后也回读一次，显示设备夹过步进的真值。为此 `/api/live` 新增
  `?did=` 单台全量回读，不回写历史采样、不额外批量。
- 常驻底部黑条（同步语态 / 家庭与视图 / 时钟）整条拆除：与统计条信息重复，
  而且固定压在内容下缘。`.plate-bar` / `.pb-*` 规则与 `--plate-*` 令牌一并删掉，
  内容区底部留白从 72px 收回 24px，`.toast` 落回页底 24px。

### ⑪ 统计条按范围重做 / 定时规则下线

- 统计条原来读的是 `deviceList`（全部设备）：选了「厨房」还显示 96 台，红框里
  的数字和脚下一屏卡片对不上。现在统一读 `scoped`（家庭 / 房间 / 搜索都算），
  并改成「设备（附「开 N」）/ 在线 / 照明 / 环境 / 传感器 / 其它 / 在线率」。
  分组口径：照明 = 灯具 + 墙面开关 / 通断器；环境 = 温湿度、空调、新风净化；
  传感器 = 纯探测器（人体、门磁、烟感…）；插座、窗帘、厨电、摄像头等归其它。
  空组不渲染，格数由 `--stat-cols` 决定，窄房间不会出现一排 0。
- 定时规则整条下线：米家自动化本来就能做「几点开灯」，再留一套只支持开/关的
  规则，用户得先判断该去哪边改。删除范围：
  `routes/sched.py`、`services/scheduler.py`、`SchedPanel.vue`、`devices/sched.ts`、
  详情 store 的 `rules/loadRules/addRule/removeRule`、统计条的「定时规则」格、
  `cli.py sched`、旧界面 `#sched-panel` 与 `renderSched()`，以及三处样式与
  `config.SCHEDULES_PATH` / `SCHED_*` 常量。
- `failure_hint_for()` 不属于定时，迁到 `services/hints.py`；`routes/devices.py`、
  `routes/camera.py` 改从这里取提示，避免为了一个函数留下整个调度器。
- `app.py` 的 `_sched_loop` 收成 `_bg_loop`：保留「每 15 跳刷新设备列表」
  （mesh 状态保鲜）与「每 9 跳未登录静默恢复」，去掉规则判定与执行。
- 老数据无需迁移：`schedules.json` 不再被读取（留着也不影响）；历史上已写入的
  `sched` 事件仍在事件流里可查。

### ⑫ 计数格即筛选

- 统计条上的格子从纯读数变成按钮：`照明 / 环境 / 传感器 / 其它` 各自只看该类，
  `在线` 只看在线设备，`设备` 回全部；同一个口子再按一次也取消（`toggleStatFilter`）。
  在线率格是仪表，不参与筛选。
- 关键取舍：**读数与卡片用两个不同的集合**。`scoped` 是家庭 / 房间 / 搜索的范围，
  `visible` 是它再叠一层 `filterByStat`。统计条读 `scoped`——若读 `visible`，
  按下「照明」后其它组计数变 0、整条会塌成只剩一格，也就没法再点回去。
  代价是筛选时「设备」格仍显示范围内总数（63），实际卡片只有 20 张，所以条下
  补一行「只看 照明 · 20 台 · 显示全部」把当前口径说清楚。
- 筛选是第二维，不写进 `filter` 键（那个键表示家庭 / 房间 / 分组层级），也不持久化：
  刷新回全部。切家庭或切房间时一并归零——留着上一处的「只看照明」，进到没有
  灯具的房间只会看到空白，还以为设备丢了。
- 可点性与无障碍：`<button>` + `aria-pressed` + `title`；样式上 `.stat-cell.is-tap`
  重置 UA 边框与默认字族，分隔线改用 `.stat-strip .stat-cell + .stat-cell`
  提高特异性，否则按钮的 `border: 0` 会吃掉格间的发丝线；选中态是主色浅底 +
  主色字，不新造胶囊圆角。窄屏两列的分隔线同样带上 `.stat-strip` 前缀。
- 天气卡在有统计筛选时隐藏（它是全局信息，不属于任何一类设备）。
- 窄屏不再拆成两列：六格仍排一行（列数跟 `--stat-cols` 走），只有在线率
  落到第二行跨满。两列会把「设备 63」与「在线 54」各占半行，读起来像三张
  互不相干的表。一行放六格靠收 padding（16 → 10 → 6）与字号（19/11 → 17/10 →
  16/9.5），标签 `white-space: nowrap` 防换行导致格子高矮不齐；在线率格要
  显式 `border-left: 0`，否则 `.stat-cell + .stat-cell` 会给它留一条竖线。

## 配置

| 环境变量 | 说明 | 默认 |
|---|---|---|
| `MIHOME_DATA_DIR` | 数据目录（缓存/事件/日志/token） | 平台用户数据目录 |
| `MIHOME_PORT` | 端口 | 8765 |
| `MIHOME_CITY` | 天气城市（卡片抽屉里也可单独切换并存本机） | 合肥 |
| `MIHOME_LOG_LEVEL` | 日志级别 | INFO |
| `MIHOME_UPDATE_REPO` | 在线升级仓库 `owner/repo`，留空禁用检测 | 空 |
| `MIHOME_UPDATE_TOKEN` | 可选 GitHub token（抬高限流 / 私有仓库） | 空 |
| `MIHOME_GITHUB_URL` | 关于窗口展示的项目主页 | 按仓库自动拼 |
| `MIHOME_UPDATE_AUTO_RESTART` | 升级后是否自动重启并刷新页面 | 开 |

## 免责声明

本项目为非官方第三方客户端，与小米公司及米家官方无任何隶属或合作关系。
仅供学习交流与个人使用；登录凭据只存本机数据目录，不上传任何第三方。
