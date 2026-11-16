/* 云端英文文案 → 中文展示名（纯函数，无 DOM 依赖）。
 *
 * 米家云端返回的枚举选项（mode / fan-level / target-temperature）与设备动作名
 * 都是英文标识，旧版直接把它们渲染出来，卡片和抽屉里就会出现 "Low"、
 * "AF-CHICKEN-WINGS" 这类字样。这里只做展示层翻译，不改云端任何值：
 * 匹配前统一小写、把下划线与连续空格归一，命中不了才退回原文。
 *
 * 词表按「同词不同义」拆开：fan-level 的 low 是低档、mode 的 low 不会出现；
 * 厨电模式用 AF-/BK-/STM- 这类前缀表示烹饪方式，译成「蒸·鱼」既保留区分，
 * 又比「STM-FISH」好读。
 */

const norm = (s: unknown): string =>
  String(s == null ? '' : s).trim().toLowerCase().replace(/[\s_]+/g, ' ')

/** 通用词表：灯、空调、洗衣机、厨电共用的高频选项。 */
const GENERIC: Record<string, string> = {
  // 状态类
  auto: '自动', manual: '手动', none: '无', null: '无', normal: '标准',
  common: '常用', off: '关', on: '开', idle: '待机', memory: '记忆',
  'user define': '自定义', custom: '自定义', calibrate: '校准', reversal: '反转',
  agemode: '年龄模式', cleanmode: '清洁模式', softmode: '柔和模式',
  'mixed mode': '混合模式', 'normal mode': '标准模式', 'jog mode': '点动模式',
  'wireless mode': '无线模式',

  // 灯光
  reading: '阅读', night: '夜晚', 'night light': '夜灯', day: '白天',
  dusk: '傍晚', sleep: '睡眠', wakeup: '唤醒', computer: '电脑', tv: '电视',
  office: '办公', entertainment: '娱乐', baby: '宝宝', 'baby care': '婴儿护理',
  hospitality: '酒店', warmth: '暖光', lighting: '照明',
  'eye protection': '护眼', breath: '呼吸', beat: '节拍', rhythm: '律动',
  'my mode-scenario 1': '自定义场景 1', 'my mode-scenario 2': '自定义场景 2',
  'my mode-scenario 3': '自定义场景 3', 'my mode-scenario 4': '自定义场景 4',

  // 空调 / 环境电器
  cool: '制冷', heat: '制热', fan: '送风', dry: '除湿', ventilate: '通风',
  defog: '除雾', 'quick defog': '快速除雾', 'quick heat': '快速制热',
  'air dry': '风干', 'ac-deodorize': '除味', 'ac-drying': '烘干',
  'ac-water-cleaning': '水洗清洁', sterilization: '除菌', 'fan-only': '仅送风',

  // 洗衣机
  cotton: '棉织物', synthetic: '化纤', wool: '羊毛', 'down coat': '羽绒服',
  jacket: '外套', shirt: '衬衫', underwear: '内衣', 'quick wash': '快洗',
  'heavy wash': '强力洗', 'daily wash': '日常洗', 'delicate wash': '轻柔洗',
  'dry air wash': '风干洗', 'rinse spin': '漂洗脱水', spin: '脱水',
  'drum clean': '筒清洁', intensive: '强效', 'quick wash dry': '快洗快干',

  // 马桶 / 热水
  'posterior wash': '臀洗', 'feminine wash': '妇洗', 'warm water': '温水',
  'boiled water': '开水', boiling: '沸腾',

  // 网络
  wireless: '无线', wired: '有线', 'wired and wireless': '有线 + 无线',

  // 厨电里「只有烹饪方式、没有食材」的模式名
  'rs-roasting': '烘烤', 'ad-air-dried': '风干', 'fm-fermentation': '发酵',
  'td-thawed': '解冻', 'rh-air-fry': '空气炸',
}

/** 按控件 key 的专属词表：同一个词在不同控件里含义不同。 */
const BY_KEY: Record<string, Record<string, string>> = {
  'fan-level': {
    low: '低档', medium: '中档', high: '高档', auto: '自动', 'stir-fry': '爆炒',
  },
  'target-temperature': {
    '30': '30℃', '40': '40℃', '60': '60℃', '96': '96℃',
    'cold water': '冷水', none: '无',
  },
}

