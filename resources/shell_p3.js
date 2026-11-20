/** @file 立体贺卡核心引擎上篇：主题隔离、4层零穿模3D渲染与防破音高响度八音盒 */
const $ = (id) => document.getElementById(id);
const cfg = window.CARD_CONFIG || {}, isChristmas = cfg.occasion === 'christmas', topFold = cfg.fold === 'vertical';
document.documentElement.classList.toggle('top-fold', topFold);
document.documentElement.classList.toggle('is-christmas', isChristmas);

/** 计算独立隔离 localStorage Key */
function computeStorageKey() {
  if (typeof cfg.cardId === 'string' && cfg.cardId.trim()) return `popup_card_blessing_v8_${cfg.cardId.trim()}`;
  const s = `${isChristmas ? 'x' : 'b'}|${topFold ? 'v' : 'h'}|${location.pathname}|${JSON.stringify(cfg.blessing || {})}`;
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return `popup_card_blessing_v8_${(h >>> 0).toString(16)}`;
}
const STORAGE_KEY = computeStorageKey();

if (isChristmas) {
  document.title = topFold ? '圣诞快乐 · 4:3 立体纸艺贺卡' : '圣诞快乐 · 手绘立体纸艺贺卡';
  $('miniNoteCakeSvg').style.display = $('cssHeaderCakeSvg').style.display = $('wickAnchor').style.display = $('iconWindSvg').style.display = 'none';
  $('miniNoteTreeSvg').style.display = $('cssHeaderTreeSvg').style.display = $('treeLightsLayer').style.display = $('iconStarSvg').style.display = 'block';
  $('miniNoteTxt').textContent = 'MERRY CHRISTMAS';
  $('cssHeaderTxt').innerHTML = '<span class="nw">MERRY&nbsp;~</span><br/><span class="nw">CHRISTMAS&nbsp;!</span>';
  $('lblPropAction').textContent = '星灯';
  $('btnPropAction').title = '轻点让圣诞树星灯璀璨绽放或柔和开关';
  $('propLayer').setAttribute('aria-label', '点击圣诞树点亮璀璨星灯');
  $('propLayer').title = '轻点圣诞树触发星灯璀璨闪烁与飘雪';
} else {
  document.title = topFold ? '生日快乐 · 4:3 立体纸艺贺卡' : '生日快乐 · 手绘立体纸艺贺卡';
  $('btnPropAction').title = '轻点直接吹灭或重燃，长按约 1 秒仿真吹气';
  $('propLayer').setAttribute('aria-label', '轻触直接熄灭或点亮蜡烛，长按仿真吹气');
  $('propLayer').title = '轻点直灭或重燃，长按仿真吹气';
}
if (topFold) document.querySelector('#coverTip span').textContent = isChristmas ? '轻触向上掀开圣诞贺卡' : '轻触向上掀开立体贺卡';
else if (isChristmas) document.querySelector('#coverTip span').textContent = '轻触翻开圣诞立体贺卡';

/** 校验有效图片 URL 或 DataURI */
function isRealUrl(v) { return typeof v === 'string' && v.trim().length > 0 && !v.includes('{{'); }

const theme = cfg.styleTheme || {}, rs = document.documentElement.style;
[['tableInner','--bi'],['tableOuter','--bo'],['paperCream','--pc'],['primaryAccent','--acc'],['secondaryAccent','--acc2'],['waxSealColor','--wax'],['filterCss','--flt']].forEach(([k,v]) => { if (theme[k]) rs.setProperty(v, theme[k]); });
const accent = theme.primaryAccent || '#4f7348', flower = theme.secondaryAccent || '#b5496b';
const EMPTY = 'data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%204%204%22%3E%3Crect%20width%3D%224%22%20height%3D%224%22%20fill%3D%22%23faf6ec%22/%3E%3C/svg%3E';
$('coverImg').src = isRealUrl(cfg.coverImageUrl) ? cfg.coverImageUrl : EMPTY;
$('insideLeftImg').src = isRealUrl(cfg.insideLeftUrl) ? cfg.insideLeftUrl : EMPTY;
$('insideRightImg').src = isRealUrl(cfg.insideRightUrl) ? cfg.insideRightUrl : EMPTY;
const archSrc = isRealUrl(cfg.archUrl) ? cfg.archUrl : EMPTY, charSrc = isRealUrl(cfg.characterImageUrl) ? cfg.characterImageUrl : EMPTY, propSrc = isRealUrl(cfg.cakeTableUrl) ? cfg.cakeTableUrl : EMPTY;
const archImgEl = $('archImg'), charImgEl = $('charImg'), propImgEl = $('propImg'), propSlotEl = $('propSlot'), envSlotEl = $('envSlot'), popupStageEl = $('popupStage');

