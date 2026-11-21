/** @file 立体贺卡核心引擎下篇：翻开前预授权麦克风、宽带吹气检测、长按兜底、刺绣长文滑动与交互 */
const HOLD_MS = 140, BLOW_MS = 860, MIC_TIMEOUT = 5000;
const flameWrapEl = $('flameWrap'), flameHaloEl = flameWrapEl ? flameWrapEl.querySelector('.flh') : null;
let blowing = false, blowProgress = 0, blowHoldTimer = null, blowRaf = null, blowStart = 0, blowOrigin = null, holdDone = null;
let supProp = false, supStage = false, supPropT = null, supStageT = null, wishMsg = '';
let blowBuf = null, blowSrc = null, blowFlt = null, blowGain = null;
let micActive = false, micPending = false, micDenied = false, micGranted = false, micSid = 0, micTried = false, micLevel = 0, openingBusy = false;
let micStream = null, micSrc = null, micGain = null, micAna = null, micMute = null, micRaf = null, micCtx = null;
const liveStreams = new Set();

function getBlowBuf(ctx) {
  if (blowBuf) return blowBuf;
  const n = Math.floor(ctx.sampleRate * 1.5), b = ctx.createBuffer(1, n, ctx.sampleRate), d = b.getChannelData(0);
  for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
  return (blowBuf = b);
}
/** 启动仿真吹风声并统一接入防破音压缩限幅总线 */
function startBlowWindSound() {
  try {
    const ctx = ensureAudioCtx(); if (!ctx) return;
    stopBlowWindSound(false);
    const now = ctx.currentTime, s = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
    s.buffer = getBlowBuf(ctx); s.loop = true; f.type = 'bandpass'; f.frequency.setValueAtTime(420, now); f.Q.setValueAtTime(1.6, now);
    g.gain.setValueAtTime(.0001, now); g.gain.linearRampToValueAtTime(.15, now + .16);
    s.connect(f); f.connect(g); g.connect(mComp || ctx.destination); s.start(now);
    blowSrc = s; blowFlt = f; blowGain = g;
  } catch {}
}
function stopBlowWindSound(puff) {
  try {
    if (mCtx && blowGain && blowSrc) {
      const now = mCtx.currentTime, ps = blowSrc;
      blowGain.gain.cancelScheduledValues(now); blowGain.gain.setValueAtTime(Math.max(.0001, blowGain.gain.value), now);
      blowGain.gain.exponentialRampToValueAtTime(.0001, now + .1); ps.stop(now + .12);
    }
    if (puff && mCtx) {
      const now = mCtx.currentTime, s = mCtx.createBufferSource(), f = mCtx.createBiquadFilter(), g = mCtx.createGain();
      s.buffer = getBlowBuf(mCtx); f.type = 'lowpass'; f.frequency.setValueAtTime(260, now); f.frequency.exponentialRampToValueAtTime(90, now + .09);
      g.gain.setValueAtTime(.09, now); g.gain.exponentialRampToValueAtTime(.0001, now + .09);
      s.connect(f); f.connect(g); g.connect(mComp || mCtx.destination); s.start(now); s.stop(now + .1);
    }
  } catch {}
  blowSrc = blowFlt = blowGain = null;
}
/** 驱动火苗迎风斜倾摇曳 */
function applyFlameWind(p, ms) {
  if (!flameWrapEl || isChristmas) return;
  if (p <= .01) { flameWrapEl.classList.remove('is-blowing'); flameWrapEl.style.transform = flameWrapEl.style.opacity = ''; if (flameHaloEl) flameHaloEl.style.transform = flameHaloEl.style.opacity = ''; return; }
  flameWrapEl.classList.add('is-blowing');
  const sk = 10 + p * 34 + Math.sin(ms * .038) * (4 + p * 5), op = Math.max(.28, 1 - p * .62).toFixed(3);
  flameWrapEl.style.transform = `skewX(${sk.toFixed(1)}deg) scale(${Math.max(.55,1-p*.36).toFixed(3)},${Math.max(.42,1-p*.48).toFixed(3)})`;
  flameWrapEl.style.opacity = op;
  if (flameHaloEl) { flameHaloEl.style.transform = `scale(${Math.max(.45,1-p*.5).toFixed(3)})`; flameHaloEl.style.opacity = op; }
}
function trackStream(st) { if (st) liveStreams.add(st); return st; }
function stopTracks(st) { if (!st) return; liveStreams.delete(st); try { st.getTracks().forEach((t) => { try { t.stop(); } catch {} }); } catch {} }
function stopAllLiveStreams() { Array.from(liveStreams).forEach((st) => stopTracks(st)); liveStreams.clear(); }
/** 停用麦克风并作废在途会话，确保 0 音轨残留 */
function stopMicDetector() {
  micSid += 1; micPending = micActive = false; micLevel = 0;
  if (micRaf) { cancelAnimationFrame(micRaf); micRaf = null; }
  try { if (micSrc) micSrc.disconnect(); if (micGain) micGain.disconnect(); if (micAna) micAna.disconnect(); if (micMute) micMute.disconnect(); } catch {}
  stopTracks(micStream); stopAllLiveStreams();
  if (micCtx && micCtx !== mCtx) micCtx.close().catch(() => {});
  micStream = micSrc = micGain = micAna = micMute = micCtx = null;
  if (musicPlaying && mCtx && mGain) try { mGain.gain.setTargetAtTime(MUSIC_MASTER_GAIN, mCtx.currentTime, .08); } catch {}
  els.micMeterFill.style.width = '4%'; if (!blowing) applyFlameWind(0, 0); syncUI();
}
/** 安全申请麦克风（5 秒超时防卡死 + 拒权不重问 + 迟到自动释放） */
async function requestMicSafe(sid, ms = MIC_TIMEOUT) {
  if (micDenied || !window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return null;
  let tout = false, tmr = null;
  const deny = (e) => ['NotAllowedError','PermissionDeniedError','SecurityError'].includes((e && e.name) || '');
  const ask = async () => {
    try { return await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation:false, noiseSuppression:false, autoGainControl:false, googEchoCancellation:false, googNoiseSuppression:false, googAutoGainControl:false, googHighpassFilter:false } }); }
    catch (e) {
      if (deny(e)) micDenied = true;
      if (!['OverconstrainedError','ConstraintNotSatisfiedError','TypeError'].includes((e && e.name) || '') || tout || sid !== micSid) return null;
      try { return await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e2) { if (deny(e2)) micDenied = true; return null; }
    }
  };
  const p = ask().then((st) => { if (st) micGranted = true; if (tout || sid !== micSid) { stopTracks(st); return null; } return trackStream(st); });
  if (!ms || ms <= 0) return p;
  const res = await Promise.race([p, new Promise((r) => { tmr = setTimeout(() => { tout = true; r(null); }, ms); })]);
  if (tmr) clearTimeout(tmr);
  return res;
}
/** 启动四频带声学吹气检测（含环境基线真实校准、时间步长积分、防高通/偏低频漏灭及抗风扇/道路/音乐/人声干扰） */
async function startMicWithStream(cStream, cCtx) {
  if (cStream) trackStream(cStream);
  if (isChristmas || !isOpen || !candleLit || micActive || micPending) { if (cStream) stopTracks(cStream); return false; }
  const sid = ++micSid; micPending = true;
  const ctx = cCtx || ensureAudioCtx();
  if (!ctx) { if (cStream) stopTracks(cStream); if (sid === micSid) micPending = false; return false; }
  const stream = trackStream(cStream || await requestMicSafe(sid, MIC_TIMEOUT));
  if (!stream || sid !== micSid || !isOpen || !candleLit) { stopTracks(stream); if (sid === micSid) micPending = false; return false; }
  try {
    if (ctx.state === 'suspended') await ctx.resume();
    if (sid !== micSid || !isOpen || !candleLit) { stopTracks(stream); if (sid === micSid) micPending = false; return false; }
    micCtx = ctx; micStream = stream; micSrc = ctx.createMediaStreamSource(stream);
    micGain = ctx.createGain(); micGain.gain.value = 4.5;
    micAna = ctx.createAnalyser(); micAna.fftSize = 1024; micAna.smoothingTimeConstant = .22;
    micMute = ctx.createGain(); micMute.gain.value = 0;
    micSrc.connect(micGain); micGain.connect(micAna); micAna.connect(micMute); micMute.connect(ctx.destination);
    const sr = ctx.sampleRate || 48000, bh = sr / 1024, tb = micAna.frequencyBinCount;
    const ss0 = Math.max(1, Math.floor(50 / bh)), se = Math.min(tb - 1, Math.max(ss0 + 2, Math.ceil(260 / bh)));
    const ls0 = Math.max(2, Math.floor(90 / bh)), le = Math.min(tb - 1, Math.max(ls0 + 6, Math.ceil(650 / bh)));
    const hs0 = Math.max(le + 1, Math.floor(1000 / bh)), he = Math.min(tb - 1, Math.max(hs0 + 10, Math.ceil(3600 / bh)));
    const ms0 = Math.min(he - 4, Math.floor(1500 / bh)), mCnt = Math.max(1, he - ms0 + 1);
    const us0 = Math.min(tb - 6, Math.max(he + 1, Math.floor(4000 / bh))), ue = Math.min(tb - 1, Math.max(us0 + 4, Math.ceil(12000 / bh)));
    const tBuf = new Float32Array(1024), fBuf = new Uint8Array(tb), mArr = new Uint8Array(mCnt), stTs = performance.now();
    let calMs = 0, calDone = false, lastTs = 0, sR = 0, sS = 0, sL = 0, sH = 0, sM = 0, sU = 0;
    let bR = .008, bS = 14, bL = 16, bH = 14, bM = 12, bU = 8, chg = 0;
    /** 计算指定频段均值、覆盖率、频谱平坦度与前 K 峰值能量占比 */
    const bandStats = (lo, hi, floorDrop, floorMin, topK) => {
      const cnt = Math.max(1, hi - lo + 1); let sum = 0, mx = 0;
      for (let i = lo; i <= hi; i++) { const v = fBuf[i]; sum += v; if (v > mx) mx = v; }
      const flr = Math.max(floorMin, mx - floorDrop); let act = 0, totP = 0, sumLogP = 0, p1 = 0, p2 = 0, p3 = 0;
      for (let i = lo; i <= hi; i++) {
        const v = fBuf[i], pw = Math.pow(10, (v - 128) / 36.4);
        if (v >= flr) act++;
        totP += pw; sumLogP += Math.log(pw + 1e-12);
        if (pw >= p1) { p3 = p2; p2 = p1; p1 = pw; } else if (pw >= p2) { p3 = p2; p2 = pw; } else if (pw > p3) { p3 = pw; }
      }
      const pk = topK <= 2 ? (p1 + p2) : (p1 + p2 + p3);
      return { mean: sum / cnt, spread: act / cnt, sfm: totP > 0 ? Math.exp(sumLogP / cnt) / (totP / cnt) : 0, peakRatio: totP > 0 ? pk / totP : 1 };
    };
    micPending = false; micActive = true; syncUI();
    const loop = (now) => {
      if (sid !== micSid || !micActive || !isOpen || !candleLit) return;
      const dt = lastTs ? Math.min(.08, Math.max(.004, (now - lastTs) / 1000)) : .016; lastTs = now;
      micAna.getFloatTimeDomainData(tBuf); micAna.getByteFrequencyData(fBuf);
      if (now - stTs < 240) { micRaf = requestAnimationFrame(loop); return; }
      let sq = 0, mSum = 0;
      for (let i = 0; i < 1024; i++) sq += tBuf[i] * tBuf[i];
      for (let i = ms0; i <= he; i++) { const v = fBuf[i]; mSum += v; mArr[i - ms0] = v; }
      const rms = Math.sqrt(sq / 1024), mMean = mSum / mCnt;
      const mSort = Uint8Array.from(mArr).sort(), mP25 = mSort[Math.floor(mCnt * .25)];
      const S = bandStats(ss0, se, 32, 14, 2), L = bandStats(ls0, le, 32, 16, 2), H = bandStats(hs0, he, 34, 14, 3), M = bandStats(ms0, he, 36, 14, 3), U = bandStats(us0, ue, 34, 14, 3);
      if (!calDone) {
        const instantHiBlow = H.mean >= 90 && (H.mean - S.mean >= 18 || U.mean >= 42) && H.sfm >= .42 && H.peakRatio <= .32 && mMean >= 70;
        const instantLoBlow = L.mean >= 100 && L.sfm >= .28 && L.peakRatio <= .48 && L.spread >= .45 && mMean < 18 && H.mean < 24;
        if (instantHiBlow || instantLoBlow) {
          calDone = true;
        } else {
          calMs += dt * 1000; sR += rms * dt; sS += S.mean * dt; sL += L.mean * dt; sH += H.mean * dt; sM += mP25 * dt; sU += U.mean * dt;
          if (calMs >= 460) {
            const sec = calMs / 1000; calDone = true;
            bR = Math.max(.004, sR / sec); bS = Math.max(8, sS / sec); bL = Math.max(8, sL / sec); bH = Math.max(8, sH / sec); bM = Math.max(0, sM / sec); bU = Math.max(4, sU / sec);
          }
          micRaf = requestAnimationFrame(loop); return;
        }
      }
      const hasClearAir = H.sfm >= .42 && U.mean >= Math.max(36, bU + 22);
      const isFullFlatRumble = !hasClearAir && (S.mean >= H.mean - 4) && (S.mean >= Math.max(24, bS + 14)) && (mMean >= Math.max(22, bM + 10));
      const hClean = H.spread >= .25 && H.peakRatio <= .42 && H.sfm >= .14;
      const hFloor = M.sfm >= .16 && mP25 >= Math.max(46, bM + 24);
      const isHighBlow = !isFullFlatRumble && (hClean || hFloor || hasClearAir) && H.mean >= Math.max(20, bH + 14, bH * 1.38) && rms >= Math.max(.008, bR * 1.45);
      const isLowShape = !isFullFlatRumble && L.sfm >= .28 && L.peakRatio <= .48 && L.spread >= .45 && (L.mean - mMean) >= 24 && mMean < 24 && mP25 < 46;
      const isLowBlow = isLowShape && L.mean >= Math.max(24, bL + 16, bL * 1.45) && rms >= Math.max(.010, bR * 1.50);
      const isWind = isHighBlow || isLowBlow;
      if (isWind) {
        const excessD = isHighBlow ? (H.mean - bH) : (L.mean - bL);
        const ws = Math.min(2.0, Math.max((rms - bR) / Math.max(.008, bR * 1.4), excessD / 24));
        micLevel = Math.min(1, .28 + ws * .62); chg = Math.min(1, chg + dt * (1.26 + Math.min(.44, ws * .26)));
      } else {
        const soft = !isFullFlatRumble && (hClean || hFloor || isLowShape || hasClearAir) && rms >= Math.max(.005, bR * 1.15) && (H.mean >= bH + 7 || L.mean >= bL + 8);
        if (isFullFlatRumble) {
          const al = Math.min(.10, dt * 1.4); bR = bR * (1 - al) + rms * al; bS = bS * (1 - al) + S.mean * al; bL = bL * (1 - al) + L.mean * al; bH = bH * (1 - al) + H.mean * al; bM = bM * (1 - al) + mP25 * al; bU = bU * (1 - al) + U.mean * al;
        } else if (!soft && rms < Math.max(.08, bR * 3.5)) {
          const al = Math.min(.04, dt * .45); bR = bR * (1 - al) + rms * al; bS = bS * (1 - al) + S.mean * al; bL = bL * (1 - al) + L.mean * al; bH = bH * (1 - al) + H.mean * al; bM = bM * (1 - al) + mP25 * al; bU = bU * (1 - al) + U.mean * al;
        }
        micLevel = soft ? Math.max(micLevel * .78, .22) : Math.max(0, micLevel * Math.pow(.08, dt * 3.5));
        chg = Math.max(0, chg - dt * (soft ? .42 : 1.55));
      }
      els.micMeterFill.style.width = `${Math.round(Math.max(4, Math.min(100, (chg * .58 + micLevel * .42) * 100)))}%`;
      if (!blowing) applyFlameWind(Math.min(1, Math.max(chg, micLevel * .88)), now);
      if (chg >= 1) { stopMicDetector(); extinguishCandle(); return; }
      micRaf = requestAnimationFrame(loop);
    };
    micRaf = requestAnimationFrame(loop); return true;
  } catch { stopTracks(stream); if (sid === micSid) stopMicDetector(); return false; }
}
/** 取消长按吹气并复位 */
function cancelHoldBlow(ext = false) {
  clearTimeout(blowHoldTimer); blowHoldTimer = null;
  if (blowRaf) { cancelAnimationFrame(blowRaf); blowRaf = null; }
  const was = blowing; blowing = false; blowProgress = 0; blowOrigin = null;
  if (was || ext) stopBlowWindSound(ext);
  applyFlameWind(0, 0); syncUI();
}
/** 长按约 1 秒仿真吹气 */
function startHoldBlow() {
  blowHoldTimer = null; if (isChristmas || !isOpen || !candleLit || blowing) return;
  blowing = true; blowProgress = 0; blowStart = performance.now(); startBlowWindSound(); syncUI();
  const step = (now) => {
    if (!blowing || !isOpen || !candleLit) return;
    const el = now - blowStart; blowProgress = Math.min(1, el / BLOW_MS);
    applyFlameWind(blowProgress, el);
    if (mCtx && blowFlt) try { blowFlt.frequency.setTargetAtTime(420 + blowProgress * 380, mCtx.currentTime, .04); } catch {}
    if (blowProgress >= 1) { holdDone = blowOrigin; if (blowOrigin === 'btn') supProp = true; else if (blowOrigin === 'cake') supStage = true; cancelHoldBlow(true); extinguishCandle(); return; }
    blowRaf = requestAnimationFrame(step);
  };
  blowRaf = requestAnimationFrame(step);
}
function extinguishCandle() { if (isChristmas || !candleLit) return; candleLit = false; stopMicDetector(); cancelHoldBlow(false); spawnCelebrationParticles(); wishMsg = '蜡烛已吹灭，愿所有温柔与美好如期而至'; syncUI(); setTimeout(() => { wishMsg = ''; syncUI(); }, 4000); }
function toggleCandle() { if (isChristmas) return; if (candleLit) extinguishCandle(); else { candleLit = true; wishMsg = ''; syncUI(); if (isOpen && micTried) startMicWithStream(); } }
function triggerChristmasStarWish() { if (!isChristmas || !isOpen) return; const l = $('treeLightsLayer'); if (!starLightsOn) { starLightsOn = true; l.classList.remove('lights-off'); } l.classList.add('lights-burst'); clearTimeout(starBurstTimer); starBurstTimer = setTimeout(() => l.classList.remove('lights-burst'), 3200); spawnCelebrationParticles(); wishMsg = '圣诞快乐，愿漫天星光与温暖常伴左右'; syncUI(); setTimeout(() => { wishMsg = ''; syncUI(); }, 4000); }

