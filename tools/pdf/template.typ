// AI教程工程 · shared PDF layout, series-pdf-v1.2.
// Pandoc template: render with --standalone --to=typst --syntax-highlighting=none.
// Inputs are local to the isolated export directory; no private workspace paths.
#let cfg = json("pdf-config.json")
#let mobile = cfg.at("profile", default: "standard") == "mobile"
#let tutorial = cfg.at("work_type", default: "book") == "tutorial"
#let language = cfg.at("language", default: "zh-CN")
#let english = language == "en"
#let traditional = language == "zh-TW"
#let local(sc, tc, en) = if english { en } else if traditional { tc } else { sc }
#let body-font = cfg.at("body_font", default: "Sarasa Gothic SC")
#let heading-font = cfg.at("heading_font", default: body-font)
#let code-font = cfg.at("code_font", default: "Sarasa Mono SC")
#let book-title = cfg.at("title", default: "")
#let author = cfg.at("author", default: "")
#let author-avatar = cfg.at("author_avatar", default: "")
#let author-mark(size, name-size) = if author-avatar != "" {
  grid(columns: (size, auto), column-gutter: 2mm, align: horizon,
    image(author-avatar, width: size, height: size, fit: "contain"),
    text(size: name-size, author))
} else { text(size: name-size, author) }
#let subtitle = cfg.at("subtitle", default: "")
#let series-title = cfg.at("series_title", default: local("普通人的 AI 工具入门系列", "普通人的 AI 工具入門系列", "AI Tools for Everyone"))
#let body-size = if mobile { 11.5pt } else { 11pt }
#let muted = luma(90)
#let rule = luma(185)

#set document(title: book-title, author: author)
#set text(
  font: body-font, size: body-size, fill: black,
  lang: if english { "en" } else { "zh" },
  region: if traditional { "TW" } else if english { "US" } else { "CN" },
  hyphenate: false,
)
#set par(justify: false, leading: 0.68em, spacing: 1.15em, first-line-indent: 0pt)
#set page(
  paper: cfg.at("paper", default: "a5"),
  margin: if mobile { (top: 9mm, bottom: 12mm, left: 7mm, right: 7mm) }
    else { (top: 18mm, bottom: 18mm, left: 16mm, right: 16mm) },
  numbering: none, header: none, footer: none,
  header-ascent: 5mm, footer-descent: if mobile { 5mm } else { 7mm },
)
#set page(..(if mobile { (width: 90mm, height: 160mm) } else { (:) }))
#set smartquote(enabled: true)
#set heading(numbering: none)
#show heading: set text(font: heading-font, weight: "bold")
#show heading: set block(sticky: true, above: 1.5em, below: 0.6em)
#show heading.where(level: 1): set heading(bookmarked: 1 <= cfg.at("bookmark_depth", default: 4))
#show heading.where(level: 2): set heading(bookmarked: 2 <= cfg.at("bookmark_depth", default: 4))
#show heading.where(level: 3): set heading(bookmarked: 3 <= cfg.at("bookmark_depth", default: 4))
#show heading.where(level: 4): set heading(bookmarked: 4 <= cfg.at("bookmark_depth", default: 4))
#show heading.where(level: 5): set heading(bookmarked: 5 <= cfg.at("bookmark_depth", default: 4))
#show heading.where(level: 6): set heading(bookmarked: 6 <= cfg.at("bookmark_depth", default: 4))
#show heading.where(level: 1): it => {
  if not tutorial { pagebreak(weak: true) }
  block(sticky: true, above: 0pt, below: 1.1em)[
    #set text(size: if mobile { 19pt } else { 21pt })
    #set par(leading: 0.4em, justify: false)
    #it
  ]
}
#show heading.where(level: 2): set text(size: if mobile { 14pt } else { 15pt }, weight: "semibold")
#show heading.where(level: 3): set text(size: 12pt, weight: "semibold")
#show heading.where(level: 4): set text(size: 11.5pt)

// Keep links visible in monochrome while preserving their destinations.
#show link: underline.with(stroke: 0.35pt + luma(135), offset: 2pt)
#set list(indent: 0.5em, body-indent: 0.8em, spacing: 0.4em)
#set enum(indent: 0.2em, body-indent: 0.7em, spacing: 0.4em)
#set footnote.entry(separator: line(length: 24%, stroke: 0.5pt + rule))
#show footnote.entry: set text(size: 8.5pt)