const layout = { archW: topFold ? 536 : 510, archH: topFold ? 224 : 300, charW: topFold ? 228 : 240, charH: topFold ? 268 : 292, propW: topFold ? 152 : 168, propH: topFold ? 186 : 198, propX: topFold ? -184 : -224, propY: topFold ? 344 : 206, envX: topFold ? 186 : 228, envY: topFold ? 338 : 202 };

/** 按真实图片比例等比适配并动态拉开防撞间距 */
function computeSafeLayout() {
  const fit = (im, el, mw, mh, wk, hk) => {
    if (!im.naturalWidth) return;
    const s = Math.min(mw / im.naturalWidth, mh / im.naturalHeight);
    layout[wk] = Math.round(im.naturalWidth * s); layout[hk] = Math.round(im.naturalHeight * s);
    if (el) Object.assign(el.style, { width: layout[wk] + 'px', height: layout[hk] + 'px', marginLeft: (-layout[wk] / 2) + 'px', marginTop: (-layout[hk]) + 'px' });
  };
  fit(archImgEl, $('archLayer'), 536, topFold ? 224 : 316, 'archW', 'archH');
  fit(charImgEl, $('charLayer'), topFold ? 236 : 262, topFold ? 270 : 308, 'charW', 'charH');
  fit(propImgEl, null, topFold ? 156 : 178, topFold ? 188 : 210, 'propW', 'propH');
  propSlotEl.style.setProperty('--pw', layout.propW + 'px');
  propSlotEl.style.setProperty('--ph', layout.propH + 'px');
  const ph = layout.propW / 2;
  if (topFold) {
    layout.propX = -Math.round(Math.max(178, Math.min(280 - ph - 16, layout.charW / 2 + ph * 0.48 + 12))); layout.propY = 346;
    layout.envX = Math.round(Math.max(182, Math.min(198, layout.charW / 2 + 46))); layout.envY = 342;
  } else {
    layout.propX = -Math.round(Math.max(210, Math.min(430 - ph - 30, layout.charW / 2 + ph + 18))); layout.propY = 208;
    layout.envX = Math.round(Math.max(216, Math.min(334, layout.charW / 2 + 88))); layout.envY = 204;
  }
}
[archImgEl, charImgEl, propImgEl].forEach((i) => i.addEventListener('load', computeSafeLayout));
archImgEl.src = $('archBack3').src = $('archBack2').src = archSrc;
charImgEl.src = $('charBack1').src = $('charBack2').src = $('charBack3').src = charSrc;
propImgEl.src = $('propBack3').src = $('propBack2').src = propSrc;
if (!isChristmas && cfg.cakeWickPos && typeof cfg.cakeWickPos.leftPct === 'number') { $('wickAnchor').style.left = cfg.cakeWickPos.leftPct + '%'; $('wickAnchor').style.top = cfg.cakeWickPos.topPct + '%'; }