let blessing = JSON.parse(JSON.stringify(cfg.blessing || {}));
try { const sv = localStorage.getItem(STORAGE_KEY); if (sv) blessing = Object.assign(blessing, JSON.parse(sv)); } catch {}
/** 渲染手工毛边棉麻刺绣祝福语并按长度自动启用布内滑动，严禁溢出毛边 */
function renderBlessing() {
  const lc = (blessing.lines || []).length, cc = (blessing.lines || []).reduce((a, s) => a + (s ? s.length : 0), 0);
  const cmp = lc >= 8 || cc >= 92, dns = !cmp && (lc >= 6 || cc >= 64), scr = lc > 8 || cc > 110;
  const card = $('linenCssCard');
  card.classList.toggle('text-compact', cmp); card.classList.toggle('text-dense', dns); card.classList.toggle('text-scroll', scr);
  $('cViewRecipient').textContent = blessing.recipient || '';
  const box = $('cViewLines'); box.innerHTML = '';
  (blessing.lines || []).forEach((t) => { const p = document.createElement('p'); p.textContent = t; box.appendChild(p); });
  $('cViewClosing').textContent = blessing.closing || '';
  $('cViewSig').textContent = blessing.signature || ''; $('cViewSubSig').textContent = blessing.subSignature || '';
  requestAnimationFrame(() => {
    const ov = card.querySelector('.linen-body');
    if (ov) { if (ov.scrollHeight > ov.clientHeight + 2) card.classList.add('text-scroll'); ov.scrollTop = 0; }
  });
}
renderBlessing();

