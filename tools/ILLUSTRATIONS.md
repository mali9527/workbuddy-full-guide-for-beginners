# 插图研究、制作与多语言工作流

已接入 Studio 的离线工具。用于正文写好后研究配图，再调用当前可用的图像工具；软件不会根据标题自动决定图意、偷偷抓网或调用收费服务。完整数据契约见 [FORMAT.md](FORMAT.md)。

所有作品继续使用 notebook-pen-v1 的同一张细方格纸与黑笔样张，只允许黑白中性灰、不透明背景，无重复版本注释。新版生成约束在 assets/illustrations/workflow-v2.json；其摘要由 policy.json 核对。历史 styles/notebook-pen-v1/style.md 和 initial-prompt.txt 保留制作时原文，旧的思维导图禁令不用于新版生产。

## 日常只做三件事

1. 写好并基本核对一个章节／教程，研究在哪里画什么；可以逐章进行，无须等整本书写完。
2. 准备确定的图意、文字与真实界面依据，按目标语言生成候选。
3. 在正文上下文中逐图、逐语言检查，采用具体版本，检查全书一致性。

日常阶段为待研究、待生成、待检查、可用。命令返回 ok 表示操作／检查无硬错误，ready 和各行状态才说明是否已经齐备；警告与未完成不能当作审校通过。

下例从总控运行，将 codex 与图号、路径换成实际目标。独立书仓使用自己的 tools/studio.py，并省略作品参数。图像参考与生产包放在书内已忽略的 .studio 中，不能纳入公开资料。

## 1. 研究写好的正文

~~~sh
python3 tools/studio.py illustrations plan codex
python3 tools/studio.py illustrations plan-check codex
~~~

第一条创建该书 .studio/visual-plan.yaml，列出所有单元、来源摘要、小节和待研究状态；不会填造图意。已有表不覆盖。回读完整章节与必要前后文，标出概念、层级、比较、步骤、状态、操作入口和结果识别等视觉机会。可以主动多用有教学价值的图，不要求先证明文字讲不清。

在相应单元填写 status: reviewed、reviewed_by、checked_on 与 conclusion。候选要写清读者收益、选形式理由、具体位置、必须出现的对象／关系／控件和图文衔接。正文变化时重新回读并更新该单元 source_sha256；不能只更新摘要而跳过研究。需要时重新生成到另一个路径对照来源摘要，不覆盖原分析。

下例为候选结构示意；必须换成真实正文与判断，不能把示例当审阅证据：

~~~yaml
id: FIG-101
reason: 这段介绍的两个对象存在归属关系，适合用分支帮助回顾
benefit: 看清材料怎样归属于当前任务
brief:
  kind: concept
  form: mindmap
  reader_question: 材料与任务是什么关系？
  takeaway: 任务组织当前需要使用的材料
  source_sections: [正文中实际存在的小节标题]
  placement: 正文中实际存在的小节标题
  composition: 一个中心和一个分支；保留两者的归属，不表达时间先后
  content_guard: 不暗示软件界面的实际按钮或自动执行结果
  text_roles:
    task: {role: author}
    material: {role: author}
  structure:
    root: task
    nodes: [task, material]
    edges: [[task, material]]
texts:
  zh-CN:
    title: 任务与材料
    caption: 材料服务于当前任务。
    alt: 当前任务为中心，连接一项参考材料。
    labels: {task: 当前任务, material: 参考材料}
  en:
    title: Tasks and materials
    caption: Reference materials support the current task.
    alt: A current task connected to a reference material node.
    labels: {task: Current task, material: Reference material}
~~~

主语言来自 book.language；目标语言先在 book.outputs.translations 中启用，例如 en: {enabled: true, directory: en}。未启用语言不进入生产。kind 是 concept 或 interface；form 可为 scene、comparison、flow、mindmap、relationship、overview、detail、sequence。思维导图要核对中心、节点、分支归属和连线，不得有环、重复父节点或遗漏节点。

~~~sh
python3 tools/studio.py illustrations register codex --figure FIG-101
~~~

登记会从已完成的分析生成 brief schema 2、各语言文字包和 FIG 登记；候选表改为引用 FIG，避免保留第二份构图全文。截图不齐的界面候选可登记，但仍不能生成。直接编辑 brief 也必须具备绑定当前小节摘要的真实 analysis 记录。

## 2. 界面图先查找、取得与研究真实界面