/** 厨电模式前缀：MG 协议里前缀即烹饪方式。 */
const FOOD_PREFIX: Record<string, string> = {
  af: '炸', bk: '烘焙', ss: '炖', stm: '蒸', sf: '煎', vd: '慢煮',
  rh: '空气炸', rs: '烘烤', fm: '发酵', ad: '风干', td: '解冻',
}

/** 厨电模式的食材 / 菜式。 */
const FOOD_ITEM: Record<string, string> = {
  'beef-steak': '牛排', 'chicken-steak': '鸡排', 'chicken-wings': '鸡翅',
  'frozen-fries': '冷冻薯条', 'pork-belly': '五花肉', shrimp: '鲜虾',
  'sweet-potato': '红薯', egg: '鸡蛋', 'egg-custard': '蛋羹', fish: '鱼',
  meat: '肉类', seafood: '海鲜', corn: '玉米', bun: '包子', bread: '面包',
  cake: '蛋糕', 'cheese-tart': '蛋挞', pizza: '披萨', dumplings: '饺子',
  vegetables: '蔬菜', salmon: '三文鱼', stew: '炖汤', dessert: '甜品',
  'baby-porridge': '宝宝粥', 'birds-nest': '燕窝',
  'miscellaneous-grains': '杂粮',
}

const hasChinese = (s: string): boolean => /[\u4e00-\u9fff]/.test(s)

/** 词表查询：连字符与空格在这里等价（normal-mode = normal mode）。 */
function lookup(table: Record<string, string> | undefined, n: string): string | undefined {
  if (!table) return undefined
  if (table[n] !== undefined) return table[n]
  const spaced = n.replace(/-/g, ' ')
  return table[spaced]
}

/** 枚举选项 → 中文。命中不了返回原文，避免把值翻译丢。 */
export function optionLabel(key: string, text: unknown): string {
  const raw = String(text == null ? '' : text)
  if (!raw) return ''
  const n = norm(raw)

  const perKey = lookup(BY_KEY[key], n)
  if (perKey !== undefined) return perKey

  const generic = lookup(GENERIC, n)
  if (generic !== undefined) return generic

  // 厨电：AF-CHICKEN-WINGS → 炸·鸡翅；AF-CUSTOM → 炸·自定义
  const dash = n.indexOf('-')
  if (dash > 0) {
    const prefix = FOOD_PREFIX[n.slice(0, dash)]
    const rest = n.slice(dash + 1)
    if (prefix) {
      if (rest === 'custom') return prefix + '·自定义'
      const item = FOOD_ITEM[rest]
      if (item) return prefix + '·' + item
    }
  }

  if (hasChinese(raw)) return raw
  // 纯数字选项：保留数字，交给调用方补单位
  if (/^-?\d+(\.\d+)?$/.test(n)) return raw
  return raw
}

