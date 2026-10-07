// Renderer-owned templates. Recipe text, timing evidence and colours are read from 15 at authoring time.
// @@pm-style
function drawBg(t) {
  ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H);
  if (PM.variant === 'poster' || PM.family === 'flow') {
    ctx.strokeStyle = rgba(C.ink, .035); ctx.lineWidth = 1;
    for (let y = 28; y < H; y += 28) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
  }
}
function overlay(t) {}
function hud(t, sc) {}
function transition(sc, lt) {}
// @@/pm-style

// @@pm-common
function pmHeading() {
  T(PM.input.title, 110, 205, { f: FK, w: 800, z: 88, fit: 1660, c: C.strong });
  if (PM.input.subtitle) T(PM.input.subtitle, 114, 285, { f: FK, w: 500, z: PM.family === 'data' ? 64 : 46, fit: 1660, c: C.dim });
}
function pmText(s, x, y, width = 1500, size = 40, color = C.ink, alpha = 1) {
  T(s, x, y, { f: FK, w: 600, z: size, fit: width, c: color, a: alpha });
}
function pmPaper(x, y, w, h, amount = 1) {
  ctx.save(); ctx.globalAlpha = amount;
  ctx.fillStyle = rgba(C.ink, .07); ctx.fillRect(x + 12, y + 16, w, h);
  ctx.fillStyle = C.panel; ctx.fillRect(x, y, w, h);
  ctx.strokeStyle = C.line; ctx.lineWidth = 2; ctx.strokeRect(x, y, w, h);
  ctx.beginPath(); ctx.moveTo(x + w - 34, y); ctx.lineTo(x + w - 34, y + 34); ctx.lineTo(x + w, y + 34);
  ctx.strokeStyle = rgba(C.ink, .18); ctx.stroke(); ctx.restore();
}
function pmPhase(p, i, count) {
  const start = i / (count + 1);
  const arrival = Math.min(1 / (count + 1), PM.arrivalSeconds / PM.input.duration);
  return Math.max(0, Math.min(1, (p - start) / arrival));
}
function pmSource(s) { pmText(s, 114, 924, 1640, 44, C.dim); }
// @@/pm-common

// @@pm-typography
function pmDrawTypography(p, lt, d) {
  pmHeading();
  if (p <= 0) return; // The first-visit poster reserves the centre-left play-button area.
  const v = PM.variant, a = PM.input;
  if (v === 'poster') {
    a.steps.forEach((row, i) => {
      const q = eO(pmPhase(p, i, a.steps.length)), y = 425 + i * 126;
      ctx.fillStyle = rgba(C.acc, .12); ctx.fillRect(106, y - 50, 8 + 1580 * q, 72);
      // Registration is confined to the title of each fact, never its source or body.
      pmText(row.label, 122 + 3 * q, y + 2 * q, 700, 50, C.acc, .18 * q);
      pmText(row.label, 120, y, 700, 50, C.strong, q);
      pmText(row.detail, 880, y, 810, 40, C.ink, q);
    });
    pmSource(a.steps.map(x => x.source).join(' · '));
    return;
  }
  const n = a.phrases.length;
  const closing = v === 'route' ? clamp((p - 2 / 3) * 3) : 0;
  const connect = [];
  a.phrases.forEach((line, i) => {
    const q = pmPhase(p, i, n), eased = eO(q);
    const move = v === 'route' ? clamp(spring(p * a.duration - a.duration * 2 / 3 - i, ...SPRING.snappy)) : 0;
    const x0 = 110 + i * 490 * move, y = 430 + i * 145 + 25 * move;
    const width = 1570 + (700 - 1570) * move, size = 94 + (76 - 94) * move;
    ctx.save(); ctx.beginPath(); ctx.rect(x0 - 10, y - 105, (width + 30) * eased, 125); ctx.clip();
    pmText(line, x0 + (1 - eased) * (v === 'mask' ? 120 : 32), y, width, size, i === n - 1 ? C.acc : C.strong);
    ctx.restore();
    if (v === 'route') {
      const measured = mw(line, FK, 600, size), scale = Math.min(1, width / measured);
      connect.push([x0, y + 38], [x0 + measured * scale, y + 38]);
      if (i < n - 1) {
        const nextMove = clamp(spring(p * a.duration - a.duration * 2 / 3 - i - 1, ...SPRING.snappy));
        const nextX = 110 + (i + 1) * 490 * nextMove, nextY = 430 + (i + 1) * 145 + 25 * nextMove;
        // A shared outer gutter keeps every vertical segment outside every text box.
        connect.push([1810, y + 38], [1810, nextY + 38], [nextX, nextY + 38]);
      }
      const wordAt = line.indexOf(a.verb);
      if (wordAt >= 0) {
        const x = x0 + mw(line.slice(0, wordAt), FK, 600, size) * scale;
        ctx.fillStyle = C.acc; ctx.fillRect(x, y + 19, mw(a.verb, FK, 600, size) * scale * eased, 5);
      }
    }
  });
  if (v === 'route') {
    ctx.strokeStyle = rgba(C.acc, .5); ctx.lineWidth = 5;
    polyPartial(connect, closing > 0 ? 2 / 3 + closing / 3 : p);
    if (closing > 0) pmText(a.verb + ' · 세 문장, 하나의 경로', 114, 878, 1640, 42, C.acc, closing);
  }
  if (v === 'mask') {
    ctx.strokeStyle = rgba(C.acc, .45); ctx.lineWidth = 5;
    polyPartial(a.line_art.map(([x, y]) => [140 + x * 1460, 870 + y * 34]), eO(Math.min(1, p * 2)));
  }
}
// @@/pm-typography

