# Studio 0.1 data and module contract

Python 3.9+. Dependencies: PyYAML, optional opencc-python-reimplemented for zh-TW.
All paths are relative to the book; work IDs and unit IDs are slugs.
Modules return dicts (JSON serializable); raise common.StudioError for actionable errors.
No network during check/build. Ordinary status doesn't build or fetch.

book.yaml:
  id: fixture-a
  title: 样例甲
  type: book | tutorial
  language: zh-CN
  product: example-a
  audience: 零基础普通人
  baseline: {product_version: fictional-1, checked_on: 2026-09-24}
  repository: {name: owner/repo, default_branch: main}
  is_test: true
  watershed: choose
  parts: # optional local reading-layout extension; independent of section/depth
    - {title: 开篇, starts_at: intro}
  units:
    - id: intro
      title: 认识样例
      path: manuscript/intro.md
      section: popular | watershed | deep | appendix
      depth: 0
      prerequisites: []
      features: [files]
      facts: [example-price]
      required_checks: [editorial, facts] # optional; otherwise inherit book.required_checks
      derived_from: null | {id: terminal-basics, version: v1}
  outputs:
    combined: 全书.md
    readme: README.md
    pdf: {enabled: true, font: "PingFang SC", paper: a5}
    translations: {zh-TW: {enabled: true, directory: zh-TW}}
  diagrams: [{id: MM-01, unit: intro, type: mindmap}]
  protected_terms: [ExampleAI]\n  toolkit: 0.1.0
  published: {version: null, pdf: null}

WorkBuddy 随书扩展（2026-10-04）：`parts` 只管理 README 与中文合订稿的读者分部。
每项仅含 `title` 与 `starts_at`，起点引用稳定单元 ID；首项从第一个单元开始，
后续起点按 units 顺序递增且不重复，至下一起点之前的单元归入当前部。
开篇、附录也可作为阅读分组。章号直接保存在单元 title 中，不从数组序号生成。
有 parts 时生成分组项目列表；合订稿采用书名 H1、分部 H2、单元 H3，正文下移两级，
代码围栏与稳定单元锚点保留。未声明 parts 时保持旧目录和合订稿行为。
此扩展未同步到总控或其他书，也不表示其他语言版与 PDF 已完成分部适配。

facts.yaml is a LIST:
  - id: example-price
    claim: 虚构额度为 10
    scope: {product: example-a, plan: fictional}
    sources: [{url: "https://example.invalid/price", checked_on: "2026-09-24"}]
    checked_on: "2026-09-24"
    category: price | quota | account | install | startup | permission | undo | stable
    ttl_days: 90
    status: confirmed | unknown | changed | false
    critical: true

