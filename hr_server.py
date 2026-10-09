import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from bleak import BleakScanner, BleakClient

HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
PORT = 8765
MAX_POINTS = 1200  # 20 min at ~1/sec

data_lock = threading.Lock()
readings = []  # [{t: ms, bpm: int}, ...]
status = {"connected": False, "device": None, "since": None}

INDEX_HTML = """<!doctype html>
<html lang="is">
<head>
<meta charset="utf-8" />
<title>Púlsöndun</title>
<style>
  :root{
    --bg:#0a0e12; --panel:#11161c; --line:#1d2630; --text:#eef2f5; --muted:#7c8a98;
    --accent:#ff5d6c; --accent-dim:#ff5d6c22; --accent-soft:#ff5d6c55; --good:#3ddc97;
    --in:#5ec8ff; --out:#ff5d6c; --hold:#f5b942;
  }
  *{box-sizing:border-box;}
  body{
    margin:0; background:var(--bg); color:var(--text);
    font-family:'Inter',-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
    min-height:100vh; display:flex; flex-direction:column;
    padding:20px 20px 28px;
  }
  .wrap{max-width:460px; margin:0 auto; width:100%; flex:1; display:flex; flex-direction:column;}
  .top{display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:8px;}
  h1{font-size:13px; font-weight:600; letter-spacing:.06em; color:var(--muted); margin:0; text-transform:uppercase;}
  .status{display:flex; align-items:center; gap:7px; font-size:12px; color:var(--muted);}
  .dot{width:7px; height:7px; border-radius:50%; background:var(--muted); flex-shrink:0;}
  .dot.live{background:var(--good); animation:pulse 1.6s infinite;}
  @keyframes pulse{
    0%{box-shadow:0 0 0 0 rgba(61,220,151,.5);}
    70%{box-shadow:0 0 0 6px rgba(61,220,151,0);}
    100%{box-shadow:0 0 0 0 rgba(61,220,151,0);}
  }

  .stage{
    flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;
    gap:28px; padding:20px 0;
  }
  .ring-wrap{position:relative; width:min(72vw, 280px); height:min(72vw, 280px); display:flex; align-items:center; justify-content:center;}
  .ripple{position:absolute; inset:0; border-radius:50%; border:1px solid var(--accent-soft); opacity:0; pointer-events:none;}
  .ripple.go{animation:ripple .9s ease-out;}
  @keyframes ripple{ 0%{transform:scale(.7); opacity:.8;} 100%{transform:scale(1.25); opacity:0;} }
  .circle{
    width:62%; height:62%; border-radius:50%;
    background:radial-gradient(circle at 32% 28%, #ffffff22, transparent 60%), linear-gradient(145deg, var(--in), var(--out));
    transition:transform 1s cubic-bezier(.4,0,.2,1);
    transform:scale(0.72);
    box-shadow:0 0 60px -10px var(--accent-soft);
    display:flex; align-items:center; justify-content:center;
  }
  .circle .count{font-size:40px; font-weight:700; font-variant-numeric:tabular-nums; color:#fff; text-shadow:0 2px 10px rgba(0,0,0,.25);}

  .phase{font-size:22px; font-weight:700; letter-spacing:.02em; text-align:center; min-height:30px;}
  .phase.in{color:var(--in);}
  .phase.out{color:var(--out);}
  .phase.hold{color:var(--hold);}

  .dots{display:flex; gap:8px;}
  .beatdot{width:9px; height:9px; border-radius:50%; background:var(--line); transition:background .15s, transform .15s;}
  .beatdot.on{background:var(--accent); transform:scale(1.25);}

  .meta{display:flex; align-items:center; gap:6px; font-size:13px; color:var(--muted); font-variant-numeric:tabular-nums;}
  .meta b{color:var(--text); font-weight:600;}

  .panel{
    background:var(--panel); border:1px solid var(--line); border-radius:16px;
    padding:16px 18px; margin-top:auto;
  }
  .row{display:flex; align-items:center; justify-content:space-between; gap:12px; padding:8px 0;}
  .row + .row{border-top:1px solid var(--line);}
  .row label{font-size:13px; color:var(--muted);}
  .stepper{display:flex; align-items:center; gap:10px;}
  .stepper button{
    width:28px; height:28px; border-radius:8px; border:1px solid var(--line); background:#161d25;
    color:var(--text); font-size:16px; cursor:pointer; display:flex; align-items:center; justify-content:center;
  }
  .stepper button:active{transform:scale(.92);}
  .stepper .n{width:22px; text-align:center; font-weight:600; font-variant-numeric:tabular-nums;}
  .pausebtn{
    width:100%; margin-top:4px; padding:11px; border-radius:10px; border:1px solid var(--line);
    background:#161d25; color:var(--text); font-size:14px; font-weight:600; cursor:pointer;
  }
  .chart-card{background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:16px 16px 10px; margin-top:14px;}
  .chart-head{display:flex; justify-content:space-between; font-size:12px; color:var(--muted); margin-bottom:4px;}
  svg#chart{display:block; width:100%; height:150px; overflow:visible;}
  .gridline{stroke:var(--line); stroke-width:1;}
  .glabel{fill:var(--muted); font-size:9px; font-family:inherit;}
  .hrline{fill:none; stroke:var(--accent); stroke-width:2.2; stroke-linejoin:round; stroke-linecap:round;}
  .hrfill{fill:var(--accent-dim); stroke:none;}
  .dotend{fill:var(--accent);}
  @media (max-width:420px){ .circle .count{font-size:32px;} }
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <h1>Púlsöndun · Box breathing</h1>
    <div class="status"><span class="dot" id="dot"></span><span id="statusText">Tengist...</span></div>
  </div>

  <div class="stage">
    <div class="ring-wrap">
      <div class="ripple" id="ripple"></div>
      <div class="circle" id="circle"><span class="count" id="beatCount">–</span></div>
    </div>
    <div class="phase" id="phaseLabel">Tengist úrinu...</div>
    <div class="dots" id="dots"></div>
    <div class="meta"><span id="bpmLabel"><b>--</b> bpm</span></div>
  </div>

  <div class="panel">
    <div class="row">
      <label>Slög á hlið</label>
      <div class="stepper">
        <button id="boxMinus">−</button><span class="n" id="boxN">5</span><button id="boxPlus">+</button>
      </div>
    </div>
    <button class="pausebtn" id="pauseBtn">Gera hlé</button>
  </div>

  <div class="chart-card">
    <div class="chart-head"><span>Hjartsláttur · síðustu 10 mín</span><span id="rangeLabel"></span></div>
    <svg id="chart" viewBox="0 0 680 150" preserveAspectRatio="none"></svg>
  </div>
</div>

<script>
const PHASES = ['in', 'hold1', 'out', 'hold2'];
const PHASE_LABEL = {in:'Andaðu inn', hold1:'Halda', out:'Andaðu út', hold2:'Halda'};
const PHASE_SCALE = {in:'1.0', hold1:'1.0', out:'0.72', hold2:'0.72'};
const PHASE_CLASS = {in:'in', hold1:'hold', out:'out', hold2:'hold'};

let boxBeats = 5;
let phaseIdx = 0;
let beatIdx = 0;
let currentBpm = null;
let running = true;
let beatTimer = null;

const circle = document.getElementById('circle');
const phaseLabel = document.getElementById('phaseLabel');
const beatCountEl = document.getElementById('beatCount');
const dotsEl = document.getElementById('dots');
const bpmLabel = document.getElementById('bpmLabel');
const ripple = document.getElementById('ripple');

function renderDots(){
  dotsEl.innerHTML = '';
  for(let i=0;i<boxBeats;i++){
    const d = document.createElement('div');
    d.className = 'beatdot' + (i < beatIdx ? ' on' : '');
    dotsEl.appendChild(d);
  }
}

function applyPhaseVisual(){
  const phase = PHASES[phaseIdx];
  phaseLabel.textContent = PHASE_LABEL[phase];
  phaseLabel.className = 'phase ' + PHASE_CLASS[phase];
  circle.style.transitionDuration = (boxBeats * beatIntervalMs()) + 'ms';
  circle.style.transform = 'scale(' + PHASE_SCALE[phase] + ')';
  beatCountEl.textContent = beatIdx + '/' + boxBeats;
  renderDots();
}

function beatIntervalMs(){
  const bpm = currentBpm && currentBpm > 25 && currentBpm < 220 ? currentBpm : 60;
  return 60000 / bpm;
}

function tick(){
  if(!running){ beatTimer = setTimeout(tick, 500); return; }
  beatIdx += 1;
  ripple.classList.remove('go'); void ripple.offsetWidth; ripple.classList.add('go');
  beatCountEl.textContent = beatIdx + '/' + boxBeats;
  renderDots();
  if(beatIdx >= boxBeats){
    phaseIdx = (phaseIdx + 1) % PHASES.length;
    beatIdx = 0;
    applyPhaseVisual();
  }
  beatTimer = setTimeout(tick, beatIntervalMs());
}

document.getElementById('boxMinus').onclick = () => { boxBeats = Math.max(2, boxBeats-1); document.getElementById('boxN').textContent = boxBeats; applyPhaseVisual(); };
document.getElementById('boxPlus').onclick  = () => { boxBeats = Math.min(10, boxBeats+1); document.getElementById('boxN').textContent = boxBeats; applyPhaseVisual(); };
document.getElementById('pauseBtn').onclick = (e) => {
  running = !running;
  e.target.textContent = running ? 'Gera hlé' : 'Halda áfram';
};

let started = false;
const WINDOW_MS = 10 * 60 * 1000;

function drawChart(points){
  const svg = document.getElementById('chart');
  const W = 680, H = 150, PAD_L = 30, PAD_R = 6, PAD_T = 10, PAD_B = 14;
  if(points.length < 2){
    svg.innerHTML = '<text x="340" y="75" text-anchor="middle" class="glabel" font-size="12">Vantar gögn...</text>';
    return;
  }
  const now = points[points.length-1].t;
  const tMin = now - WINDOW_MS, tMax = now;
  const visible = points.filter(p => p.t >= tMin);
  const bpms = visible.map(p => p.bpm);
  let yMin = Math.min(...bpms), yMax = Math.max(...bpms);
  if(yMax - yMin < 10){ const mid=(yMax+yMin)/2; yMin = mid-5; yMax = mid+5; }
  yMin -= 4; yMax += 4;

  const x = t => PAD_L + (t - tMin) / (tMax - tMin || 1) * (W - PAD_L - PAD_R);
  const y = v => PAD_T + (1 - (v - yMin) / (yMax - yMin)) * (H - PAD_T - PAD_B);

  let gridHtml = '';
  const ticks = 3;
  for(let i=0;i<=ticks;i++){
    const v = yMin + (yMax-yMin)*i/ticks;
    const yy = y(v);
    gridHtml += `<line x1="${PAD_L}" y1="${yy}" x2="${W-PAD_R}" y2="${yy}" class="gridline"/>`;
    gridHtml += `<text x="2" y="${yy+3}" class="glabel">${Math.round(v)}</text>`;
  }

  let d = `M ${x(visible[0].t)} ${y(visible[0].bpm)}`;
  for(let i=1;i<visible.length;i++) d += ` L ${x(visible[i].t)} ${y(visible[i].bpm)}`;
  const area = d + ` L ${x(visible[visible.length-1].t)} ${H-PAD_B} L ${x(visible[0].t)} ${H-PAD_B} Z`;
  const last = visible[visible.length-1];

  svg.innerHTML = gridHtml +
    `<path d="${area}" class="hrfill"/>` +
    `<path d="${d}" class="hrline"/>` +
    `<circle cx="${x(last.t)}" cy="${y(last.bpm)}" r="3.5" class="dotend"/>`;
}

async function poll(){
  try{
    const res = await fetch('/data', {cache:'no-store'});
    const data = await res.json();
    const dot = document.getElementById('dot');
    const statusText = document.getElementById('statusText');
    if(data.status.connected){
      dot.classList.add('live');
      statusText.textContent = data.status.device || 'Tengt';
    } else {
      dot.classList.remove('live');
      statusText.textContent = 'Aftengt – reyni aftur...';
    }
    const pts = data.readings;
    if(pts.length){
      currentBpm = pts[pts.length-1].bpm;
      bpmLabel.innerHTML = '<b>' + currentBpm + '</b> bpm';
      if(!started){
        started = true;
        applyPhaseVisual();
        tick();
      }
      drawChart(pts);
    }
  } catch(e){
    document.getElementById('statusText').textContent = 'Nær ekki í þjón...';
  }
}

setInterval(poll, 1000);
poll();
</script>
</body>
</html>
"""


