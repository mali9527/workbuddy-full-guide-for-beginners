# Studio 0.1.0 使用说明

Python 3.9+；依赖固定在 requirements.txt。从书仓根目录运行 python tools/studio.py，或加全局 --root。全局 --json 放在命令前。单书工具独立运行，不读取私有总控。

## 查看与检查

~~~sh
python tools/studio.py status
python tools/studio.py check
python tools/studio.py check --publication --units understand choose --language zh-CN
python tools/studio.py check --publication --language zh-TW
~~~

默认 check 输出结构问题和证据缺口；--publication 将所选单元需要的证据作为阻断条件。默认选择全部单元。单元可在 book.yaml 中用非空 required_checks 覆盖书级需求：纯概念单元可只需 editorial/facts，通常有操作承诺的单元保留 operations；本书已按作者明确范围排除客户端实操验证，具体需求以本书 book.yaml、AGENTS.md 及适用范围说明为准，不能据此登记运行通过。变更此范围会使旧摘要待复核；非必需项可有理由地记 not_applicable，不能用 N/A 越过已声明必需项。状态汇总不构建、不开网络；总控模式只有显式 status --write-roadmap 才更新 ROADMAP 的作品受管区；其中证据数量只是登记概览，当前有效性以 check 为准。

检查记录的 source_commit 必须是可取得的源稿提交，paths 必须包含该单元正文。审校记录本身的后续提交不会自我失效，正文、相关配置与事实的变化会使记录需要复核。完整数据格式见 FORMAT.md。

## 构建与翻译

~~~sh
python tools/studio.py build
python tools/studio.py build --check
python tools/studio.py build --zh-tw
~~~

build 先检查权威输入，再在临时目录生成；最后只写配置的生成物与 studio:nav/toc/release 区域。人工介绍保留。受管区域或合订稿有人工修改时停止。缺少标记时人工定位插入，不能由脚本重写整章。

.studio/generated.json 是本地生成物的上次写入记录，本书通过 .gitignore 保留在本地，不公开整个 .studio。首次克隆先运行 build 建立清单，再运行 git diff --exit-code 确认跟踪文件没有变化，最后 check --publication。CI执行同样的步骤；发现生成内容不一致必须修正源稿或构建记录，不能删除清单来强制覆盖人工修改。清单只保护生成内容，不判定事实正确。

繁体需先在工作分支提交原稿；translations.yaml 记录来源、转换版本、文件摘要和审读状态。translation-overrides.yaml 支持 unit、language、可选唯一 anchor、expected、replacement。修订必须唯一命中，否则停止。未登记的译文手改保留现场，整理为规则后再合并。代码围栏、行内代码、路径、链接目标和 protected_terms 不转换。Mermaid 内的可见中文随代码保留，需要时用定位明确的修订规则转换图中文字，再审读。

翻译初稿标 pending；实际审读后才可把 review 改为 pass。源稿或结果变化会重新待审。简体发布不自动声明繁体已同步。

## PDF

仅明确要求时使用：

~~~sh
python tools/studio.py build --pdf --source v2026.09.1 --version v2026.09.1 --export-id 01
~~~

完整操作见 [PDF 导出与检查](PDF.md)。默认共用 A5 标准版，`--pdf-profile mobile` 选择实验窄版，`--export-date YYYY-MM-DD` 固定导出日期。源提交中的 outputs.pdf.enabled 必须为 true。工具从 Git 固定快照构建，不读工作区未提交正文；输出 build/pdf/<正文版本>/<导出号>/，含 PDF、export.json 和 qa.json；诊断保存在 build/pdf-work/。已有导出号拒绝覆盖。视觉审阅的结论需另行记录。

PDF 可选 Python 依赖安装 `python -m pip install -r tools/requirements-pdf.txt`，普通 Markdown 构建不需要。`python tools/studio.py --json pdf-check /绝对路径/book.pdf` 只读检查字体嵌入、链接、越界及稀疏候选；加 `--render --output 新目录` 生成至多12个代表页，需已有 Poppler。机器通过不等于视觉通过。

Mac 环境采用 Pandoc、Typst、中文字体；有 Mermaid 时使用锁定 Mermaid CLI。安装可选 Node 依赖：PUPPETEER_SKIP_DOWNLOAD=true npm ci --prefix tools，并将 STUDIO_CHROME 指向已安装 Chrome 可执行文件。独立安装的渲染器可通过 STUDIO_MMDC 指定。没有图的 Markdown 路径不加载这些工具。