checks/*.yaml: a single record or list:
  unit: intro
  source_commit: full Git SHA of checked source (no self-reference)
  paths: [manuscript/intro.md]
  kind: editorial | facts | operations | trial
  result: pass | fail | unknown | not_applicable
  checked_on: "2026-09-24"
  engine: claude | codex | human
  author_engine: codex
  platforms: [mac]
  limitations: ""
  reason: ""

Public records never contain private report paths or names of trial participants.
book.required_checks default [editorial, facts, operations] per publish unit;
book.platforms default [mac]; tutorial may set appropriate required_checks.
Editorial review may use the authoring engine, another engine, or a human; engine and author_engine must truthfully name claude, codex, or human. Cross-engine review is optional and runs only when explicitly requested by the author. Its absence is not a publication gate and needs no override reason. Do not create an unknown/fail editorial record merely because cross-review was not requested. Existing evidence, freshness, operations, and human-trial checks still apply.

translations.yaml: mapping with entries list; builder owns exact details.
workspace.yaml:
  phase: M
  series: 普通人的 AI 工具入门系列
  works:
    - {id: fixture-a, path: tools/tests/fixtures/book-a, state: writing, is_test: true, priority: 1}
  candidates:
    - {id: claude-code, state: awaiting-P0}
  test_repositories: []
  records: private

Common API: load_yaml(path), atomic_write(path,text), safe_path(root,relative),
run_git(root,*args), git_commit(root,ref="HEAD"), slug(text), stripped_generated(text).
Check API: check_book(book_dir, publication=False, scope=None, today=None, freshness=True) -> {ok, issues:[{level,code,path,message}], summary:{...}}.
Build API: build_book(book_dir, check_only=False, translate=False, pdf=False, source_ref=None, version=None, export_id=None, language=None, pdf_profile=None, export_date=None) -> dict.
Release API is agent-owned; notify root once names are fixed; CLI wired by root.
Every agent writes only assigned files. Tests use unittest and temporary Git repos.

## PDF 版式契约 · series-pdf-v1.1

完整操作见 [PDF.md](PDF.md)。总控与书内入口共用 `studio_lib/pdf_export.py` 和 `pdf/template.typ`，不再为某本书复制修改导出器。正文与配置取指定提交 C，调用方工具、模板及其模块摘要单独保存。

`outputs.pdf` 保留 `enabled/font/paper`；新增可选 `profile`（standard/mobile）、`body_font`、`heading_font`、`code_font`、`font_paths`（书内目录列表）、`toc`、`toc_depth`、`bookmark_depth`、`figure_appendix`、`author`、`subtitle`、`series_title`。正文默认兼容 `font`，默认 PingFang SC；代码默认 Sarasa Mono SC。新作品模板采用静态 Sarasa Gothic SC。系统字体模式只核对名称，不冒称字体文件已固定；`font_paths` 模式记录文件摘要并关闭系统/嵌入字体搜索。

标准默认 A5/11pt/上下18mm左右16mm；mobile 为实验配置90×160mm/11.5pt/上9mm下12mm左右7mm。纸面目录默认1层，书签4层；教程默认无纸面目录。大图附录默认关闭，可显式启用。v1.1的标题/段距/图注及常规图片高度限制见PDF.md；明确配对的图说明合并为语义图注，同页且保留来源内容，普通正文不参与合并。新排版不改变插图身份、纸笔风格或已采用字节。PDF 目前仅支持来源提交的主语言 zh-CN/zh-TW/en，不自动产出译文。

导出结果为 `build/pdf/<version>/<export-id>/` 下的 PDF、`export.json`、`qa.json`。每导出号只容纳一个阅读配置，成功或失败诊断均不覆盖。诊断为 `build/pdf-work/<version>/<export-id>/`：`commands.json`、`input-files.json`、`qa.json`（已完成检查时）、失败 `export.json`、完整 `source/` 快照与实际调用方的 `caller-tools/`。`source/code-sources.json` 保存从 C 正文提取的原始逻辑代码块及行内代码（节点类型、顺序、类名与文本），排版适配不得改动其内容、类型、次数或顺序；它同时用于核对视觉折行后的复制结果。

`export.json` schema 2 记录 `source_commit/version/export_id/profile/language/export_date`、`config`、`layout_version/layout_sha256/builder_sha256/tool_sources`、`tools/font_inputs`、文件名及SHA、页数、机器与视觉状态。`toolkit_version` 是 C 中的书配置，不代替调用方实际文件摘要。`visual_review` 默认 pending，不能由程序改为 pass。

`inspect_pdf(path, output_dir=None, render=False)` 惰性加载PDF依赖；返回 `ok/errors/warnings/pages/page_details/links/fonts/sha256/visual_review/rendered_files/tools`。`pdf-check` 纯扫描不写文件；`--render --output` 最多生成12个代表页，拒绝覆盖。机械检查不证明全书目视或实际阅读器复制/跳转通过。
\ntranslations.yaml entries: unit, language, path, source_commit, source_sha256, converter, output_sha256, policy_sha256 (conversion terms and local patches), review (pending|pass).\ntranslation-overrides.yaml list: unit, language: zh-TW, anchor (optional unique context), expected (exactly once after anchor), replacement.\n

## 手绘插图字段（增量契约）

`diagrams` 增加可选字段 `spec`；`type: illustration` 时必须指向书仓内的 brief。原 `{id, unit, type}` 记录仍可用于历史图示。

```yaml
- id: FIG-001
  unit: intro
  type: illustration
  spec: assets/illustrations/FIG-001/brief.yaml
```

brief 的必需字段：`schema_version: 1`、`title`、`reader_question`、`takeaway`、`source_sections`（精确标题列表）、`placement`（精确标题）、`composition`、`content_guard`、`style`、`labels`（相对 brief 的 YAML 标签列表）。可选 `caption`、`source_ids`、`language_variants` 只作设计数据，不得据其手填值宣称已完成。

风格包路径为 `assets/illustrations/styles/<style>/`，保存 `style.md`、`prefix.txt`、`reference.png`、`paper.png`、`approval.json`。paper 是全书统一、不透明的细方格底稿；reference 是作者确认的完整效果图，两者不能混淆。

每次候选保存于 `revisions/rNN/`：`zh-CN.png`、`inputs.json`、`prompt.txt`、`provenance.json`、通过后的 `review.json`。来源快照的 fingerprint 包含 brief、标签、正文小节、单元所引事实、风格文件摘要和提示词摘要；自动导航及本系统的成对插图块不参加正文摘要。`selection.yaml` 只选择具体版本并记录相同的图片和输入摘要。

PNG 文件按真实格式、CRC、解压数据、不透明性与宽度（至少 1400 px）检查。机械尺寸通过不等于印刷或手机可读性通过；后者必须单独看实际版面。审校对象更换或输入过期均不得沿用旧的通过记录。

插图风格执行检查：公共前缀缺失（包括误写为 undefined）时不能制作生产包；所有采用图在 import/select/check/PDF 读取时解码检查透明度及颜色。彩色像素或明显色偏被拒绝；中性纸纹仅容许每通道 24/255 内的噪声，超过 12/255 的像素不得多于 0.5%。这不是把彩色图去色的转换。仍须人工检查笔触、纸底与文字。图内不得添加重复的界面版本注释。审校记录新增 monochrome: pass，不能只凭旧的 visual: pass 采用。

## 系列插图策略

每个真实作品必须有 assets/illustrations/policy.json，即使 diagrams 为空。schema_version 固定为 1，style 固定为 notebook-pen-v1，files 是 prefix.txt、paper.png、reference.png 三个文件名到 SHA-256 的映射；路径固定在 assets/illustrations/styles/notebook-pen-v1/。style.md 与 approval.json 也必须存在。策略描述已采用视觉基准，不写入已冻结候选的输入摘要，添加同基准策略不会让现有采用稿失效。风格文档属于各书已冻结的制作依据，规则正文更新仍遵循原有来源失效机制。

new-book 从总控 assets/illustrations/ 复制，不能仅依赖模板里可能漂移的纸底。illustrations status 在总控不指定作品时检查全部登记作品及 book/tutorial 模板，并比较其策略与总控基准；独立书仓只读取本书快照。

check 与 build 的结构检查不以“已有 illustration 登记”为前提：无图新书也查策略，正文未登记图片和原生 Mermaid、活动旧图登记均报错。仅无策略且 is_test: true 的历史虚构测试夹具保留旧机制兼容，不能作为真实作品的风格例外。

## Illustration workflow v2 and language editions

Runtime guide: [ILLUSTRATIONS.md](ILLUSTRATIONS.md). V1 frozen inputs remain readable. New real-book production uses v2 when workflow-v2.json is installed; explicit migration preserves legacy metadata and image revisions. The visual policy may additionally pin workflow: {schema_version: 2, path: assets/illustrations/workflow-v2.json, sha256: ...}; this extension does not change v1 input fingerprints.

- .studio/visual-plan.yaml: schema_version: 2; units entries contain unit, source_sha256 (normalized body excluding navigation/managed figures), status: pending|reviewed, reviewed_by, checked_on, conclusion, sections, candidates. A candidate has id, reason, benefit, brief, texts. After register/migrate it contains only id and figure; the brief becomes authoritative.
- brief schema 2: kind: concept|interface; form: scene|comparison|flow|mindmap|relationship|overview|detail|sequence. Retains reader_question, takeaway, source_sections, placement, composition, content_guard, style. analysis binds source_sha256 to the canonical list of source snippets and includes reviewed_by, checked_on, reason, benefit. labels maps enabled locale codes to language-package paths. text_roles maps stable IDs to {role: author|ui|literal|example}; literal also needs value. terms optionally selects IDs from book-local terms.yaml. textless: true is allowed only for concept with no text_roles.
- Language packages contain title, caption, alt and labels: {stable_id: exact_text}. A package must use exactly the common set of IDs; only that locale's package affects its image fingerprint. Title/caption/alt are not duplicated in the common brief. The renderer omits all lettering including the title when textless is true; caption/alt stay in surrounding text.
- Mind maps use structure: {root: node_id, nodes: [ids], edges: [[parent, child], ...]}. Nodes refer to stable label IDs; the tree must be connected, acyclic and have one parent per non-root node. This is an illustration, not the legacy mindmap renderer.
- Interface brief ui: product, surface, platform, version, environment, ui_locale, state, references: [IDs], controls: [{label, reference, region}]. ui_variants optionally replaces ui for a specific tutorial locale; reference_states optionally maps reference ID to an actual frame state. Do not infer software UI locale from tutorial language.
- References: assets/illustrations/references/<ID>.yaml; id, source_url, optional asset_url/limitations, identity fields matching ui, status: verified, sanitized: true, reviewed_by, checked_on, viewed_image_sha256. reference-add validates viewed hash, adds image_sha256 and dimensions, stores the actual sanitized PNG privately as .studio/references/<ID>.png. regions contain id, box: [x0,y0,x1,y1] normalized to the reference image, text when a UI label is used, treatment: keep|simplify|omit, reason. A crop uses its own ID plus parent and parent_sha256. Metadata revisions are immutable; use a new ID for changed bytes.
- V2 pack lives under .studio. It includes role-labelled actual images and references.json, inputs.json, prompt.txt, and a receipt template. Receipt requires input_fingerprint, actual tool, reference IDs/roles/SHA-256 and passed: true only for images actually delivered to the tool. In a reuse receipt the references are marked reused, with an exact reviewed, originally generated source revision; it is not a new provider call.
- V2 candidates: revisions/<locale>/rNN/<locale>.png, frozen inputs/prompt/provenance, and exact review. Provenance records locale and actual receipt. selection.yaml: {schema_version: 2, languages: {locale: {revision, image_sha256, input_fingerprint}}}. Candidate import, selection and reuse serialize writes per FIG. No candidate or review is overwritten.
- Review: existing image/input hashes, reviewer/date and content/text/visual/background/monochrome pass; additionally language, structure: pass and localization: pass. Interfaces require interface: pass plus references mapping IDs to the inspected hashes. Publication also requires placement: pass. A source URL, synthetic test receipt, or one locale's pass never proves another locale was reviewed.
- Book language setup remains book.language plus outputs.translations: {en: {enabled: true, directory: en}}. Generic translation records reuse translations.yaml entries with converter: reviewed-localization-v2, unit, language, path, source_sha256, input_fingerprint, output_sha256, review, reviewer, checked_on. Translation text hashes ignore managed artwork and navigation because artwork has independent exact-byte validation. Actual image markers must remain complete and unique.
- Generic translation packs and reviewed imports preserve literal code and protected terms. Review binds language, input_fingerprint, output_sha256 and meaning/terminology/readability pass. Overwriting unregistered human changes requires an explicit reviewed merge with merged_from_sha256 and merge_note; the old human text is archived privately. Legacy zh-TW conversion continues with its existing record format.
- build --language <locale> or translations build --language <locale> assembles reviewed translated units and adopted locale images offline. No implicit source-language fallback. A publication check only requires declared locales; missing, stale or unread locale assets cannot pass. Unused terms and another locale's wording do not invalidate a current image.

Book-local private reference files are not required for independent offline verification; safe metadata, frozen inputs and exact review are. Production pack creation still requires the actual reference images. Changes at a source URL are researched explicitly and saved under a new reference ID; ordinary build/status never fetch the network.

illustrations gallery --output .studio/...html 输出按 FIG／语言排列的 358 px 对照页，附固定纸底。兼容 v1 已采用图；未启用语言不显示，目标语言缺图不借用主语言。预览不自动写入审校。

v2 成图导入、采用与核验进一步要求每像素 R=G=B，且宽高与固定 paper.png 一致；v1 历史图沿用其原检查以保持可重现。统一格距和黑笔手感仍须目视，不由尺寸与灰度代替。

## Author branding

Optional `book.yaml.branding` maps `name`, optional `name_en`, `avatar` (book-local PNG or SVG path), and `sha256` (exact asset SHA-256). Omission preserves legacy behavior. Author photographs keep their original colors and are not teaching FIG assets. `check` validates the asset and digest; combined Markdown includes a 48px signature. PDF source snapshots provide the avatar; `export.json.author_branding` records name, relative path and digest. The shared template uses a 22mm standard / 16mm mobile cover portrait and an 8mm body header portrait; branded body top margins are 20mm standard / 18mm mobile. Portraits never load from host-private paths or the live working tree during fixed-source exports.