使用内置 Web 查找官方帮助、演示或原始界面图，也可在获授权的实际软件环境中采集。取得 PNG 实物并实际查看；只有 URL、网页描述或搜索缩略图时仍是缺口。保留真实产品、端、平台、版本、环境、UI 语言和页面状态；原图有私密信息时先制作去敏参考，只将所需去敏图传给生成工具。

界面参考 metadata 示例（以下均为占位，需要真实证据）：

~~~yaml
id: UI-product-input-v1
source_url: https://example.invalid/replace-with-real-source
asset_url: https://example.invalid/replace-with-real-image
product: 实际产品
surface: desktop
platform: mac
version: 实际版本或 unknown（另写 limitations）
environment: local
ui_locale: en
state: input-ready
status: verified
sanitized: true
reviewed_by: 实际查看与核验者
checked_on: '2026-09-25'
viewed_image_sha256: 实际已查看的那张PNG的SHA256
regions:
  - id: input
    box: [0.1, 0.2, 0.8, 0.9]
    text: 实际控件原文
    treatment: keep
    reason: 本图需要帮助读者找到的输入区域
~~~

坐标为实际原图宽高归一化 [x0,y0,x1,y1]。每个区域说明保留、简化或省略理由；不能从没看过的图猜坐标。裁切图使用新 ID，并记录 parent 与 parent_sha256。多状态图用 ui.reference_states 为各参考分别指定实际状态；不能拼造不存在的窗口。

~~~sh
python3 tools/studio.py illustrations reference-add codex --metadata /absolute/reference.yaml --image /absolute/sanitized.png
~~~

工具校验文件摘要，私有实物保存到 .studio/references，安全的来源和区域摘要保存到 assets/illustrations/references。已保存参考不可覆盖，更新使用新 ID。书仓独立核验不依赖私有截图，但重新生成必须有实际图像文件。

界面 brief 增加 ui，包含 product、surface、platform、version、environment、ui_locale、state、references；controls 把每个 role: ui 的标签映射到 {label, reference, region}。标签必须等于区域中核实的 text。书是中文不代表软件界面也要翻成中文；切换软件语言先取得对应真实依据。讲解圈注使用 role: author，命令等使用 {role: literal, value: pwd}。

## 3. 生成包、真实调用与候选

~~~sh
python3 tools/studio.py illustrations pack codex --figure FIG-101 --language zh-CN --output .studio/packs/FIG-101-zh-r01
~~~

生产包包含 inputs.json、prompt.txt、references.json、参考图片及 receipt-template.json。纸底、笔触样张、真实界面参考各有角色、ID 与 SHA-256。不要把软件截图的颜色和主题带入成图。

使用当前可用图像生成工具：实际传入清单中的图片，明确纸张是底稿、样张是笔触、截图只供结构参考。若工具不能读取这些图片，不用“提示词里写了路径”冒充传入；先解决输入能力或保留待处理。生成器看到的标题／标签只取目标语言文字包，构图说明不是要画进图中的文字。实际调用结束后按真实输入填写回执：tool、可知的 model、各参考 passed: true 和输入摘要；未实际传入不能填写 true。模板默认全部 false。

~~~sh
python3 tools/studio.py illustrations import codex --figure FIG-101 --language zh-CN --image /absolute/result.png --pack .studio/packs/FIG-101-zh-r01 --revision r01 --tool image_gen --receipt /absolute/receipt.json
~~~

新版只接收与固定纸张母版宽高相同、每个像素 R=G=B 的不透明 PNG；轻微色偏也拒绝；不会自动去色或贴底来让坏图通过。候选保存为 revisions/zh-CN/r01/zh-CN.png，英语使用独立的 revisions/en/r01/en.png。已存在版本不覆盖。

## 4. 查看候选再采用

~~~sh
python3 tools/studio.py illustrations preview codex --figure FIG-101 --language zh-CN --revision r01 --output .studio/previews/FIG-101-zh-r01.html
~~~

实际打开私有预览，看 358 px 阅读尺寸、全文上下文、源截图与结构底稿，核对纸色、格距、黑笔、文字、连线、UI 原文和箭头。图片不可读就修订；图片文件存在与生成成功都不能代替看图。只把实际完成的检查写成 pass。

审校 JSON：image_sha256、input_fingerprint、language、reviewer、checked_on，以及 content、text、visual、background、monochrome、structure、localization。界面图另需 interface: pass 与 references: {参考ID: 图片SHA256}。在预览和对应语言上下文中完成阅读检查后才填 placement: pass；未做时可采用候选但仍显示待检查，不能发行。审校与图片／输入绑定，修改后使用新修订，不能回改既有通过记录。