def parse_hr(data: bytearray):
    flags = data[0]
    if flags & 0x1:
        return int.from_bytes(data[1:3], byteorder="little")
    return data[1]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        encoded = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, INDEX_HTML)
        elif self.path.startswith("/data"):
            with data_lock:
                payload = {"status": status, "readings": readings[-MAX_POINTS:]}
            self._send(200, json.dumps(payload), "application/json")
        else:
            self._send(404, "not found")

    def log_message(self, fmt, *args):
        pass


def run_http_server():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.serve_forever()


HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"


async def ble_loop():
    while True:
        try:
            print("Skanna fyrir taeki med Heart Rate Service...", flush=True)
            found = await BleakScanner.discover(timeout=10.0, return_adv=True)
            target = None
            for d, adv in found.values():
                uuids = [u.lower() for u in (adv.service_uuids or [])]
                if HR_SERVICE_UUID in uuids:
                    target = d
                    break
                if d.name and "instinct" in d.name.lower():
                    target = d
                    break
            if not target:
                print("Fann ekki urid (" + str(len(found)) + " taeki samtals), reyni aftur...", flush=True)
                await asyncio.sleep(2)
                continue

            def handle_hr(_, data: bytearray):
                bpm = parse_hr(data)
                ts = int(time.time() * 1000)
                with data_lock:
                    readings.append({"t": ts, "bpm": bpm})
                    if len(readings) > MAX_POINTS:
                        del readings[0:len(readings) - MAX_POINTS]

            async with BleakClient(target) as client:
                with data_lock:
                    status["connected"] = True
                    status["device"] = target.name
                    status["since"] = int(time.time() * 1000)
                await client.start_notify(HR_MEASUREMENT_UUID, handle_hr)
                print(f"Tengt vid {target.name}, les hjartslatt...")
                while client.is_connected:
                    await asyncio.sleep(1)
        except Exception as e:
            print(f"Villa: {e}")
        finally:
            with data_lock:
                status["connected"] = False
            await asyncio.sleep(3)


def main():
    t = threading.Thread(target=run_http_server, daemon=True)
    t.start()
    print(f"Opna http://127.0.0.1:{PORT}/ i vafra")
    asyncio.run(ble_loop())


if __name__ == "__main__":
    main()
