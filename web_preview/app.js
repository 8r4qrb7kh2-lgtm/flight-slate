const REPORT_URL = "../artifacts/feature_pages/final_report.json";
const canvas = document.getElementById("matrix");
const ctx = canvas.getContext("2d");
const pageLabel = document.getElementById("pageLabel");
const statusLabel = document.getElementById("statusLabel");
const analysisLabel = document.getElementById("analysisLabel");
const hoverLabel = document.getElementById("hoverLabel");

const LED_PITCH = 12;
const LED_RADIUS = 4;
const LED_MARGIN = 8;
const CENTER_COLOR = "rgba(94, 225, 255, 0.35)";
const BOUNDS_COLOR = "rgba(255, 209, 102, 0.8)";
const BOARD_BG = "#070b10";

const state = {
  report: null,
  keys: [],
  pageIndex: 0,
  frameIndex: 0,
  showBounds: true,
  showCenter: true,
  image: null,
  pixels: null,
};

function parseBoolParam(value, fallback) {
  if (value == null) {
    return fallback;
  }
  return value !== "0" && value.toLowerCase() !== "false";
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function currentEntries() {
  return state.report[state.keys[state.pageIndex]];
}

function currentEntry() {
  return currentEntries()[state.frameIndex];
}

function imageUrlFor(entry) {
  return new URL(`../${entry.paths.raw}`, window.location.href).href;
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = url;
  });
}

async function loadFrame() {
  const entry = currentEntry();
  const image = await loadImage(imageUrlFor(entry));
  const offscreen = document.createElement("canvas");
  offscreen.width = image.width;
  offscreen.height = image.height;
  const offscreenCtx = offscreen.getContext("2d");
  offscreenCtx.drawImage(image, 0, 0);
  state.image = image;
  state.pixels = offscreenCtx.getImageData(0, 0, image.width, image.height).data;
  render();
}

function pixelOffset(x, y) {
  return (y * 128 + x) * 4;
}

function pixelColor(x, y) {
  const offset = pixelOffset(x, y);
  const data = state.pixels;
  return `rgb(${data[offset]}, ${data[offset + 1]}, ${data[offset + 2]})`;
}

function drawLed(x, y, color) {
  const drawX = LED_MARGIN + x * LED_PITCH + LED_PITCH / 2;
  const drawY = LED_MARGIN + y * LED_PITCH + LED_PITCH / 2;
  ctx.beginPath();
  ctx.arc(drawX, drawY, LED_RADIUS, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
}

function drawOverlays(entry) {
  if (state.showCenter) {
    const centerX = LED_MARGIN + 64 * LED_PITCH;
    const centerY = LED_MARGIN + 32 * LED_PITCH;
    ctx.strokeStyle = CENTER_COLOR;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(centerX, LED_MARGIN);
    ctx.lineTo(centerX, LED_MARGIN + 64 * LED_PITCH);
    ctx.moveTo(LED_MARGIN, centerY);
    ctx.lineTo(LED_MARGIN + 128 * LED_PITCH, centerY);
    ctx.stroke();
  }

  if (state.showBounds) {
    const bounds = entry.analysis.content_bounds;
    if (bounds && bounds.length === 4) {
      const [left, top, right, bottom] = bounds;
      const x = LED_MARGIN + left * LED_PITCH;
      const y = LED_MARGIN + top * LED_PITCH;
      const width = (right - left + 1) * LED_PITCH;
      const height = (bottom - top + 1) * LED_PITCH;
      ctx.strokeStyle = BOUNDS_COLOR;
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, width, height);
    }
  }
}

function updateLabels() {
  const key = state.keys[state.pageIndex];
  const entries = currentEntries();
  const entry = currentEntry();
  pageLabel.textContent = `Page ${state.pageIndex + 1}/${state.keys.length}: ${key} | Frame ${state.frameIndex + 1}/${entries.length}`;
  statusLabel.textContent = `${state.showBounds ? "Bounds on" : "Bounds off"} | ${state.showCenter ? "Center on" : "Center off"}`;
  document.title = `Preview | ${key} | ${state.frameIndex + 1}/${entries.length}`;
  const analysis = entry.analysis;
  const bounds = analysis.content_bounds?.join(", ") ?? "--";
  const unexpected = analysis.unexpected_colors?.length ?? 0;
  analysisLabel.textContent = `bounds: [${bounds}]\nnon-bg pixels: ${analysis.non_background_pixels}\nunexpected colors: ${unexpected}`;
  const params = new URLSearchParams();
  params.set("page", state.keys[state.pageIndex]);
  params.set("frame", String(state.frameIndex));
  params.set("bounds", state.showBounds ? "1" : "0");
  params.set("center", state.showCenter ? "1" : "0");
  history.replaceState(null, "", `?${params.toString()}`);
}

function render() {
  if (!state.pixels) {
    return;
  }

  ctx.fillStyle = BOARD_BG;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  for (let y = 0; y < 64; y += 1) {
    for (let x = 0; x < 128; x += 1) {
      drawLed(x, y, pixelColor(x, y));
    }
  }

  drawOverlays(currentEntry());
  updateLabels();
}

function nextPage(direction) {
  state.pageIndex = (state.pageIndex + direction + state.keys.length) % state.keys.length;
  state.frameIndex = 0;
  loadFrame();
}

function nextFrame(direction) {
  const entries = currentEntries();
  state.frameIndex = (state.frameIndex + direction + entries.length) % entries.length;
  loadFrame();
}

function handleKey(event) {
  switch (event.key) {
    case "ArrowRight":
      nextPage(1);
      event.preventDefault();
      break;
    case "ArrowLeft":
      nextPage(-1);
      event.preventDefault();
      break;
    case "ArrowDown":
      nextFrame(1);
      event.preventDefault();
      break;
    case "ArrowUp":
      nextFrame(-1);
      event.preventDefault();
      break;
    case "b":
    case "B":
      state.showBounds = !state.showBounds;
      render();
      break;
    case "c":
    case "C":
      state.showCenter = !state.showCenter;
      render();
      break;
    default:
      break;
  }
}

function handlePointer(event) {
  if (!state.pixels) {
    return;
  }
  const rect = canvas.getBoundingClientRect();
  const x = Math.floor((event.clientX - rect.left - LED_MARGIN) / LED_PITCH);
  const y = Math.floor((event.clientY - rect.top - LED_MARGIN) / LED_PITCH);
  if (x < 0 || x >= 128 || y < 0 || y >= 64) {
    hoverLabel.textContent = "Pixel: --";
    return;
  }
  const offset = pixelOffset(x, y);
  const data = state.pixels;
  hoverLabel.textContent = `Pixel: (${x}, ${y}) rgb(${data[offset]}, ${data[offset + 1]}, ${data[offset + 2]})`;
}

async function init() {
  const response = await fetch(REPORT_URL);
  state.report = await response.json();
  state.keys = Object.keys(state.report);
  const params = new URLSearchParams(window.location.search);
  const pageKey = params.get("page");
  if (pageKey && state.keys.includes(pageKey)) {
    state.pageIndex = state.keys.indexOf(pageKey);
  }
  state.showBounds = parseBoolParam(params.get("bounds"), true);
  state.showCenter = parseBoolParam(params.get("center"), true);
  state.frameIndex = clamp(Number.parseInt(params.get("frame") || "0", 10) || 0, 0, currentEntries().length - 1);
  window.addEventListener("keydown", handleKey);
  canvas.addEventListener("mousemove", handlePointer);
  await loadFrame();
}

init().catch((error) => {
  pageLabel.textContent = "Failed to load preview";
  statusLabel.textContent = String(error);
});
