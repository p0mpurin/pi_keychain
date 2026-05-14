(() => {
  const canvas = document.getElementById('sketch');
  const statusEl = document.getElementById('draw-status');
  const sendBtn = document.getElementById('send-canvas');
  const clearBtn = document.getElementById('clear-canvas');
  if (!canvas || !sendBtn || !clearBtn) return;

  const panelW = Number(canvas.dataset.panelW || '250');
  const panelH = Number(canvas.dataset.panelH || '122');

  const ctx = canvas.getContext('2d');
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.lineWidth = 4;
  ctx.strokeStyle = '#000';
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  let drawing = false;

  function pos(evt) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const clientX = evt.touches ? evt.touches[0].clientX : evt.clientX;
    const clientY = evt.touches ? evt.touches[0].clientY : evt.clientY;
    return {
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY,
    };
  }

  function down(evt) {
    evt.preventDefault();
    drawing = true;
    const { x, y } = pos(evt);
    ctx.beginPath();
    ctx.moveTo(x, y);
  }

  function move(evt) {
    if (!drawing) return;
    evt.preventDefault();
    const { x, y } = pos(evt);
    ctx.lineTo(x, y);
    ctx.stroke();
  }

  function up(evt) {
    evt.preventDefault();
    drawing = false;
  }

  canvas.addEventListener('mousedown', down);
  canvas.addEventListener('mousemove', move);
  window.addEventListener('mouseup', up);

  canvas.addEventListener('touchstart', down, { passive: false });
  canvas.addEventListener('touchmove', move, { passive: false });
  canvas.addEventListener('touchend', up, { passive: false });

  clearBtn.addEventListener('click', () => {
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.beginPath();
    statusEl.textContent = '';
  });

  sendBtn.addEventListener('click', async () => {
    statusEl.textContent = 'Sending…';
    sendBtn.disabled = true;
    try {
      const exportCanvas = document.createElement('canvas');
      exportCanvas.width = panelW;
      exportCanvas.height = panelH;
      const ex = exportCanvas.getContext('2d');
      ex.fillStyle = '#fff';
      ex.fillRect(0, 0, panelW, panelH);
      ex.drawImage(canvas, 0, 0, panelW, panelH);
      const image = exportCanvas.toDataURL('image/png');

      const res = await fetch('/api/draw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || body.ok === false) {
        statusEl.textContent = body.error || `Failed (${res.status})`;
      } else {
        statusEl.textContent = 'Sent.';
      }
    } catch (e) {
      statusEl.textContent = 'Network error';
    } finally {
      sendBtn.disabled = false;
    }
  });
})();