// @@pm-flow
function pmDrawFlow(p, lt, d) {
  pmHeading();
  if (p <= 0) return;
  const a = PM.input, v = PM.variant;
  if (v === 'drawing') {
    const n = a.drawings.length;
    a.drawings.forEach((row, i) => {
      const x = 240 + i * 1450 / Math.max(1, n - 1), q = eO(pmPhase(p, i, n));
      ctx.strokeStyle = C.acc; ctx.lineWidth = 6;
      polyPartial(row.points.map(([u, w]) => [x - 90 + u * 180, 430 + w * 210]), q);
      pmText(row.label, x - 130, 735, 260, 40, C.strong, q);
    });
    a.relations.forEach((row, i) => {
      const x1 = 240 + row.from * 1450 / Math.max(1, n - 1), x2 = 240 + row.to * 1450 / Math.max(1, n - 1);
      ctx.strokeStyle = rgba(C.acc, .4); ctx.lineWidth = 3;
      polyPartial([[x1, 680], [x1, 790 + 40 * i], [x2, 790 + 40 * i], [x2, 680]], eO(Math.max(0, Math.min(1, (p - .4) * 3))));
      pmText(row.label, Math.min(x1, x2), 824 + 40 * i, Math.abs(x2 - x1), 28, C.dim, inv(.45, .75, p));
    });
    return;
  }
  const rows = a.steps, n = rows.length, active = Math.min(n - 1, Math.floor(p * n));
  if (v === 'recursive') {
    rows.forEach((row, i) => {
      const q = eO(pmPhase(p, i, n));
      const x = 460 + i * 150, y = 340 + i * 75, width = 1120 - i * 210;
      pmPaper(x, y, width, 435 - i * 75, q);
      pmText(row.label, x + 30, y + 54, width - 70, 46, C.strong, q);
      if (i === active || p > .98 && i === n - 1) pmText(row.detail, x + 30, y + 145, width - 70, 36, C.ink, q);
    });
    pmSource(a.stop_condition);
    return;
  }
  if (v === 'notes') {
    rows.forEach((row, i) => {
      const q = eO(pmPhase(p, i, n)), x = 210 + i * 1500 / n, y = 370 + (i % 2) * 95;
      const width = Math.min(430, 1410 / n);
      pmPaper(x, y + 40 * (1 - q), width, 350, q);
      pmText(row.label, x + 22, y + 83, width - 44, 46, C.strong, q);
      pmText(row.detail, x + 22, y + 166, width - 44, 36, C.ink, q);
      pmText(row.source, x + 22, y + 287, width - 44, 28, C.dim, q);
    });
    pmSource(a.product + ' · ' + a.verified_result);
    return;
  }
  if (v === 'milestone') {
    const pts = rows.map((_, i) => [230 + i * 1440 / Math.max(1, n - 1), 480 + (i % 2) * 170]);
    ctx.strokeStyle = C.acc; ctx.lineWidth = 5; polyPartial(pts, eO(Math.min(1, p * 1.25)));
    rows.forEach((row, i) => {
      const [x, y] = pts[i], q = eO(pmPhase(p, i, n));
      dot(x, y, 15, C.acc, q);
      pmText(row.date, x - 100, y - 50, 240, 38, C.acc, q);
      pmText(row.label, x - 100, y + 75, 270, 42, C.strong, q);
    });
    pmSource(rows.map(x => x.source).join(' · '));
    return;
  }
  // One ribbon persists through all three phases; labels change only after the previous phase resolves.
  const closing = Math.max(0, (p - 2 / 3) * 3);
  const progress = Math.min(1, p), left = 790, right = 1690, y = 540 - 150 * clamp(spring(closing * a.duration / 3, ...SPRING.snappy)), width = right - left;
  ctx.save(); ctx.fillStyle = C.panel; ctx.strokeStyle = C.line; ctx.lineWidth = 2;
  const ribbonHeight = 150 + 40 * Math.sin(progress * Math.PI), corner = 15 + 30 * progress;
  ctx.beginPath(); ctx.roundRect(left - 65, y - ribbonHeight / 2, width + 130, ribbonHeight, corner); ctx.fill(); ctx.stroke();
  ctx.fillStyle = rgba(C.acc, .12); ctx.beginPath(); ctx.roundRect(left - 65, y - ribbonHeight / 2, (width + 130) * progress, ribbonHeight, corner); ctx.fill();
  ctx.strokeStyle = C.acc; ctx.lineWidth = 5; polyPartial([[left, y], [right, y]], progress);
  rows.forEach((row, i) => {
    const x = left + i * width / Math.max(1, n - 1), q = eO(pmPhase(p, i, n));
    dot(x, y, 10 + 8 * q, C.acc, .25 + .75 * q);
    pmText(row.label, x - 85, y - 43, Math.min(220, width / n), 46, C.strong, .3 + .7 * q);
  });
  ctx.restore();
  if (p < 2 / 3) {
    const local = p * n - Math.floor(p * n);
    const gate = Math.min(clamp(local * a.duration / n / .35), clamp((1 - local) * a.duration / n / .25));
    ctx.save(); ctx.beginPath(); ctx.rect(104, 335, 1700 * gate, 500); ctx.clip();
    pmText(rows[active].label, 114, 435, 610, 88, C.acc);
    pmText(rows[active].detail, 114, 770, 1640, 68);
    ctx.restore();
  } else {
    pmText('완료 이력', 114, 390, 610, 54, C.acc, Math.min(1, closing * 4));
    rows.forEach((row, i) => {
      const q = clamp(spring(closing * a.duration / 3 - 60 / a.bpm - i, ...SPRING.snappy)), y0 = 545 + i * 450 / n;
      pmText(row.label, 114, y0, 410, 60, C.strong, q);
      pmText(row.detail, 570, y0, 1130, 64, C.ink, q);
    });
  }
  if (v === 'decision') {
    pmSource(a.input_source + ' · ' + a.verification_step);
  }
}
// @@/pm-flow

