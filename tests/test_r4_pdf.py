import json
from pathlib import Path
import sys
import fitz
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bind_court_pdf as binder
import stamp_evidence as stamper

def pdf(path, text='SOURCE', width=595,height=842):
    d=fitz.open(); p=d.new_page(width=width,height=height); p.insert_text((10,20),text); d.save(path); d.close()
    return path

def test_manifest_relative_path_wins(tmp_path,monkeypatch):
    a=tmp_path/'a'; a.mkdir(); b=tmp_path/'b'; b.mkdir()
    pdf(a/'same.pdf','RIGHT'); pdf(b/'same.pdf','WRONG')
    manifest=a/'list.json'; manifest.write_text(json.dumps([{'file':'same.pdf'}]))
    monkeypatch.chdir(b)
    out=b/'out.pdf'
    assert binder.main(['-i',str(manifest),'-o',str(out)])==0
    with fitz.open(out) as d: assert 'RIGHT' in d[0].get_text() and 'WRONG' not in d[0].get_text()

@pytest.mark.parametrize('alias',['same','hardlink','symlink'])
def test_binder_refuses_input_collision(tmp_path,alias):
    source=pdf(tmp_path/'source.pdf'); before=source.read_bytes(); out=tmp_path/'out.pdf'
    if alias=='same': out=source
    elif alias=='symlink': out.symlink_to(source)
    else: out.hardlink_to(source)
    manifest=tmp_path/'list.json'; manifest.write_text(json.dumps([{'file':str(source)}]))
    assert binder.main(['-i',str(manifest),'-o',str(out)]) != 0
    assert source.read_bytes()==before

def test_serialized_volumes_obey_limit(tmp_path):
    items=[{'file':str(pdf(tmp_path/f'{i}.pdf',f'SOURCE {i}')),'label':str(i),'title':''} for i in range(3)]
    singles=binder.bind_volumes(items,10**7)
    combined=len(singles[0]['doc'].tobytes(garbage=4,deflate=True)); singles[0]['doc'].close()
    limit=combined-100
    manifest=tmp_path/'list.json'; manifest.write_text(json.dumps(items))
    assert binder.main(['-i',str(manifest),'-o',str(tmp_path/'out.pdf'),'--max-mb',str(limit/1024/1024)])==0
    outputs=list(tmp_path.glob('out*.pdf')); assert len(outputs)>1
    assert all(p.stat().st_size<=limit for p in outputs)

def test_impossibly_small_limit_fails(tmp_path):
    source=pdf(tmp_path/'source.pdf'); manifest=tmp_path/'list.json'; manifest.write_text(json.dumps([{'file':str(source)}]))
    assert binder.main(['-i',str(manifest),'-o',str(tmp_path/'out.pdf'),'--max-mb','0.0001'])!=0
    assert not list(tmp_path.glob('out*.pdf'))

@pytest.mark.parametrize('failure',['font','label','bates','page'])
def test_stamper_refuses_missing_required_marks(tmp_path,monkeypatch,failure):
    source=pdf(tmp_path/'source.pdf',width=60 if failure=='page' else 595,height=60 if failure=='page' else 842)
    out=tmp_path/'out.pdf'
    font=tmp_path/'invalid.ttf'; font.write_bytes(b'not a font')
    if failure=='font': monkeypatch.setattr(stamper,'_get_korean_font',lambda:str(font))
    label='A'*1000 if failure=='label' else '갑 제1호증'
    prefix='P'*1000 if failure=='bates' else 'P'
    assert not stamper.stamp_pdf_pymupdf(str(source),str(out),label,bates_prefix=prefix,allow_broken_font=failure!='font')
    assert not out.exists()