// Markdown separators should not create a page containing only a rule.
#let horizontalrule = block(sticky: true, above: 1em, below: 1em,
  line(length: 100%, stroke: 0.5pt + rule))
#show quote.where(block: true): it => block(
  width: 100%, breakable: true, inset: (left: 10pt, right: 6pt, y: 6pt),
  stroke: (left: 1.2pt + rule),
)[
  #set text(size: 0.94em)
  #set par(justify: false, leading: 0.58em)
  #it.body
]
#show terms.item: it => block(breakable: true)[
  #text(weight: "bold", it.term)
  #block(inset: (left: 1em, top: -0.3em), it.description)
]

// Logical newlines are retained. Text layout permits visual wrapping and page
// breaks; copying wrapped lines still depends on the PDF reader and needs QA.
#show raw.where(block: true): it => block(
  width: 100%, breakable: true,
  inset: if mobile { 6pt } else { 8pt },
  fill: luma(246), stroke: (left: 1pt + luma(170)),
)[
  #set smartquote(enabled: false)
  #set text(font: (code-font, body-font), size: if mobile { 9pt } else { 8.6pt },
    ligatures: false, hyphenate: false)
  #set par(justify: false, leading: 0.55em, spacing: 0pt)
  #layout(size => {
    let widths = (:)
    for (index, source-line) in it.text.split("\n").enumerate() {
      if index > 0 { linebreak() }
      if measure(text(source-line)).width <= size.width - 1pt {
        text(source-line)
      } else {
        // Only overlong lines need cluster measurements, cached for this block.
        let chunk = ""
        let used = 0pt
        for cluster in source-line.clusters() {
          if cluster not in widths { widths.insert(cluster, measure(text(cluster)).width) }
          let advance = widths.at(cluster)
          if used + advance > size.width - 1pt and chunk != "" {
            text(chunk)
            linebreak()
            chunk = ""
            used = 0pt
          }
          chunk += cluster
          used += advance
        }
        text(chunk)
      }
    }
  })
]
#show raw.where(block: false): it => {
  set smartquote(enabled: false)
  text(font: (code-font, body-font), size: 0.88em, ligatures: false, it.text)
}

// Pandoc emits a semantic table.header inside a figure(kind: table).
// Allow the figure to paginate so Typst can repeat that header.
#set table(inset: (x: 5pt, y: 5pt), stroke: (top: none, left: none, right: none, bottom: 0.35pt + luma(210)))
#set table.hline(stroke: 0.6pt + rule)
#set table.header(repeat: true)
#set table.cell(breakable: false)
#show table: set align(left)
#show table: set text(size: if mobile { 9.5pt } else { 9pt })
#show table: set par(justify: false, leading: 0.5em)
#show table.cell.where(y: 0): set text(weight: "bold")
#show table.cell.where(y: 0): set table.cell(fill: luma(243))
#show figure.where(kind: table): set block(breakable: true)
#show figure.where(kind: table): set figure.caption(position: top)
#show figure.where(kind: image): set figure.caption(position: bottom)
#show figure.where(kind: image): set block(breakable: false, above: 1.0em, below: 1.1em)
#show figure.where(kind: image): it => {
  // Bound tall illustrations without cropping, stretching, or a fixed-height box.
  // Explicit heights (including the optional landscape appendix) are untouched.
  show image.where(height: auto): img => layout(size => {
    let natural = measure(img, width: size.width, height: auto)
    let ratio = natural.width / natural.height
    let cap = if mobile { 80mm } else { 110mm }
    let w = calc.min(natural.width, cap * ratio)
    align(center, image(img.source, width: w, height: w / ratio,
      fit: "contain", alt: img.at("alt", default: none)))
  })
  it
}
#set image(fit: "contain")
#set figure(gap: 7pt, numbering: none, placement: none)
#show figure.caption: set align(left)
#show figure.caption: set text(size: 9.5pt, fill: luma(65))
#show figure.caption: set par(justify: false, leading: 0.5em)

$for(header-includes)$
$header-includes$
$endfor$

