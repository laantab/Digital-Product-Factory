"""Bounded free stock acquisition and source-derived chapter summaries.

Stock metadata relevance is a filter, not a claim of visual/semantic inspection.
No generated image provider, secret persistence, arbitrary hosts or redirects.
"""
import hashlib
import io
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
import uuid
import requests
from PIL import Image,ImageOps
from .publishing import verified_file


def safe_url(value,host):
    if not isinstance(value,str):raise ValueError('Missing image URL')
    parsed=urlsplit(value)
    if (parsed.scheme!='https' or parsed.hostname!=host or parsed.username or parsed.password
            or parsed.port not in {None,443} or parsed.fragment):raise ValueError('Unapproved image host')
    return value


def words(value):
    ignored={'about','after','before','chapter','clear','create','guide','simple','small','their',
             'these','through','using','weekly','with','your','setting','running','practical'}
    return {word.rstrip('s') for word in re.findall(r'[a-z]{4,}',value.lower()) if word not in ignored}


def relevant(query,description):
    matches=words(query)&words(description)
    generic={'team','work','people','group','paper','office','table','home'}
    return len(matches)>=2 or bool(matches-generic)


def overview(chapter):
    points=[]
    for paragraph in chapter['text'].split('\n\n'):
        sentence=re.split(r'(?<=[.!?])\s+',paragraph.strip())[0]
        if 5<=len(sentence.split())<=45 and sentence not in points:points.append(sentence)
        if len(points)==3:break
    return points


class Stock:
    def __init__(self,root,budget=30,limit=4):
        self.root=Path(root);self.deadline=time.monotonic()+budget;self.limit=limit
        self.session=requests.Session()

    def close(self):self.session.close()

    def request(self,url,**kwargs):
        remaining=self.deadline-time.monotonic()
        if remaining<=.1:raise ValueError('Stock acquisition budget reached')
        response=self.session.get(url,timeout=min(6,remaining),allow_redirects=False,**kwargs)
        if response.status_code!=200:raise ValueError('Stock provider unavailable')
        return response

    def candidates(self,query):
        key=os.environ.get('PEXELS_API_KEY','')
        if key:
            try:
                result=self.request('https://api.pexels.com/v1/search',
                    params={'query':query[:200],'per_page':8,'orientation':'landscape'},
                    headers={'Authorization':key}).json()
                for photo in result.get('photos',[]):
                    if relevant(query,photo.get('alt','')):
                        yield {'provider':'Pexels','id':str(photo['id']),'alt':photo['alt'],
                            'url':safe_url(photo['src'].get('large2x') or photo['src']['original'],'images.pexels.com'),
                            'page':safe_url(photo['url'],'www.pexels.com'),
                            'photographer':photo['photographer'],'license':'https://www.pexels.com/license/'}
            except (requests.RequestException,ValueError,KeyError,TypeError):pass
        key=os.environ.get('UNSPLASH_ACCESS_KEY','') or os.environ.get('UNSPLASH_API_KEY','')
        if key:
            try:
                result=self.request('https://api.unsplash.com/search/photos',
                    params={'query':query[:200],'per_page':8,'orientation':'landscape'},
                    headers={'Authorization':'Client-ID '+key}).json()
                for photo in result.get('results',[]):
                    description=photo.get('alt_description') or photo.get('description') or ''
                    if relevant(query,description):
                        yield {'provider':'Unsplash','id':str(photo['id']),'alt':description,
                            'url':safe_url(photo['urls']['regular'],'images.unsplash.com'),
                            'original':safe_url(photo['urls']['raw'],'images.unsplash.com'),
                            'page':safe_url(photo['links']['html'],'unsplash.com'),
                            'download':safe_url(photo['links']['download_location'],'api.unsplash.com'),
                            'photographer':photo['user']['name'],'license':'https://unsplash.com/license'}
            except (requests.RequestException,ValueError,KeyError,TypeError):pass

    def acquire(self,query):
        if self.limit<=0:return None
        for candidate in self.candidates(query):
            response=None
            try:
                host='images.pexels.com' if candidate['provider']=='Pexels' else 'images.unsplash.com'
                url=safe_url(candidate.get('original',candidate['url']),host)
                if host=='images.unsplash.com':
                    parsed=urlsplit(url);params=dict(parse_qsl(parsed.query));params.update(w='1800',q='90',fit='max',auto='format')
                    url=urlunsplit(parsed._replace(query=urlencode(params)))
                response=self.request(url,stream=True)
                chunks=[];size=0
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>12_000_000 or time.monotonic()>self.deadline:raise ValueError('Image budget exceeded')
                    chunks.append(chunk)
                with Image.open(io.BytesIO(b''.join(chunks))) as source:
                    if source.width*source.height>40_000_000:raise ValueError('Image too large')
                    image=ImageOps.exif_transpose(source).convert('RGB')
                    if image.width<1500 or image.height<900:raise ValueError('Image resolution too low')
                    image.thumbnail((2400,1800));output=io.BytesIO();image.save(output,'JPEG',quality=92)
                if candidate['provider']=='Unsplash':
                    location=safe_url(candidate['download'],'api.unsplash.com')
                    if not re.fullmatch(r'/photos/[A-Za-z0-9_-]+/download',urlsplit(location).path):
                        raise ValueError('Invalid download tracking route')
                    key=os.environ.get('UNSPLASH_ACCESS_KEY','') or os.environ.get('UNSPLASH_API_KEY','')
                    self.request(location,headers={'Authorization':'Client-ID '+key})
                data=output.getvalue();folder=self.root/'ebook-v2-media';folder.mkdir(parents=True,exist_ok=True)
                path=folder/(uuid.uuid4().hex+'.jpg')
                with path.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
                receipt={'key':str(path.relative_to(self.root)),'size':len(data),
                         'sha256':hashlib.sha256(data).hexdigest()}
                verified_file(self.root,receipt)
                self.limit-=1
                return {'file':receipt,'alt':candidate['alt'],'provider':candidate['provider'],
                    'photographer':candidate['photographer'],'source_url':candidate['page'],
                    'license_url':candidate['license'],'width':image.width,'height':image.height,
                    'review_scope':'Resolution and metadata relevance; owner page review required'}
            except (requests.RequestException,OSError,ValueError,KeyError,TypeError,Image.DecompressionBombError):pass
            finally:
                if response is not None:response.close()
        return None