## 发布

以下以独立书仓为例；私有记录必须在书仓外。先核对已授权范围，工具不会替代作者决定。

~~~sh
python tools/studio.py release prepare --records ../private/my-guide/releases --version v2026.09.1 --source HEAD --repo owner/repo --notes-file ../release-notes.md
python tools/studio.py release audit --plan ../private/my-guide/releases/v2026.09.1/plan.json --repo owner/repo
python tools/studio.py release publish --plan ../private/my-guide/releases/v2026.09.1/plan.json --repo owner/repo --account account-name --execute
python tools/studio.py release resume --plan ../private/my-guide/releases/v2026.09.1/plan.json --repo owner/repo --account account-name --execute
python tools/studio.py release entries --plan ../private/my-guide/releases/v2026.09.1/plan.json
~~~

总控模式在 action 后加作品 ID。prepare 要求干净书仓，并在固定提交重新做公开条件检查；清单冻结来源、范围、目标、说明与附件字节。附件使用 --asset，可重复。GitHub 默认不提升 latest；若本次授权含推荐版更新，prepare 时加 --promote --expected-latest 原标签。无原推荐时不传原标签。

publish/resume 通过 gh 已有登录调用 GitHub，要求明确 --repo/--account/--execute。测试作品与 M 阶段必须使用 workspace.yaml 的 test_repositories 允许清单；不把 fixtures 的占位 owner/repo 当真实目标。先让来源提交存在于指定远端，脚本本身不 push 分支。发布响应不明先 audit/resume，不重建附件。

entries 只在本地更新 book.yaml 与 README，要求可核对的公开回执；不会 push。已公开但入口失败应补入口，不能重传正式附件。较新入口已经存在时拒绝旧版本覆盖。

延后 PDF 用 --kind pdf --source-version v2026.09.1 --version pdf-v2026.09.1-01，--source 必须解析到正文标签同一个 C；不提升正文 latest。

## 工具升级

采用版本见 tools/TOOLKIT_VERSION，tools/toolkit-manifest.json 记录入库时各工具文件。先比较已采用版本、本地定制和新源；本地有定制时展示差异并建立升级任务，不能直接覆盖。总控的 tools/toolkit_diff.py 只做比较，没有升级写入动作。

升级后运行 check/build 与对应测试，确认本书规范差异，再更新采用版本。工具升级不自动更新产品事实或正文。


## 历史 schema 1 手绘插图命令

以下一节保留旧格式说明；本书当前28张图均使用 schema 2，以 [ILLUSTRATIONS.md](ILLUSTRATIONS.md) 为实际生产入口。schema 2 要求完全中性灰度，并支持按语言独立生成与验收。不要把下面旧格式的颜色容差或语言限制当作新版规则。

每张图登记于 `book.yaml.diagrams`，`type: illustration`，`spec` 指向 `assets/illustrations/FIG-001/brief.yaml`。纸底和已确认样张随书保存。最终 PNG 必须不透明；透明和半透明像素在导入与构建检查中阻断。

```sh
python tools/studio.py illustrations status
python tools/studio.py illustrations pack --figure FIG-001 --output .studio/illustrations/pack-001
# 在可用图像工具中使用 pack-001/prompt.txt，以风格包 paper.png 为底稿。
python tools/studio.py illustrations import --figure FIG-001 --pack .studio/illustrations/pack-001 --image /path/to/candidate.png --revision r01 --tool image_gen.imagegen --reference-used
python tools/studio.py illustrations select --figure FIG-001 --revision r01 --review /path/to/review.json
python tools/studio.py check
python tools/studio.py build
```

总控运行时，在动作后指定作品 ID，例如 `illustrations status claude-code`。`--image` 和 `--review` 是本机输入；生产包输出路径须在书仓内。版本已存在时拒绝覆盖；下一次使用 `r02` 和新生产包。工具不调用生成服务，不假设模型、成本或种子；实际未知值保留 unknown。

审校 JSON 至少包含 `reviewer`、`checked_on`、`image_sha256`、`input_fingerprint`，以及 `content/text/visual/background: pass`。应先对照正文、逐字标签、箭头与统一纸底进行真实看图检查，再填写结果。`placement` 的阅读复核另记；`select` 只完成工作稿采用，不能代替有效编辑复核或其他公开条件；跨引擎审核仅由作者手动选用。