/** 同步底部控制栏、烛火/星灯与顶部极简提示条 */
function syncUI() {
  els.lblOpen.textContent = isOpen ? '合上' : '翻开贺卡';
  els.openControls.style.display = isOpen ? 'inline-flex' : 'none';
  sparklesEl.classList.toggle('show', isOpen);
  $('btnMusic').classList.toggle('music-on', musicPlaying);
  $('lblMusic').textContent = musicPlaying ? '八音盒' : '音乐';
  const bp = $('btnPropAction');
  if (isChristmas) { bp.classList.toggle('star-on', starLightsOn); $('lblPropAction').textContent = '星灯'; }
  else {
    bp.classList.toggle('blowing-on', blowing); $('lblPropAction').textContent = blowing ? '吹气中' : (candleLit ? '吹蜡烛' : '点蜡烛');
    if (flameWrapEl) flameWrapEl.style.display = candleLit ? 'block' : 'none';
    $('smokeWrap').style.display = candleLit ? 'none' : 'block';
  }
  els.btnResetView.style.display = (Math.abs(userTiltX) > 2 || Math.abs(userTiltY) > 2) ? 'inline-flex' : 'none';
  let tip = wishMsg || (openingBusy ? '正在准备吹蜡烛麦克风，请在弹窗中点击允许或跳过' : (!isChristmas && blowing ? '轻轻吹气中，继续按住即可吹灭蜡烛' : (!isChristmas && isOpen && candleLit && micActive ? '对着麦克风轻轻吹气即可吹灭蜡烛' : (!isOpen && !topFold ? (isChristmas ? '轻触封面翻开立体圣诞贺卡' : '轻触封面翻开立体生日贺卡') : ''))));
  els.statusText.textContent = tip; els.statusPill.classList.toggle('hidden', !tip);
  els.statusDot.classList.toggle('blowing', !isChristmas && blowing);
  els.statusDot.classList.toggle('mic-live', !isChristmas && !blowing && (micActive || openingBusy) && !wishMsg);
  els.micMeterTrack.classList.toggle('show', !isChristmas && isOpen && candleLit && micActive && !wishMsg && !blowing);
}
syncUI();

