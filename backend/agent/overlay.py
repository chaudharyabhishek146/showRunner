"""On-page overlay: a visible cursor and a narration caption.

Playwright moves a real mouse, but the OS cursor is not composited into
screenshots and is invisible on a screen share. Without a pointer the audience
sees things happen with no idea *where* — buttons activate on their own.

So the cursor is drawn into the page itself: a synthetic pointer that glides to
each target, pulses on click, and shows up in every frame because it is DOM,
not chrome. The same overlay carries a caption bar with the current narration,
so the browser view is self-explanatory even when shared on its own.

Everything here is injected via `add_init_script`, so it survives navigation.
"""

from __future__ import annotations

# Installed on every document. Idempotent — re-running it is a no-op.
OVERLAY_INIT_JS = r"""
(() => {
  const NS = '__agentOverlay';
  if (window[NS]) return;

  // `text` and `at` survive a rebuild, so a mid-narration SPA navigation
  // doesn't drop the caption the presenter is talking over.
  const state = { cursor: null, caption: null, spot: null, text: '', at: null };

  function build() {
    // Whatever a hostile page does to us, the demo keeps running: a broken
    // overlay is a cosmetic problem, an exception here would be a dead step.
    try { install(); } catch (e) { /* no overlay on this page */ }
  }

  function install() {
    if (!document.body) return;
    // Not `if (state.ready)`: single-page apps re-render document.body and take
    // our nodes with them. YouTube does this on every in-app navigation, and a
    // build() that trusted a boolean would leave the rest of the demo with no
    // cursor and no captions — the audience watching buttons fire by
    // themselves, which is the exact failure this overlay exists to prevent.
    if (state.cursor && state.cursor.isConnected &&
        state.caption && state.caption.isConnected) return;

    // --- pointer ---------------------------------------------------------
    const cur = document.createElement('div');
    cur.id = '__agent_cursor';
    cur.setAttribute('aria-hidden', 'true');
    cur.style.cssText = [
      'position:fixed', 'left:0', 'top:0', 'width:28px', 'height:28px',
      'z-index:2147483647', 'pointer-events:none', 'will-change:transform',
      'transform:translate3d(-80px,-80px,0)',
      'transition:transform 520ms cubic-bezier(.22,.61,.36,1)',
      'filter:drop-shadow(0 3px 6px rgba(0,0,0,.45))',
    ].join(';');
    // Built node by node rather than with innerHTML: sites that set a Trusted
    // Types CSP (YouTube, Gmail, plenty of enterprise apps) throw on any HTML
    // string assignment, and that exception used to take the whole overlay
    // down — no cursor, no captions, on exactly the products worth demoing.
    const SVG = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('width', '28');
    svg.setAttribute('height', '28');
    svg.setAttribute('viewBox', '0 0 28 28');
    svg.setAttribute('fill', 'none');
    const path = document.createElementNS(SVG, 'path');
    path.setAttribute(
      'd', 'M6 3.5 L6 21.5 L10.6 17.3 L13.6 24 L17 22.4 L14.1 15.9 L20.5 15.6 Z');
    path.setAttribute('fill', '#ffffff');
    path.setAttribute('stroke', '#12151d');
    path.setAttribute('stroke-width', '1.6');
    path.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(path);
    cur.appendChild(svg);
    // Rebuilt cursors resume where the old one was, so the pointer doesn't
    // teleport back to the corner in the middle of a step.
    if (state.at) {
      cur.style.transform =
        'translate3d(' + state.at[0] + 'px,' + state.at[1] + 'px,0)';
    }
    document.body.appendChild(cur);
    state.cursor = cur;

    // --- caption bar -----------------------------------------------------
    const cap = document.createElement('div');
    cap.id = '__agent_caption';
    cap.setAttribute('aria-hidden', 'true');
    cap.style.cssText = [
      'position:fixed', 'left:50%', 'bottom:28px', 'transform:translateX(-50%)',
      'max-width:min(860px,88vw)', 'z-index:2147483646', 'pointer-events:none',
      'background:rgba(11,13,18,.93)', 'color:#e8ecf4',
      'border:1px solid rgba(255,92,0,.55)', 'border-radius:12px',
      'padding:13px 20px', 'font:500 16px/1.5 ui-sans-serif,-apple-system,Segoe UI,sans-serif',
      'box-shadow:0 12px 36px rgba(0,0,0,.5)', 'text-align:center',
      'opacity:0', 'transition:opacity 260ms ease',
    ].join(';');
    cap.textContent = state.text;
    cap.style.opacity = state.text ? '1' : '0';
    document.body.appendChild(cap);
    state.caption = cap;

    // Keyframes for the click pulse. Re-added only if the rebuild lost them.
    if (!document.getElementById('__agent_keyframes')) {
      const style = document.createElement('style');
      style.id = '__agent_keyframes';
      style.textContent =
        '@keyframes __agent_pulse{' +
        '0%{transform:translate3d(-50%,-50%,0) scale(.35);opacity:.95}' +
        '100%{transform:translate3d(-50%,-50%,0) scale(2.6);opacity:0}}';
      document.head.appendChild(style);
    }
  }

  window[NS] = {
    install: build,

    moveTo(x, y) {
      build();
      state.at = [x - 5, y - 3];
      if (state.cursor) {
        state.cursor.style.transform =
          'translate3d(' + state.at[0] + 'px,' + state.at[1] + 'px,0)';
      }
    },

    click(x, y) {
      build();
      const ring = document.createElement('div');
      ring.style.cssText = [
        'position:fixed', 'left:' + x + 'px', 'top:' + y + 'px',
        'width:46px', 'height:46px', 'border-radius:50%',
        'border:3px solid #ff5c00', 'z-index:2147483646',
        'pointer-events:none', 'animation:__agent_pulse 620ms ease-out forwards',
      ].join(';');
      document.body.appendChild(ring);
      setTimeout(() => ring.remove(), 700);
    },

    // A soft spotlight so the audience knows what is about to be used.
    spotlight(x, y, w, h) {
      build();
      // Exactly one thing is highlighted at a time. The timers below normally
      // handle that, but Chrome throttles timers in a backgrounded window, and
      // a demo that accumulates three orange rings has stopped pointing at
      // anything. Retiring the previous box here is not timer-dependent.
      if (state.spot) state.spot.remove();
      const box = document.createElement('div');
      box.style.cssText = [
        'position:fixed', 'left:' + (x - 6) + 'px', 'top:' + (y - 6) + 'px',
        'width:' + (w + 12) + 'px', 'height:' + (h + 12) + 'px',
        'border:2.5px solid #ff5c00', 'border-radius:8px',
        'background:rgba(255,92,0,.10)', 'z-index:2147483645',
        'pointer-events:none', 'transition:opacity 300ms ease',
        // Dims the rest of the page to pull the eye to the target. Kept light
        // on purpose — heavier and the product itself looks washed out.
        'box-shadow:0 0 0 9999px rgba(11,13,18,.14)',
      ].join(';');
      document.body.appendChild(box);
      state.spot = box;
      setTimeout(() => {
        box.style.opacity = '0';
        setTimeout(() => {
          box.remove();
          if (state.spot === box) state.spot = null;
        }, 320);
      }, 1400);
    },

    caption(text) {
      state.text = text || '';
      build();
      if (!state.caption) return;
      state.caption.textContent = state.text;
      state.caption.style.opacity = state.text ? '1' : '0';
    },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }
})();
"""

# `add_init_script` takes a raw script, but `page.evaluate` treats a
# function-shaped string as something to *call* — an IIFE passed straight to it
# evaluates to undefined and then gets invoked. Wrapping it in an arrow keeps
# one source of truth for the overlay while satisfying both call sites.
OVERLAY_EVAL_JS = "() => {\n" + OVERLAY_INIT_JS + "\n}"
