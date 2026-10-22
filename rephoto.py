
"""1915 rephotography worker: for each archive photo, find the modern Street View camera angle.
Candidates: official Google panoramas within 150 m. Coarse: DINOv2 similarity over perspective crops.
Fine: DISK + LightGlue matches, MAGSAC homography, then solve heading/pitch/field of view; one refinement pass.
Writes /workspace/1915/site/data/rephoto.json  {photoId: [pano, lat, lon, heading, pitch, hfov, inliers, date]}"""
import os, sys, io, json, math, time, re, traceback
os.environ.setdefault('TORCH_HOME', '/tmp/torch')
import numpy as np, cv2, torch, requests
from PIL import Image
import concurrent.futures as cf
from streetlevel import streetview
import kornia.feature as KF
torch.set_num_threads(4)
BASE = '/workspace/1915'
OUT = BASE + '/site/data/rephoto.json'
TRIED = BASE + '/rephoto_tried.json'
QA = '/tmp/rephoto_qa'; os.makedirs(QA, exist_ok=True)
PC = '/tmp/panos'; os.makedirs(PC, exist_ok=True)
photos = {r[0]: r for r in json.load(open(BASE + '/site/data/photos.json'))}
queue = json.load(open(BASE + '/rephoto_queue.json'))
res = json.load(open(OUT)) if os.path.exists(OUT) else {}
tried = json.load(open(TRIED)) if os.path.exists(TRIED) else {}
dino = torch.hub.load('facebookresearch/dinov2', 'dinov2_vits14', verbose=False).eval()
disk = KF.DISK.from_pretrained('depth').eval()
lg = KF.LightGlueMatcher('disk').eval()
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1); STD = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)

def gray3(a):
    g = cv2.equalizeHist(cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)); return np.stack([g] * 3, -1)
def hist(pid):
    b = requests.get(f'https://s3-us-west-1.amazonaws.com/oldsf/images/{pid}.jpg', timeout=30).content
    return np.array(Image.open(io.BytesIO(b)).convert('RGB'))
def nearby(la, lo, R=150, step=30):
    pts = []; dl = step / 111000; dlo = step / (111000 * math.cos(math.radians(la))); n = int(R / step)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            if (i * step) ** 2 + (j * step) ** 2 <= R * R: pts.append((la + i * dl, lo + j * dlo))
    def f(p):
        for t in range(3):
            try: return streetview.find_panorama(p[0], p[1], radius=25, search_third_party=False)
            except Exception: time.sleep(1 + t)
    out = {}
    with cf.ThreadPoolExecutor(12) as ex:
        for p in ex.map(f, pts):
            if p and p.id not in out: out[p.id] = p
    return list(out.values())
def pimg(p, zoom):
    fn = f'{PC}/{p.id}_{zoom}.jpg'
    if os.path.exists(fn): return np.array(Image.open(fn))
    im = streetview.get_panorama(p, zoom=zoom).convert('RGB'); im.save(fn, quality=88); return np.array(im)
