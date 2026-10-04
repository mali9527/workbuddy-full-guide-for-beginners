"""Reviewed content plans, role-labelled references and locale-aware illustration v2.

Network research and visual judgements are performed by the editor, not inferred
from file existence. All commands here are offline and preserve adopted revisions.
"""
from pathlib import Path
from contextlib import contextmanager
from datetime import date, datetime, timezone
import copy
import json
import os
import re
import shutil
import struct
from .common import StudioError, atomic_write, load_yaml, dump_yaml, safe_path
from . import illustrations as core

RULES_PATH = 'assets/illustrations/workflow-v2.json'
PLAN_PATH = '.studio/visual-plan.yaml'
FORMS = {'scene', 'comparison', 'flow', 'mindmap', 'relationship', 'overview', 'detail', 'sequence'}
UI_FIELDS = ('product', 'surface', 'platform', 'environment', 'ui_locale', 'state', 'version')

def need(value, message):
    if not value: raise StudioError(message)

def nonempty(value):
    return isinstance(value, str) and bool(value.strip())

def locale(book, language=None):
    value = language or book.get('language', 'zh-CN')
    need(isinstance(value, str) and re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', value), '无效语言代码')
    known = {book.get('language', 'zh-CN')} | {k for k, v in (book.get('outputs', {}).get('translations') or {}).items() if isinstance(v, dict) and v.get('enabled')}
    need(value in known, '该语言尚未在 book.yaml 启用：' + value)
    return value

def languages(book):
    return [book.get('language', 'zh-CN')] + [k for k,v in (book.get('outputs', {}).get('translations') or {}).items() if isinstance(v,dict) and v.get('enabled') and k != book.get('language', 'zh-CN')]

def clean(text):
    text = core.MANAGED.sub('', text)
    return re.sub(r'<!-- studio:nav -->[\s\S]*?<!-- /studio:nav -->', '', text).strip()

def body_digest(text):
    return core.digest(re.sub(r'\n{3,}', '\n\n', clean(text)))

def snippets(root, unit, headings):
    need(isinstance(headings,list) and headings and all(nonempty(h) for h in headings), '需要来源小节')
    text = safe_path(root, unit['path']).read_text()
    return [{'heading':h, 'text':core.section(text,h)} for h in headings]

def evidence_stamp(value, field='reviewed_by'):
    need(isinstance(value,dict) and nonempty(value.get(field)), '需要真实的研究／审校人员记录')
    try: date.fromisoformat(str(value['checked_on']))
    except (KeyError, ValueError): raise StudioError('需要有效 checked_on 日期')

@contextmanager
def lock(root, identity):
    need(re.fullmatch(r'[A-Za-z0-9-]+', identity), '无效写入锁身份')
    path = safe_path(root, '.studio/locks/' + identity + '.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    try: fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError: raise StudioError('该对象正在写入；保留锁并核对现场：' + identity)
    try:
        os.write(fd, str(os.getpid()).encode()); os.close(fd)
        yield
    finally: path.unlink(missing_ok=True)


def plan(root, output=PLAN_PATH):
    root=Path(root).resolve();book,_=core.figures(root);dest=safe_path(root,output)
    need(not dest.exists(), '规划已存在；在原表继续研究，不覆盖人工分析')
    entries=[]
    for u in book['units']:
        body=safe_path(root,u['path']).read_text()
        entries.append({'unit':u['id'],'source_sha256':body_digest(body),'status':'pending',
            'reviewed_by':None,'checked_on':None,'conclusion':'',
            'sections':re.findall(r'(?m)^#{1,6} (.+)$',clean(body)), 'candidates':[]})
    dump_yaml(dest,{'schema_version':2,'units':entries})
    return {'ok':True,'outputs':[str(dest)],'stage':'待研究','pending':['回读已写正文并填写候选和选择理由；不自动猜图或填写通过']}


def plan_check(root, path=PLAN_PATH):
    book,_=core.figures(root);value=load_yaml(safe_path(root,path));units={u['id']:u for u in book['units']}
    rows=[];seen=set();candidates=[]
    for entry in value.get('units',[]):
        uid=entry.get('unit');need(uid in units and uid not in seen,'规划单元未知或重复');seen.add(uid)
        current=body_digest(safe_path(root,units[uid]['path']).read_text())
        ready=entry.get('status')=='reviewed' and entry.get('source_sha256')==current
        if ready:
            evidence_stamp(entry);need(nonempty(entry.get('conclusion')),'已研究章节需要结论，包括不配图理由')
        for c in entry.get('candidates',[]):
            if c.get('figure'):continue
            brief=c.get('brief',{});is_ui=brief.get('kind')=='interface'
            candidates.append({'id':c.get('id','未编号'),'unit':uid,'kind':brief.get('kind'),'form':brief.get('form'),
                'stage':'待研究' if not ready or is_ui else '待生成',
                'reason':'待真实界面参考与区域核验后登记' if is_ui else '按已研究方案登记后生成'})
        rows.append({'unit':uid,'stage':'已研究' if ready else '待研究','source':'current' if entry.get('source_sha256')==current else 'stale','candidates':len(entry.get('candidates',[]))})
    need(seen==set(units),'规划必须覆盖所有登记单元；未写正文可标 pending')
    return {'ok':True,'units':rows,'ready':sum(x['stage']=='已研究' for x in rows),'total':len(rows),'unregistered_candidates':candidates,'network':'未访问'}


def register(root, figure, path=PLAN_PATH, migrate=False):
    root=Path(root).resolve();need(re.fullmatch(r'FIG-\d+',figure),'图号应为 FIG-001 等')
    with lock(root,'register'), lock(root,figure):
        book,records=core.figures(root);existing=[r for r in records if r['id']==figure]
        need(len(existing)==(1 if migrate else 0),'迁移须已有唯一图号；新增图号不能重复')
        data=load_yaml(safe_path(root,path));matches=[(e,c) for e in data['units'] for c in e.get('candidates',[]) if c.get('id')==figure]
        need(len(matches)==1,'候选图号须唯一');entry,candidate=matches[0]
        plan_check(root,path)
        unit=next(u for u in book['units'] if u['id']==entry['unit'])
        need(entry.get('status')=='reviewed' and entry['source_sha256']==body_digest(safe_path(root,unit['path']).read_text()),'先按当前正文完成配图研究')
        for k in ('reason','benefit'):need(nonempty(candidate.get(k)), '候选缺少 '+k)
        brief=copy.deepcopy(candidate.get('brief',{}));texts=candidate.get('texts')
        need(isinstance(texts,dict) and book.get('language','zh-CN') in texts,'需要主语言文字包')
        brief.update(schema_version=2,style=core.STYLE_ID)
        need(brief.get('kind') in ('concept','interface') and brief.get('form') in FORMS,'需要 kind 与 form')
        source=snippets(root,unit,brief.get('source_sections'))
        brief['analysis']={'source_sha256':core.digest(source),'reviewed_by':entry['reviewed_by'],'checked_on':str(entry['checked_on']), 'reason':candidate['reason'],'benefit':candidate['benefit']}
        folder=safe_path(root,'assets/illustrations/'+figure)
        if migrate:
            need(existing[0]['unit']==unit['id'] and existing[0]['spec']==str((folder/'brief.yaml').relative_to(root)),'迁移不得更改所属单元或猜测非标准路径')
            need(load_yaml(folder/'brief.yaml').get('schema_version')==1,'只能从旧版迁移；新版直接研究修订')
            need(not (folder/'legacy-v1').exists(),'旧版归档已存在；保留现场')
        else:need(not folder.exists(),'图目录已存在，不覆盖')
        brief['labels']={lang:'labels.'+locale(book,lang)+('.v2' if migrate else '')+'.yaml' for lang in texts}
        book_before=(root/'book.yaml').read_text();plan_before=safe_path(root,path).read_text()
        preserved={f.name:f.read_bytes() for f in folder.glob('*.yaml')} if migrate else {}
        try:
            folder.mkdir(parents=True,exist_ok=migrate)
            if migrate:
                (folder/'legacy-v1').mkdir()
                for name,contents in preserved.items():(folder/'legacy-v1'/name).write_bytes(contents)
                dump_yaml(folder/'selection.yaml',{'schema_version':2,'languages':{}})
            for lang,text in texts.items():
                need(not (folder/brief['labels'][lang]).exists(),'语言包已存在，不覆盖')
                dump_yaml(folder/brief['labels'][lang],text)
            dump_yaml(folder/'brief.yaml',brief)
            if not migrate:book.setdefault('diagrams',[]).append({'id':figure,'unit':unit['id'],'type':'illustration','spec':str((folder/'brief.yaml').relative_to(root))})
            dump_yaml(root/'book.yaml',book)
            spec(root,figure,book.get('language','zh-CN'),require_evidence=False)
            candidate.clear();candidate.update(id=figure,figure=figure)
            dump_yaml(safe_path(root,path),data)
        except Exception:
            atomic_write(root/'book.yaml',book_before);atomic_write(safe_path(root,path),plan_before)
            if migrate:
                for name in brief['labels'].values():
                    if name not in preserved:(folder/name).unlink(missing_ok=True)
                for name,contents in preserved.items():(folder/name).write_bytes(contents)
                if 'selection.yaml' not in preserved:(folder/'selection.yaml').unlink(missing_ok=True)
                if (folder/'legacy-v1').exists():shutil.rmtree(folder/'legacy-v1')
            elif folder.exists():shutil.rmtree(folder)
            raise
    return {'ok':True,'figure':figure,'stage':'待研究' if brief['kind']=='interface' else '待生成','outputs':[str(folder)],'historical_images_preserved':True}


def reference_path(root,rid):
    need(isinstance(rid,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',rid) and rid not in ('paper','style'),'无效或保留的参考 ID')
    return safe_path(root,'assets/illustrations/references/'+rid+'.yaml')

def reference_file(root,rid):
    reference_path(root,rid)
    return safe_path(root,'.studio/references/'+rid+'.png')

def image_dimensions(data):
    need(data[:8]==b'\x89PNG\r\n\x1a\n' and len(data)>32 and data[12:16]==b'IHDR','真实界面参考需为可查看 PNG')
    width,height=struct.unpack('>II',data[16:24]);need(width>0 and height>0,'参考图片尺寸无效')
    return [width,height]

def validate_reference(record):
    evidence_stamp(record)
    record['checked_on']=str(record['checked_on'])
    for key in (*UI_FIELDS,'version','source_url','image_sha256','viewed_image_sha256'):
        need(nonempty(record.get(key)), '界面参考缺少 '+key)
    need(record['viewed_image_sha256']==record['image_sha256'],'查看记录必须绑定实际图片字节')
    need(record.get('sanitized') is True,'只保存并传入去敏参考')
    need(record.get('status')=='verified','参考尚未实际查看并核验')
    need(re.match(r'https?://',record['source_url']) or record['source_url'].startswith('capture:'),'需要来源页或本人采集记录')
    regions=record.get('regions');need(isinstance(regions,list) and regions,'需要实际界面区域分析')
    ids=set()
    for r in regions:
        need(nonempty(r.get('id')) and r['id'] not in ids,'区域 ID 为空或重复');ids.add(r['id'])
        box=r.get('box');need(isinstance(box,list) and len(box)==4 and all(type(x) in (int,float) and 0<=x<=1 for x in box) and box[0]<box[2] and box[1]<box[3], '区域坐标为原图归一化 [x0,y0,x1,y1]')
        need(r.get('treatment') in ('keep','simplify','omit') and nonempty(r.get('reason')), '每个区域需要保留／简化／省略理由')
    return record

def reference_add(root,metadata,image):
    value=copy.deepcopy(load_yaml(metadata));rid=value.get('id');path=reference_path(root,rid);image_path=reference_file(root,rid)
    need(not path.exists() and not image_path.exists(),'参考版本不可覆盖；换用新的参考 ID')
    data=Path(image).read_bytes();dims=image_dimensions(data);digest=core.digest(data)
    need(value.get('viewed_image_sha256')==digest,'先实际查看这张图片，记录其 SHA-256，不能只提供链接')
    value.update(image_sha256=digest,dimensions=dims)
    validate_reference(value)
    # A separate crop must have its own ID and point back to the exact original.
    if value.get('parent'):
        parent=load_yaml(reference_path(root,value['parent']))
        need(value.get('parent_sha256')==parent.get('image_sha256'),'裁切参考的原图摘要不一致')
    with lock(root,'references'):
        need(not path.exists() and not image_path.exists(),'参考已由另一操作写入')
        image_path.parent.mkdir(parents=True,exist_ok=True)
        image_path.write_bytes(data)
        try: dump_yaml(path,value)
        except Exception: image_path.unlink();raise
    return {'ok':True,'reference':rid,'sha256':digest,'outputs':[str(path)],'private_image':str(image_path)}


def spec(root,figure,language=None,require_evidence=True):
    book,record,brief,folder,unit=core.resolve(root,figure);lang=locale(book,language)
    need(brief.get('schema_version')==2,'新工作流需要 brief schema_version: 2')
    need(brief.get('kind') in ('concept','interface') and brief.get('form') in FORMS,'不支持的 kind/form')
    need(brief['form']!='mindmap' or brief['kind']=='concept','思维导图属于 concept 构图')
    for k in ('reader_question','takeaway','composition','content_guard','placement'):need(nonempty(brief.get(k)),'单图缺少 '+k)
    if brief.get('textless'):need(brief.get('kind')=='concept' and not brief.get('text_roles'),'无字图只能是没有图内标签的概念图')
    source=snippets(root,unit,brief.get('source_sections'));analysis=brief.get('analysis')
    evidence_stamp(analysis)
    need(analysis.get('source_sha256')==core.digest(source),'相关正文已变或尚未完成配图研究')
    need(nonempty(analysis.get('reason')) and nonempty(analysis.get('benefit')),'需要配图形式选择理由与读者收益')
    paths=brief.get('labels');need(isinstance(paths,dict) and lang in paths,'缺少目标语言文字包：'+lang)
    text=load_yaml(core.local(root,(folder/paths[lang]).relative_to(Path(root).resolve()).as_posix()))
    for k in ('title','caption','alt'):need(nonempty(text.get(k)),'语言文字包缺少 '+k)
    labels=text.get('labels');need(isinstance(labels,dict),'labels 需要稳定 ID 映射')
    definition=brief.get('text_roles',{});need(set(labels)==set(definition),'语言文字 ID 与共同底稿不一致')
    for key,value in labels.items():
        need(nonempty(value),'空文字标签：'+key)
        role=definition[key];need(role.get('role') in ('author','ui','literal','example'),'未知文字角色')
        if role['role']=='literal':need(value==role.get('value'),'受保护的命令／标识不能翻译：'+key)
    ui=copy.deepcopy((brief.get('ui_variants') or {}).get(lang,brief.get('ui',{})))
    refs=[]
    if brief['kind']=='interface' and require_evidence:
        for k in UI_FIELDS:need(nonempty(ui.get(k)),'界面图缺少 '+k)
        need(isinstance(ui.get('references'),list) and ui['references'],'界面图缺少真实参考')
        for rid in ui['references']:
            ref=validate_reference(load_yaml(reference_path(root,rid)))
            need(ref['id']==rid,'参考 ID 不一致')
            for k in UI_FIELDS:
                expected = ui.get('reference_states', {}).get(rid, ui[k]) if k == 'state' else ui[k]
                need(ref[k]==expected,'参考界面不匹配：'+k)
            path=reference_file(root,rid)
            if path.exists():need(core.digest(path.read_bytes())==ref['image_sha256'],'参考图片已改变；使用新 ID 重新核验')
            refs.append(ref)
        mappings=ui.get('controls',[]);seen=set()
        for control in mappings:
            key=control.get('label');need(key in labels and key not in seen,'控件映射未知或重复');seen.add(key)
            ref=next((r for r in refs if r['id']==control.get('reference')),None);need(ref,'控件缺少参考')
            region=next((r for r in ref['regions'] if r['id']==control.get('region')),None)
            need(region and region['treatment']!='omit','控件缺少保留区域')
            need(labels[key]==region.get('text'),'真实控件原文不匹配：'+key)
        need(seen=={k for k,v in definition.items() if v['role']=='ui'},'真实控件须逐项映射截图区域')
    elif brief['kind']=='concept':need(not any(v['role']=='ui' for v in definition.values()),'概念图不能以 UI 标签绕过真实依据')
    structure=brief.get('structure',{})
    if brief['form']=='mindmap':
        nodes=structure.get('nodes',[]);edges=structure.get('edges',[]);center=structure.get('root')
        need(nodes and len(nodes)==len(set(nodes)) and set(nodes)<=set(labels) and center in nodes,'思维导图节点／中心无效')
        need(all(isinstance(e,list) and len(e)==2 and set(e)<=set(nodes) and e[0]!=e[1] for e in edges),'导图连线含未知节点')
        parent={}
        for a,b in edges:need(b!=center and b not in parent,'导图节点存在多父级或中心回连');parent[b]=a
        need(len(edges)==len(nodes)-1,'导图分支遗漏或重复')
        for node in nodes:
            visited=set();cursor=node
            while cursor!=center:
                need(cursor not in visited and cursor in parent,'导图有环或不可达节点');visited.add(cursor);cursor=parent[cursor]
    return book,record,brief,folder,unit,lang,text,source,ui,refs


def semantic_evidence(value):
    # Rechecking an unchanged fact/reference date does not change the drawing.
    # Current evidence validity is still checked before this projection.
    if isinstance(value,dict):
        return {k:semantic_evidence(v) for k,v in value.items() if k not in ('checked_on','reviewed_by')}
    if isinstance(value,list):return [semantic_evidence(v) for v in value]
    return value


def inputs(root,figure,language=None):
    root=Path(root).resolve()
    book,record,b,folder,unit,lang,text,source,ui,refs=spec(root,figure,language)
    refs=semantic_evidence(refs)
    core.style_policy(root,book);need(b['style']==core.STYLE_ID,'必须使用系列统一风格')
    rules=core.read_json(safe_path(root,RULES_PATH));need(rules.get('schema_version')==2 and rules.get('style')==core.STYLE_ID,'缺少新版共用生产规则')
    style=safe_path(root,'assets/illustrations/styles/'+core.STYLE_ID)
    assets=[{'id':'paper','role':'paper','sha256':core.digest((style/'paper.png').read_bytes())},
            {'id':'style','role':'style','sha256':core.digest((style/'reference.png').read_bytes())}]
    assets += [{'id':r['id'],'role':'interface','sha256':r['image_sha256']} for r in refs]
    # Project style.md is a historical frozen v1 input. v2 uses an explicit rules
    # version and the same immutable visual assets, so old candidates stay current.
    hashes={k:core.digest((style/k).read_bytes()) for k in core.VISUAL_FILES}
    terms_path=root/'terms.yaml';terms=load_yaml(terms_path) if terms_path.exists() else {}
    used_terms={}
    for tid in b.get('terms',[]):
        need(tid in terms and lang in terms[tid],'缺少本图术语的目标语言：'+tid)
        used_terms[tid]=terms[tid][lang]
    shared={k:b.get(k) for k in ('kind','form','reader_question','takeaway','composition','content_guard','structure','text_roles','placement','textless')}
    facts=load_yaml(root/'facts.yaml') if (root/'facts.yaml').exists() else []
    facts=semantic_evidence(json.loads(json.dumps(facts,default=str)))
    prompt='\n\n'.join([str(rules['style_prompt']),str(rules['profiles'][b['kind']]),
        'CONTENT STRUCTURE (instructions; never render these descriptions as labels): '+json.dumps(shared,ensure_ascii=False),
        'BOOK LANGUAGE: '+lang+'; UI LANGUAGE: '+str(ui.get('ui_locale','not applicable')),
        'TEXTLESS: '+str(bool(b.get('textless')))+'; when true, render NO letters or title. Title/caption/alt remain metadata.',
        'EXACT AUTHOR/UI TEXT BY STABLE ID: '+json.dumps(text,ensure_ascii=False),
        'TERMS: '+json.dumps(used_terms,ensure_ascii=False),
        'REFERENCE ROLES (paper/style control appearance; interface controls geometry and exact UI text only): '+json.dumps(assets,ensure_ascii=False),
        'VERIFIED UI REGIONS: '+json.dumps(refs,ensure_ascii=False)])
    need('界面示意，布局随版本变化' not in prompt,'已废止的重复界面注释不能进入提示词')
    need(all(word in rules['style_prompt'] for word in ('BLACK GEL PEN','grid','OPAQUE','R=G=B')),'风格约束缺失')
    need(not re.search(r'\bundefined\b',prompt),'提示词存在未解析变量')
    payload={'schema_version':2,'figure':figure,'unit':record['unit'],'language':lang,'source_path':unit['path'],
        'design':shared,'sources':source,'facts':[f for f in facts if f.get('id') in unit.get('facts',[])],
        'text':text,'terms':used_terms,'ui':ui if b['kind']=='interface' else {},'references':refs,
        'reference_assets':assets,'style_files':hashes,'rules':rules,'prompt_sha256':core.digest(prompt.encode())}
    return payload,core.digest(payload),prompt


def pack(root,figure,destination,language=None):
    root=Path(root).resolve();payload,fingerprint,prompt=inputs(root,figure,language)
    dest=safe_path(root,destination);need(dest.relative_to(root).parts[0]=='.studio','新版生产包放在私有 .studio 内，避免公开参考截图')
    need(not dest.exists(),'生产包已存在，禁止覆盖')
    files={ 'paper':root/'assets/illustrations/styles'/core.STYLE_ID/'paper.png','style':root/'assets/illustrations/styles'/core.STYLE_ID/'reference.png'}
    files.update({r['id']:reference_file(root,r['id']) for r in payload['references']})
    for a in payload['reference_assets']:
        need(files[a['id']].is_file(),'生产需要实际参考图片，不能只传链接：'+a['id'])
        need(core.digest(files[a['id']].read_bytes())==a['sha256'],'实际参考字节与核验记录不符')
    stage=dest.with_name(dest.name+'.preparing');need(not stage.exists(),'临时生产包已存在')
    try:
        stage.mkdir(parents=True)
        manifest=[]
        for a in payload['reference_assets']:
            target='references/'+a['id']+'.png';(stage/'references').mkdir(exist_ok=True)
            shutil.copy2(files[a['id']],stage/target);manifest.append({**a,'path':target})
        core.save_json(stage/'inputs.json',{'inputs':payload,'fingerprint':fingerprint,'created_at':datetime.now(timezone.utc).isoformat()})
        core.save_json(stage/'references.json',manifest);atomic_write(stage/'prompt.txt',prompt+'\n')
        core.save_json(stage/'receipt-template.json',{'input_fingerprint':fingerprint,'tool':'','model':'unknown','references':[dict(a,passed=False) for a in payload['reference_assets']]})
        stage.rename(dest)
    except Exception:
        if stage.exists():shutil.rmtree(stage)
        raise
    return {'ok':True,'outputs':[str(dest)],'language':payload['language'],'network':'未访问','generation':'未执行'}


def validate_receipt(receipt,payload,fingerprint):
    need(receipt.get('input_fingerprint')==fingerprint and nonempty(receipt.get('tool')),'生成回执须绑定本生产包和实际工具')
    need(receipt.get('mode','generated') in ('generated','reuse'),'未知制作回执类型')
    if receipt.get('mode')=='reuse':need(receipt.get('source') and payload['design'].get('textless') is True,'复用需要明确无字图来源')
    refs=receipt.get('references');need(isinstance(refs,list) and len(refs)==len(payload['reference_assets']),'缺少实际传入参考记录')
    actual={r.get('id'):r for r in refs};need(len(actual)==len(refs),'重复参考记录')
    for expected in payload['reference_assets']:
        got=actual.get(expected['id'],{})
        need(all(got.get(k)==v for k,v in expected.items()) and (got.get('reused') is True if receipt.get('mode')=='reuse' else got.get('passed') is True),'实际传入的参考角色／字节不符：'+expected['id'])


def revision_path(folder,lang,revision):
    need(isinstance(revision,str) and re.fullmatch(r'r\d{2,}',revision),'修订号应为 r01 等')
    return core.local(folder,'revisions/'+lang+'/'+revision)


def artwork_info(root, image):
    info=core.png_info(image)
    need(info['max_channel_delta']==0,'新版图片必须严格中性灰 R=G=B，不接受偏色像素')
    paper=Path(root)/'assets/illustrations/styles'/core.STYLE_ID/'paper.png'
    need([info['width'],info['height']]==image_dimensions(paper.read_bytes()),'成图画幅必须与固定方格纸母版一致')
    need(info['width']>=1400,'图片宽度不足 1400 px')
    return info


def import_candidate(root,figure,image,production_pack,revision,tool,language=None,receipt_path=None):
    root=Path(root).resolve();book,_,_,folder,_=core.resolve(root,figure);lang=locale(book,language)
    with lock(root,figure):
        payload,fp,prompt=inputs(root,figure,lang);pack_dir=safe_path(root,production_pack)
        saved=core.read_json(pack_dir/'inputs.json')
        need(saved.get('inputs')==payload and saved.get('fingerprint')==fp and (pack_dir/'prompt.txt').read_text().rstrip('\n')==prompt,'生产包与当前输入不一致')
        refs=core.read_json(pack_dir/'references.json')
        need(len(refs)==len(payload['reference_assets']),'生产包参考缺失')
        for expected in payload['reference_assets']:
            found=[r for r in refs if r.get('id')==expected['id']]
            need(len(found)==1 and all(found[0].get(k)==v for k,v in expected.items()),'生产包参考清单变更')
            need(core.digest(safe_path(pack_dir,found[0]['path']).read_bytes())==expected['sha256'],'生产包参考图片变更')
        need(receipt_path,'新版导入需要实际生成回执 --receipt')
        receipt=core.read_json(receipt_path);validate_receipt(receipt,payload,fp)
        need(tool==receipt['tool'],'实际工具与回执不符')
        info=artwork_info(root,image)
        if receipt.get('mode')=='reuse':verify_reuse(root,figure,payload,receipt,info['sha256'])
        need(info['width']>=1400,'图片宽度不足 1400 px')
        dest=revision_path(folder,lang,revision);need(not dest.exists(),'修订已存在，禁止覆盖')
        stage=dest.with_name('.'+dest.name+'-import');need(not stage.exists(),'导入临时目录已存在')
        try:
            stage.mkdir(parents=True)
            shutil.copy2(image,stage/(lang+'.png'));need(core.png_info(stage/(lang+'.png'))==info,'导入中图片改变')
            core.save_json(stage/'inputs.json',saved);atomic_write(stage/'prompt.txt',prompt+'\n')
            core.save_json(stage/'provenance.json',{'schema_version':2,'figure':figure,'language':lang,'image':info,'input_fingerprint':fp,'tool':tool,'receipt':receipt,'created_at':datetime.now(timezone.utc).isoformat()})
            stage.rename(dest)
        except Exception:
            if stage.exists():shutil.rmtree(stage)
            raise
    return {'ok':True,'outputs':[str(dest)],'stage':'待检查','language':lang}


def validate_review(review,payload,info,fp,reading=False):
    core.validate_review(review,info['sha256'],fp);evidence_stamp(review,'reviewer')
    need(review.get('language')==payload['language'],'审校语言不匹配')
    for key in ('structure','localization'):
        need(review.get(key)=='pass','采用前必须完成 '+key+' 审校')
    if payload['design']['kind']=='interface':
        need(review.get('interface')=='pass','界面结构尚未逐项核对')
        need(review.get('references')=={r['id']:r['image_sha256'] for r in payload['references']},'界面审校引用与实际截图不符')
    if reading:need(review.get('placement')=='pass','实际语言版阅读检查尚未通过')


def selected(root,figure,language=None,current=True,reading=False):
    book,_,b,folder,unit=core.resolve(root,figure);lang=locale(book,language)
    need(b['schema_version']==2,'旧图尚未进行多语言迁移')
    selection=load_yaml(folder/'selection.yaml');value=selection.get('languages',{}).get(lang)
    need(value,'缺少目标语言采用图：'+lang)
    dest=revision_path(folder,lang,value.get('revision'));image=artwork_info(root,dest/(lang+'.png'))
    provenance=core.read_json(dest/'provenance.json');frozen=core.read_json(dest/'inputs.json');payload=frozen.get('inputs');fp=core.digest(payload)
    need(frozen.get('fingerprint')==fp==value.get('input_fingerprint')==provenance.get('input_fingerprint'),'采用输入摘要不符')
    need(payload.get('figure')==figure and payload.get('language')==lang,'采用图身份或语言不符')
    need(image==provenance.get('image') and image['sha256']==value.get('image_sha256'),'采用图字节已变')
    need(core.digest((dest/'prompt.txt').read_text().rstrip('\n').encode())==payload['prompt_sha256'],'采用提示词已变')
    validate_receipt(provenance['receipt'],payload,fp)
    if provenance['receipt'].get('mode')=='reuse':verify_reuse(root,figure,payload,provenance['receipt'],image['sha256'])
    validate_review(core.read_json(dest/'review.json'),payload,image,fp,reading)
    if current:need(inputs(root,figure,lang)[1]==fp,'插图来源／目标语言文字已过期')
    return dest/(lang+'.png'),payload,value


def block(figure,image,source,text,language):
    from urllib.parse import quote
    def escaped(value):
        return re.sub(r"([\\`*_{}\[\]<>])", r"\\\1", value.replace('\n',' '))
    path=quote(os.path.relpath(image,source.parent),safe='/.-_')
    return ('<!-- diagram: '+figure+' -->\n!['+escaped(text['alt'])+']('+path+')\n\n'+
            ('*图：' if language.startswith('zh') else '*Figure: ')+escaped(text['caption'])+'*\n<!-- /diagram: '+figure+' -->')


def place(body,figure,replacement,heading=None):
    matches=[m for m in core.MANAGED.finditer(body) if m.group(1)==figure]
    need(len(matches)<=1,'正文重复图号')
    if matches:
        m=matches[0];return body[:m.start()]+replacement+body[m.end():]
    need(heading,'译文必须保留稳定的插图标记，不能按中文标题猜位置')
    matches=list(re.finditer(r'(?m)^#{1,6} '+re.escape(heading)+r'\s*$',body))
    need(len(matches)==1,'插入小节须唯一命中')
    pos=matches[0].end();return body[:pos]+'\n\n'+replacement+'\n'+body[pos:]


def source_path(root,book,unit,language):
    if language==book.get('language','zh-CN'):return safe_path(root,unit['path'])
    from .localization import target_path
    return target_path(root,book,unit,language)


def select(root,figure,revision,review_path,language=None):
    root=Path(root).resolve();book,_,b,folder,unit=core.resolve(root,figure);lang=locale(book,language)
    with lock(root,figure):
        payload,fp,_=inputs(root,figure,lang);dest=revision_path(folder,lang,revision)
        image=artwork_info(root,dest/(lang+'.png'));provenance=core.read_json(dest/'provenance.json');frozen=core.read_json(dest/'inputs.json')
        need(provenance.get('image')==image and provenance.get('input_fingerprint')==fp and frozen.get('inputs')==payload and frozen.get('fingerprint')==fp,'候选已变化或输入过期')
        need(core.digest((dest/'prompt.txt').read_text().rstrip('\n').encode())==payload['prompt_sha256'],'候选提示词改变')
        validate_receipt(provenance['receipt'],payload,fp)
        if provenance['receipt'].get('mode')=='reuse':verify_reuse(root,figure,payload,provenance['receipt'],image['sha256'])
        review=core.read_json(review_path);validate_review(review,payload,image,fp)
        source=source_path(root,book,unit,lang);old=source.read_text()
        if lang!=book.get('language','zh-CN'):
            from .localization import unit_status
            need(unit_status(root,book,unit,lang)['status']=='current','先导入并核对当前语言正文；保留人工修改')
        new=place(old,figure,block(figure,dest/(lang+'.png'),source,payload['text'],lang),b['placement'] if lang==book.get('language','zh-CN') else None)
        sp=folder/'selection.yaml';previous=sp.read_text() if sp.exists() else None
        selection=load_yaml(sp) if previous else {'schema_version':2,'languages':{}}
        need(selection.get('schema_version')==2,'不能覆盖旧版采用记录')
        review_dest=dest/'review.json'
        if review_dest.exists():
            prior=core.read_json(review_dest)
            if prior!=review:
                # Reading review follows adoption. Only this one-way completion is
                # allowed; preserve the original review of the same exact pixels.
                need(prior.get('placement')!='pass' and review.get('placement')=='pass'
                     and {k:v for k,v in prior.items() if k!='placement'}=={k:v for k,v in review.items() if k!='placement'},
                     '修订已有不同审校，除补齐入稿检查外须使用新修订')
                archive=dest/'review-before-placement.json'
                need(not archive.exists(),'入稿补审归档已存在；核对现场')
                core.save_json(archive,prior)
        core.save_json(review_dest,review)
        selection['languages'][lang]={'revision':revision,'image_sha256':image['sha256'],'input_fingerprint':fp}
        try:dump_yaml(sp,selection);atomic_write(source,new)
        except Exception:
            if previous is None:sp.unlink(missing_ok=True)
            else:atomic_write(sp,previous)
            atomic_write(source,old);raise
    return {'ok':True,'stage':'可用' if review.get('placement')=='pass' else '待检查','outputs':[str(source),str(sp)],'pending':[] if review.get('placement')=='pass' else ['当前语言入稿阅读检查']}


def audit(root,publication=False,scope=None,language=None):
    book,records=core.figures(root);langs=[locale(book,language)] if language else [book.get('language','zh-CN')];rows=[];issues=[]
    for record in records:
        if scope is not None and record['unit'] not in scope:continue
        b=load_yaml(safe_path(root,record['spec']))
        if b.get('schema_version')!=2:continue
        for lang in langs:
            row={'id':record['id'],'unit':record['unit'],'language':lang,'kind':b.get('kind'),'form':b.get('form'),'stage':'待研究'}
            adopted = False
            selection_path = safe_path(root,record['spec']).parent/'selection.yaml'
            if selection_path.exists():
                selection_data = load_yaml(selection_path) or {}
                adopted = lang in selection_data.get('languages',{})
            try:
                payload,fp,_=inputs(root,record['id'],lang);row['stage']='待生成'
                _,_,_,folder,unit=core.resolve(root,record['id'])
                if (folder/'selection.yaml').exists() and lang in load_yaml(folder/'selection.yaml').get('languages',{}):
                    image,payload,selection=selected(root,record['id'],lang,reading=publication)
                    source=source_path(root,book,unit,lang);blocks=[m.group(0) for m in core.MANAGED.finditer(source.read_text()) if m.group(1)==record['id']]
                    need(blocks==[block(record['id'],image,source,payload['text'],lang)],'入稿图片、文字或位置标记与采用记录不一致')
                    review=core.read_json(image.parent/'review.json');row.update(stage='可用' if review.get('placement')=='pass' else '待检查',revision=selection['revision'])
                else:
                    candidates=[p.parent.name for p in (folder/'revisions'/lang).glob('r*/provenance.json') if core.read_json(p).get('input_fingerprint')==fp]
                    if candidates:row.update(stage='待检查',candidates=sorted(candidates))
                    raise StudioError('候选待审／采用' if candidates else '缺少当前语言已采用图片')
            except (StudioError,OSError,ValueError,KeyError,TypeError) as e:
                row['reason']=str(e);issues.append({'level':'error' if publication or adopted else 'warning','code':'illustration_v2_pending','path':record['spec'],'message':record['id']+' ['+lang+']: '+str(e)})
            rows.append(row)
    return {'ok':not any(i['level']=='error' for i in issues),'figures':rows,'issues':issues,'network':'未访问','generation':'未执行'}


def verify_reuse(root,figure,payload,receipt,image_hash):
    source=receipt.get('source',{});book,_,_,folder,_=core.resolve(root,figure)
    lang=locale(book,source.get('language'));dest=revision_path(folder,lang,source.get('revision'))
    frozen=core.read_json(dest/'inputs.json');other=frozen['inputs'];fp=core.digest(other)
    need(frozen.get('fingerprint')==fp==source.get('input_fingerprint'),'复用来源输入摘要不符')
    need(other.get('figure')==figure and other.get('language')==lang,'复用来源身份不符')
    need(payload['design'].get('textless') is True and other['design'].get('textless') is True and not other['text']['labels'] and not payload['text']['labels'],'仅明确的无字图可以复用')
    for k in ('design','sources','facts','ui','references','reference_assets','style_files','rules'):
        need(payload[k]==other[k],'复用图的共同内容／风格不一致：'+k)
    info=artwork_info(root,dest/(lang+'.png'));need(info['sha256']==image_hash==source.get('image_sha256'),'复用图片字节不符')
    provenance=core.read_json(dest/'provenance.json');need(provenance.get('image')==info and provenance.get('input_fingerprint')==fp,'复用来源制作记录不符')
    need(core.digest((dest/'prompt.txt').read_text().rstrip('\n').encode())==other['prompt_sha256'],'复用来源提示词改变')
    validate_review(core.read_json(dest/'review.json'),other,info,fp)
    # Require an actual generated origin, so reuse records cannot form cycles.
    need(provenance['receipt'].get('mode','generated')=='generated','复用应指向最初生成且已审的版本')
    validate_receipt(provenance['receipt'],other,fp)


def reuse(root,figure,source_language,language,revision,production_pack):
    root=Path(root).resolve();book,_,_,folder,_=core.resolve(root,figure);target=locale(book,language)
    source_image,other,selection=selected(root,figure,source_language)
    payload,fp,prompt=inputs(root,figure,target)
    receipt={'mode':'reuse','tool':'reuse-reviewed-artwork','input_fingerprint':fp,
        'references':[dict(a,reused=True) for a in payload['reference_assets']],
        'source':{'language':source_language,'revision':selection['revision'],'image_sha256':core.png_info(source_image)['sha256'],'input_fingerprint':selection['input_fingerprint']}}
    verify_reuse(root,figure,payload,receipt,receipt['source']['image_sha256'])
    pack_dir=safe_path(root,production_pack)
    receipt_file=pack_dir/'reuse-receipt.json';need(not receipt_file.exists(),'复用回执已存在，不覆盖')
    core.save_json(receipt_file,receipt)
    return import_candidate(root,figure,source_image,production_pack,revision,receipt['tool'],target,receipt_file)


def preview(root,figure,revision,language,output):
    """Private before-adoption comparison; review in a real browser at reading size."""
    import html
    root=Path(root).resolve();book,_,_,folder,unit=core.resolve(root,figure);lang=locale(book,language)
    dest=revision_path(folder,lang,revision);image=dest/(lang+'.png');info=core.png_info(image)
    frozen=core.read_json(dest/'inputs.json');payload=frozen['inputs']
    need(payload.get('figure')==figure and payload.get('language')==lang,'候选身份不符')
    need(core.digest(payload)==frozen['fingerprint'],'候选输入摘要不符')
    target=safe_path(root,output);need(target.relative_to(root).parts[0]=='.studio','含真实截图的对照预览只能放在私有 .studio')
    need(not target.exists(),'预览已存在，换版本保留审阅对象')
    def img(path):return '<img src="'+html.escape(os.path.relpath(path,target.parent),quote=True)+'">'
    references=''.join('<section><h3>'+html.escape(r['id'])+'</h3>'+img(reference_file(root,r['id']))+'</section>' for r in payload['references'] if reference_file(root,r['id']).exists())
    source=source_path(root,book,unit,lang)
    body=source.read_text() if source.exists() else '[Target language manuscript missing]'
    document='<!doctype html><html lang="'+lang+'"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+html.escape(figure)+' review</title><style>body{font:16px/1.7 system-ui;margin:24px;color:#111;background:#eee}article{background:white;padding:16px;max-width:760px;margin:auto}img{max-width:100%;height:auto}details{margin:16px 0}pre{white-space:pre-wrap;word-break:break-word}.phone{width:358px;max-width:100%;margin:auto}section{margin:24px 0}</style><article><h1>'+html.escape(figure+' · '+lang)+'</h1><p>Candidate SHA-256: '+info['sha256']+'</p><h2>Reading size · 358 px</h2><div class="phone">'+img(image)+'<p>'+html.escape(payload['text']['caption'])+'</p></div><details><summary>Manuscript context</summary><pre>'+html.escape(body)+'</pre></details><details><summary>Verified references and structural analysis</summary>'+references+'<pre>'+html.escape(json.dumps(payload['references'] or payload['design'],ensure_ascii=False,indent=2))+'</pre></details><h2>Full-size comparison</h2>'+img(image)+'</article></html>'
    atomic_write(target,document)
    return {'ok':True,'outputs':[str(target)],'visual_review':'未执行；需要实际打开查看后记录'}


def gallery(root, output, language=None):
    """A book-wide visual comparison; rendering never records a visual pass."""
    import html
    from urllib.parse import quote
    root=Path(root).resolve();book,records=core.figures(root)
    langs=[locale(book,language)] if language else languages(book)
    target=safe_path(root,output)
    need(target.relative_to(root).parts[0]=='.studio','全书对照预览放在私有 .studio 内')
    need(not target.exists(),'全书预览已存在，换版本保留现场')
    reports=[core.audit(root,language=lang) for lang in langs];cards=[]
    def img(path):
        return '<img loading="lazy" src="'+html.escape(quote(os.path.relpath(path,target.parent),safe='/.-_'),quote=True)+'">'
    for lang,report in zip(langs,reports):
        for record in records:
            _,_,brief,folder,_=core.resolve(root,record['id'])
            selection_path=folder/'selection.yaml';selection=load_yaml(selection_path) if selection_path.exists() else {}
            row=next((r for r in report['figures'] if r['id']==record['id']),{})
            errors=[i['message'] for i in report['issues'] if record['id'] in i['message']]
            image=None
            if brief['schema_version']==2 and lang in selection.get('languages',{}):
                image=revision_path(folder,lang,selection['languages'][lang]['revision'])/(lang+'.png')
            elif brief['schema_version']==1 and lang==book.get('language','zh-CN') and selection.get('revision'):
                need(re.fullmatch(r'r\d{2,}',selection['revision']),'历史修订号无效')
                image=core.local(folder,'revisions/'+selection['revision']+'/zh-CN.png')
            body=img(image) if image and image.is_file() else '<p>Missing image for this language / 当前语言缺图</p>'
            cards.append('<section><h2>'+html.escape(record['id']+' · '+lang)+'</h2><p>'+html.escape(str(row.get('stage',row.get('status','待处理'))))+'</p>'+body+'<p>'+html.escape('; '.join(errors))+'</p></section>')
    paper=root/'assets/illustrations/styles'/core.STYLE_ID/'paper.png'
    page='<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Book illustration review</title><style>body{font:16px/1.6 system-ui;background:#eee;color:#111;margin:24px}main{display:flex;flex-wrap:wrap;gap:24px}section{box-sizing:content-box;width:358px;max-width:100%;padding:16px;background:white}img{max-width:100%;height:auto}h2{font-size:18px}</style><h1>全书插图与语言版对照</h1><p>358 px 阅读宽；逐图检查同一纸张、黑白与黑笔、标签、关系和可读性。本页不代表目视验收通过。</p><main><section><h2>统一纸底</h2>'+img(paper)+'</section>'+''.join(cards)+'</main></html>'
    atomic_write(target,page)
    return {'ok':True,'outputs':[str(target)],'visual_review':'未执行；实际查看全书后记录','pending':[i['message'] for r in reports for i in r['issues']]}