/** 渲染圣诞树顶星与树冠闪烁星灯 */
function renderChristmasTreeLights() {
  if (!isChristmas) return;
  const tl = cfg.treeLights || {}, starEl = $('treeTopStar');
  const hasStarKey = Object.prototype.hasOwnProperty.call(tl, 'topStar');
  const ts = hasStarKey ? tl.topStar : { leftPct: 50, topPct: 8.5 };
  if (starEl) {
    if (ts && typeof ts.leftPct === 'number' && typeof ts.topPct === 'number') {
      starEl.style.display = ''; starEl.style.left = ts.leftPct + '%'; starEl.style.top = ts.topPct + '%';
    } else { starEl.style.display = 'none'; }
  }
  const def = [[45,24,9,.1,1.7,1],[56,29,8,.5,2,0],[39,39,10,.9,1.6,1],[58,42,8,1.3,2.1,0],[33,53,10,.3,1.8,1],[50,51,9,.8,1.6,0],[65,55,8,1.4,2.2,1],[30,67,9,.6,1.9,0],[48,65,10,1.1,1.7,1],[67,68,9,.2,2,0]].map(([leftPct,topPct,size,delay,duration,warm])=>({leftPct,topPct,size,delay,duration,warm:!!warm}));
  const wrap = $('treeLightsWrap'); wrap.innerHTML = '';
  const pts = (tl && Array.isArray(tl.lights)) ? tl.lights : def;
  pts.forEach((pt) => {
    const n = document.createElement('span'), sz = pt.size || 9; n.className = 'sln';
    n.style.cssText = `left:${pt.leftPct}%;top:${pt.topPct}%;width:${sz}px;height:${sz}px;--delay:${pt.delay||0}s;--dur:${pt.duration||1.8}s;--core:${pt.warm?'#fff9d6':'#fff'};--glow:${pt.warm?'rgba(255,214,102,.92)':'rgba(255,244,196,.88)'}`;
    wrap.appendChild(n);
  });
}
renderChristmasTreeLights();
const usePhotoLinen = false;

const sparklesEl = $('sparklesLayer');
[[15,18],[28,12],[46,15],[67,14],[82,20],[12,36],[88,34]].forEach(([x,y],i)=>{ const s=document.createElement('span'); s.className='sd'; s.style.cssText=`left:${x}%;top:${y}%;width:3.5px;height:3.5px;animation-delay:${i*.4}s`; sparklesEl.appendChild(s); });

let isOpen = false, openProgress = 0, candleLit = true, starLightsOn = true, starBurstTimer = null;
let userTiltX = 0, userTiltY = 0, stageScale = 1, closedScale = 1, dragging = false, sx = 0, sy = 0, bx = 0, by = 0, moved = 0;
const els = { rig:$('cardRig'), shadow:$('tableShadow'), left:$('leftLeaf'), right:$('rightLeaf'), arch:$('archLayer'), char:$('charLayer'), charShadow:$('charShadow'), prop:$('propLayer'), env:$('envelopeLayer'), coverTip:$('coverTip'), openControls:$('openControls'), lblOpen:$('lblOpen'), statusPill:$('statusPill'), statusDot:$('statusDot'), statusText:$('statusText'), micMeterTrack:$('micMeterTrack'), micMeterFill:$('micMeterFill'), btnResetView:$('btnResetView') };

/** 按视口尺寸自适应缩放舞台，保证手机竖屏与拖拽零裁边 */
function updateScale() {
  const vw = window.innerWidth, sh = $('stageWrap').clientHeight || (window.innerHeight - 110);
  if (topFold) { stageScale = Math.max(.24, Math.min(1.02, Math.min((vw - 28) / 700, (sh - 28) / 910))); closedScale = Math.max(.28, Math.min(1.02, Math.min((vw - 32) / 620, (sh - 28) / 470))); return; }
  stageScale = Math.max(.22, Math.min(1.12, Math.min((vw - 28) / 1000, (sh - 28) / 610)));
}
updateScale(); window.addEventListener('resize', updateScale);
if ('ResizeObserver' in window) new ResizeObserver(updateScale).observe($('stageWrap'));