// Author portrait retains its original colors; teaching artwork keeps its paper.
#if not tutorial [
  #v(10mm)
  #text(size: 9pt, fill: muted, series-title)
  #v(if mobile { 12mm } else { 22mm })
  #block[
    #set text(font: heading-font, size: if mobile { 24pt } else { 34pt }, weight: "bold")
    #set par(justify: false, leading: 0.42em)
    #book-title
  ]
  #if subtitle != "" { block(above: 1.5em, text(size: 13pt, fill: muted, subtitle)) }
  #v(1fr)
  #line(length: 32mm, stroke: 0.8pt + black)
  #v(5mm)
  #author-mark(if mobile { 16mm } else { 22mm }, 11pt)
  #v(4mm)
  #text(size: 9pt, fill: muted, cfg.at("version", default: ""))
  #v(3mm)
  #text(size: 9pt, fill: muted, cfg.at("export_date", default: ""))
  #v(10mm)
  #pagebreak()
]

// Build provenance belongs to the export, independent of the manuscript.
#let edition-info() = block(breakable: false)[
  #set text(size: if mobile { 9.5pt } else { 10pt })
  #set par(justify: false, leading: 0.6em)
  #text(font: heading-font, size: 15pt, weight: "bold", local("关于本书", "關於本書", "About this edition"))
  #v(5mm)
  #book-title
  #if author != "" { parbreak(); author }
  #v(5mm)
  #local("正文版本", "正文版本", "Text version") #h(0.5em) #cfg.at("version", default: "")
  #parbreak()
  #local("导出编号", "匯出編號", "Export ID") #h(0.5em) #cfg.at("export_id", default: "")
  #parbreak()
  #local("导出日期", "匯出日期", "Export date") #h(0.5em) #cfg.at("export_date", default: "")
  #parbreak()
  #local("阅读版式", "閱讀版式", "Reading layout") #h(0.5em) #if mobile {
    local("手机窄版 · 试验配置", "手機窄版 · 試驗配置", "Mobile · experimental")
  } else { local("标准版", "標準版", "Standard") }
  #parbreak()
  #local("正文来源提交", "正文來源提交", "Manuscript commit")
  #parbreak()
  #text(font: code-font, size: 7.2pt, cfg.at("source_commit", default: ""))
  #if cfg.at("source_url", default: "") != "" {
    parbreak()
    link(cfg.source_url)[#local("查看来源仓库", "查看來源倉庫", "View source repository")]
  }
]
#if not tutorial [#edition-info() #pagebreak()]

// A short printed contents page and detailed PDF bookmarks serve different uses.
#if cfg.at("toc", default: not tutorial) [
  #set page(numbering: "i", footer: context align(center, text(size: 8pt, fill: muted, counter(page).display("i"))))
  #counter(page).update(1)
  #set outline.entry(fill: repeat([·], gap: 0.5em))
  #show outline.entry: set par(leading: 0.5em, spacing: 0.7em)
  #outline(title: local("目录", "目錄", "Contents"), depth: cfg.at("toc_depth", default: 1))
  #pagebreak()
]

#counter(page).update(1)
#set page(
  numbering: "1",
  margin: if mobile and author-avatar != "" { (top: 18mm, bottom: 12mm, left: 7mm, right: 7mm) }
    else if mobile { (top: 9mm, bottom: 12mm, left: 7mm, right: 7mm) }
    else { (top: if author-avatar != "" { 20mm } else { 18mm }, bottom: 18mm, left: 16mm, right: 16mm) },
  header: if author-avatar != "" {
    grid(columns: (auto, 1fr), column-gutter: 4mm, align: horizon,
      author-mark(8mm, 8pt),
      align(right, text(size: if mobile { 7pt } else { 7.5pt }, fill: muted, book-title)))
  } else if mobile { none } else { align(right, text(size: 7.5pt, fill: muted, book-title)) },
  footer: context align(center, text(size: 8pt, fill: muted, counter(page).display("1"))),
)

#if tutorial [
  #text(size: 8pt, fill: muted, series-title)
  #v(2mm)
  #text(size: 8pt, fill: muted, author + " · " + cfg.at("version", default: "") + " · " + cfg.at("export_date", default: ""))
  #v(5mm)
]

$for(include-before)$
$include-before$
$endfor$
$body$

#if tutorial [
  #v(1em)
  #horizontalrule
  #edition-info()
]
$for(include-after)$
$include-after$
$endfor$