// @@pm-data
function pmDrawData(p, lt, d) {
  pmHeading();
  if (p <= 0) return;
  const a = PM.input;
  if (PM.variant === 'signal') {
    const low = Math.min(...a.signal_data), high = Math.max(...a.signal_data), span = high - low;
    const path = a.signal_data.map((value, i) => [150 + i * 1500 / (a.signal_data.length - 1), 690 - 260 * (value - low) / span]);
    ctx.strokeStyle = C.acc; ctx.lineWidth = 5; polyPartial(path, eO(Math.min(1, p * 1.8)));
    a.steps.forEach((row, i) => {
      const q = eO(pmPhase(Math.max(0, p - .18), i, a.steps.length));
      pmText(row.label, 155 + i * 1480 / a.steps.length, 365, 1430 / a.steps.length, 50, C.strong, q);
      pmText(row.detail, 155 + i * 1480 / a.steps.length, 800, 1430 / a.steps.length, 36, C.ink, q);
    });
    pmSource((a.signal_kind === 'synthetic' ? '합성 신호 · ' : '관측 신호 · ') + a.signal_source);
    return;
  }
  const rows = a.numbers, total = rows.reduce((sum, row) => sum + row.value, 0), n = rows.length;
  const completed = Math.min(n - 1, Math.floor(p * n));
  const landed = rows.slice(0, completed).reduce((sum, row) => sum + row.value, 0);
  const amount = landed + rows[completed].value * eO(Math.max(0, Math.min(1, p * n - completed)));
  const fractional = rows.some(row => !Number.isInteger(row.value));
  const displayAmount = fractional ? Number(amount.toFixed(2)) : Math.round(amount);
  pmText('누적 합계', 114, 389, 610, 48, C.strong);
  pmText(p > .98 ? a.total_display : displayAmount.toLocaleString('en-US'), 110, 610, 620, 220, C.acc);
  pmText(rows[0].unit, 114, 706, 610, 52, C.strong);
  if (p > 2 / 3) pmText('완료 합계: ' + rows.map(row => row.value).join(' + ') + ' = ' + a.total_display, 114, 934, 1640, 72, C.acc, Math.min(1, (p - 2 / 3) * 3));
  const x = 905, top = 350, trackWidth = 760;
  rows.forEach((row, i) => {
    const q = eO(pmPhase(p, i, n)), y = top + i * 535 / n;
    pmText(row.label, x, y, 530, 48, C.strong);
    ctx.fillStyle = C.panel; ctx.fillRect(x, y + 21, trackWidth, 35);
    ctx.fillStyle = C.acc; ctx.fillRect(x, y + 21, trackWidth * row.value / Math.max(1, total) * q, 35);
    pmText(String(row.value) + ' ' + row.unit, x + 565, y, 195, 64, C.ink, q);
  });
  if (p <= 2 / 3) pmSource([...new Set(rows.map(x => x.source))].join(' · '));
}
// @@/pm-data
