from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import sqlite3
import threading
import time
import urllib.request
import urllib.parse

GATEWAY = "http://host.docker.internal:7153/stats.json"
PRIME = "http://172.17.0.1:28916/stats.json"
PUBLIC_STATS = "https://terminuspool.xyz/api/stats"

STATE_DIR = os.environ.get(
    "TERMINUS_STATE_DIR",
    os.path.join(os.path.dirname(__file__), "state")
)
HISTORY_DB = os.path.join(STATE_DIR, "terminus-history.sqlite3")
HISTORY_LOCK = threading.Lock()
HISTORY_RETENTION_SECONDS = 8 * 24 * 60 * 60
COLLECTOR_PATH = os.environ.get(
    "TERMINUS_COLLECTOR_PATH",
    "/api/local-stats"
)
COLLECTOR_ENABLED = os.environ.get(
    "TERMINUS_COLLECTOR_ENABLED",
    "true"
).lower() not in ("0", "false", "no")


def _history_connection():
    os.makedirs(STATE_DIR, exist_ok=True)
    connection = sqlite3.connect(HISTORY_DB, timeout=3)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pool_history (
            minute INTEGER PRIMARY KEY,
            hashrate REAL NOT NULL,
            miners INTEGER NOT NULL,
            connections INTEGER NOT NULL,
            accepted INTEGER NOT NULL,
            rejected INTEGER NOT NULL,
            height INTEGER NOT NULL
        )
        """
    )
    return connection


def record_history(sample):
    minute = int(time.time()) // 60 * 60

    with HISTORY_LOCK:
        with _history_connection() as connection:
            connection.execute(
                """
                INSERT INTO pool_history (
                    minute, hashrate, miners, connections,
                    accepted, rejected, height
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(minute) DO UPDATE SET
                    hashrate=excluded.hashrate,
                    miners=excluded.miners,
                    connections=excluded.connections,
                    accepted=excluded.accepted,
                    rejected=excluded.rejected,
                    height=excluded.height
                """,
                (
                    minute,
                    float(sample.get("hashrate", 0) or 0),
                    int(sample.get("poolMiners", 0) or 0),
                    int(sample.get("connections", 0) or 0),
                    int(sample.get("accepted", 0) or 0),
                    int(sample.get("rejected", 0) or 0),
                    int(sample.get("height", 0) or 0),
                )
            )
            connection.execute(
                "DELETE FROM pool_history WHERE minute < ?",
                (minute - HISTORY_RETENTION_SECONDS,)
            )


def load_history(hours=24, max_points=288):
    cutoff = int(time.time()) - (hours * 60 * 60)

    with HISTORY_LOCK:
        with _history_connection() as connection:
            rows = connection.execute(
                """
                SELECT minute, hashrate, miners, connections,
                       accepted, rejected, height
                FROM pool_history
                WHERE minute >= ?
                ORDER BY minute ASC
                """,
                (cutoff,)
            ).fetchall()

    if len(rows) > max_points:
        stride = max(1, len(rows) // max_points)
        sampled = rows[::stride]
        if sampled[-1] != rows[-1]:
            sampled.append(rows[-1])
        rows = sampled[-max_points:]

    points = [
        {
            "ts": row[0],
            "hashrate": row[1],
            "miners": row[2],
            "connections": row[3],
            "accepted": row[4],
            "rejected": row[5],
            "height": row[6],
        }
        for row in rows
    ]

    values = [point["hashrate"] for point in points]
    summary = {
        "samples": len(points),
        "averageHashrate": (
            sum(values) / len(values) if values else 0
        ),
        "peakHashrate": max(values) if values else 0,
        "lowHashrate": min(values) if values else 0,
    }

    return points, summary


def collect_history_forever():
    # The dashboard API remains the single telemetry reader. This
    # background loop performs one local, read-only GET per minute so
    # durable history continues even when no browser is open.
    time.sleep(5)

    while True:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8080" +
                COLLECTOR_PATH +
                "?collector=1",
                timeout=8
            ) as response:
                response.read()
        except Exception:
            pass

        time.sleep(60)

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TERMINUS POOL // XBT</title>
<meta name="description" content="Terminus Pool is a non-custodial, DATUM-first XBT BLAKE2b mining pool with live telemetry and public DATUM and SV1 access.">
<meta name="theme-color" content="#050912">
<link rel="canonical" href="https://terminuspool.xyz/">
<meta property="og:type" content="website">
<meta property="og:title" content="Terminus Pool // XBT">
<meta property="og:description" content="Non-custodial, DATUM-first XBT BLAKE2b mining with live pool telemetry.">
<meta property="og:url" content="https://terminuspool.xyz/">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="Terminus Pool // XBT">
<meta name="twitter:description" content="Non-custodial, DATUM-first XBT BLAKE2b mining with live pool telemetry.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%23050912'/%3E%3Cpath d='M14 16h36v9H37v25H27V25H14z' fill='%2343f5ff'/%3E%3C/svg%3E">
<style>
:root{
  --bg:#050912;
  --panel:#07111b;
  --panel2:#091823;
  --line:#123747;
  --cyan:#43f5ff;
  --green:#72ffb4;
  --pink:#ff4fb8;
  --purple:#aa72ff;
  --gold:#ffc85c;
  --text:#e7faff;
  --muted:#7895a0;
}
*{box-sizing:border-box}
html{background:var(--bg)}
body{
  margin:0;
  color:var(--text);
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  background:
    linear-gradient(rgba(34,110,130,.045) 1px,transparent 1px),
    linear-gradient(90deg,rgba(34,110,130,.045) 1px,transparent 1px),
    radial-gradient(circle at 50% -10%,#10243b 0,#050912 48%);
  background-size:32px 32px,32px 32px,auto;
}
.shell{max-width:1380px;margin:auto;padding:34px 28px 70px}
header{
  display:flex;justify-content:space-between;align-items:center;
  gap:24px;margin-bottom:22px
}
.brand{display:flex;gap:18px;align-items:center;min-width:0}
.badge{
  width:76px;height:76px;flex:0 0 76px;
  display:grid;place-items:center;
  font-weight:1000;font-size:24px;letter-spacing:2px;
  color:#fff;
  background:linear-gradient(145deg,#102f3d,#07151f);
  border:1px solid #39dce8;
  clip-path:polygon(16% 0,84% 0,100% 16%,100% 84%,84% 100%,16% 100%,0 84%,0 16%);
  box-shadow:0 0 25px #20d9e533
}
.brandText{min-width:0}
h1{
  margin:0;font-size:clamp(26px,4vw,54px);line-height:.98;
  letter-spacing:.06em;font-weight:1000;white-space:nowrap
}
.tagline{
  margin-top:8px;color:var(--green);font-size:14px;
  letter-spacing:.22em;font-weight:800
}
.stackline{
  margin-top:7px;color:#78c9d2;font-size:12px;letter-spacing:.12em
}
.live{
  border:1px solid #1f6873;background:#07131b;
  padding:12px 16px;color:var(--cyan);
  white-space:nowrap;font-size:12px;letter-spacing:.08em
}
.live.bad{color:#ff7890;border-color:#7d2736}

.hero{
  height:390px;position:relative;overflow:hidden;
  border:1px solid #164956;border-radius:10px;
  background:
    radial-gradient(circle at 68% 27%,rgba(198,75,184,.15),transparent 28%),
    linear-gradient(#07101d,#0a1021 48%,#100d26);
  box-shadow:inset 0 0 80px #0009,0 16px 70px #0007
}
.hero:after{
  content:"";position:absolute;inset:0;pointer-events:none;z-index:20;
  background:repeating-linear-gradient(
    0deg,transparent 0,transparent 3px,rgba(89,239,255,.025) 4px
  )
}
.heroText{
  position:absolute;z-index:15;left:34px;top:27px;
  border-left:4px solid var(--cyan);padding-left:17px
}
.kicker{font-size:11px;letter-spacing:.22em;color:#77dbe4;margin-bottom:9px}
.heroTitle{
  font-size:clamp(32px,5vw,58px);font-weight:1000;letter-spacing:.03em
}
.heroSub{
  margin-top:7px;color:var(--green);font-weight:900;
  font-size:14px;letter-spacing:.19em
}
.heroMicro{margin-top:12px;color:#7895a0;font-size:11px;letter-spacing:.12em}

.stars{
  position:absolute;inset:0 0 45% 0;
  background-image:
    radial-gradient(circle,#fff 1px,transparent 1.5px),
    radial-gradient(circle,#9df7ff 1px,transparent 1.7px),
    radial-gradient(circle,#fff 1.4px,transparent 2px);
  background-size:113px 83px,167px 119px,241px 151px;
  background-position:13px 17px,71px 34px,122px 8px;
  opacity:.75
}
.sun{
  position:absolute;z-index:2;width:175px;height:175px;
  left:66%;top:84px;border-radius:50%;
  background:repeating-linear-gradient(
    to bottom,#ffcf6b 0,#ffcf6b 13px,#ff7b9d 14px,#ff4fa9 20px,#341d54 21px,#341d54 24px
  );
  box-shadow:0 0 50px #ff4fa966
}
.mountainBack,.mountainFront{
  position:absolute;left:-3%;width:106%;bottom:92px;z-index:4;
}
.mountainBack{
  height:150px;background:#171738;
  clip-path:polygon(0 81%,9% 58%,17% 69%,29% 34%,40% 65%,53% 28%,64% 70%,77% 42%,88% 65%,100% 38%,100% 100%,0 100%);
  box-shadow:inset 0 2px #4772a255
}
.mountainFront{
  height:125px;bottom:69px;background:#0a1630;
  clip-path:polygon(0 75%,11% 49%,22% 72%,33% 39%,45% 76%,58% 48%,68% 70%,80% 34%,91% 67%,100% 52%,100% 100%,0 100%);
}
.horizon{
  position:absolute;left:0;right:0;bottom:76px;height:2px;z-index:6;
  background:linear-gradient(90deg,transparent,var(--pink),var(--cyan),transparent);
  box-shadow:0 0 22px #48f5ff
}
.road{
  position:absolute;z-index:8;left:22%;right:22%;height:155px;bottom:-18px;
  background:
    linear-gradient(90deg,#1cebd022 1px,transparent 1px) 0 0/12% 100%,
    linear-gradient(#08131c,#030508);
  clip-path:polygon(43% 0,57% 0,100% 100%,0 100%);
  border-top:1px solid #53f5ef88
}
.road:before{
  content:"";position:absolute;left:49.4%;top:8px;width:1.2%;height:145px;
  background:repeating-linear-gradient(to bottom,#affff5 0 13px,transparent 13px 27px);
  transform:perspective(180px) rotateX(29deg);
  transform-origin:top;
  animation:roadRush .8s linear infinite
}
.road:after{
  content:"";position:absolute;inset:0;
  background:linear-gradient(90deg,#00ffe522,transparent 22%,transparent 78%,#00ffe522)
}
.car{
  position:absolute;z-index:12;left:50%;bottom:16px;
  transform:translateX(-50%);
  width:116px;height:41px;
  animation:carCruise 5.8s ease-in-out infinite;
  will-change:transform;
  background:linear-gradient(#182337,#070a11);
  clip-path:polygon(13% 30%,26% 8%,75% 8%,88% 30%,100% 53%,95% 100%,5% 100%,0 53%);
  border-bottom:2px solid #0fe7d8;
  filter:drop-shadow(0 0 9px #ff39b34f)
}
.car:before,.car:after{
  content:"";position:absolute;bottom:10px;width:28px;height:8px;
  background:#ff3ba6;box-shadow:0 0 12px #ff3ba6;
  animation:tailPulse 1.7s ease-in-out infinite
}
.car:before{left:15px}.car:after{right:15px}

@keyframes carCruise{
  0%,100%{
    transform:translateX(-50%) translateX(-7px) translateY(0) rotate(-.3deg)
  }
  25%{
    transform:translateX(-50%) translateX(2px) translateY(-2px) rotate(.1deg)
  }
  50%{
    transform:translateX(-50%) translateX(8px) translateY(0) rotate(.35deg)
  }
  75%{
    transform:translateX(-50%) translateX(1px) translateY(-1px) rotate(0)
  }
}

@keyframes roadRush{
  from{background-position:0 0}
  to{background-position:0 27px}
}

@keyframes tailPulse{
  0%,100%{opacity:.78;filter:brightness(.9)}
  50%{opacity:1;filter:brightness(1.35)}
}

@media(prefers-reduced-motion:reduce){
  .car,.car:before,.car:after,.road:before{
    animation:none !important
  }
}

.sectionTitle{
  display:flex;align-items:center;gap:12px;
  margin:36px 0 15px;color:var(--pink);
  letter-spacing:.22em;font-size:12px;font-weight:900
}
.sectionTitle:before{content:"";width:4px;height:17px;background:var(--green)}
.sectionTitle:after{content:"";height:1px;flex:1;background:linear-gradient(90deg,#5d284c,transparent)}

.accountSearch{
  display:flex;
  gap:10px;
  margin-bottom:10px
}
.accountSearch input{
  flex:1;
  min-width:0;
  padding:14px 16px;
  color:var(--text);
  background:#040a0f;
  border:1px solid #185264;
  outline:none;
  font:inherit
}
.accountSearch input:focus{
  border-color:var(--cyan);
  box-shadow:0 0 16px #43f5ff22
}
.accountSearch button{
  padding:14px 18px;
  border:1px solid #207481;
  background:#09212a;
  color:var(--cyan);
  font:inherit;
  font-weight:900;
  cursor:pointer
}
.accountSearch .clear{
  color:#8aa3ab;
  border-color:#29424a;
  background:#091016
}
.accountHint{
  margin:0 0 14px;
  color:#66858f;
  font-size:10px;
  letter-spacing:.12em
}
.accountHint.good{color:var(--green)}
.accountHint.badText{color:#ff6f8d}

.grid{display:grid;gap:12px}
.grid6{grid-template-columns:repeat(6,1fr)}
.grid5{grid-template-columns:repeat(5,1fr)}
.grid4{grid-template-columns:repeat(4,1fr)}
.card{
  position:relative;min-height:112px;padding:18px;
  border:1px solid #123541;background:linear-gradient(145deg,#08141d,#060c13);
  overflow:hidden
}
.card:before{
  content:"";position:absolute;top:0;left:0;width:38%;height:2px;
  background:var(--green);box-shadow:0 0 11px var(--green)
}
.label{font-size:10px;color:#7795a0;letter-spacing:.13em;text-transform:uppercase}
.value{
  margin-top:12px;font-size:clamp(18px,2vw,28px);font-weight:900;
  word-break:break-word
}
.card.ok .value{color:var(--green);text-shadow:0 0 12px #72ffb433}
.card.bad .value{color:#ff6f8d}
.card.cyan .value{color:var(--cyan)}
.card.purple .value{color:#c28cff}
.card.gold .value{color:var(--gold)}
.card.small .value{font-size:18px}
.card.tiny .value{font-size:13px;line-height:1.5}

.twoCol{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}

.access{
  position:relative;
  border-radius:8px;
}

.access:after{
  content:"";
  position:absolute;
  inset:0;
  pointer-events:none;
  border-radius:8px;
  background:linear-gradient(
    135deg,
    rgba(67,245,255,.035),
    transparent 38%,
    rgba(255,79,184,.025)
  );
}

.accessLabel{
  margin:17px 0 7px;
  color:#678895;
  font-size:9px;
  letter-spacing:.18em;
  font-weight:900;
}

.copyRow{
  position:relative;
  z-index:2;
  display:flex;
  align-items:stretch;
  gap:8px;
}

.copyText{
  flex:1;
  min-width:0;
  padding:11px 12px;
  color:var(--cyan);
  background:#03080d;
  border:1px solid #173f4b;
  font-size:12px;
  line-height:1.45;
  overflow-wrap:anywhere;
}

.copyBtn{
  flex:0 0 auto;
  min-width:76px;
  border:1px solid #287783;
  background:#08202a;
  color:var(--cyan);
  padding:0 13px;
  font:inherit;
  font-size:10px;
  font-weight:1000;
  letter-spacing:.12em;
  cursor:pointer;
  transition:.16s ease;
}

.copyBtn:hover{
  border-color:var(--cyan);
  background:#0b2b36;
  box-shadow:0 0 15px #43f5ff20;
  transform:translateY(-1px)
}

.identityAccess{
  margin-top:14px;
  box-shadow:inset 3px 0 var(--cyan)
}

.identityGrid{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:13px;
  margin-top:15px
}

.identityWide{grid-column:1/-1}

.copyToast{
  position:fixed;
  right:22px;
  bottom:22px;
  z-index:9999;
  padding:12px 16px;
  border:1px solid #2bd9be;
  background:#071713;
  color:var(--green);
  font-size:11px;
  font-weight:1000;
  letter-spacing:.15em;
  opacity:0;
  transform:translateY(12px);
  pointer-events:none;
  transition:.2s ease;
  box-shadow:0 12px 40px #0009
}

.copyToast.show{
  opacity:1;
  transform:translateY(0)
}
.access{
  border:1px solid #164653;background:#07121a;padding:20px;min-height:175px
}
.access.gateway{box-shadow:inset 3px 0 var(--cyan)}
.access.primary{box-shadow:inset 3px 0 var(--green)}
.access.legacy{box-shadow:inset 3px 0 var(--pink)}
.access h3{margin:0 0 7px;font-size:17px}
.access .mode{font-size:10px;letter-spacing:.17em;color:#83dce4;margin-bottom:18px}
.endpoint{
  color:var(--cyan);font-size:15px;padding:10px 12px;
  border:1px solid #16414e;background:#040a0f;overflow-wrap:anywhere
}
.note{margin-top:12px;color:#7895a0;font-size:11px;line-height:1.7}
.note strong{color:#d8f9ff}

.graphCard{
  margin-top:14px;border:1px solid #123541;background:#07111a;padding:18px
}
.historySummary{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:10px;
  margin-top:12px
}
.historyMetric{
  border:1px solid #163c47;
  background:#050d14;
  padding:11px 12px;
  min-width:0
}
.historyMetric .label{
  color:#7895a0;
  font-size:8px;
  letter-spacing:.14em
}
.historyMetric .value{
  margin-top:5px;
  color:var(--cyan);
  font-size:14px;
  font-weight:900
}
.healthMatrix{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:12px
}
.healthItem{
  position:relative;
  min-height:112px;
  border:1px solid #173e49;
  background:linear-gradient(145deg,#07131b,#050b11);
  padding:16px
}
.healthItem:before{
  content:"";
  position:absolute;
  left:0;top:0;bottom:0;
  width:3px;
  background:var(--green)
}
.healthItem.degraded:before{background:var(--gold)}
.healthItem.offline:before{background:#ff5975}
.healthName{
  color:#8eb4be;
  font-size:9px;
  font-weight:900;
  letter-spacing:.14em
}
.healthState{
  margin-top:10px;
  color:var(--green);
  font-size:16px;
  font-weight:1000
}
.healthItem.degraded .healthState{color:var(--gold)}
.healthItem.offline .healthState{color:#ff7890}
.healthDetail{
  margin-top:7px;
  color:#7895a0;
  font-size:9px;
  line-height:1.5
}
.poolHashrateGraph{
  margin-top:0;
  box-shadow:inset 0 0 35px #43f5ff08
}
.graphTop{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:20px;
  margin-bottom:12px
}

.graphStats{
  display:flex;
  align-items:center;
  gap:10px
}

.graphPill{
  padding:7px 9px;
  border:1px solid #23515c;
  background:#061017;
  color:var(--green);
  font-size:9px;
  font-weight:900;
  letter-spacing:.12em
}
.graphTitle{font-size:11px;color:#7795a0;letter-spacing:.16em}
#graphNow{color:var(--cyan);font-weight:900}
svg{
  display:block;
  width:100%;
  height:180px;
  background:
    linear-gradient(rgba(67,245,255,.045) 1px,transparent 1px);
  background-size:100% 25%;
  border-top:1px solid #10303a;
  border-bottom:1px solid #10303a
}
#graphFill{fill:#26dce40d}
#graphLine{fill:none;stroke:#4bf4ff;stroke-width:3;filter:drop-shadow(0 0 4px #4bf4ff)}

.blockBanner{
  display:none;margin-top:16px;padding:15px;text-align:center;
  border:1px solid #7a6024;background:#211807;color:var(--gold);
  font-weight:1000;letter-spacing:.1em
}
footer{
  margin-top:42px;padding-top:20px;border-top:1px solid #11303b;
  color:#486976;font-size:10px;letter-spacing:.12em;text-align:center
}

@media(max-width:1050px){
  .twoCol{grid-template-columns:repeat(2,1fr)}
  .grid6{grid-template-columns:repeat(3,1fr)}
  .grid5{grid-template-columns:repeat(3,1fr)}
  .grid4{grid-template-columns:repeat(2,1fr)}
  .healthMatrix{grid-template-columns:repeat(2,1fr)}
  .hero{height:350px}
}
@media(max-width:760px){
  .shell{padding:20px 14px 45px}
  header{align-items:flex-start}
  .badge{width:58px;height:58px;flex-basis:58px;font-size:18px}
  h1{font-size:clamp(22px,7.2vw,34px)}
  .tagline{font-size:10px}
  .stackline{font-size:9px}
  header .live{display:none}
  .hero{height:330px}
  .heroText{left:22px;top:22px}
  .heroMicro{display:none}
  .twoCol{grid-template-columns:1fr}
}
@media(max-width:600px){
  .copyRow{flex-direction:column}
  .copyBtn{min-height:40px}
  .identityGrid{grid-template-columns:1fr}
  .identityWide{grid-column:auto}
  .graphStats{
    align-items:flex-end;
    flex-direction:column;
    gap:5px
  }
  .historySummary{grid-template-columns:repeat(2,1fr)}
}

@media(max-width:520px){
  .hero{height:300px}
  .heroTitle{font-size:28px}
  .heroSub{font-size:10px}
  .sun{width:105px;height:105px;top:72px;left:65%}
  .mountainBack{
    height:112px;bottom:89px;
    clip-path:polygon(0 78%,10% 58%,23% 68%,36% 49%,49% 69%,62% 52%,76% 70%,89% 55%,100% 66%,100% 100%,0 100%)
  }
  .mountainFront{
    height:95px;bottom:69px;
    clip-path:polygon(0 72%,13% 57%,27% 69%,40% 53%,54% 72%,67% 56%,81% 69%,92% 58%,100% 66%,100% 100%,0 100%)
  }
  .road{left:15%;right:15%;height:129px}
  .car{width:94px;height:34px;bottom:14px}
  .grid6,.grid5,.grid4{grid-template-columns:repeat(2,1fr)}
  .card{min-height:100px;padding:14px}
  .value{font-size:19px}
}

/* TERMINUS_MOON_GRAPH_V3 */

/* --- QUARTER / CRESCENT MOON --- */
.skyMoon{
    width:88px !important;
    height:88px !important;
    right:86px !important;
    top:66px !important;
    overflow:hidden !important;
    background:
        radial-gradient(circle at 28% 32%,
            #ffffff 0%,
            #dff7ff 28%,
            #9ddaff 65%,
            #5a9fe8 100%) !important;
    box-shadow:
        0 0 15px rgba(67,245,255,.42),
        0 0 42px rgba(170,114,255,.22) !important;
}

/* dark lunar shadow = strong quarter/crescent phase */
.skyMoon:before{
    content:"" !important;
    position:absolute !important;
    width:92px !important;
    height:92px !important;
    border-radius:50% !important;
    left:30px !important;
    top:-2px !important;
    background:#07101d !important;
    box-shadow:
        -5px 0 8px rgba(5,9,18,.85),
        -10px 0 18px rgba(5,9,18,.45) !important;
    z-index:3 !important;
}

/* subtle crater texture only on the lit side */
.skyMoon:after{
    content:"" !important;
    position:absolute !important;
    inset:0 !important;
    border-radius:50% !important;
    background:
        radial-gradient(circle at 19px 20px,
            rgba(72,112,150,.18) 0 6px,
            transparent 7px),
        radial-gradient(circle at 27px 45px,
            rgba(72,112,150,.13) 0 5px,
            transparent 6px),
        radial-gradient(circle at 18px 65px,
            rgba(72,112,150,.10) 0 4px,
            transparent 5px) !important;
    z-index:2 !important;
}

/* --- HASHRATE CHART POLISH --- */
.poolHashrateGraph{
    position:relative;
    overflow:hidden;
}

/* animated radar / scanner sweep */
.poolHashrateGraph:after{
    content:"";
    position:absolute;
    top:52px;
    bottom:18px;
    width:120px;
    left:-150px;
    pointer-events:none;
    background:linear-gradient(
        90deg,
        transparent,
        rgba(67,245,255,.035),
        rgba(67,245,255,.12),
        rgba(114,255,180,.07),
        transparent
    );
    filter:blur(3px);
    animation:hashScan 6s linear infinite;
}

@keyframes hashScan{
    from{left:-150px}
    to{left:calc(100% + 150px)}
}

#graphPeakDot{
    filter:drop-shadow(0 0 8px rgba(255,200,92,.85));
}

.graphMetricText{
    font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    font-size:18px;
    font-weight:900;
    letter-spacing:1px;
}

@media(max-width:520px){
    .skyMoon{
        width:58px !important;
        height:58px !important;
        right:22px !important;
        top:54px !important;
    }

    .skyMoon:before{
        width:62px !important;
        height:62px !important;
        left:20px !important;
    }
}


/* TERMINUS_HALFSCREEN_POLISH_V1 */

html,body{
    overflow-x:hidden;
}

body{
    text-wrap:pretty;
}

.shell{
    width:min(100%, 1420px);
    margin-inline:auto;
}

header,
.hero,
[class*="hero"],
[class*="topbar"],
[class*="topBar"]{
    min-width:0;
}

.card,
.graphCard,
.poolHashrateGraph,
.heroPanel,
.heroCard,
.panel,
.copyCard,
.infoCard,
.endpointCard,
.v3AccessCard,
.accountCard,
.lookupCard,
.searchCard{
    min-width:0;
}

.card *,
.graphCard *,
.poolHashrateGraph *,
.heroPanel *,
.heroCard *{
    min-width:0;
}

button,
.copyBtn,
.actionBtn,
.lookupBtn,
.clearBtn{
    white-space:nowrap;
}

input,
button,
textarea,
select{
    max-width:100%;
}

svg{
    max-width:100%;
}

/* clean chart shell */
.poolHashrateGraph,
.graphCard{
    overflow:hidden;
}

/* more graceful default wrapping */
#telemetry,
#miner,
#network,
#window,
#sv1,
#access{
    min-width:0;
}

#telemetry > *,
#miner > *,
#network > *,
#window > *,
#sv1 > *,
#access > *{
    min-width:0;
}

/* ---------------------------------
   HALF SCREEN / SNAPPED DESKTOP
---------------------------------- */
@media (max-width: 1280px){

    .shell{
        max-width:none;
        padding:22px 18px 44px !important;
    }

    header{
        display:grid !important;
        grid-template-columns:minmax(0,1fr) auto !important;
        gap:14px !important;
        align-items:start !important;
        margin-bottom:18px !important;
    }

    header > *{
        min-width:0;
    }

    h1{
        font-size:clamp(30px, 4vw, 54px) !important;
        line-height:1.02 !important;
        letter-spacing:2px !important;
    }

    .heroTitle{
        font-size:clamp(40px, 5vw, 68px) !important;
        line-height:.96 !important;
        letter-spacing:2px !important;
    }

    .heroCard,
    .heroPanel,
    .panel,
    .graphCard,
    .poolHashrateGraph{
        border-radius:16px !important;
    }

    .heroCard,
    .heroPanel{
        padding:18px !important;
    }

    .heroArt,
    .heroScene,
    .heroCanvas,
    .heroGraphic{
        min-height:320px !important;
        height:320px !important;
    }

    .sectionTitle{
        font-size:14px !important;
        letter-spacing:4px !important;
        gap:10px !important;
        margin:28px 0 12px !important;
    }

    .card{
        padding:16px 16px 15px !important;
    }

    .poolHashrateGraph,
    .graphCard{
        min-height:300px !important;
    }

    /* telemetry-style grids become 2 columns cleanly */
    #telemetry,
    #miner,
    #network,
    #window,
    #sv1,
    #access{
        display:grid !important;
        grid-template-columns:repeat(2, minmax(0, 1fr)) !important;
        gap:14px !important;
    }

    /* search rows / action bars wrap better */
    .accountSearch,
    .searchRow,
    .lookupRow,
    .actionRow,
    .copyRow,
    .endpointRow{
        display:grid !important;
        grid-template-columns:minmax(0,1fr) auto auto !important;
        gap:10px !important;
        align-items:stretch !important;
    }

    .accountSearch input,
    .searchRow input,
    .lookupRow input{
        width:100% !important;
        min-width:0 !important;
    }

    .live,
    .statusPill,
    .livePill{
        justify-self:end;
        max-width:100%;
    }
}

/* ---------------------------------
   TIGHT HALF SCREEN / SMALL LAPTOP
---------------------------------- */
@media (max-width: 1080px){

    .shell{
        padding:18px 14px 36px !important;
    }

    header{
        grid-template-columns:1fr !important;
        gap:12px !important;
    }

    .live,
    .statusPill,
    .livePill{
        justify-self:start !important;
        width:100%;
    }

    .heroCard,
    .heroPanel{
        padding:16px !important;
    }

    .heroArt,
    .heroScene,
    .heroCanvas,
    .heroGraphic{
        min-height:280px !important;
        height:280px !important;
    }

    .heroTitle{
        font-size:clamp(34px, 6vw, 54px) !important;
    }

    #telemetry,
    #network,
    #window,
    #sv1,
    #access{
        grid-template-columns:repeat(2, minmax(0, 1fr)) !important;
    }

    #miner{
        grid-template-columns:repeat(2, minmax(0, 1fr)) !important;
    }

    .accountSearch,
    .searchRow,
    .lookupRow,
    .actionRow,
    .copyRow,
    .endpointRow{
        grid-template-columns:1fr 1fr !important;
    }

    .accountSearch input,
    .searchRow input,
    .lookupRow input{
        grid-column:1 / -1 !important;
    }

    .poolHashrateGraph,
    .graphCard{
        min-height:280px !important;
    }
}

/* ---------------------------------
   LARGE TABLET / VERY TIGHT SPLIT
---------------------------------- */
@media (max-width: 820px){

    #telemetry,
    #miner,
    #network,
    #window,
    #sv1,
    #access{
        grid-template-columns:1fr !important;
    }

    .accountSearch,
    .searchRow,
    .lookupRow,
    .actionRow,
    .copyRow,
    .endpointRow{
        grid-template-columns:1fr !important;
    }

    .heroArt,
    .heroScene,
    .heroCanvas,
    .heroGraphic{
        min-height:240px !important;
        height:240px !important;
    }

    .poolHashrateGraph,
    .graphCard{
        min-height:250px !important;
    }

    .sectionTitle{
        margin-top:24px !important;
    }
}


/* TERMINUS_FINAL_HALFSCREEN_POLISH */

/* slightly richer app background */
body{
    background:
        radial-gradient(circle at 50% -10%,
            rgba(24,67,95,.20),
            transparent 42%),
        #050912 !important;
}

/* premium card edges */
.card,
.graphCard,
.poolHashrateGraph,
.access{
    box-shadow:
        inset 0 1px 0 rgba(67,245,255,.04),
        0 8px 30px rgba(0,0,0,.16);
}

/* section titles tighten up */
.sectionTitle{
    font-weight:1000 !important;
    text-shadow:0 0 14px rgba(255,79,184,.12);
}

/* hero gets a subtle internal frame */
.hero{
    box-shadow:
        inset 0 0 0 1px rgba(67,245,255,.025),
        inset 0 -80px 100px rgba(0,0,0,.20),
        0 16px 50px rgba(0,0,0,.25) !important;
}

/* quarter moon separation from sun */
.skyMoon{
    right:128px !important;
    top:50px !important;
    z-index:6 !important;
}

.skyMoonGlow{
    right:108px !important;
    top:34px !important;
}

/* hero typography */
.heroText{
    max-width:58% !important;
}

.heroTitle{
    text-shadow:
        0 0 18px rgba(231,250,255,.08);
}

.heroSub{
    text-shadow:
        0 0 12px rgba(114,255,180,.12);
}

/* graph presentation */
.poolHashrateGraph{
    border-color:#174653 !important;
    background:
        linear-gradient(
            180deg,
            rgba(7,20,29,.98),
            rgba(4,11,17,.98)
        ) !important;
}

.graphTop{
    padding-bottom:12px;
    border-bottom:1px solid rgba(67,245,255,.12);
}

.graphTitle{
    color:#72a9b5 !important;
    font-weight:900 !important;
    letter-spacing:.16em !important;
}

#graphNow{
    font-size:18px !important;
    color:var(--cyan) !important;
    text-shadow:0 0 14px rgba(67,245,255,.22);
}

.graphPill{
    border-color:#1a6770 !important;
    color:var(--green) !important;
    background:#061218 !important;
    box-shadow:inset 0 0 14px rgba(114,255,180,.04);
}

/* half screen sweet spot */
@media (min-width:821px) and (max-width:1080px){

    .shell{
        padding-top:18px !important;
    }

    header{
        grid-template-columns:auto minmax(0,1fr) !important;
        align-items:center !important;
        column-gap:14px !important;
        row-gap:10px !important;
    }

    .brand{
        grid-column:1 / -1;
        gap:14px !important;
    }

    .badge{
        width:70px !important;
        height:70px !important;
        flex-basis:70px !important;
    }

    .live{
        grid-column:1 / -1;
        width:auto !important;
        min-width:0 !important;
        padding:10px 14px !important;
        font-size:11px !important;
    }

    h1{
        font-size:clamp(30px,4.5vw,44px) !important;
    }

    .tagline{
        margin-top:6px !important;
    }

    .stackline{
        margin-top:5px !important;
        line-height:1.45 !important;
    }

    .hero{
        height:374px !important;
    }

    .heroText{
        left:36px !important;
        top:30px !important;
        max-width:62% !important;
    }

    .heroTitle{
        font-size:clamp(38px,5.5vw,56px) !important;
    }

    .sun{
        right:auto !important;
        left:66% !important;
    }

    .poolHashrateGraph{
        min-height:265px !important;
    }

    .graphTop{
        gap:12px !important;
    }
}

/* very narrow desktop / tablet */
@media (max-width:820px){

    .skyMoon{
        right:82px !important;
        top:48px !important;
    }

    .heroText{
        max-width:70% !important;
    }

    .heroTitle{
        font-size:36px !important;
    }

    .graphTop{
        align-items:flex-start !important;
        flex-direction:column !important;
    }

    .graphStats{
        width:100%;
        flex-direction:row !important;
        justify-content:space-between;
        align-items:center !important;
    }
}

/* phone */
@media (max-width:520px){

    .skyMoon{
        right:52px !important;
        top:50px !important;
    }

    .heroText{
        max-width:78% !important;
    }

    .heroTitle{
        font-size:28px !important;
    }
}


/* TERMINUS_PIGGY_MINER_STATS_V1 */

.piggyLabel {
    display:inline-flex;
    align-items:center;
    gap:7px;
}

.piggyIcon {
    display:inline-block;
    width:25px;
    height:25px;
    flex:0 0 25px;
    vertical-align:middle;

    background:
        url("data:image/webp;base64,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")
        center/contain no-repeat;

    filter:
        drop-shadow(0 0 5px rgba(67,245,255,.35))
        drop-shadow(0 0 8px rgba(255,79,184,.20));
}

@media(max-width:760px) {
    .piggyIcon {
        width:22px;
        height:22px;
        flex-basis:22px;
    }
}


/* TERMINUS_XBT_PIG_BRAND_V1 */

.badge.piggyBrand {
    width:82px !important;
    height:82px !important;
    flex:0 0 82px !important;
    padding:0 !important;

    border-radius:18px !important;
    clip-path:none !important;

    border:1px solid rgba(67,245,255,.58) !important;

    background:
        #020813
        url("data:image/webp;base64,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")
        center/cover no-repeat !important;

    box-shadow:
        0 0 0 1px rgba(67,245,255,.08),
        0 0 22px rgba(67,245,255,.13),
        0 0 32px rgba(255,79,184,.07),
        inset 0 0 18px rgba(0,0,0,.25) !important;

    color:transparent !important;
    text-indent:-9999px !important;
    overflow:hidden !important;
}

.badge.piggyBrand:before,
.badge.piggyBrand:after {
    display:none !important;
}

@media(max-width:760px) {
    .badge.piggyBrand {
        width:62px !important;
        height:62px !important;
        flex-basis:62px !important;
        border-radius:14px !important;
    }
}

@media(max-width:520px) {
    .badge.piggyBrand {
        width:56px !important;
        height:56px !important;
        flex-basis:56px !important;
        border-radius:13px !important;
    }
}


/* TERMINUS_GRAND_OPENING_PROMO */
.launchPromo{
    margin:18px 0 26px;
    padding:20px 22px;
    border:1px solid rgba(67,245,255,.30);
    border-radius:14px;
    background:
        linear-gradient(135deg,
            rgba(8,24,34,.98),
            rgba(10,18,31,.98));
    box-shadow:
        inset 0 1px 0 rgba(114,255,180,.05),
        0 0 30px rgba(67,245,255,.05),
        0 14px 40px rgba(0,0,0,.22);
    display:grid;
    grid-template-columns:minmax(0,1.35fr) minmax(300px,.65fr);
    gap:24px;
    align-items:center;
    overflow:hidden;
    position:relative;
}

.launchPromo:before{
    content:"";
    position:absolute;
    inset:0;
    pointer-events:none;
    background:
        linear-gradient(90deg,
            rgba(67,245,255,.04),
            transparent 35%,
            rgba(255,79,184,.035));
}

.launchPromoCopy,
.launchPromoClock{
    position:relative;
    z-index:1;
}

.launchPromoKicker{
    color:#72ffb4;
    font-size:10px;
    font-weight:900;
    letter-spacing:.18em;
    margin-bottom:7px;
}

.launchPromoTitle{
    color:#43f5ff;
    font-size:28px;
    line-height:1;
    font-weight:1000;
    letter-spacing:.05em;
    text-shadow:0 0 18px rgba(67,245,255,.18);
}

.launchPromoText{
    margin-top:10px;
    color:#d7edf3;
    font-size:13px;
    line-height:1.55;
    max-width:720px;
}

.launchPromoMeta{
    margin-top:9px;
    color:#8daab4;
    font-size:10px;
    font-weight:900;
    letter-spacing:.11em;
}

.launchPromoClock{
    border-left:1px solid rgba(67,245,255,.14);
    padding-left:24px;
}

.launchPromoClockLabel{
    color:#7895a0;
    font-size:9px;
    font-weight:900;
    letter-spacing:.16em;
    margin-bottom:10px;
}

.promoCountdown{
    display:grid;
    grid-template-columns:repeat(4,1fr);
    gap:7px;
}

.promoUnit{
    min-width:0;
    padding:10px 5px 9px;
    text-align:center;
    background:#060d15;
    border:1px solid rgba(67,245,255,.16);
    border-radius:9px;
}

.promoNumber{
    display:block;
    color:#e7faff;
    font-size:22px;
    font-weight:1000;
    line-height:1;
    font-variant-numeric:tabular-nums;
}

.promoLabel{
    display:block;
    margin-top:6px;
    color:#657f89;
    font-size:8px;
    font-weight:900;
    letter-spacing:.10em;
}

@media(max-width:760px){
    .launchPromo{
        grid-template-columns:1fr;
        gap:16px;
        padding:17px;
    }

    .launchPromoClock{
        border-left:0;
        border-top:1px solid rgba(67,245,255,.14);
        padding-left:0;
        padding-top:16px;
    }

    .launchPromoTitle{
        font-size:24px;
    }
}

/* TERMINUS_UX_V1 */
html{scroll-behavior:smooth}
body{overflow-x:hidden}
a{color:inherit}
a:focus-visible,button:focus-visible,input:focus-visible{
    outline:2px solid var(--gold);
    outline-offset:3px;
}
.skipLink{
    position:fixed;
    left:14px;
    top:14px;
    z-index:1000;
    transform:translateY(-180%);
    padding:11px 14px;
    border:1px solid var(--cyan);
    background:#02070d;
    color:var(--cyan);
    font-weight:900;
    text-decoration:none;
}
.skipLink:focus{transform:translateY(0)}
.topNav{
    display:flex;
    flex-wrap:wrap;
    gap:8px;
    margin:-6px 0 18px;
}
.topNav a,.heroActions a{
    display:inline-flex;
    align-items:center;
    justify-content:center;
    min-height:44px;
    padding:10px 14px;
    border:1px solid #1d6571;
    background:#07151f;
    color:#a7dce3;
    font-size:10px;
    font-weight:900;
    letter-spacing:.12em;
    text-decoration:none;
}
.topNav a:first-child,.heroActions .primaryAction{
    border-color:var(--green);
    background:linear-gradient(135deg,#0a2c29,#071b22);
    color:var(--green);
    box-shadow:0 0 20px #72ffb414;
}
.heroActions{
    display:flex;
    flex-wrap:wrap;
    gap:8px;
    margin-top:18px;
}
.quickConnect{
    margin:18px 0 28px;
    padding:20px 22px;
    border:1px solid rgba(114,255,180,.38);
    border-radius:14px;
    background:linear-gradient(135deg,rgba(7,25,29,.98),rgba(9,18,31,.98));
    box-shadow:0 14px 40px rgba(0,0,0,.24);
}
.quickConnectHead{
    display:flex;
    justify-content:space-between;
    align-items:flex-end;
    gap:18px;
    margin-bottom:14px;
}
.quickConnectHead h2{
    margin:0;
    color:var(--green);
    font-size:22px;
    letter-spacing:.08em;
}
.quickConnectHead p{
    margin:5px 0 0;
    color:#8aacb6;
    font-size:11px;
    line-height:1.55;
}
.quickConnectHead a{
    color:var(--cyan);
    font-size:10px;
    font-weight:900;
    letter-spacing:.1em;
    white-space:nowrap;
}
.quickConnectGrid{
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:12px;
}
.quickEndpoint{
    min-width:0;
    padding:15px;
    border:1px solid #164651;
    background:#050d14;
}
.quickEndpoint.recommended{border-left:4px solid var(--green)}
.quickEndpoint.gateway{border-left:4px solid var(--cyan)}
.quickEndpoint.legacy{border-left:4px solid var(--pink)}
.quickLabel{
    color:#7a9ba5;
    font-size:9px;
    font-weight:900;
    letter-spacing:.16em;
}
.quickValue{
    margin:8px 0 11px;
    color:var(--cyan);
    font-size:13px;
    overflow-wrap:anywhere;
}
.quickEndpoint .copyBtn{
    width:100%;
    min-height:44px;
}
.quickNote{
    margin-top:10px;
    color:#819ca5;
    font-size:10px;
    line-height:1.55;
}
.accountHint{min-height:20px}
.copyToast[aria-live]{pointer-events:none}

.versionBadge{
    display:inline-block;
    margin-top:7px;
    padding:4px 8px;
    border:1px solid rgba(67,245,255,.32);
    border-radius:4px;
    background:rgba(4,18,26,.72);
    color:var(--cyan);
    font-size:9px;
    font-weight:900;
    letter-spacing:.14em;
    box-shadow:0 0 12px rgba(67,245,255,.08);
}

@media(max-width:760px){
    header{gap:12px}
    .brand{gap:12px;align-items:flex-start}
    .brandText{overflow:hidden}
    h1{
        white-space:normal;
        overflow-wrap:anywhere;
        font-size:clamp(23px,8vw,31px);
        line-height:1.04;
    }
    .topNav{margin-top:-2px}
    .topNav a{flex:1 1 30%;padding-inline:8px}
    .heroText{right:18px}
    .heroActions{margin-top:14px}
    .heroActions a{padding:9px 11px}
    .quickConnect{padding:17px}
    .quickConnectHead{align-items:flex-start;flex-direction:column}
    .quickConnectGrid{grid-template-columns:1fr}
    .copyBtn{min-height:44px}
}

@media(max-width:430px){
    .topNav a{flex-basis:100%}
    .heroActions a{flex:1 1 100%}
    .heroTitle{font-size:26px}
    .kicker{font-size:9px}
}

/* TERMINUS_MOBILE_DECLUTTER_V1 */
@media(max-width:760px){
    .topNav{display:none}
    header{margin-bottom:14px}
    .badge{width:52px;height:52px;flex-basis:52px}
    .tagline{margin-top:6px}
    .stackline{margin-top:5px}
    .hero{height:285px}
    .heroActions{display:none}
}

@media(max-width:430px){
    .shell{padding-top:14px}
    header{gap:9px}
    .brand{gap:10px}
    h1{font-size:clamp(21px,7.6vw,28px)}
    .hero{height:270px}
    .heroText{left:18px;right:18px;top:20px}
}
</style>
</head>
<body>
<a class="skipLink" href="#mainContent">SKIP TO MAIN CONTENT</a>
<div id="copyToast" class="copyToast" role="status" aria-live="polite">COPIED TO CLIPBOARD</div>

<div class="shell">

<header>
  <div class="brand">
    <div class="badge piggyBrand" title="Terminus Pool // XBT" aria-label="Terminus Pool XBT Piggybank">XBT</div>
    <div class="brandText">
      <h1>TERMINUS POOL // XBT</h1>
      <div class="tagline">THE LAST WORD IN MINING</div>
      <div class="stackline">RATUM PRIME // GATEWAY // BLAKE2B NODE LINK</div>
      <div class="versionBadge">TERMINUSPOOL v0.2.10</div>
    </div>
  </div>
  <div id="live" class="live">● NODE LINK ACTIVE</div>
</header>

<nav class="topNav" aria-label="Primary navigation">
  <a href="#startMining">START MINING</a>
  <a href="#poolStats">LIVE STATS</a>
  <a href="#minerAccounting">MINER LOOKUP</a>
</nav>

<main id="mainContent">
<section class="hero" aria-labelledby="heroTitle">
  <div class="stars"></div>
  <div class="sun"></div>
  <div class="mountainBack"></div>
  <div class="mountainFront"></div>
  <div class="horizon"></div>
  <div class="road"></div>
  <div class="car"></div>

  <div class="heroText">
    <div class="kicker">NEON HIGHWAY // MIDNIGHT RUN</div>
    <div class="heroTitle" id="heroTitle">TERMINUS POOL</div>
    <div class="heroSub">THE LAST WORD IN MINING</div>
    <div class="heroMicro">DATUM-FIRST // CYBER MOUNTAIN // XBT BLAKE2B</div>
    <div class="heroActions">
      <a class="primaryAction" href="#startMining">START MINING</a>
      <a href="#poolStats">VIEW LIVE STATS</a>
    </div>
  </div>
</section>


<!-- TERMINUS_GRAND_OPENING_PROMO -->
<section class="launchPromo" id="launchPromo">
  <div class="launchPromoCopy">
    <div class="launchPromoKicker">
      GRAND OPENING // LIMITED-TIME LAUNCH PROMO
    </div>

    <div class="launchPromoTitle" id="promoTitle">
      0% DATUM FEE
    </div>

    <div class="launchPromoText" id="promoText">
      Mine Terminus over DATUM with zero operational fee
      through November 5, 2026.
    </div>

    <div class="launchPromoMeta" id="promoMeta">
      STANDARD DATUM OPERATIONAL FEE AFTER PROMO: 1%
    </div>
  </div>

  <div class="launchPromoClock">
    <div class="launchPromoClockLabel" id="promoClockLabel">
      PROMO TIME REMAINING
    </div>

    <div class="promoCountdown" id="promoCountdown">
      <div class="promoUnit">
        <span class="promoNumber" id="promoDays">00</span>
        <span class="promoLabel">DAYS</span>
      </div>

      <div class="promoUnit">
        <span class="promoNumber" id="promoHours">00</span>
        <span class="promoLabel">HOURS</span>
      </div>

      <div class="promoUnit">
        <span class="promoNumber" id="promoMinutes">00</span>
        <span class="promoLabel">MIN</span>
      </div>

      <div class="promoUnit">
        <span class="promoNumber" id="promoSeconds">00</span>
        <span class="promoLabel">SEC</span>
      </div>
    </div>
  </div>
</section>

<section class="quickConnect" id="startMining" aria-labelledby="startMiningTitle">
  <div class="quickConnectHead">
    <div>
      <h2 id="startMiningTitle">START MINING IN 60 SECONDS</h2>
      <p>Use your XBT payout address as the username. Add <strong>.worker</strong> if you want a worker name.</p>
    </div>
    <a href="#connectionDetails">FULL CONNECTION DETAILS ↓</a>
  </div>
  <div class="quickConnectGrid">
    <div class="quickEndpoint recommended">
      <div class="quickLabel">NATIVE DATUM // RECOMMENDED // 0% PROMO FEE</div>
      <div class="quickValue">datum.terminuspool.xyz:28915</div>
      <button type="button" class="copyBtn" aria-label="Copy DATUM endpoint" data-copy="datum.terminuspool.xyz:28915" onclick="copyField(this)">COPY DATUM ENDPOINT</button>
      <div class="quickNote">For DATUM-compatible clients · Username: <strong>payout_address.worker</strong></div>
    </div>
    <div class="quickEndpoint gateway">
      <div class="quickLabel">SV1 / RENTALS // STANDARD MINERS</div>
      <div class="quickValue">stratum.terminuspool.xyz:23341</div>
      <button type="button" class="copyBtn" aria-label="Copy SV1 rentals endpoint" data-copy="stratum.terminuspool.xyz:23341" onclick="copyField(this)">COPY SV1 / RENTALS ENDPOINT</button>
      <div class="quickNote">Standard miners and Mining Rig Rentals · Username: <strong>payout_address.worker</strong></div>
    </div>
    <div class="quickEndpoint legacy">
      <div class="quickLabel">SV1 PIGGYBANK // 5% REDISTRIBUTION</div>
      <div class="quickValue">stratum.terminuspool.xyz:23340</div>
      <button type="button" class="copyBtn" aria-label="Copy SV1 Piggybank endpoint" data-copy="stratum.terminuspool.xyz:23340" onclick="copyField(this)">COPY SV1 PIGGYBANK ENDPOINT</button>
      <div class="quickNote">Piggybank redistribution lane · Username: <strong>payout_address.worker</strong> · Password: <strong>x</strong></div>
    </div>
  </div>
</section>

<div class="sectionTitle" id="poolStats">LIVE-POOL-HASHRATE</div>

<div class="graphCard poolHashrateGraph">
  <div class="graphTop">
    <div class="graphTitle">
      TERMINUS POOL // ROLLING LIVE HASHRATE
    </div>

    <div class="graphStats">
      <span id="graphMiners" class="graphPill">0 POOL MINERS</span>
      <div id="graphNow">0.000 TH/s</div>
    </div>
  </div>

  <svg viewBox="0 0 1000 220" preserveAspectRatio="none">
    <path id="graphFill"></path>
    <path id="graphLine"></path>
  </svg>
  <div id="historySummary" class="historySummary" aria-label="24-hour pool summary"></div>
</div>

<div class="sectionTitle">POOL-TELEMETRY</div>
<div id="telemetry" class="grid grid6"></div>

<div class="sectionTitle">OPERATOR-HEALTH // READ-ONLY</div>
<div id="healthMatrix" class="healthMatrix" aria-live="polite"></div>

<div class="sectionTitle" id="minerAccounting">MINER-ACCOUNTING</div>

<div class="accountSearch">
  <input
    id="accountAddress"
    type="text"
    placeholder="SEARCH XBT PAYOUT ADDRESS // bc1..."
    autocomplete="off"
    autocapitalize="none"
    spellcheck="false"
    aria-label="XBT payout address"
    aria-describedby="accountHint"
  >
  <button id="accountGo" type="button">LOOK UP</button>
  <button id="accountClear" class="clear" type="button">CLEAR</button>
</div>

<div id="accountHint" class="accountHint" role="status" aria-live="polite">
  SEARCH YOUR PAYOUT ADDRESS TO VIEW ACCOUNTING
</div>

<div id="miner" class="grid grid4" style="display:none"></div>

<div class="sectionTitle">NETWORK-UPLINK</div>
<div id="network" class="grid grid4"></div>

<div class="sectionTitle">SV1-PIGGY-BANK // REDISTRIBUTION</div>
<div id="window" class="grid grid5"></div>

<div class="sectionTitle" id="connectionDetails">PUBLIC-ACCESS</div>

<div class="twoCol">

  <div class="access primary">
    <h3>NATIVE DATUM</h3>
    <div class="mode">DATUM-COMPATIBLE CLIENTS // RECOMMENDED</div>

    <div class="accessLabel">PUBLIC DATUM ENDPOINT</div>
    <div class="copyRow">
      <div class="copyText">datum.terminuspool.xyz:28915</div>
      <button
        type="button"
        class="copyBtn"
        aria-label="Copy DATUM endpoint"
        data-copy="datum.terminuspool.xyz:28915"
        onclick="copyField(this)"
      >COPY</button>
    </div>

    <div class="note">
      For <strong>DATUM-compatible clients</strong> connecting natively.<br>
      Username: <strong>payout_address.worker</strong><br>
      Grand Opening DATUM fee: <strong>0%</strong><br>
      Promo through <strong>November 5, 2026</strong><br>
      Standard DATUM operational fee after promo: <strong>1%</strong>.
    </div>
  </div>

  <div class="access gateway">
    <h3>SV1 / RENTALS</h3>
    <div class="mode">STANDARD MINERS // MINING RIG RENTALS</div>

    <div class="accessLabel">PUBLIC SV1 / RENTALS ENDPOINT</div>
    <div class="copyRow">
      <div class="copyText">stratum.terminuspool.xyz:23341</div>
      <button
        type="button"
        class="copyBtn"
        aria-label="Copy SV1 rentals endpoint"
        data-copy="stratum.terminuspool.xyz:23341"
        onclick="copyField(this)"
      >COPY</button>
    </div>

    <div class="note">
      Connect using ordinary <strong>Stratum V1</strong>.<br>
      The gateway translates SV1 traffic into <strong>DATUM</strong> upstream.<br>
      Ideal for standard miners and <strong>Mining Rig Rentals</strong>.<br>
      Username: <strong>payout_address.worker</strong><br>
      Grand Opening DATUM fee: <strong>0%</strong><br>
      Standard DATUM operational fee after promo: <strong>1%</strong>.
    </div>
  </div>

  <div class="access legacy">
    <h3>SV1 PIGGYBANK</h3>
    <div class="mode">PUBLIC SV1 // 5% REDISTRIBUTION LANE</div>

    <div class="accessLabel">PUBLIC SV1 PIGGYBANK ENDPOINT</div>
    <div class="copyRow">
      <div class="copyText">stratum.terminuspool.xyz:23340</div>
      <button
        type="button"
        class="copyBtn"
        aria-label="Copy SV1 Piggybank endpoint"
        data-copy="stratum.terminuspool.xyz:23340"
        onclick="copyField(this)"
      >COPY</button>
    </div>

    <div class="note">
      Connect using ordinary <strong>Stratum V1</strong>.<br>
      Username: <strong>payout_address.worker</strong><br>
      Password: <strong>x</strong><br>
      SV1 Piggybank redistribution: <strong>5%</strong>.
    </div>
  </div>

</div>

<div class="access identityAccess">
  <h3>POOL IDENTITY // RATUM PRIME</h3>
  <div class="mode">VERIFY YOUR TERMINUS CONNECTION</div>

  <div class="identityGrid">

    <div>
      <div class="accessLabel">PRIME PUBLIC KEY</div>
      <div class="copyRow">
        <div id="primePubkey" class="copyText">LOADING...</div>
        <button
          type="button"
          id="copyPrimePubkey"
          class="copyBtn"
          aria-label="Copy Prime public key"
          data-copy=""
          onclick="copyField(this)"
        >COPY</button>
      </div>
    </div>

    <div>
      <div class="accessLabel">POOL PAYOUT SCRIPT</div>
      <div class="copyRow">
        <div id="poolPayoutScript" class="copyText">LOADING...</div>
        <button
          type="button"
          id="copyPayoutScript"
          class="copyBtn"
          aria-label="Copy pool payout script"
          data-copy=""
          onclick="copyField(this)"
        >COPY</button>
      </div>
    </div>

    <div class="identityWide">
      <div class="accessLabel">COINBASE TAG</div>
      <div class="copyRow">
        <div id="coinbaseTag" class="copyText">LOADING...</div>
        <button
          type="button"
          id="copyCoinbaseTag"
          class="copyBtn"
          aria-label="Copy coinbase tag"
          data-copy=""
          onclick="copyField(this)"
        >COPY</button>
      </div>
    </div>

  </div>
</div>

<div id="blockBanner" class="blockBanner"></div>
</main>

<footer>
TERMINUS POOL // THE LAST WORD IN MINING // DATUM-FIRST ARCHITECTURE // XBT BLAKE2B
</footer>

</div>

<script>
const $=id=>document.getElementById(id);

let accountAddress =
  localStorage.getItem("terminusAccountAddress") || "";

$("accountAddress").value=accountAddress;

function lookupAccount(){
  accountAddress=$("accountAddress").value.trim();

  if(!accountAddress){
    localStorage.removeItem("terminusAccountAddress");
    $("accountHint").textContent=
      "ENTER AN XBT PAYOUT ADDRESS TO SEARCH";
    $("accountHint").className="accountHint badText";
    $("miner").style.display="none";
    $("miner").innerHTML="";
    $("accountAddress").focus();
    return;
  }

  localStorage.setItem("terminusAccountAddress",accountAddress);
  refresh();
}

$("accountGo").addEventListener("click",lookupAccount);

$("accountClear").addEventListener("click",()=>{
  accountAddress="";
  $("accountAddress").value="";
  localStorage.removeItem("terminusAccountAddress");
  refresh();
});

$("accountAddress").addEventListener("keydown",e=>{
  if(e.key==="Enter") lookupAccount();
});

async function copyField(btn){
  const value=(btn.dataset.copy||"").trim();
  if(!value) return;

  try{
    await navigator.clipboard.writeText(value);
  }catch(e){
    const ta=document.createElement("textarea");
    ta.value=value;
    ta.style.position="fixed";
    ta.style.opacity="0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }

  const old=btn.textContent;
  btn.textContent="COPIED";

  const toast=$("copyToast");
  toast.textContent="COPIED TO CLIPBOARD";
  toast.classList.add("show");

  setTimeout(()=>{
    btn.textContent=old;
    toast.classList.remove("show");
  },1200);
}

function num(v,d=0){
  const n=Number(v);
  return Number.isFinite(n)?n.toLocaleString(undefined,{
    minimumFractionDigits:d,maximumFractionDigits:d
  }):"0";
}

function compact(v){
  let n=Number(v)||0;
  if(n>=1e12)return (n/1e12).toFixed(2)+"T";
  if(n>=1e9)return (n/1e9).toFixed(2)+"B";
  if(n>=1e6)return (n/1e6).toFixed(2)+"M";
  if(n>=1e3)return (n/1e3).toFixed(2)+"K";
  return num(n,0);
}

function bestShareFmt(v){
    const n=Number(v)||0;

    if(n<=0) return "WAITING FOR SHARE";
    if(n>=1e15) return (n/1e15).toFixed(2)+"P";
    if(n>=1e12) return (n/1e12).toFixed(2)+"T";
    if(n>=1e9)  return (n/1e9).toFixed(2)+"G";
    if(n>=1e6)  return (n/1e6).toFixed(2)+"M";
    if(n>=1e3)  return (n/1e3).toFixed(2)+"K";

    return n.toFixed(2);
}

function card(label,value,cls=""){
  return `<div class="card ${cls}">
    <div class="label">${label}</div>
    <div class="value">${value}</div>
  </div>`;
}

function healthItem(component){
  const state=String(component.status||"offline").toLowerCase();
  const safeState=["healthy","degraded","offline"].includes(state)
    ? state
    : "offline";

  return `<div class="healthItem ${safeState}">
    <div class="healthName">${component.name||"UNKNOWN COMPONENT"}</div>
    <div class="healthState">${safeState.toUpperCase()}</div>
    <div class="healthDetail">${component.detail||"NO TELEMETRY"}</div>
  </div>`;
}

function historyMetric(label,value){
  return `<div class="historyMetric">
    <div class="label">${label}</div>
    <div class="value">${value}</div>
  </div>`;
}


function injectVisualFx(){
    if(document.getElementById("terminusFxStyles")) return;

    const style=document.createElement("style");
    style.id="terminusFxStyles";
    style.textContent=`
    .skyFxLayer{
        position:absolute;
        inset:0;
        pointer-events:none;
        overflow:hidden;
        z-index:1;
    }
    .skyNebula{
        position:absolute;
        width:320px;
        height:320px;
        right:8%;
        top:-90px;
        border-radius:50%;
        background:radial-gradient(circle,
            rgba(170,114,255,.18) 0%,
            rgba(67,245,255,.10) 28%,
            rgba(255,79,184,.06) 50%,
            rgba(0,0,0,0) 72%);
        filter:blur(10px);
        animation:nebulaPulse 8s ease-in-out infinite;
        opacity:.9;
    }
    .skyMoonGlow{
        position:absolute;
        right:68px;
        top:54px;
        width:118px;
        height:118px;
        border-radius:50%;
        background:radial-gradient(circle,
            rgba(67,245,255,.18) 0%,
            rgba(170,114,255,.10) 42%,
            rgba(0,0,0,0) 72%);
        filter:blur(12px);
        animation:moonGlow 5.5s ease-in-out infinite;
    }
    .skyMoon{
        position:absolute;
        right:84px;
        top:66px;
        width:78px;
        height:78px;
        border-radius:50%;
        background:
            radial-gradient(circle at 30% 30%,
                rgba(255,255,255,.92) 0%,
                rgba(226,245,255,.92) 32%,
                rgba(165,218,255,.78) 68%,
                rgba(98,176,255,.56) 100%);
        box-shadow:
            0 0 18px rgba(67,245,255,.35),
            0 0 42px rgba(170,114,255,.18);
        opacity:.92;
    }
    .skyMoon:after{
        content:"";
        position:absolute;
        width:26px;
        height:26px;
        border-radius:50%;
        left:20px;
        top:18px;
        background:rgba(120,149,160,.15);
        box-shadow:
            20px 12px 0 4px rgba(120,149,160,.12),
            10px 34px 0 1px rgba(120,149,160,.10);
    }
    .skyStar{
        position:absolute;
        border-radius:50%;
        background:#dffcff;
        box-shadow:
            0 0 6px rgba(67,245,255,.65),
            0 0 12px rgba(170,114,255,.25);
        animation:starTwinkle var(--dur) ease-in-out infinite,
                  starDrift var(--drift) linear infinite;
        opacity:var(--op);
    }

    #graphDot{
        filter:drop-shadow(0 0 8px rgba(67,245,255,.9));
    }
    #graphPulse{
        transform-origin:center;
        animation:graphPulse 1.8s ease-out infinite;
    }
    .graphCard svg{
        overflow:visible;
    }

    @keyframes starTwinkle{
        0%,100%{opacity:calc(var(--op) * .55); transform:scale(.9)}
        50%{opacity:1; transform:scale(1.35)}
    }
    @keyframes starDrift{
        0%{transform:translateY(0)}
        50%{transform:translateY(-2px)}
        100%{transform:translateY(0)}
    }
    @keyframes moonGlow{
        0%,100%{transform:scale(.98); opacity:.72}
        50%{transform:scale(1.04); opacity:1}
    }
    @keyframes nebulaPulse{
        0%,100%{opacity:.65; transform:scale(.98)}
        50%{opacity:1; transform:scale(1.03)}
    }
    @keyframes graphPulse{
        0%{opacity:.75; r:6}
        100%{opacity:0; r:20}
    }`;
    document.head.appendChild(style);
}

function initSkyFx(){
    const hero=document.querySelector(
        ".heroArt, .heroScene, .heroVisual, .heroGraphic, .heroIllustration, .hero"
    );
    if(!hero || hero.dataset.fxReady) return;

    hero.dataset.fxReady="1";
    hero.style.position=hero.style.position || "relative";
    hero.style.overflow="hidden";

    const layer=document.createElement("div");
    layer.className="skyFxLayer";

    const nebula=document.createElement("div");
    nebula.className="skyNebula";
    layer.appendChild(nebula);

    const moonGlow=document.createElement("div");
    moonGlow.className="skyMoonGlow";
    layer.appendChild(moonGlow);

    const moon=document.createElement("div");
    moon.className="skyMoon";
    layer.appendChild(moon);

    for(let i=0;i<28;i++){
        const star=document.createElement("div");
        star.className="skyStar";
        const size=(Math.random()*2.8+1.2).toFixed(2);
        star.style.width=size+"px";
        star.style.height=size+"px";
        star.style.left=(Math.random()*92+2)+"%";
        star.style.top=(Math.random()*42+4)+"%";
        star.style.setProperty("--op",(Math.random()*.55+.35).toFixed(2));
        star.style.setProperty("--dur",(Math.random()*2.8+1.8).toFixed(2)+"s");
        star.style.setProperty("--drift",(Math.random()*7+5).toFixed(2)+"s");
        star.style.animationDelay=
            `${(Math.random()*4).toFixed(2)}s, ${(Math.random()*3).toFixed(2)}s`;
        layer.appendChild(star);
    }

    hero.appendChild(layer);
}

function ensureGraphFx(svg){
    if(!svg) return {};

    let defs=svg.querySelector("defs");
    if(!defs){
        defs=document.createElementNS("http://www.w3.org/2000/svg","defs");
        svg.insertBefore(defs, svg.firstChild);
    }

    if(!svg.querySelector("#graphStrokeGradient")){
        const strokeGrad=document.createElementNS("http://www.w3.org/2000/svg","linearGradient");
        strokeGrad.setAttribute("id","graphStrokeGradient");
        strokeGrad.setAttribute("x1","0%");
        strokeGrad.setAttribute("y1","0%");
        strokeGrad.setAttribute("x2","100%");
        strokeGrad.setAttribute("y2","0%");
        strokeGrad.innerHTML=`
            <stop offset="0%" stop-color="#43f5ff"/>
            <stop offset="55%" stop-color="#72ffb4"/>
            <stop offset="100%" stop-color="#aa72ff"/>`;
        defs.appendChild(strokeGrad);
    }

    if(!svg.querySelector("#graphFillGradient")){
        const fillGrad=document.createElementNS("http://www.w3.org/2000/svg","linearGradient");
        fillGrad.setAttribute("id","graphFillGradient");
        fillGrad.setAttribute("x1","0%");
        fillGrad.setAttribute("y1","0%");
        fillGrad.setAttribute("x2","0%");
        fillGrad.setAttribute("y2","100%");
        fillGrad.innerHTML=`
            <stop offset="0%" stop-color="rgba(67,245,255,.32)"/>
            <stop offset="45%" stop-color="rgba(67,245,255,.15)"/>
            <stop offset="100%" stop-color="rgba(67,245,255,0)"/>`;
        defs.appendChild(fillGrad);
    }

    if(!svg.querySelector("#graphGlowFilter")){
        const filter=document.createElementNS("http://www.w3.org/2000/svg","filter");
        filter.setAttribute("id","graphGlowFilter");
        filter.innerHTML=`
            <feGaussianBlur stdDeviation="3.2" result="blur"/>
            <feMerge>
                <feMergeNode in="blur"/>
                <feMergeNode in="SourceGraphic"/>
            </feMerge>`;
        defs.appendChild(filter);
    }

    let dot=svg.querySelector("#graphDot");
    if(!dot){
        dot=document.createElementNS("http://www.w3.org/2000/svg","circle");
        dot.setAttribute("id","graphDot");
        dot.setAttribute("r","5");
        dot.setAttribute("fill","#43f5ff");
        svg.appendChild(dot);
    }

    let pulse=svg.querySelector("#graphPulse");
    if(!pulse){
        pulse=document.createElementNS("http://www.w3.org/2000/svg","circle");
        pulse.setAttribute("id","graphPulse");
        pulse.setAttribute("r","6");
        pulse.setAttribute("fill","none");
        pulse.setAttribute("stroke","#43f5ff");
        pulse.setAttribute("stroke-opacity",".8");
        pulse.setAttribute("stroke-width","2");
        svg.appendChild(pulse);
    }

    return {dot,pulse};
}

function smoothPath(points){
    if(points.length<2) return "";
    let d=`M ${points[0][0]} ${points[0][1]}`;
    for(let i=0;i<points.length-1;i++){
        const p0=points[i-1] || points[i];
        const p1=points[i];
        const p2=points[i+1];
        const p3=points[i+2] || p2;

        const cp1x=p1[0]+(p2[0]-p0[0])/6;
        const cp1y=p1[1]+(p2[1]-p0[1])/6;
        const cp2x=p2[0]-(p3[0]-p1[0])/6;
        const cp2y=p2[1]-(p3[1]-p1[1])/6;

        d+=` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2[0]} ${p2[1]}`;
    }
    return d;
}

function drawGraph(values){
    const svg=document.getElementById("hashGraph") ||
              document.querySelector(".graphCard svg");

    const line=document.getElementById("line") ||
               document.getElementById("graphLine");

    const fill=document.getElementById("fill") ||
               document.getElementById("graphFill");

    if(!svg || !line || !fill) return;

    const fx=ensureGraphFx(svg);

    function svgEl(tag,id){
        let el=id ? svg.querySelector("#"+id) : null;

        if(!el){
            el=document.createElementNS(
                "http://www.w3.org/2000/svg",
                tag
            );

            if(id) el.setAttribute("id",id);
        }

        return el;
    }

    let grid=svg.querySelector("#hashGrid");

    if(!grid){
        grid=svgEl("g","hashGrid");
        svg.insertBefore(grid,fill);
    }

    let bars=svg.querySelector("#hashBars");

    if(!bars){
        bars=svgEl("g","hashBars");
        svg.insertBefore(bars,fill);
    }

    let avgGroup=svg.querySelector("#hashAverage");

    if(!avgGroup){
        avgGroup=svgEl("g","hashAverage");
        svg.insertBefore(avgGroup,line);
    }

    let peakDot=svg.querySelector("#graphPeakDot");

    if(!peakDot){
        peakDot=svgEl("circle","graphPeakDot");
        peakDot.setAttribute("r","5");
        peakDot.setAttribute("fill","#ffc85c");
        peakDot.setAttribute("stroke","#fff0bc");
        peakDot.setAttribute("stroke-width","2");
        svg.appendChild(peakDot);
    }

    let peakLabel=svg.querySelector("#graphPeakLabel");

    if(!peakLabel){
        peakLabel=svgEl("text","graphPeakLabel");
        peakLabel.setAttribute("fill","#ffc85c");
        peakLabel.setAttribute("class","graphMetricText");
        peakLabel.setAttribute("text-anchor","middle");
        svg.appendChild(peakLabel);
    }

    if(!values || values.length < 2){
        line.setAttribute("d","");
        fill.setAttribute("d","");
        grid.innerHTML="";
        bars.innerHTML="";
        avgGroup.innerHTML="";

        [fx.dot,fx.pulse,peakDot].forEach(el=>{
            if(el){
                el.setAttribute("cx","-100");
                el.setAttribute("cy","-100");
            }
        });

        peakLabel.textContent="";
        return;
    }

    const nums=values
        .map(v=>Number(v))
        .filter(Number.isFinite);

    if(nums.length < 2) return;

    const max=Math.max(...nums);
    const min=Math.min(...nums);
    const avg=nums.reduce((a,b)=>a+b,0)/nums.length;

    /*
      Give the graph breathing room rather than mapping
      min/max directly to the roof/floor.
    */
    const rawRange=Math.max(max-min,0.001);

    const padding=Math.max(
        rawRange*.28,
        max*.025,
        .05
    );

    const low=Math.max(0,min-padding);
    const high=max+padding;
    const displayRange=Math.max(high-low,.001);

    const yFor=v=>{
        const pct=(v-low)/displayRange;

        return Math.max(
            16,
            Math.min(
                205,
                205-(pct*174)
            )
        );
    };

    const points=nums.map((v,i)=>{
        const x=(i/(nums.length-1))*1000;
        return [x,yFor(v)];
    });

    const path=smoothPath(points);
    const last=points[points.length-1];

    /* -----------------------------
       MAIN GLOWING CURVE
       ----------------------------- */
    line.setAttribute("d",path);
    line.setAttribute(
        "stroke",
        "url(#graphStrokeGradient)"
    );
    line.setAttribute("stroke-width","4");
    line.setAttribute("stroke-linecap","round");
    line.setAttribute("stroke-linejoin","round");
    line.setAttribute("fill","none");
    line.setAttribute(
        "filter",
        "url(#graphGlowFilter)"
    );

    fill.setAttribute(
        "d",
        path+` L ${last[0]} 220 L 0 220 Z`
    );

    fill.setAttribute(
        "fill",
        "url(#graphFillGradient)"
    );

    fill.setAttribute("stroke","none");

    /* -----------------------------
       DASHED GUIDE GRID
       ----------------------------- */
    grid.innerHTML="";

    [25,50,75].forEach(percent=>{
        const y=205-(percent/100)*174;

        const guide=svgEl("line");

        guide.setAttribute("x1","0");
        guide.setAttribute("x2","1000");
        guide.setAttribute("y1",y);
        guide.setAttribute("y2",y);

        guide.setAttribute(
            "stroke",
            "rgba(120,149,160,.18)"
        );

        guide.setAttribute(
            "stroke-dasharray",
            "7 11"
        );

        guide.setAttribute("stroke-width","1");

        grid.appendChild(guide);
    });

    /* -----------------------------
       HASHRATE HISTOGRAM
       ----------------------------- */
    bars.innerHTML="";

    /*
      Limit bars so a long history does not turn
      into a solid rectangle.
    */
    const step=Math.max(
        1,
        Math.ceil(nums.length/48)
    );

    const samples=[];

    for(let i=0;i<nums.length;i+=step){
        samples.push({
            i,
            value:nums[i]
        });
    }

    const barWidth=Math.max(
        5,
        (1000/samples.length)*.55
    );

    samples.forEach((sample,index)=>{
        const x=
            (sample.i/(nums.length-1))*1000;

        const y=yFor(sample.value);

        const rect=svgEl("rect");

        rect.setAttribute(
            "x",
            x-barWidth/2
        );

        rect.setAttribute("y",y);
        rect.setAttribute(
            "width",
            barWidth
        );

        rect.setAttribute(
            "height",
            Math.max(4,215-y)
        );

        rect.setAttribute("rx","2");

        rect.setAttribute(
            "fill",
            index===samples.length-1
                ? "rgba(67,245,255,.23)"
                : "rgba(114,255,180,.10)"
        );

        bars.appendChild(rect);
    });

    /* -----------------------------
       AVERAGE LINE + LABEL
       ----------------------------- */
    avgGroup.innerHTML="";

    const avgY=yFor(avg);

    const avgLine=svgEl("line");

    avgLine.setAttribute("x1","0");
    avgLine.setAttribute("x2","1000");
    avgLine.setAttribute("y1",avgY);
    avgLine.setAttribute("y2",avgY);

    avgLine.setAttribute(
        "stroke",
        "rgba(255,79,184,.55)"
    );

    avgLine.setAttribute(
        "stroke-dasharray",
        "14 12"
    );

    avgLine.setAttribute("stroke-width","1.5");

    const avgText=svgEl("text");

    avgText.setAttribute("x","18");
    avgText.setAttribute(
        "y",
        Math.max(20,avgY-8)
    );

    avgText.setAttribute(
        "fill",
        "#ff72c4"
    );

    avgText.setAttribute(
        "class",
        "graphMetricText"
    );

    avgText.textContent=
        "AVG "+avg.toFixed(3)+" TH/s";

    avgGroup.appendChild(avgLine);
    avgGroup.appendChild(avgText);

    /* -----------------------------
       PEAK MARKER
       ----------------------------- */
    let peakIndex=0;

    for(let i=1;i<nums.length;i++){
        if(nums[i]>nums[peakIndex]){
            peakIndex=i;
        }
    }

    const peak=points[peakIndex];

    peakDot.setAttribute(
        "cx",
        peak[0]
    );

    peakDot.setAttribute(
        "cy",
        peak[1]
    );

    peakLabel.setAttribute(
        "x",
        peak[0]
    );

    peakLabel.setAttribute(
        "y",
        Math.max(18,peak[1]-14)
    );

    peakLabel.textContent=
        "PEAK "+nums[peakIndex].toFixed(3);

    /* -----------------------------
       LIVE PULSE
       ----------------------------- */
    if(fx.dot){
        fx.dot.setAttribute(
            "cx",
            last[0]
        );

        fx.dot.setAttribute(
            "cy",
            last[1]
        );
    }

    if(fx.pulse){
        fx.pulse.setAttribute(
            "cx",
            last[0]
        );

        fx.pulse.setAttribute(
            "cy",
            last[1]
        );
    }
}

async function refresh(){
  try{
    const params=new URLSearchParams();
    params.set("ts",Date.now().toString());

    if(accountAddress){
      params.set("address",accountAddress);
    }

    const r=await fetch(
      "/api/stats?"+params.toString(),
      {cache:"no-store"}
    );
    if(!r.ok)throw new Error("HTTP "+r.status);

    const d=await r.json();
    const ready=String(d.status||"").includes("Ready");

    const pubkey=d.primePubkey||"";
    const payoutScript=d.poolPayoutScript||"";
    const tag=d.coinbaseTag||"";

    $("primePubkey").textContent=pubkey||"UNAVAILABLE";
    $("copyPrimePubkey").dataset.copy=pubkey;

    $("poolPayoutScript").textContent=payoutScript||"UNAVAILABLE";
    $("copyPayoutScript").dataset.copy=payoutScript;

    $("coinbaseTag").textContent=tag||"UNAVAILABLE";
    $("copyCoinbaseTag").dataset.copy=tag;

    $("live").className=ready?"live":"live bad";
    $("live").textContent=
      (ready?"● NODE LINK ACTIVE // ":"● NODE LINK DEGRADED // ")+
      new Date().toLocaleTimeString();

    $("telemetry").innerHTML=
      card("SYSTEM STATUS",d.status||"Unknown",ready?"ok":"bad")+
      card("LIVE POOL HASHRATE",num(d.hashrate,3)+" TH/s","cyan")+
      card("POOL MINERS",num(d.poolMiners,0))+
      card("WINDOW SHARES",num(d.windowShares,0),"purple")+
      card("POOL SHARE FLOOR",compact(Number(d.shareDifficulty)||1024),"cyan")+
      card("BLOCKS FOUND",num(d.blocks,0),Number(d.blocks)>0?"gold":"");

    $("healthMatrix").innerHTML=(d.health||[])
      .map(healthItem)
      .join("");

    const historySummary=d.historySummary||{};
    $("historySummary").innerHTML=
      historyMetric(
        "24H AVERAGE",
        num(historySummary.averageHashrate,3)+" TH/s"
      )+
      historyMetric(
        "24H PEAK",
        num(historySummary.peakHashrate,3)+" TH/s"
      )+
      historyMetric(
        "24H LOW",
        num(historySummary.lowHashrate,3)+" TH/s"
      )+
      historyMetric(
        "PERSISTENT SAMPLES",
        num(historySummary.samples,0)
      );

    if(!d.accountQuery){

      $("accountHint").textContent=
        "SEARCH YOUR PAYOUT ADDRESS TO VIEW ACCOUNTING";

      $("accountHint").className="accountHint";

      $("miner").style.display="none";
      $("miner").innerHTML="";

    }else if(!d.accountFound){

      $("accountHint").textContent=
        "NO ACCOUNT FOUND // CHECK THE PAYOUT ADDRESS";

      $("accountHint").className="accountHint badText";

      $("miner").style.display="none";
      $("miner").innerHTML="";

    }else{

      $("accountHint").textContent=
        "ACCOUNT FOUND // "+(d.minerTag||"UNTAGGED");

      $("accountHint").className="accountHint good";

      $("miner").style.display="grid";

      $("miner").innerHTML=
        card("PAYOUT ADDRESS",d.identity||"N/A","tiny")+
        card("MINER TAG",d.minerTag||"UNTAGGED","cyan")+
        card("PRIME HASHRATE",num(d.primeHashrate,3)+" TH/s","cyan")+
        card("WINDOW WORK",compact(d.minerWork||0))+
        card("GATEWAY WORK",compact(d.ownGatewayWork||0))+

        card(
            "BEST SHARE",
            bestShareFmt(d.bestShare)
        )+

        card(
            '<span class="piggyLabel"><span class="piggyIcon"></span>SV1 PIGGYBANK SHARE</span>',
            num(d.sv1PiggySharePercent,2)+"%"
        )+

        card(
            '<span class="piggyLabel"><span class="piggyIcon"></span>SV1 PIGGYBANK REWARD</span>',
            num(d.sv1PiggyRewardXbt,8)+" XBT"
        )+

        card("WINDOW OWNERSHIP",num(d.sharePercent,2)+"%","purple")+
        card(
          "PROJECTED PAYOUT",
          num(d.estimatedPayoutXbt,8)+" XBT",
          "gold"
        )+
        card(
          "PAYOUT STATUS",
          d.payable
            ? "PAYABLE"
            : (d.unpayableReason||"LOCKED"),
          d.payable ? "ok":"bad"
        );
    }

    $("network").innerHTML=
      card("CHAIN HEIGHT",num(d.height,0))+
      card("NETWORK DIFFICULTY",(Number(d.difficulty||0)/1e9).toFixed(2)+"G","small")+
      card("COINBASE VALUE",num(d.blockValue,8)+" XBT","gold")+
      card("NETWORK HASHRATE",num(d.networkTh,2)+" TH/s","small");

    const redistributionPct=
      Number(d.sv1SubsidyBps||0)/100;

    $("window").innerHTML=
      card(
        "PUBLIC SV1 WORK",
        compact(d.sv1PublicWork||0),
        "cyan"
      )+
      card(
        "SV1 REDISTRIBUTION RATE",
        num(Number(d.sv1FeeBps||0)/100,2)+"%",
        "purple"
      )+
      card(
            '<span class="piggyLabel"><span class="piggyIcon"></span>PIGGY BANK</span>',
        
        num(Number(d.sv1FeeSats||0)/100000000,8)+" XBT",
        "gold"
      )+
      card(
        "REASSIGNED WORK",
        compact(d.sv1ReassignedWork||0),
        "cyan"
      )+
      card(
        "REDISTRIBUTION STATUS",
        redistributionPct>=100
          ? "100% REASSIGNED"
          : num(redistributionPct,2)+"% REASSIGNED",
        redistributionPct>=100 ? "ok":"purple"
      );

    $("graphNow").textContent=num(d.hashrate,3)+" TH/s";
    $("graphMiners").textContent=
      num(d.poolMiners,0)+" POOL MINERS";

    drawGraph(d.hashHistory||[]);

    if(Number(d.blocks)>0){
      $("blockBanner").style.display="block";
      $("blockBanner").textContent=
        "🔥 BLOCKS FOUND: "+num(d.blocks,0)+" // TERMINUS POOL HAS HIT";
    }else{
      $("blockBanner").style.display="none";
    }

  }catch(e){
    $("live").textContent="● NODE LINK DATA ERROR";
    $("live").className="live bad";
    $("healthMatrix").innerHTML=healthItem({
      name:"TELEMETRY API",
      status:"offline",
      detail:"LIVE DATA UNAVAILABLE"
    });
  }
}

injectVisualFx();
initSkyFx();
refresh();

const REFRESH_MS=10000;
let refreshTimer=setInterval(()=>{
  if(!document.hidden) refresh();
},REFRESH_MS);

document.addEventListener("visibilitychange",()=>{
  if(!document.hidden) refresh();
});

/* TERMINUS_GRAND_OPENING_PROMO_COUNTDOWN
   Promo is valid through Nov 5, 2026.
   Midnight entering Nov 6 in Toronto ends the promotion.
*/
const PROMO_END = new Date("2026-11-06T00:00:00-05:00").getTime();

function renderPromoCountdown(){
    const now = Date.now();
    let remaining = PROMO_END - now;

    const daysEl = document.getElementById("promoDays");
    const hoursEl = document.getElementById("promoHours");
    const minutesEl = document.getElementById("promoMinutes");
    const secondsEl = document.getElementById("promoSeconds");

    if (!daysEl || !hoursEl || !minutesEl || !secondsEl) return;

    if (remaining <= 0){
        remaining = 0;

        document.getElementById("promoTitle").textContent =
            "GRAND OPENING PROMO COMPLETE";

        document.getElementById("promoText").textContent =
            "The 0% DATUM Grand Opening promotion ended November 5, 2026.";

        document.getElementById("promoMeta").textContent =
            "STANDARD DATUM OPERATIONAL FEE: 1%";

        document.getElementById("promoClockLabel").textContent =
            "PROMOTION COMPLETE";
    }

    const totalSeconds = Math.floor(remaining / 1000);

    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    daysEl.textContent = String(days).padStart(2, "0");
    hoursEl.textContent = String(hours).padStart(2, "0");
    minutesEl.textContent = String(minutes).padStart(2, "0");
    secondsEl.textContent = String(seconds).padStart(2, "0");
}

renderPromoCountdown();
setInterval(renderPromoCountdown, 1000);

</script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):

    server_version = "TerminusDashboard"
    sys_version = ""

    def version_string(self):
        return self.server_version

    def send_security_headers(self):
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()"
        )
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'"
        )
        self.send_header(
            "Strict-Transport-Security",
            "max-age=31536000"
        )

    def send_json(self,obj,status=200):
        body=json.dumps(obj).encode()

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header("Cache-Control","no-store")
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Content-Length",str(len(body)))
        self.send_security_headers()
        self.end_headers()

        self.wfile.write(body)

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)

        self.send_response(200)

        if parsed.path in ("/api/stats", "/api/local-stats"):
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8"
            )
            self.send_header("Cache-Control","no-store")
            self.send_header("Access-Control-Allow-Origin","*")
        else:
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Cache-Control","public, max-age=60")

        self.send_security_headers()
        self.end_headers()

    def do_GET(self):

        parsed = urllib.parse.urlparse(self.path)

        if parsed.path in ("/api/stats", "/api/local-stats"):

            try:

                query = urllib.parse.parse_qs(parsed.query)

                account_query = (
                    query.get("address", [""])[0] or ""
                ).strip()

                normalized_account = account_query

                # Accept either:
                # bc1...
                # bc1....worker
                if "." in normalized_account:
                    normalized_account = (
                        normalized_account.split(".",1)[0]
                    )

                gateway=json.load(
                    urllib.request.urlopen(
                        GATEWAY,
                        timeout=1.25
                    )
                )

                prime=json.load(
                    urllib.request.urlopen(
                        PRIME,
                        timeout=1.25
                    )
                )

                s=gateway.get("stratum",{})
                accepted=gateway.get("shares_accepted",{})
                rejected=gateway.get("shares_rejected",{})
                job=gateway.get("job",{})

                pool=prime.get("pool",{})
                window=prime.get("window",{})
                network=prime.get("network",{})
                blocks=prime.get("blocks",{})

                public_gateway_fee=prime.get(
                    "public_gateway_fee",{}
                )

                miners=window.get("miners",[])

                # Pool-wide telemetry comes from every miner
                # currently represented in Prime's window.
                pool_hash_hs=0.0

                for pool_miner in miners:
                    try:
                        pool_hash_hs += float(
                            pool_miner.get("hashrate_hs",0) or 0
                        )
                    except:
                        pass

                pool_hash_th=(
                    pool_hash_hs/1_000_000_000_000
                )

                pool_miner_count=len(miners)

                miner={}
                account_found=False

                if normalized_account:

                    wanted=normalized_account.lower()

                    for candidate in miners:

                        identity=str(
                            candidate.get("identity","")
                        ).strip().lower()

                        if identity == wanted:
                            miner=candidate
                            account_found=True
                            break

                else:
                    # Do not expose a miner account until an
                    # explicit payout-address lookup is made.
                    miner={}
                    account_found=False

                gateway_hash=float(
                    s.get("hashrate_ths",0) or 0
                )

                prime_hash_hs=float(
                    miner.get("hashrate_hs",0) or 0
                )

                prime_hash_th=prime_hash_hs/1_000_000_000_000

                # Dashboard headline/chart represents the
                # complete Prime pool, not legacy SV1 Gateway.
                display_hash = pool_hash_th

                network_hashps=float(
                    s.get("network_hashps",0) or 0
                )

                payout_sats=int(
                    miner.get("payout_sats",0) or 0
                )

                data={
                    "accountQuery":
                        account_query,

                    "accountFound":
                        account_found,

                    "primePubkey":
                        pool.get("pubkey",""),

                    "poolPayoutScript":
                        pool.get("payout_script",""),

                    "coinbaseTag":
                        pool.get("coinbase_tag",""),

                    "sv1Tag":
                        public_gateway_fee.get(
                            "public_gateway_tag",""
                        ),

                    "sv1FeeBps":
                        public_gateway_fee.get(
                            "fee_bps",0
                        ),

                    "sv1SubsidyBps":
                        public_gateway_fee.get(
                            "subsidy_bps",0
                        ),

                    "sv1PublicWork":
                        public_gateway_fee.get(
                            "public_gateway_work","0"
                        ),

                    "sv1FeeWork":
                        public_gateway_fee.get(
                            "fee_work","0"
                        ),

                    "sv1FeeSats":
                        public_gateway_fee.get(
                            "fee_sats",0
                        ),

                    "sv1ReassignedWork":
                        public_gateway_fee.get(
                            "reassigned_work","0"
                        ),

                    "sv1ReassignedSats":
                        public_gateway_fee.get(
                            "reassigned_sats",0
                        ),

                    "sv1OwnGatewayWork":
                        public_gateway_fee.get(
                            "own_gateway_work","0"
                        ),

                    "status":
                        gateway.get("status","Unknown"),

                    "uptime":
                        gateway.get("uptime","N/A"),

                    "connections":
                        s.get("connections",0),

                    "hashrate":
                        display_hash,

                    "poolMiners":
                        pool_miner_count,

                    "primeHashrate":
                        prime_hash_th,

                    "accepted":
                        accepted.get("count",0),

                    "rejected":
                        rejected.get("count",0),

                    "shareDifficulty":
                        (
                            accepted.get("diff",0)
                            or prime.get("pool",{}).get(
                                "min_difficulty",0
                            )
                        ),

                    "height":
                        job.get(
                            "height",
                            network.get("tip_height",0)
                        ),

                    "difficulty":
                        job.get(
                            "difficulty",
                            network.get("difficulty",0)
                        ),

                    "blockValue":
                        job.get(
                            "value_btc",
                            (
                                network.get(
                                    "coinbase_value",0
                                ) or 0
                            )/100000000
                        ),

                    "networkTh":
                        network_hashps/1_000_000_000_000,

                    "windowShares":
                        window.get("shares",0),

                    "windowWork":
                        window.get("work","0"),

                    "identity":
                        miner.get("identity",""),

                    "minerTag":
                        miner.get("tag",""),

                    "ownGatewayWork":
                        miner.get("own_gateway_work","0"),

                    "bestShare":
                        float(
                            miner.get(
                                "best_share",0
                            ) or 0
                        ),

                    "sv1PiggySharePercent":
                        (
                            int(
                                miner.get(
                                    "own_gateway_work",0
                                ) or 0
                            )
                            /
                            int(
                                public_gateway_fee.get(
                                    "own_gateway_work",0
                                ) or 0
                            )
                            * 100.0
                        )
                        if int(
                            public_gateway_fee.get(
                                "own_gateway_work",0
                            ) or 0
                        ) > 0
                        else 0.0,

                    "sv1PiggyRewardSats":
                        round(
                            int(
                                public_gateway_fee.get(
                                    "reassigned_sats",0
                                ) or 0
                            )
                            *
                            int(
                                miner.get(
                                    "own_gateway_work",0
                                ) or 0
                            )
                            /
                            int(
                                public_gateway_fee.get(
                                    "own_gateway_work",0
                                ) or 0
                            )
                        )
                        if int(
                            public_gateway_fee.get(
                                "own_gateway_work",0
                            ) or 0
                        ) > 0
                        else 0,

                    "sv1PiggyRewardXbt":
                        (
                            round(
                                int(
                                    public_gateway_fee.get(
                                        "reassigned_sats",0
                                    ) or 0
                                )
                                *
                                int(
                                    miner.get(
                                        "own_gateway_work",0
                                    ) or 0
                                )
                                /
                                int(
                                    public_gateway_fee.get(
                                        "own_gateway_work",0
                                    ) or 0
                                )
                            )
                            / 100000000
                        )
                        if int(
                            public_gateway_fee.get(
                                "own_gateway_work",0
                            ) or 0
                        ) > 0
                        else 0.0,


                    "unpayableReason":
                        miner.get("unpayable_reason"),

                    "minerWork":
                        miner.get("work","0"),

                    "sharePercent":
                        float(
                            miner.get(
                                "share_percent",0
                            ) or 0
                        ),

                    "estimatedPayoutXbt":
                        payout_sats/100000000,

                    "payable":
                        miner.get(
                            "payable",False
                        ),

                    "blocks":
                        blocks.get("found",0)
                }

                history_persistent = True
                try:
                    record_history(data)
                    history_points, history_summary = load_history()
                except Exception:
                    history_persistent = False
                    history_points = [{
                        "ts": int(time.time()),
                        "hashrate": display_hash,
                        "miners": pool_miner_count,
                        "connections": s.get("connections",0),
                        "accepted": accepted.get("count",0),
                        "rejected": rejected.get("count",0),
                        "height": data.get("height",0),
                    }]
                    history_summary = {
                        "samples": 1,
                        "averageHashrate": display_hash,
                        "peakHashrate": display_hash,
                        "lowHashrate": display_hash,
                    }

                gateway_ready = "ready" in str(
                    gateway.get("status", "")
                ).lower()
                chain_height = int(data.get("height",0) or 0)

                data["history24h"] = history_points
                data["hashHistory"] = [
                    point["hashrate"] for point in history_points
                ]
                data["historySummary"] = history_summary
                data["historyPersistent"] = history_persistent
                data["lastUpdated"] = int(time.time())
                data["health"] = [
                    {
                        "name": "RATUM PRIME",
                        "status": "healthy",
                        "detail": (
                            str(pool_miner_count) +
                            " miners represented in payout window"
                        ),
                    },
                    {
                        "name": "SV1 GATEWAY",
                        "status": (
                            "healthy" if gateway_ready else "degraded"
                        ),
                        "detail": (
                            str(s.get("connections",0)) +
                            " active connections // " +
                            str(gateway.get("status","Unknown"))
                        ),
                    },
                    {
                        "name": "KNOTS NODE",
                        "status": (
                            "healthy" if chain_height > 0 else "degraded"
                        ),
                        "detail": (
                            "tip height " + str(chain_height)
                            if chain_height > 0
                            else "chain tip unavailable"
                        ),
                    },
                    {
                        "name": "24H HISTORY",
                        "status": (
                            "healthy" if history_persistent else "degraded"
                        ),
                        "detail": (
                            str(history_summary.get("samples",0)) +
                            " durable samples"
                            if history_persistent
                            else "current-sample fallback active"
                        ),
                    },
                ]

                self.send_json(data)

            except Exception as e:

                # /api/local-stats is the operator-only upstream used
                # by the Terminus VPS relay. Never fall back from this
                # route or a relay outage could recurse back into itself.
                if parsed.path == "/api/local-stats":
                    self.send_json(
                        {"error":str(e)},
                        500
                    )
                    return

                # Public-client mode: on a normal Umbrel install there
                # is no local RATUM Prime/Gateway. Fall back to the
                # public Terminus relay while preserving account lookup.
                try:
                    public_url = PUBLIC_STATS

                    if parsed.query:
                        public_url += "?" + parsed.query

                    req = urllib.request.Request(
                        public_url,
                        headers={
                            "User-Agent":
                                "Terminus-Umbrel-Client/0.2.10"
                        }
                    )

                    with urllib.request.urlopen(
                        req,
                        timeout=8
                    ) as r:
                        public_data = json.load(r)

                    public_data["dataSource"] = "public-relay"

                    self.send_json(public_data)

                except Exception as public_error:
                    self.send_json(
                        {
                            "error":
                                "local and public stats unavailable",
                            "local":
                                str(e),
                            "public":
                                str(public_error)
                        },
                        502
                    )

        else:

            body=HTML.encode()

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8"
            )
            self.send_header(
                "Cache-Control",
                "public, max-age=60"
            )
            self.send_header("Content-Length",str(len(body)))
            self.send_security_headers()
            self.end_headers()

            self.wfile.write(body)

if __name__ == "__main__":
    if COLLECTOR_ENABLED:
        threading.Thread(
            target=collect_history_forever,
            daemon=True,
            name="terminus-history-collector"
        ).start()

    HTTPServer(
        ("0.0.0.0",8080),
        Handler
    ).serve_forever()