const LEAF_END = 0.56, POPUP_GATE = 0.58;
let lastLoopTs = 0;
/** 两段式零穿模主渲染循环（支持左右横版与 4:3 上下翻折版） */
function render3DLoop(ts) {
  const now = typeof ts === 'number' ? ts : performance.now();
  const dt = lastLoopTs ? Math.min(.08, Math.max(.004, (now - lastLoopTs) / 1000)) : .016; lastLoopTs = now;
  const diff = (isOpen ? 1 : 0) - openProgress;
  openProgress = Math.abs(diff) > .0012 ? openProgress + diff * (1 - Math.exp(-dt * 4.8)) : (isOpen ? 1 : 0);
  const p = openProgress, leafEase = 1 - Math.pow(1 - Math.min(1, p / LEAF_END), 2.2);
  els.coverTip.style.opacity = p < .08 ? '1' : '0';

  if (topFold) {
    const sc = closedScale + (stageScale - closedScale) * leafEase;
    els.rig.style.transform = `scale(${sc.toFixed(4)}) translate3d(0,${(-206 + 218 * leafEase).toFixed(1)}px,0) rotateX(${(8 + 38 * leafEase + userTiltX).toFixed(2)}deg) rotateY(${userTiltY.toFixed(2)}deg)`;
    els.shadow.style.transform = 'translate3d(0,16px,-24px)';
    els.left.style.transform = `translateZ(${(3.2 * (1 - leafEase)).toFixed(2)}px) rotateX(${(-179.4 + 153.4 * leafEase).toFixed(2)}deg)`;
    els.right.style.transform = 'rotateX(0deg)';
    if (p < POPUP_GATE) { popupStageEl.classList.add('popup-hidden'); requestAnimationFrame(render3DLoop); return; }
    popupStageEl.classList.remove('popup-hidden');
    const rise = Math.sin(((p - POPUP_GATE) / (1 - POPUP_GATE)) * Math.PI / 2), sy = Math.max(.04, rise).toFixed(4);
    els.arch.style.transform = `translate3d(0,14px,10px) rotateX(-68deg) scaleY(${sy})`;
    els.char.style.transform = `translate3d(0,240px,16px) rotateX(-70deg) scaleY(${sy})`;
    els.charShadow.style.opacity = (.28 * rise).toFixed(3); els.charShadow.style.transform = `translate3d(0,244px,2px) scale(${(.72 + .28 * rise).toFixed(3)})`;
    propSlotEl.style.transform = `translate3d(${layout.propX}px,${layout.propY}px,10px)`; els.prop.style.transform = `rotateX(-70deg) scaleY(${sy})`;
    envSlotEl.style.transform = `translate3d(${layout.envX}px,${layout.envY}px,10px)`; els.env.style.transform = `rotateX(-64deg) scaleY(${sy})`;
    requestAnimationFrame(render3DLoop); return;
  }

  const sc = stageScale + (Math.max(.42, stageScale) - stageScale) * (1 - leafEase);
  els.rig.style.transform = `scale(${sc.toFixed(4)}) translate3d(${(-215 * (1 - leafEase)).toFixed(1)}px,${(40 * leafEase).toFixed(1)}px,0) rotateX(${(10 + 38 * leafEase + userTiltX).toFixed(2)}deg) rotateY(${(-4 * (1 - leafEase) + userTiltY).toFixed(2)}deg)`;
  els.shadow.style.width = `${(440 + 420 * leafEase).toFixed(1)}px`; els.shadow.style.transform = `translate3d(${(215 * (1 - leafEase)).toFixed(1)}px,20px,-24px)`;
  const pa = 3.5 * leafEase, la = 179.4 * (1 - leafEase) + pa;
  els.left.style.transform = `translateZ(${(3.2 * (1 - leafEase)).toFixed(2)}px) rotateY(${la.toFixed(2)}deg)`;
  els.right.style.transform = `rotateY(${(-pa).toFixed(2)}deg)`;
  if (p < POPUP_GATE) { popupStageEl.classList.add('popup-hidden'); requestAnimationFrame(render3DLoop); return; }
  popupStageEl.classList.remove('popup-hidden');
  const rise = Math.sin(((p - POPUP_GATE) / (1 - POPUP_GATE)) * Math.PI / 2), sy = Math.max(.04, rise).toFixed(4);
  const rad = pa * Math.PI / 180, sinA = Math.sin(rad), cosA = Math.cos(rad), lRad = la * Math.PI / 180, sinL = Math.sin(lRad), cosL = Math.cos(lRad), ms = Math.max(sinA, sinL);
  const az = layout.archW * .5 * ms + 14, cz = layout.charW * .5 * ms + 18;
  els.arch.style.transform = `translate3d(0,-46px,${az.toFixed(1)}px) rotateX(-68deg) scaleY(${sy})`;
  els.char.style.transform = `translate3d(0,158px,${cz.toFixed(1)}px) rotateX(-70deg) scaleY(${sy})`;
  els.charShadow.style.opacity = (.28 * rise).toFixed(3); els.charShadow.style.transform = `translate3d(0,162px,${(cz - 6).toFixed(1)}px) scale(${(.7 + .3 * rise).toFixed(3)})`;
  propSlotEl.style.transform = `translate3d(${(layout.propX * cosL).toFixed(1)}px,${layout.propY}px,${(-layout.propX * sinL + 10).toFixed(1)}px) rotateY(${la.toFixed(2)}deg)`;
  els.prop.style.transform = `rotateX(-70deg) scaleY(${sy})`;
  envSlotEl.style.transform = `translate3d(${(layout.envX * cosA).toFixed(1)}px,${layout.envY}px,${(layout.envX * sinA + 10).toFixed(1)}px) rotateY(${(-pa).toFixed(2)}deg)`;
  els.env.style.transform = `rotateX(-64deg) scaleY(${sy})`;
  requestAnimationFrame(render3DLoop);
}
requestAnimationFrame(render3DLoop);