/** 设备动作名 → 中文（摄像头、扫地机等按钮）。 */
const ACTION_LABELS: Record<string, string> = {
  bind: '绑定', ctrl: '控制', format: '格式化', identify: '识别',
  next: '下一个', pause: '暂停', play: '播放', previous: '上一个',
  seek: '快进定位', stop: '停止', toggle: '切换', 'turn-off': '关闭',
  'turn-on': '开启', 'wake-up': '唤醒', 'find-device': '查找设备',
  'follow-led': '指示灯跟随', 'capture-log': '导出日志',
  'cancel-cooking': '取消烹饪', 'cancel-steam-clean': '取消蒸汽清洁',
  'clear-code': '清除绑定码', 'clear-map': '清除地图', 'close-water-clean': '结束水洗',
  'confirm-clean': '确认清洁', 'continue-sweep': '继续清扫',
  'cycle-timing-off': '关闭循环定时', 'cycle-timing-on': '开启循环定时',
  'delete-map': '删除地图', 'delete-remote-control': '删除遥控器',
  'download-voice': '下载语音', 'emit-virtual-event': '触发虚拟事件',
  'empty-host-water-tank': '清空清水箱', 'enter-remote': '进入遥控',
  'enter-roast': '进入烘烤', 'enter-steam-cleaning': '进入蒸汽清洁',
  'enter-water-clean': '进入水洗', 'execute-text-directive': '执行文本指令',
  'exit-remote': '退出遥控', 'get-download-status': '查询下载状态',
  'get-room-configs': '读取房间配置', 'input-source-switch': '切换输入源',
  'lbrc-req-bind': '请求绑定遥控', 'lbrc-req-unbind': '请求解绑遥控',
  'led-cofig-off': '关闭指示灯', 'led-cofig-on': '开启指示灯',
  'off-led': '关闭指示灯', 'on-led': '开启指示灯', 'toggle-led': '切换指示灯',
  'local-timing-off': '关闭本地定时', 'local-timing-on': '开启本地定时',
  'manually-back-up-map': '手动备份地图', 'match-code': '匹配绑定码',
  'merge-rooms': '合并房间', 'modify-order-clean': '按顺序清扫',
  'mute-off': '取消静音', 'mute-on': '静音',
  'on-or-temperature': '开机或调温', 'on-switch-brightness': '开关亮度',
  'opposition-led': '对向指示灯', 'overcharging-off': '关闭过充保护',
  'overcharging-on': '开启过充保护', 'pause-sweeping': '暂停清扫',
  'play-music': '播放音乐', 'play-radio': '播放电台', 'play-text': '朗读文本',
  'pop-up': '弹出', 'remote-control': '遥控器', 'req-distance-period': '请求里程周期',
  'reset-brush-head-life': '重置刷头寿命', 'reset-brush-life': '重置刷子寿命',
  'reset-filter-life': '重置滤芯寿命', 'reset-occupy-status': '重置占用状态',
  'restore-factory': '恢复出厂', 'resume-cook': '继续烹饪',
  'set-channel-name': '设置频道名', 'set-channel-number': '设置频道号',
  'set-customize': '自定义设置', 'set-map': '设置地图', 'set-map-name': '设置地图名',
  'set-room-clean-configs': '设置房间清扫', 'set-room-name': '设置房间名',
  'set-water-guard': '设置水量档', 'spatial-learn-reset': '重置空间学习',
  'spatial-learn-start': '开始空间学习', 'split-room': '拆分房间',
  'start-base-station-cleaning': '基站自清洁', 'start-charge': '开始充电',
  'start-check': '开始检测', 'start-cook': '开始烹饪', 'start-dry': '开始烘干',
  'start-dust-arrest': '开始集尘', 'start-mop-wash': '开始洗拖布',
  'start-p2p-stream': '开始取流', 'start-recipe-cook': '按菜谱烹饪',
  'start-room-sweep': '清扫指定房间', 'start-sweep': '开始清扫',
  'start-wash': '开始洗涤', 'start-zone-sweep': '划区清扫',
  'stop-alarm': '停止警报', 'stop-and-gocharge': '停止并充电',
  'stop-check': '停止检测', 'stop-dry': '停止烘干',
  'stop-mop-wash': '停止洗拖布', 'stop-stream': '停止取流',
  'stop-sweeping': '停止清扫', 'stop-working': '停止工作',
  'sync-manual-check': '同步手动检测', 'toggle-light-mode': '切换灯光模式',
  'triggeroffdelay': '触发延时关闭', 'tv-switchon': '打开电视',
  'update-properties-data': '更新属性', 'back-mop-wash': '洗拖布',
}

/** 动作名里的「词根 + 方向」组合：brightness-up → 亮度 ＋。 */
const ACTION_ROOT: Record<string, string> = {
  brightness: '亮度', 'fan-speed': '风速', cct: '色温', channel: '频道',
  volume: '音量', temperature: '温度', speed: '速度',
}
const ACTION_SUFFIX: Record<string, string> = {
  up: '＋', increase: '＋', down: '－', reduce: '－', switch: '开关',
}

/** 动作名 → 中文；未收录的按词根规则拼，仍拼不出就退回原文。 */
export function actionLabel(name: unknown): string {
  const raw = String(name == null ? '' : name)
  if (!raw) return ''
  if (hasChinese(raw)) return raw
  const n = norm(raw)
  const exact = lookup(ACTION_LABELS, n)
  if (exact !== undefined) return exact
  // 动作名里也有一批是模式名（normal-mode、wireless-mode），共用同一张词表
  const generic = lookup(GENERIC, n)
  if (generic !== undefined) return generic
  const dash = n.lastIndexOf('-')
  if (dash > 0) {
    const root = ACTION_ROOT[n.slice(0, dash)]
    const suffix = ACTION_SUFFIX[n.slice(dash + 1)]
    if (root && suffix) return root + ' ' + suffix
  }
  return raw
}