def persp(eq, hd, pt, fov, w, h, ph):
    H, W = eq.shape[:2]; f = 0.5 * w / math.tan(math.radians(fov) / 2)
    xs, ys = np.meshgrid(np.arange(w) - w / 2 + 0.5, np.arange(h) - h / 2 + 0.5)
    x = xs; y = -ys; z = np.full_like(xs, f); p = math.radians(pt)
    y2 = y * math.cos(p) + z * math.sin(p); z2 = -y * math.sin(p) + z * math.cos(p)
    lon = np.arctan2(x, z2) + math.radians(hd - ph); lat = np.arctan2(y2, np.sqrt(x * x + z2 * z2))
    u = ((lon / (2 * math.pi) + 0.5) % 1) * W; v = (0.5 - lat / math.pi) * H
    return cv2.remap(eq, u.astype(np.float32), v.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
@torch.no_grad()
def dfeat(imgs, side=224):
    out = []
    for a in imgs:
        a = cv2.resize(gray3(a), (side, max(14, side * a.shape[0] // a.shape[1] // 14 * 14)))
        x = ((torch.from_numpy(a).permute(2, 0, 1).float() / 255) - MEAN) / STD
        o = dino.forward_features(x[None])
        out.append(torch.nn.functional.normalize(torch.cat([o['x_norm_clstoken'][0], o['x_norm_patchtokens'][0].mean(0)]), dim=0))
    return torch.stack(out)
@torch.no_grad()
def dfe(a, m=640):
    s = m / max(a.shape[:2]); a = cv2.resize(gray3(a), (int(a.shape[1] * s) // 16 * 16, int(a.shape[0] * s) // 16 * 16))
    f = disk(torch.from_numpy(a).permute(2, 0, 1).float()[None] / 255, n=2048, pad_if_not_divisible=True)[0]
    return f.keypoints, f.descriptors, a.shape[:2]
@torch.no_grad()
def match(fa, fb):
    ka, da, sa = fa; kb, db, sb = fb
    if len(ka) < 8 or len(kb) < 8: return 0, None
    la_ = KF.laf_from_center_scale_ori(ka[None], torch.ones(1, len(ka), 1, 1)); lb_ = KF.laf_from_center_scale_ori(kb[None], torch.ones(1, len(kb), 1, 1))
    _, idx = lg(da, db, la_, lb_, hw1=torch.tensor(sa), hw2=torch.tensor(sb))
    if len(idx) < 12: return 0, None
    Hm, mask = cv2.findHomography(ka[idx[:, 0]].numpy(), kb[idx[:, 1]].numpy(), cv2.USAC_MAGSAC, 6.0)
    if Hm is None: return 0, None
    return int(mask.sum()), Hm
def ray(x, y, hd, pt, fov, w, h):
    f = 0.5 * w / math.tan(math.radians(fov) / 2); X = x - w / 2; Y = -(y - h / 2); Z = f; p = math.radians(pt)
    Y2 = Y * math.cos(p) + Z * math.sin(p); Z2 = -Y * math.sin(p) + Z * math.cos(p)
    return math.degrees(math.atan2(X, Z2)) + hd, math.degrees(math.atan2(Y2, math.hypot(X, Z2)))
def solve(fh, Hm, crop_shape, sb, hd, pt, fov):
    hh, hw = fh[2]; ch, cw = crop_shape; sx = cw / sb[1]; sy = ch / sb[0]
    def m(x, y):
        v = Hm @ np.array([x, y, 1.0]); return v[0] / v[2] * sx, v[1] / v[2] * sy
    cx, cy = m(hw / 2, hh / 2); lx, ly = m(0, hh / 2); rx, ry = m(hw, hh / 2)
    hc, pc = ray(cx, cy, hd, pt, fov, cw, ch); hl, _ = ray(lx, ly, hd, pt, fov, cw, ch); hr, _ = ray(rx, ry, hd, pt, fov, cw, ch)
    return hc % 360, pc, (hr - hl) % 360

def align(pid):
    r = photos[pid]; H0 = hist(pid); asp = H0.shape[0] / H0.shape[1]
    panos = nearby(r[1], r[2])
    if not panos: return None, 'no panos'
    hf = dfeat([H0])[0]; cands = []
    for p in panos:
        ph = math.degrees(p.heading); eq = pimg(p, 2)
        hs = list(range(0, 360, 20))
        sims = (dfeat([persp(eq, h, 4, 70, 336, int(336 * asp), ph) for h in hs]) @ hf).tolist()
        cands += [(s, p, h) for s, h in zip(sims, hs)]
    cands.sort(key=lambda x: -x[0])
    fh = dfe(H0); found = []
    for s, p, hd in cands[:16]:
        eq = pimg(p, 3); ph = math.degrees(p.heading); b = (0,)
        for fov in (40, 60, 85):
            w = 640; h = int(w * asp); c = persp(eq, hd, 4, fov, w, h, ph); fc = dfe(c)
            n, Hm = match(fh, fc)
            if n > b[0]: b = (n, p, hd, 4, fov, Hm, c.shape[:2], fc[2])
        if b[0] >= 25: found.append(b)
    found.sort(key=lambda x: -x[0])
    if not found: return None, 'weak'
    final = (0,)
    for n, p, hd, pt, fov, Hm, cs, sb in found[:3]:
        eq = pimg(p, 3); ph = math.degrees(p.heading); ok = True
        for it in range(2):
            hd, pt, fov = solve(fh, Hm, cs, sb, hd, pt, fov)
            if not (8 <= fov <= 110 and -35 <= pt <= 45): ok = False; break
            w = 640; h = int(w * asp); c = persp(eq, hd, pt, fov, w, h, ph); fc = dfe(c)
            n2, Hm2 = match(fh, fc)
            if n2 < 25: ok = False; break
            n, Hm, cs, sb = n2, Hm2, c.shape[:2], fc[2]
        if ok:
            hd2, pt2, fov2 = solve(fh, Hm, cs, sb, hd, pt, fov)
            if n > final[0] and 8 <= fov2 <= 110: final = (n, p, hd2, pt2, fov2)
    if final[0] < 40: return None, f'weak after refine {final[0]}'
    n, p, hd, pt, fov = final
    eq = pimg(p, 3); ph = math.degrees(p.heading)
    W_ = 520; Hh = int(W_ * asp)
    now = persp(eq, hd, pt, fov, W_, Hh, ph); then = cv2.resize(H0, (W_, Hh))
    Image.fromarray(np.concatenate([then, now, (0.5 * then + 0.5 * now).astype(np.uint8)], 1)).save(f'{QA}/{pid}.jpg', quality=82)
    return [p.id, round(p.lat, 7), round(p.lon, 7), round(hd, 2), round(pt, 2), round(fov, 2), n, str(p.date or '')], 'ok'


sys.path.insert(0, '/workspace')
from mterm import term
REPO = '/Users/behzadhaghgoo/code/1915'
last_push = {'n': len(res), 't': time.time()}
def push(force=False):
    new = len(res) - last_push['n']
    if new <= 0 or not (force or new >= 4 or time.time() - last_push['t'] > 1800): return
    try:
        t = term(); t.write(REPO + '/data/rephoto.json', open(OUT).read())
        r = t.run(f"cd {REPO} && git add data/rephoto.json && git commit -q -m 'Same-angle Street View for {len(res)} photos' && git push -q 2>&1 | tail -2", description='1915: push newly aligned photos')
        print('pushed', len(res), (r.get('out') or '').strip(), flush=True)
        last_push['n'] = len(res); last_push['t'] = time.time()
    except Exception as e:
        print('push failed', repr(e)[:200], flush=True)

def save():
    tmp = OUT + '.tmp'; json.dump(res, open(tmp, 'w'), separators=(',', ':')); os.replace(tmp, OUT)
    json.dump(tried, open(TRIED, 'w'))
for pid in queue:
    if pid in res or pid in tried or pid not in photos: continue
    t0 = time.time()
    try:
        v, why = align(pid)
    except Exception as e:
        v, why = None, 'error ' + repr(e)[:120]; traceback.print_exc()
    if v: res[pid] = v
    tried[pid] = why
    save()
    print(pid, why, v and v[3:7], round(time.time() - t0), 's', flush=True)
    push()
push(force=True)
print('queue done', flush=True)