let mCtx = null, mGain = null, mRev = null, mTimer = null, mIdx = 0, musicPlaying = false, mComp = null, mOutGain = null;
const MUSIC_MASTER_GAIN = 0.78;
const FREQ = { D4:293.7,E4:329.6,F4:349.2,G4:392,A4:440,Bb4:466.2,B4:493.9,C5:523.3,D5:587.3,E5:659.3,F5:698.5,G5:784,A5:880 };
const ACTIVE_SCORE = isChristmas
  ? [['G4',1],['C5',1,'E4'],['C5',.5],['D5',.5],['C5',.5],['B4',.5],['A4',1,'F4'],['A4',1],['A4',1],['D5',1,'F4'],['D5',.5],['E5',.5],['D5',.5],['C5',.5],['B4',1,'G4'],['G4',1],['G4',1],['E5',1,'G4'],['E5',.5],['F5',.5],['E5',.5],['D5',.5],['C5',1,'A4'],['A4',1],['G4',.5],['G4',.5],['A4',1,'F4'],['D5',1,'G4'],['B4',1,'G4'],['C5',2.8,'E4',1]]
  : [['C5',.75],['C5',.25],['D5',1,'F4'],['C5',1,'A4'],['F5',1,'A4'],['E5',2,'G4'],['C5',.75],['C5',.25],['D5',1,'E4'],['C5',1,'G4'],['G5',1,'Bb4'],['F5',2,'A4'],['C5',.75],['C5',.25],['C5',1,'F4'],['A5',1,'C5'],['F5',1,'A4'],['E5',1,'G4'],['D5',1.6,'F4'],['Bb4',.75],['Bb4',.25],['A5',1,'C5'],['F5',1,'A4'],['G5',1,'Bb4'],['F5',2.8,'A4',1]];
const BEAT_MS = isChristmas ? 420 : 560;