/** 翻开/合上贺卡：首次先预授权再展开，已授权老访客零等待展开并后台重连 */
async function toggleCard() {
  if (openingBusy) return;
  if (isOpen) { isOpen = false; stopMicDetector(); cancelHoldBlow(false); stopMusic(); syncUI(); return; }
  const ctx = ensureAudioCtx();
  const canMic = !isChristmas && candleLit && !micDenied && window.isSecureContext && navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === 'function';
  if (canMic && micGranted) { isOpen = true; startMusic(); syncUI(); startMicWithStream(null, ctx); return; }
  let pre = null;
  if (canMic) {
    openingBusy = true; micTried = true; const ps = ++micSid; syncUI();
    try { pre = await requestMicSafe(ps, MIC_TIMEOUT); } catch { pre = null; } finally { openingBusy = false; }
    if (ps !== micSid) { stopTracks(pre); syncUI(); return; }
  }
  isOpen = true; startMusic();
  if (pre && !isChristmas && candleLit) startMicWithStream(pre, ctx); else if (pre) stopTracks(pre);
  syncUI();
}
function openLetter() { cancelHoldBlow(false); setEd(false); const m = $('letterModal'); m.classList.add('open'); m.scrollTop = 0; }
function hit(el, cx, cy, tp = 14) { const r = el.getBoundingClientRect(); return cx >= r.left - 12 && cx <= r.right + 12 && cy >= r.top - tp && cy <= r.bottom + 12; }
function resetSup(k) { if (k === 'btn') { clearTimeout(supPropT); supPropT = setTimeout(() => { supProp = false; }, 160); } else { clearTimeout(supStageT); supStageT = setTimeout(() => { supStage = false; }, 160); } }

