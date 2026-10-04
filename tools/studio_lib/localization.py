"""Offline text localization packs and reviewed, protected locale editions.

A human or available language model translates source.md. Import binds the actual
review to that output; build never silently performs translation or substitutes
another locale's illustrations.
"""
from pathlib import Path
import json
import re
from .common import StudioError, atomic_write, load_yaml, dump_yaml, safe_path
from . import illustrations as core
from . import illustration_workflow as wf

CONVERTER='reviewed-localization-v2'

def target_path(root,book,unit,language):
    wf.locale(book,language)
    wf.need(language!=book.get('language','zh-CN'),'翻译目标不能是主语言')
    config=book.get('outputs',{}).get('translations',{}).get(language,{})
    directory=config.get('directory');base=safe_path(root,directory)
    wf.need(base.resolve()!=Path(root).resolve() and base.relative_to(Path(root).resolve()).parts[0] not in ('.git','.studio','tools','assets','checks'),'译文目录会覆盖机制／源资产')
    target=safe_path(root,str(Path(directory)/unit['path']))
    wf.need(target not in [safe_path(root,u['path']) for u in book['units']],'译文不能覆盖源稿')
    return target

def text_hash(text):
    # Illustration bytes, alt and captions are checked by the image workflow.
    return wf.body_digest(text)

def unit_input(root,book,unit,language):
    lang=wf.locale(book,language);target_path(root,book,unit,lang)
    body=safe_path(root,unit['path']).read_text();source=wf.clean(body)
    terms=load_yaml(Path(root)/'terms.yaml') if (Path(root)/'terms.yaml').exists() else {}
    primary=book.get('language','zh-CN')
    used={k:{primary:v[primary],lang:v[lang]} for k,v in terms.items() if isinstance(v,dict) and isinstance(v.get(primary),str) and v[primary] in source and lang in v}
    for key,v in terms.items():
        if isinstance(v,dict) and isinstance(v.get(primary),str) and v[primary] in source:
            wf.need(lang in v,'正文使用的术语缺少目标语言：'+key)
    figures=[d['id'] for d in book.get('diagrams',[]) if d.get('unit')==unit['id'] and d.get('type')=='illustration']
    payload={'unit':unit['id'],'language':lang,'source_language':primary,'source_sha256':text_hash(body),
             'source_path':unit['path'],'figures':figures,'terms':used,'protected_terms':book.get('protected_terms',[])}
    return payload,core.digest(payload)

def entries(root):
    path=Path(root)/'translations.yaml'
    value=load_yaml(path) if path.exists() else {'entries':[]}
    wf.need(isinstance(value,dict) and isinstance(value.get('entries'),list),'translations.yaml 格式无效')
    ids=[(e.get('unit'),e.get('language')) for e in value['entries']]
    wf.need(len(ids)==len(set(ids)),'重复译文登记')
    return value

def markers(body):return re.findall(r'<!-- diagram: (FIG-\d+) -->',body)

def unit_status(root,book,unit,language):
    row={'unit':unit['id'],'language':language,'status':'missing'}
    try:
        payload,fp=unit_input(root,book,unit,language)
        e=next((e for e in entries(root)['entries'] if e.get('unit')==unit['id'] and e.get('language')==language),None)
        if not e:return row
        if e.get('converter')!=CONVERTER:
            if language=='zh-TW':
                from .builder import translation_status
                return dict(translation_status(root,book,[unit['id']])[0],language=language)
            raise StudioError('译文未按当前机制登记')
        path=target_path(root,book,unit,language)
        wf.need(e.get('path')==str(path.relative_to(Path(root).resolve())),'译文路径与登记不一致')
        if e.get('input_fingerprint')!=fp:row['status']='stale';return row
        if not path.exists():return row
        if text_hash(path.read_text())!=e.get('output_sha256'):row['status']='modified';return row
        wf.need(markers(path.read_text())==payload['figures'] or sorted(markers(path.read_text()))==sorted(payload['figures']),'译文插图标记不完整／重复')
        row['status']='current' if e.get('review')=='pass' and e.get('reviewer') and e.get('checked_on') else 'review_pending'
        return row
    except (StudioError,OSError,ValueError,KeyError,TypeError) as e:row.update(status='invalid',reason=str(e));return row