/** 唤醒 Web Audio 并串接防破音限幅器与安全峰值余量 */
function ensureAudioCtx() {
  try {
    if (!mCtx) {
      const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return null;
      mCtx = new AC(); mComp = mCtx.createDynamicsCompressor();
      mComp.threshold.value = -12; mComp.knee.value = 10; mComp.ratio.value = 8; mComp.attack.value = .002; mComp.release.value = .14;
      mOutGain = mCtx.createGain(); mOutGain.gain.value = .84; mComp.connect(mOutGain); mOutGain.connect(mCtx.destination);
      mGain = mCtx.createGain(); mGain.gain.value = MUSIC_MASTER_GAIN; mGain.connect(mComp);
      mRev = mCtx.createGain(); mRev.gain.value = .36;
      const dly = mCtx.createDelay(), fb = mCtx.createGain(), lp = mCtx.createBiquadFilter();
      dly.delayTime.value = .17; fb.gain.value = .28; lp.type = 'lowpass'; lp.frequency.value = 3200;
      mRev.connect(dly); dly.connect(lp); lp.connect(fb); fb.connect(dly); lp.connect(mGain);
      try { const b = mCtx.createBuffer(1,1,mCtx.sampleRate), s = mCtx.createBufferSource(); s.buffer = b; s.connect(mCtx.destination); s.start(0); } catch {}
    }
    if (mCtx.state === 'suspended') mCtx.resume().catch(() => {});
    return mCtx;
  } catch { return null; }
}
/** 拨动三层温暖谐波机械八音盒音符 */
function pluck(f, v) {
  if (!mCtx || !f) return;
  const now = mCtx.currentTime;
  [['sine',1,.78,.007,1.42,1.48,1],['triangle',2,.26,.004,.42,.45,1],['sine',3.01,.15,.003,.11,.13,0]].forEach(([tp,m,a,ak,dc,sp,rv]) => {
    const o = mCtx.createOscillator(), g = mCtx.createGain(); o.type = tp; o.frequency.setValueAtTime(f * m, now);
    g.gain.setValueAtTime(.0001, now); g.gain.linearRampToValueAtTime(a * v, now + ak); g.gain.exponentialRampToValueAtTime(.0001, now + dc);
    o.connect(g); g.connect(mGain); if (rv) g.connect(mRev); o.start(now); o.stop(now + sp);
  });
}
function stepMusic() { if (!musicPlaying) return; const [n,b,h,e] = ACTIVE_SCORE[mIdx]; pluck(FREQ[n],1); if (h) pluck(FREQ[h],.46); mIdx=(mIdx+1)%ACTIVE_SCORE.length; mTimer=setTimeout(stepMusic, b*BEAT_MS+(e?1100:0)); }
function startMusic() { if (musicPlaying) return; const c = ensureAudioCtx(); if (c && mGain) { mGain.gain.setValueAtTime(MUSIC_MASTER_GAIN, c.currentTime); musicPlaying = true; mIdx = 0; clearTimeout(mTimer); stepMusic(); } syncUI(); }
function stopMusic() { musicPlaying = false; clearTimeout(mTimer); if (mCtx && mGain) try { mGain.gain.setTargetAtTime(.0001, mCtx.currentTime, .08); } catch {} syncUI(); }
/** 释放花瓣或雪花飘落粒子 */
function spawnCelebrationParticles() {
  const layer = $('petalsLayer'), cols = isChristmas ? ['#fff','#fdf6e3','#c84b3e','#4f7348','#e8b954'] : [flower,accent,'#e899ab','#f0be59'];
  for (let i = 0; i < 28; i++) {
    const sp = document.createElement('span'), sn = isChristmas && i % 2 === 0, sz = sn ? 5 + (i % 5) : 9 + (i % 6);
    sp.className = sn ? 'ptl sf' : 'ptl';
    sp.style.cssText = `left:${6+Math.random()*88}%;width:${sz}px;height:${sz}px;background:${cols[i%cols.length]};animation-delay:${(Math.random()*.9).toFixed(2)}s;--dx:${Math.round((Math.random()-.5)*115)}px`;
    layer.appendChild(sp); setTimeout(() => sp.remove(), 4800);
  }
}