window.addEventListener('pagehide', () => { stopMicDetector(); cancelHoldBlow(false); });
document.addEventListener('visibilitychange', () => { if (document.hidden) cancelHoldBlow(false); });
$('btnToggleOpen').onclick = toggleCard;
$('btnMusic').onclick = () => (musicPlaying ? stopMusic() : startMusic());
$('btnResetView').onclick = () => { userTiltX = userTiltY = 0; syncUI(); };
$('btnLetter').onclick = openLetter;

const btnProp = $('btnPropAction');
btnProp.addEventListener('contextmenu', (e) => e.preventDefault());
btnProp.addEventListener('pointerdown', (e) => { if (isChristmas || (e.pointerType === 'mouse' && e.button !== 0)) return; supProp = false; clearTimeout(supPropT); holdDone = null; if (!isOpen || !candleLit) return; ensureAudioCtx(); blowOrigin = 'btn'; blowHoldTimer = setTimeout(startHoldBlow, HOLD_MS); });
['pointerup','pointercancel','pointerleave'].forEach((ev) => btnProp.addEventListener(ev, () => { if (isChristmas) return; if (holdDone === 'btn') { holdDone = null; supProp = true; resetSup('btn'); return; } if (blowOrigin !== 'btn') return; if (blowing) { supProp = true; resetSup('btn'); } cancelHoldBlow(false); }));
btnProp.addEventListener('click', () => { if (isChristmas) { triggerChristmasStarWish(); return; } if (supProp) { supProp = false; clearTimeout(supPropT); return; } toggleCandle(); });
els.prop.addEventListener('keydown', (e) => { if ((e.key === 'Enter' || e.key === ' ') && isOpen) { e.preventDefault(); if (isChristmas) triggerChristmasStarWish(); else toggleCandle(); } });