def prepare(book,root):
    stock=Stock(root)
    try:
        result=[]
        for chapter in book['chapters']:
            subject=book.get('topic') or book['title']
            terms=[w for w in re.findall(r'[A-Za-z]{4,}',subject.lower()) if w.rstrip('s') in words(subject)]
            if len(terms)<3:terms.extend(w for w in re.findall(r'[A-Za-z]{4,}',chapter['title'].lower()) if w.rstrip('s') in words(chapter['title']))
            query=' '.join(list(dict.fromkeys(terms))[:6])
            photo=stock.acquire(query)
            result.append({'photo':photo,'overview':overview(chapter)})
        return result
    finally:stock.close()


def photo_bytes(root,visual):
    return verified_file(root,visual['photo']['file']) if visual.get('photo') else None


def credit(photo):
    return 'Photo by '+photo['photographer']+' on '+photo['provider']


def handler(payload,repair):
    import fitz
    from .publishing import render_pdf,THEMES
    root=Path(payload['root']);book=payload['book'];visuals=prepare(book,root)
    covers={};folder=root/'ebook-v2-media';folder.mkdir(parents=True,exist_ok=True)
    for theme in THEMES:
        with fitz.open(stream=render_pdf({**book,'theme':theme,'visuals':visuals},root=root,only_cover=True),filetype='pdf') as document:
            if len(document)!=1:raise ValueError('Cover layout overflow')
            data=document[0].get_pixmap(matrix=fitz.Matrix(300/72,300/72),alpha=False).tobytes('jpeg')
        path=folder/(uuid.uuid4().hex+'.jpg')
        with path.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        covers[theme]={'key':str(path.relative_to(root)),'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    return {'root':str(root),'visuals':visuals,'covers':covers}


def valid(output):
    from .publishing import THEMES
    try:
        root=output['root']
        if set(output['covers'])!=set(THEMES):return False
        for receipt in output['covers'].values():
            with Image.open(io.BytesIO(verified_file(root,receipt))) as image:
                if image.size!=(1800,2700):return False
        for visual in output['visuals']:
            if not isinstance(visual['overview'],list):return False
            if visual.get('photo'):photo_bytes(root,visual)
        return True
    except (OSError,KeyError,TypeError,ValueError):return False