~~~sh
python3 tools/studio.py illustrations select codex --figure FIG-101 --language zh-CN --revision r01 --review /absolute/review.json
python3 tools/studio.py illustrations status codex
~~~

选择按语言更新 selection.yaml 与正文对应 FIG 块。共享图意、标签或参考变化时，相关版本失效；只改英文文字不会导致中文图失效。整个书还要逐图看一致性，不能只看单张样图。

## 5. 正文与插图一起本地化

单书 terms.yaml 是小型稳定 ID → 语言表达映射；正文按实际用到的词、插图按 brief.terms 选择依赖。新增无关术语不要求重画全书。标签、标题、图注和替代说明均在各语言文字包中维护。

~~~sh
python3 tools/studio.py translations pack codex --unit first-task --language en --output .studio/translations/first-task-en-r01
~~~

在 source.md 的基础上翻译正文，保留 FIG 标记、命令、代码和受保护词；自然表达不要求与中文等长。翻译是编辑任务，离线命令不伪装成自动英语翻译。完成含义、术语和可读性核对，记录 language、input_fingerprint、output_sha256、reviewer、checked_on、meaning/terminology/readability: pass；输出摘要为 localization.text_hash 的结果，排除受管图片块与导航。

~~~sh
python3 tools/studio.py translations import codex --unit first-task --language en --pack .studio/translations/first-task-en-r01 --text /absolute/translated.md --review /absolute/translation-review.json
~~~

重新导入发现人工修改时停止覆盖。先回读并合并人工修改；真正审过合并结果后，在审校记录中填写 merged_from_sha256（当前人工版本的正文摘要）与 merge_note。工具保存原人工版到私有历史后再导入，不能为了绕过检查随手补摘要。

接着准备 labels.en.yaml，按英文生成、预览、采用图片。长标签可换行、扩框或拆图，不能小到难读、改变节点关系或实际 UI 位置。原软件控件仍按 ui_locale 保留，不能自造“英文按钮”。

明确 textless: true、无图内标签的 concept 图可以用复用命令创建目标语候选；仍须审阅该语言的图注、替代说明与入稿，不继承中文语言审校：

~~~sh
python3 tools/studio.py illustrations pack codex --figure FIG-101 --language en --output .studio/packs/FIG-101-en-r01
python3 tools/studio.py illustrations reuse codex --figure FIG-101 --source-language zh-CN --language en --revision r01 --pack .studio/packs/FIG-101-en-r01
~~~

上述 reuse 只适合明确无字图，不适用于前面的含字思维导图示例。复用记录写明旧图来源，不冒充新生成调用。

~~~sh
python3 tools/studio.py translations status codex --language en
python3 tools/studio.py build codex --language en
python3 tools/studio.py check codex --publication --language en
~~~

build --language en 使用已经审读的英文正文和已采用英文图，生成 en/combined.md；缺图、过期或未审时报告，不回退中文。未启用语言不产生待办，未列入发行范围的语言不阻塞完整语言版。普通 build/check/status 保持离线。传统 build --zh-tw 仍可使用原繁简路径，但不会把图内文字翻译冒充已完成。

## 旧书与快照

旧图片、制作包、SHA-256 和审校结果保持可读。新版项目的新生产使用 schema 2。需要重做旧 FIG 时，先在研究表填同一图号的新方案，再运行 illustrations migrate <作品> --figure FIG-xxx；旧 metadata 保存到 legacy-v1，原图片字节保留，等待新版各语言候选审校，不把旧风格通过自动当作界面事实通过。

总控、两种模板和独立书仓使用相同工具模块、workflow-v2.json 及视觉策略。已有书不因工具更新自动启用英语、翻译正文、迁移 42 张旧图或更换图片。正文、截图检索、视觉判断由执行者真实完成；工具负责保存依据、校验与防止误用。

采用后补入稿检查时，对同一张图的原审校记录仅将 placement 从 pending 改为 pass，再次 select 同一修订；工具保留 review-before-placement.json。其他审校结论变化需要新修订，不能借补审替换图片或放宽内容／风格检查。


全书检查时生成带统一纸底的对照页，同屏检查所有 FIG 与启用语言；缺语言图显示空缺，不借用中文图：

~~~sh
python3 tools/studio.py illustrations gallery codex --output .studio/previews/book-r01.html
~~~

这一步只生成预览；纸张格距、笔触、真实 UI 对照与小字可读性仍需要实际查看，并按图写入检查记录。