const colsEl = document.querySelector('.lcols'), modalEl = $('letterModal');
function setEd(show) { $('editorBox').classList.toggle('show', show); colsEl.classList.toggle('mobile-editing', show); if (show) setTimeout(() => { modalEl.scrollTop = 0; }, 30); }
document.querySelectorAll('#editorBox .ed-input,#editorBox .ed-area').forEach((f) => f.addEventListener('focus', () => setTimeout(() => { try { f.scrollIntoView({ behavior:'smooth', block:'center' }); } catch {} }, 260)));
function updateTip() {
  const el = $('edLineTip'); if (!el) return;
  const lv = ($('inLines').value || '').split('\n').map((s) => s.trim()).filter(Boolean), tc = lv.reduce((a, s) => a + s.length, 0), ov = lv.length > 8 || tc > 110;
  el.textContent = ov ? `当前共 ${lv.length} 行 / ${tc} 字（超出建议的 7 行 / 100 字），保存后将完整保留并在刺绣布内支持上下滑动。` : `当前共 ${lv.length} 行 / ${tc} 字（建议保持 3~7 行、100 字以内，刺绣留白最美观）。`;
  el.classList.toggle('warn', ov);
}
$('inLines').addEventListener('input', updateTip);
$('btnCloseLetter').onclick = () => { modalEl.classList.remove('open'); setEd(false); };
$('btnEditToggle').onclick = () => { const sh = !$('editorBox').classList.contains('show'); if (sh) { $('inRecipient').value = blessing.recipient || ''; $('inLines').value = (blessing.lines || []).join('\n'); $('inClosing').value = blessing.closing || ''; $('inSig').value = blessing.signature || ''; $('inSubSig').value = blessing.subSignature || ''; updateTip(); } setEd(sh); };
$('btnSaveTxt').onclick = () => { blessing = { recipient:$('inRecipient').value.trim(), lines:$('inLines').value.split('\n').map((s)=>s.trim()).filter(Boolean), closing:$('inClosing').value.trim(), signature:$('inSig').value.trim(), subSignature:$('inSubSig').value.trim() }; try { localStorage.setItem(STORAGE_KEY, JSON.stringify(blessing)); } catch {} renderBlessing(); setEd(false); };
$('btnResetTxt').onclick = () => { blessing = JSON.parse(JSON.stringify(cfg.blessing || {})); try { localStorage.removeItem(STORAGE_KEY); } catch {} renderBlessing(); setEd(false); };