`status` 从现场推导 planned / selected / placed 与 current / stale。正文相关小节、所引事实、brief、标签、纸底或风格变化会使采用记录过期。标题必须唯一命中；不会模糊猜测位置。正文中的图、图注由成对 diagram 注释界定，自动导航不影响来源摘要。

合订稿和固定提交 PDF 复用仓库中选定的图片字节，不重新生成。繁体 Markdown 的转换不会改动图内文字，`check --language zh-TW` 会单独报告图中文字本地化待验，正式公开时阻断。当前实现只自动采用 zh-CN 图片，繁体图片的独立选择与生成适配器仍待扩展。

插图风格执行检查：公共前缀缺失（包括误写为 undefined）时不能制作生产包；所有采用图在 import/select/check/PDF 读取时解码检查透明度及颜色。彩色像素或明显色偏被拒绝；中性纸纹仅容许每通道 24/255 内的噪声，超过 12/255 的像素不得多于 0.5%。这不是把彩色图去色的转换。仍须人工检查笔触、纸底与文字。图内不得添加重复的界面版本注释。审校记录新增 monochrome: pass，不能只凭旧的 visual: pass 采用。

## 在整个项目中使用

总控 `.venv/bin/python tools/studio.py illustrations status` 会核对全部登记作品和两种模板，包括尚未生成图片的书。总控 assets/illustrations/ 是系列母版；new-book 自动把策略与完整风格包复制到新书。每本书独立运行时仍使用自己的 assets/illustrations/policy.json 和风格快照。

纸底、参考样张和生成前缀的哈希必须符合采用策略；未登记的正文图片、原生 Mermaid 和活动旧图会阻断检查。采用前仍要逐张查看方格纸、黑色中性笔画法、黑白、不透明及无重复界面版本声明。现有工具不会替你生成图片、对彩色图去色或补写未执行的视觉检查。

## GitHub 运营工具（总控）

`growth.py` 使用 Python 标准库，与 studio 的正文生产分开。配置在 growth/catalog.json：version=1，series.title，works 含 id/path/status/repo/description/topics/homepage/start_path/related；cover/social_preview 可选，图片与起读路径相对书仓。draft 不强制起读页；public 必须有真实仓库和本地入口。related 只允许引用其他已公开作品。

```sh
python3 tools/growth.py --root . check
python3 tools/growth.py --root . metadata-plan --work claude-code
python3 tools/growth.py --root . snapshot --work claude-code
```

check 离线核对配置、路径边界、README 本地 Markdown 资源/私有路径、图片 PNG 规格和公开互链；不自动访问外部链接、检查所有 HTML 或证明内容事实。metadata-plan 输出拟设元数据，不修改 GitHub。snapshot 用 gh 参数数组只读调用元数据和四个 Traffic 接口，写 private/<id>/growth/snapshots/；逐项保存成功、失败和 null。Traffic 需要相应读取权限，数据不可用不填零。工具不收集访问者身份、不保存 token、不发布、不安装调度器。


多语言可选字段：locales 以 zh-CN/en 为键，各项含 status(published/overview/draft)、readme_path、start_path、cover。published 必须有真实README和该语言起读页；overview只有介绍页可读，不能视为全文出版；draft可留空。localized_descriptions 保存各语言候选文案，GitHub仍只有一个实际About，工具不按访客语言自动切换。

## 正文后配图与多语言

使用 [插图与多语言工作流](ILLUSTRATIONS.md)。新增 illustrations plan/plan-check/register/migrate/reference-add/preview/reuse；pack/import/select 增加 --language，导入 v2 候选须有真实 --receipt。概念图与界面图共用链路，思维导图是 concept 的 form: mindmap。

translations pack/import/status/build 接入已启用的英文等语言；正文、图中文字和成图共同核对。build --language en 使用已审读英文正文与已采用英文图，不自动翻译、不回退到中文图。传统 --zh-tw 路径保留。所有生成工具和真实视觉研究由执行者在明确生产阶段使用，普通检查与构建保持离线。

作者彩色头像与署名使用 `book.yaml.branding`；总控规范见 `standards/branding.md`，独立书内见 `tools/standards/branding.md`。普通检查验证书内资产摘要，合订稿和PDF复用同一照片。