def status(root,language=None,scope=None,images=True,publication=False):
    root=Path(root).resolve();book,_=core.figures(root)
    langs=[wf.locale(book,language)] if language else wf.languages(book)
    rows=[];issues=[];figures=[];planning=None;image_ready=True;pending=[]
    for lang in langs:
        if lang!=book.get('language','zh-CN'):
            for unit in book['units']:
                if scope is not None and unit['id'] not in scope:continue
                row=unit_status(root,book,unit,lang);rows.append(row)
                if row['status']!='current':issues.append({'level':'error' if publication else 'warning','code':'translation_'+row['status'],'path':unit['path'],'message':lang+': '+row.get('reason',row['status'])})
        if images:
            report=core.audit(root,publication=publication,scope=scope,language=lang)
            figures.extend(report['figures']);issues.extend(report['issues']);planning=report.get('planning');image_ready=image_ready and report.get('ready',False);pending.extend(report.get('pending',[]))
    return {'ok':not any(x['level']=='error' for x in issues),'ready':image_ready and not issues and all(r['status']=='current' for r in rows) and all(f.get('stage') in ('可用','placed') for f in figures),'translations':rows,'figures':figures,'planning':planning,'pending':pending,'issues':issues,'policy':core.style_policy(root,book),'legacy_remaining':sum(d.get('type') in ('mindmap','flowchart') for d in book.get('diagrams',[])),'network':'未访问'}

def pack(root,unit_id,language,output):
    root=Path(root).resolve();book,_=core.figures(root);unit=next((u for u in book['units'] if u['id']==unit_id),None)
    wf.need(unit,'未知单元');payload,fp=unit_input(root,book,unit,language)
    dest=safe_path(root,output);wf.need(not dest.exists(),'译文包已存在，禁止覆盖')
    body=safe_path(root,unit['path']).read_text()
    body=re.sub(r'<!-- studio:nav -->[\s\S]*?<!-- /studio:nav -->','',body)
    for fid in payload['figures']:
        _,_,brief,_,_=core.resolve(root,fid)
        empty='<!-- diagram: '+fid+' -->\n<!-- /diagram: '+fid+' -->'
        body=wf.place(body,fid,empty,brief['placement'])
    # Move links to the target edition, keeping commands/code intact.
    from .builder import translation_links
    body=translation_links(root,unit,body,book['units'],book['outputs']['translations'][language]['directory'])
    dest.mkdir(parents=True)
    core.save_json(dest/'inputs.json',{'inputs':payload,'fingerprint':fp,'source_text_sha256':core.digest(body.encode())})
    atomic_write(dest/'source.md',body)
    atomic_write(dest/'instructions.md','Translate into '+language+'. Preserve diagram markers, code blocks, inline code and protected terms. Use the supplied terminology. Keep natural phrasing and the original instructional meaning. Do not invent UI translations. Review the result before importing.\n')
    return {'ok':True,'outputs':[str(dest)],'language':language,'translation':'未执行'}