const stage = $('stageWrap');
stage.addEventListener('contextmenu', (e) => { if (isOpen && (hit(els.prop, e.clientX, e.clientY, 18) || hit(els.env, e.clientX, e.clientY, 16))) e.preventDefault(); });
stage.addEventListener('pointerdown', (e) => { if (e.pointerType === 'mouse' && e.button !== 0) return; supStage = false; clearTimeout(supStageT); dragging = true; sx = e.clientX; sy = e.clientY; bx = userTiltX; by = userTiltY; moved = 0; stage.classList.add('dragging'); if (!isChristmas && isOpen && candleLit && hit(els.prop, e.clientX, e.clientY, 18)) { ensureAudioCtx(); holdDone = null; blowOrigin = 'cake'; blowHoldTimer = setTimeout(startHoldBlow, HOLD_MS); } });
stage.addEventListener('pointermove', (e) => { if (!dragging) return; const dx = e.clientX - sx, dy = e.clientY - sy; moved = Math.hypot(dx, dy); if (moved >= 10 && blowOrigin === 'cake') cancelHoldBlow(false); const n = window.innerWidth <= 520; userTiltY = Math.max(n ? -14 : -24, Math.min(n ? 14 : 24, by + dx * .13)); userTiltX = Math.max(n ? -10 : -16, Math.min(n ? 12 : 18, bx - dy * .11)); syncUI(); });
['pointerup','pointercancel','pointerleave'].forEach((ev) => stage.addEventListener(ev, () => { dragging = false; stage.classList.remove('dragging'); if (isChristmas) return; if (holdDone === 'cake') { holdDone = null; supStage = true; resetSup('cake'); return; } if (blowOrigin === 'cake') { if (blowing) { supStage = true; resetSup('cake'); } cancelHoldBlow(false); } }));
stage.addEventListener('click', (e) => { if (supStage) { supStage = false; clearTimeout(supStageT); return; } if (moved >= 10) return; if (!isOpen) { toggleCard(); return; } if (hit(els.prop, e.clientX, e.clientY, 18)) { if (isChristmas) triggerChristmasStarWish(); else toggleCandle(); return; } if (hit(els.env, e.clientX, e.clientY, 16)) openLetter(); });

window.__cardDebug = { getState: () => ({ occasion:cfg.occasion||'birthday', fold:cfg.fold||'horizontal', isOpen, openProgress, candleLit, blowing, blowProgress, micActive, micLevel, starLightsOn, musicPlaying, usePhotoLinen, userTiltX, userTiltY, layout:{...layout} }), setTilt:(tx,ty)=>{ userTiltX=tx; userTiltY=ty; syncUI(); }, startMicWithStream, stopMicDetector, startHoldBlow, cancelHoldBlow, extinguishCandle, toggleCandle, triggerChristmasStarWish, openLetter, toggleCard };