def import_text(root,unit_id,language,pack_path,text_path,review_path):
    root=Path(root).resolve();book,_=core.figures(root);unit=next((u for u in book['units'] if u['id']==unit_id),None)
    wf.need(unit,'未知单元');payload,fp=unit_input(root,book,unit,language)
    production=safe_path(root,pack_path);saved=core.read_json(production/'inputs.json');original=(production/'source.md').read_text()
    wf.need(saved.get('inputs')==payload and saved.get('fingerprint')==fp and saved.get('source_text_sha256')==core.digest(original.encode()),'译文包已过期或被修改')
    text=Path(text_path).read_text();review=core.read_json(review_path)
    wf.evidence_stamp(review,'reviewer')
    wf.need(review.get('language')==language and review.get('input_fingerprint')==fp and review.get('output_sha256')==text_hash(text),'译文审校对象不匹配')
    wf.need(all(review.get(k)=='pass' for k in ('meaning','terminology','readability')),'译文语义、术语和可读性须审校')
    wf.need(sorted(markers(text))==sorted(payload['figures']),'译文必须保留全部且唯一的 FIG 标记')
    wf.need(len(core.MANAGED.findall(text))==len(payload['figures']),'译文插图标记未闭合')
    # Literal code is protected; localized demo code requires an intentional source
    # variant rather than an automatic global replacement.
    code=r'(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1\s*$'
    wf.need([m.group(0) for m in re.finditer(code,original)]==[m.group(0) for m in re.finditer(code,text)],'翻译不能擅自改变代码块')
    inline=r'(?<!`)`[^`\n]+`(?!`)'
    wf.need(sorted(re.findall(inline,original))==sorted(re.findall(inline,text)),'翻译不能擅自改变行内命令或标识')
    for term in payload['protected_terms']:
        if term in original:wf.need(term in text,'受保护的术语丢失：'+term)
    target=target_path(root,book,unit,language)
    with wf.lock(root,'translations'):
        metadata=entries(root);old=next((e for e in metadata['entries'] if e.get('unit')==unit_id and e.get('language')==language),None)
        if target.exists() and (not old or text_hash(target.read_text())!=old.get('output_sha256')):
            current_hash=text_hash(target.read_text())
            wf.need(review.get('merged_from_sha256')==current_hash and wf.nonempty(review.get('merge_note')),'译文有未登记人工修订；先保存合并，不覆盖')
            archive=safe_path(root,'.studio/translation-history/'+unit_id+'/'+language+'/'+current_hash+'.md')
            if not archive.exists():atomic_write(archive,target.read_text())
        # Remove provider-supplied images: editions resolve only reviewed locale assets.
        for fid in payload['figures']:
            empty='<!-- diagram: '+fid+' -->\n<!-- /diagram: '+fid+' -->'
            try:
                image,p,_=wf.selected(root,fid,language)
                empty=wf.block(fid,image,target,p['text'],language)
            except (StudioError,OSError):pass
            text=wf.place(text,fid,empty)
        previous=target.read_text() if target.exists() else None
        record={'unit':unit_id,'language':language,'path':str(target.relative_to(root)),
            'source_sha256':payload['source_sha256'],'input_fingerprint':fp,'output_sha256':text_hash(text),'converter':CONVERTER,
            'review':'pass','reviewer':review['reviewer'],'checked_on':str(review['checked_on'])}
        metadata['entries']=[e for e in metadata['entries'] if not(e.get('unit')==unit_id and e.get('language')==language)]+[record]
        try:atomic_write(target,text);dump_yaml(root/'translations.yaml',metadata)
        except Exception:
            if previous is None:target.unlink(missing_ok=True)
            else:atomic_write(target,previous)
            raise
    return {'ok':True,'outputs':[str(target)],'pending':['逐语言插图与入稿检查，translations status 查看缺口']}

def build(root,language,check_only=False):
    root=Path(root).resolve();book,_=core.figures(root);wf.locale(book,language)
    wf.need(language!=book.get('language','zh-CN'),'主语言请使用普通 build')
    report=status(root,language,publication=True)
    wf.need(report['ok'],'目标语言图文尚未齐备：'+json.dumps(report['issues'],ensure_ascii=False))
    config=book['outputs']['translations'][language];dest=safe_path(root,str(Path(config['directory'])/'combined.md'))
    wf.need(dest not in [target_path(root,book,u,language) for u in book['units']],'合订稿不能覆盖译文')
    from .builder import rewritten_body
    translated_units=[dict(u,path=str(target_path(root,book,u,language).relative_to(root))) for u in book['units']]
    chunks=['<!-- Generated by studio localization; edit translated units. -->']
    from .branding import author_html
    signature=author_html(root,book,dest.parent,language)
    if signature:chunks.append(signature)
    for u in translated_units:
        chunks+=['<a id="'+u['id']+'"></a>',rewritten_body(root,u,safe_path(root,u['path']).read_text(),dest.parent,translated_units)]
    output='\n\n'.join(chunks)+'\n';manifest=safe_path(root,'.studio/localized-'+language+'.json')
    if dest.exists() and dest.read_text()!=output:
        old=core.read_json(manifest) if manifest.exists() else {}
        wf.need(old.get('sha256')==core.digest(dest.read_bytes()),'合订译文有人工修改，保留现场')
    changed=not dest.exists() or dest.read_text()!=output
    if not check_only:
        atomic_write(dest,output);core.save_json(manifest,{'sha256':core.digest(output.encode()),'language':language})
    return {'ok':not changed if check_only else True,'outputs':[str(dest)],'changed':changed,'network':'未访问','translation':'未执行'}

def command(root,args):
    action=args.action
    if action=='status':return status(root,args.language)
    if action=='build':return build(root,args.language,args.check)
    wf.need(args.unit and args.language,'需要 --unit 和 --language')
    if action=='pack':
        wf.need(args.output,'需要 --output');return pack(root,args.unit,args.language,args.output)
    if action=='import':
        wf.need(args.pack and args.text and args.review,'需要 --pack、--text、--review')
        return import_text(root,args.unit,args.language,args.pack,args.text,args.review)
    raise StudioError('未知语言操作')
